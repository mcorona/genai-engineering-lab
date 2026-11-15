"""Activity 4: the authorization server (a local Keycloak, the legacybridge realm) issues exactly the tokens the
MCP server is going to require. Requires Keycloak running (auth/arrancar.sh) and auth/.secretos.env; otherwise it is skipped.
No API ($0)."""
import json
import time
import urllib.parse
import urllib.request

import pytest

from auth import pkce
from auth.pkce import CLIENTE, EMISOR, RECURSO, SCOPES_TODOS, ErrorOAuth, autorizar, canjear, claims, obtener_token


def _disponible():
    try:
        pkce.descubrimiento()
        return pkce.SECRETOS.exists()
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _disponible(), reason="Keycloak no está corriendo (semana-14/auth/arrancar.sh)")

PERFILES = {  # the scopes each profile can receive (the plan's decisions, amenazas.md)
    "analista": {"legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer"},
    "almacenista": {"legado:leer"},
    "vendedor": {"legado:leer", "legado:ventas"},
}


@pytest.fixture(scope="module")
def meta():
    return pkce.descubrimiento()


def test_descubrimiento(meta):
    assert meta["issuer"] == EMISOR == "http://127.0.0.1:8180/realms/legacybridge"
    assert "S256" in meta["code_challenge_methods_supported"]
    assert meta["authorization_response_iss_parameter_supported"] is True          # RFC 9207
    assert "authorization_code" in meta["grant_types_supported"]
    assert set(SCOPES_TODOS) <= set(meta["scopes_supported"])
    assert meta["jwks_uri"].startswith(EMISOR)


@pytest.mark.parametrize("usuario", list(PERFILES))
def test_token_por_perfil(usuario):
    """Asks for the 4 scopes: each profile receives only its own; aud = the MCP server's canonical URI (RFC 8707)."""
    tok = obtener_token(usuario, scopes=SCOPES_TODOS)
    c = claims(tok["access_token"])
    assert set(c["scope"].split()) & set(SCOPES_TODOS) == PERFILES[usuario]
    assert set(tok["scope"].split()) & set(SCOPES_TODOS) == PERFILES[usuario]
    assert c["aud"] in (RECURSO, [RECURSO])
    assert c["iss"] == EMISOR and c["azp"] == CLIENTE and c["sub"]
    assert c["exp"] - c["iat"] == 300 and tok["expires_in"] == 300
    assert tok["token_type"].lower() == "bearer"


def test_scope_minimo():
    c = claims(obtener_token("analista", scopes=["legado:leer"])["access_token"])
    assert set(c["scope"].split()) & set(SCOPES_TODOS) == {"legado:leer"}


def test_firma_rs256_verificable_con_jwks(meta):
    """What the MCP server will do (activity 5): the signature via JWKS, a fixed alg, exact iss and aud, exp."""
    import jwt
    tok = obtener_token("vendedor", scopes=["legado:leer"])["access_token"]
    assert jwt.get_unverified_header(tok)["alg"] == "RS256"
    clave = jwt.PyJWKClient(meta["jwks_uri"]).get_signing_key_from_jwt(tok).key
    c = jwt.decode(tok, clave, algorithms=["RS256"], audience=RECURSO, issuer=EMISOR,
                   options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    assert c["azp"] == CLIENTE
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(tok, clave, algorithms=["RS256"], audience="http://127.0.0.1:9999/mcp", issuer=EMISOR)


def test_sin_resource_la_audiencia_sigue_siendo_la_uri_canonica():
    """The agent client's audience mapper issues the MCP server's canonical URI (not the client id `legado-mcp`).
    Reason: Keycloak 26.8 loses the `resource` audience when refreshing offline tokens, and Claude Code always asks for
    `offline_access`. With a single resource server in the realm, the audience stays fixed to it; a different `resource`
    is still `invalid_target` (the following tests)."""
    c = claims(obtener_token("analista", scopes=["legado:leer"], resource=None)["access_token"])
    assert c["aud"] in (RECURSO, [RECURSO])


def test_resource_desconocido_invalid_target():
    with pytest.raises(ErrorOAuth) as e:
        obtener_token("analista", scopes=["legado:leer"], resource="http://127.0.0.1:9999/mcp")
    assert e.value.error == "invalid_target"


def test_resource_distinto_en_el_canje_invalid_target():
    aut = autorizar("analista", pkce.password("analista"), ["legado:leer"])
    with pytest.raises(ErrorOAuth) as e:
        canjear(aut, resource="http://127.0.0.1:9999/mcp")
    assert e.value.error == "invalid_target"


def test_pkce_obligatorio_y_s256():
    for metodo in (None, "plain"):
        with pytest.raises(ErrorOAuth) as e:
            obtener_token("analista", scopes=["legado:leer"], metodo=metodo)
        assert e.value.error in ("invalid_request", "pagina_de_error"), metodo


def test_verifier_incorrecto_invalid_grant():
    aut = autorizar("analista", pkce.password("analista"), ["legado:leer"])
    with pytest.raises(ErrorOAuth) as e:
        canjear(aut, verifier=pkce.pkce_par()[0])
    assert e.value.error == "invalid_grant"


def test_codigo_de_un_solo_uso():
    aut = autorizar("analista", pkce.password("analista"), ["legado:leer"])
    canjear(aut)
    with pytest.raises(ErrorOAuth) as e:
        canjear(aut)
    assert e.value.error == "invalid_grant"


def test_redirect_solo_loopback_registrado():
    for redirect in ("https://evil.example/callback", "http://127.0.0.1:53682/otra", "http://192.168.1.10:53682/callback"):
        with pytest.raises(ErrorOAuth) as e:
            autorizar("analista", pkce.password("analista"), ["legado:leer"], redirect=redirect)
        assert e.value.error == "pagina_de_error", redirect
    # loopback with any port (RFC 8252 §7.3)
    assert autorizar("analista", pkce.password("analista"), ["legado:leer"],
                     redirect="http://127.0.0.1:61234/callback")["code"]


def test_iss_en_la_respuesta_de_autorizacion(meta):
    aut = autorizar("almacenista", pkce.password("almacenista"), ["legado:leer"])
    assert aut["iss"] == meta["issuer"]


def test_password_grant_y_credenciales_deshabilitados(meta):
    for datos in ({"grant_type": "password", "client_id": CLIENTE, "username": "analista",
                   "password": pkce.password("analista"), "scope": "legado:leer"},
                  {"grant_type": "client_credentials", "client_id": CLIENTE}):
        with pytest.raises(ErrorOAuth) as e:
            pkce._token(meta["token_endpoint"], datos)
        assert e.value.error in ("unauthorized_client", "invalid_client"), datos["grant_type"]


def test_contrasena_incorrecta():
    with pytest.raises(ErrorOAuth) as e:
        autorizar("analista", "incorrecta", ["legado:leer"])
    assert e.value.error == "login_fallido"


def test_el_servidor_mcp_no_inicia_flujos(meta):
    """legado-mcp is only an audience (bearer-only): it cannot request tokens or authorize users."""
    with pytest.raises(ErrorOAuth):
        pkce._token(meta["token_endpoint"], {"grant_type": "client_credentials", "client_id": "legado-mcp"})
    with pytest.raises(ErrorOAuth):
        autorizar("analista", pkce.password("analista"), ["legado:leer"], cliente="legado-mcp")


def test_refresh_conserva_audiencia_y_scopes():
    tok = obtener_token("vendedor", scopes=["legado:leer", "legado:ventas"])
    nuevo = pkce.refrescar(tok)
    c = claims(nuevo["access_token"])
    assert c["aud"] in (RECURSO, [RECURSO]) and set(c["scope"].split()) & set(SCOPES_TODOS) == PERFILES["vendedor"]
    with pytest.raises(ErrorOAuth) as e:
        pkce.refrescar(tok)                      # revokeRefreshToken: the previous refresh token no longer works
    assert e.value.error == "invalid_grant"




def test_offline_access_para_clientes_mcp():
    """Claude Code asks for `scope=<from the challenge> offline_access`: the realm accepts it, the refresh token is offline (bounded
    by offlineSessionIdleTimeout / offlineSessionMaxLifespan) and the audience survives the refresh. Without the canonical
    URI mapper, Keycloak 26.8 returned `aud=legado-mcp` after refreshing an offline token and the server answered 401."""
    tok = obtener_token("almacenista", scopes=["legado:leer", "offline_access"])
    c = claims(tok["access_token"])
    assert c["aud"] in (RECURSO, [RECURSO])
    assert set(c["scope"].split()) & set(SCOPES_TODOS) == {"legado:leer"}
    assert claims(tok["refresh_token"])["typ"] == "Offline"
    nuevo = pkce.refrescar(tok)
    assert claims(nuevo["access_token"])["aud"] in (RECURSO, [RECURSO])
    assert claims(pkce.refrescar(nuevo, resource=None)["access_token"])["aud"] in (RECURSO, [RECURSO])


A2A = "http://127.0.0.1:8015/"   # week 15, activity 7: the remote purchasing specialist


def test_token_a2a_con_audiencia_propia():
    """The supervisor asks for the A2A specialist's token with its own client and `resource`: the audience is only the
    specialist (not the MCP server), and only a profile with purchasing receives the scope."""
    c = claims(obtener_token("analista", scopes=["legado:compras:proponer"], resource=A2A,
                             cliente="legacybridge-supervisor")["access_token"])
    assert c["aud"] in (A2A, [A2A]) and c["azp"] == "legacybridge-supervisor"
    assert "legado:compras:proponer" in c["scope"].split()
    c = claims(obtener_token("almacenista", scopes=["legado:compras:proponer"], resource=A2A,
                             cliente="legacybridge-supervisor")["access_token"])
    assert "legado:compras:proponer" not in c["scope"].split()
