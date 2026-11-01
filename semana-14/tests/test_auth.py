"""Actividad 5: el servidor MCP como resource server OAuth con permisos mínimos. Sin API ($0).

Los tokens se firman aquí con llaves RSA de prueba y un JWKS local (file://): así cada caso negativo es exacto y no
depende de Keycloak. La prueba de punta a punta con Keycloak real corre si está levantado (auth/arrancar.sh).
Las pruebas de base de datos corren con PG_ADMIN_DSN (crean los roles por perfil de auth/roles_bd.sql)."""
import asyncio
import base64
import json
import os
import time

import jwt
import pytest
from conftest import HAY_BASE, ServidorHTTP
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from servidor import oauth
from servidor.http import Trazas
from servidor.oauth import ContextoOAuth, PoolConexiones, VerificadorJWT, fabrica_oauth, scopes_requeridos
from servidor.primitivas import crear_servidor
from test_transporte import crudo, peticion

EMISOR = "http://127.0.0.1:8180/realms/legacybridge"
PERFILES = {"analista": ["legado:leer", "legado:ventas", "legado:proveedores", "legado:compras:proponer"],
            "almacenista": ["legado:leer"],
            "vendedor": ["legado:leer", "legado:ventas"]}


# ---------- llaves, JWKS y tokens de prueba ----------

def _llave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


LLAVE, OTRA_LLAVE = _llave(), _llave()


@pytest.fixture(scope="module")
def jwks():
    """JWKS del emisor de prueba servido por HTTP en loopback (PyJWT solo acepta http/https para el JWKS)."""
    import http.server
    import threading
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(LLAVE.public_key()))
    datos = json.dumps({"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]}).encode()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/realms/legacybridge/protocol/openid-connect/certs"
    srv.shutdown()


def token(recurso, sub="analista", scopes=None, llave=LLAVE, kid="k1", alg="RS256", **cambios):
    ahora = int(time.time())
    claims = {"iss": EMISOR, "aud": recurso, "sub": f"sub-{sub}", "azp": "legacybridge-agente", "typ": "Bearer",
              "scope": " ".join(PERFILES.get(sub, []) if scopes is None else scopes), "iat": ahora, "exp": ahora + 300}
    claims.update(cambios)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, llave, algorithm=alg, headers={"kid": kid})


def srv_oauth(jwks, conexion=None, **kw):
    pool = PoolConexiones(os.environ["NLQ_LEGADO_DSN"], 4) if conexion is not None else None
    return ServidorHTTP(crear_servidor(fabrica_oauth(pool)), emisor=EMISOR,
                        verificador=lambda recurso: VerificadorJWT(EMISOR, recurso, jwks), **kw)


def con_token(s, tok, cuerpo, **kw):
    return crudo(s, cuerpo=cuerpo, headers={"Authorization": f"Bearer {tok}", **kw.pop("headers", {})}, **kw)


def cliente(url, tok, fn):
    import httpx2

    async def _c():
        async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {tok}"}) as http:
            async with Client(streamable_http_client(url, http_client=http)) as c:
                return await fn(c)
    return asyncio.run(_c())


def desafio(h):
    return h.get("www-authenticate", "")


LISTA = peticion("tools/list")


# ---------- Protected Resource Metadata y 401 ----------


def _trazas(s, n=1, espera_s=2.0):
    """La traza se escribe después de enviar la respuesta (incluye estado y bytes): se espera a que exista."""
    fin = time.monotonic() + espera_s
    while len(s.trazas.ultimas) < n and time.monotonic() < fin:
        time.sleep(0.01)
    return list(s.trazas.ultimas)

def test_metadatos_rfc9728(jwks):
    with srv_oauth(jwks) as s:
        estado, _, cuerpo = crudo(s, metodo="GET", cuerpo=None, encabezados_mcp=False, ruta="/.well-known/oauth-protected-resource/mcp")
    m = json.loads(cuerpo)
    assert estado == 200
    assert m["resource"] == s.recurso and m["authorization_servers"] == [EMISOR]
    assert m["scopes_supported"] == ["legado:leer"] and m["bearer_methods_supported"] == ["header"]


def test_token_ausente_401(jwks):
    with srv_oauth(jwks) as s:
        estado, h, cuerpo = crudo(s, cuerpo=LISTA)
        traza = _trazas(s)[-1]
    assert estado == 401
    w = desafio(h)
    assert w.startswith("Bearer ") and 'scope="legado:leer"' in w
    assert f'resource_metadata="http://127.0.0.1:{s.puerto}/.well-known/oauth-protected-resource/mcp"' in w
    assert json.loads(cuerpo)["error"] == "invalid_token"
    assert traza["resultado"] == "rechazado" and traza["sujeto"] is None


def _rechazado_401(jwks, hacer_token):
    with srv_oauth(jwks) as s:
        estado, h, _ = con_token(s, hacer_token(s.recurso), LISTA)
    assert estado == 401, estado
    assert 'error="invalid_token"' in desafio(h) and "resource_metadata=" in desafio(h)


def test_token_expirado_401(jwks):
    _rechazado_401(jwks, lambda r: token(r, iat=int(time.time()) - 900, exp=int(time.time()) - 60))


def test_otro_emisor_401(jwks):
    _rechazado_401(jwks, lambda r: token(r, iss="http://127.0.0.1:8180/realms/otro"))


def test_token_otra_audiencia_401(jwks):
    _rechazado_401(jwks, lambda r: token(r, aud="http://127.0.0.1:9999/mcp"))
    _rechazado_401(jwks, lambda r: token(r, aud="legado-mcp"))      # lo que emitía Keycloak sin resource y lo que emite al refrescar un token offline sin el mapper de URI


def test_firma_alterada_401(jwks):
    def alterado(r):
        cab, cuerpo, firma = token(r, sub="almacenista").split(".")
        c = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
        c["scope"] = "legado:leer legado:ventas legado:proveedores legado:compras:proponer"   # escalar scopes
        nuevo = base64.urlsafe_b64encode(json.dumps(c).encode()).rstrip(b"=").decode()
        return f"{cab}.{nuevo}.{firma}"
    _rechazado_401(jwks, alterado)


def test_alg_none_401(jwks):
    def none(r):
        cab = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT", "kid": "k1"}).encode()).rstrip(b"=").decode()
        cuerpo = token(r).split(".")[1]
        return f"{cab}.{cuerpo}."
    _rechazado_401(jwks, none)

    def hs256_con_llave_publica(r):   # confusión HS/RS: la llave pública como secreto HMAC
        pub = LLAVE.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        import hashlib
        import hmac
        cab = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode()).rstrip(b"=")
        cuerpo = token(r).split(".")[1].encode()
        firma = base64.urlsafe_b64encode(hmac.new(pub, cab + b"." + cuerpo, hashlib.sha256).digest()).rstrip(b"=")
        return (cab + b"." + cuerpo + b"." + firma).decode()
    _rechazado_401(jwks, hs256_con_llave_publica)


@pytest.mark.parametrize("caso", ["sin_aud", "aud_ajena_en_lista", "kid_desconocido", "otra_llave_mismo_kid",
                                  "id_token", "sin_sub", "basura", "sin_exp"])
def test_tokens_invalidos_401(jwks, caso):
    hacer = {
        "sin_aud": lambda r: token(r, aud=None),
        "aud_ajena_en_lista": lambda r: token(r, aud=["http://127.0.0.1:9999/mcp", "legado-mcp"]),
        "kid_desconocido": lambda r: token(r, llave=OTRA_LLAVE, kid="k2"),
        "otra_llave_mismo_kid": lambda r: token(r, llave=OTRA_LLAVE),
        "id_token": lambda r: token(r, typ="ID"),
        "sin_sub": lambda r: token(r, sub=None) if False else jwt.encode(
            {k: v for k, v in jwt.decode(token(r), options={"verify_signature": False}).items() if k != "sub"},
            LLAVE, algorithm="RS256", headers={"kid": "k1"}),
        "basura": lambda r: "esto.no.es-un-jwt",
        "sin_exp": lambda r: token(r, exp=None),
    }[caso]
    _rechazado_401(jwks, hacer)


def test_esquema_no_bearer_y_token_en_query_401(jwks):
    with srv_oauth(jwks) as s:
        tok = token(s.recurso)
        basic = crudo(s, cuerpo=LISTA, headers={"Authorization": "Basic YWRtaW46YWRtaW4="})
        query = crudo(s, cuerpo=LISTA, ruta=f"/mcp?access_token={tok}")
        valido = con_token(s, tok, LISTA)
    assert basic[0] == 401 and 'error="invalid_request"' in desafio(basic[1])
    assert query[0] == 401
    assert valido[0] == 200


def test_jwks_con_cache(jwks):
    v = VerificadorJWT(EMISOR, "http://127.0.0.1:8014/mcp", jwks)
    llamadas = []
    original = v.jwks.fetch_data
    v.jwks.fetch_data = lambda: llamadas.append(1) or original()
    for i in range(25):
        assert v.verificar(token("http://127.0.0.1:8014/mcp", sub="vendedor")).subject == "sub-vendedor"
    assert len(llamadas) == 1
    # kid desconocido: se rechaza; dentro de la ventana de enfriamiento (30 s) no fuerza otra descarga del JWKS, así un
    # atacante no puede usar tokens con kid inventados para inundar al emisor
    for _ in range(10):
        with pytest.raises(oauth.ErrorToken):
            v.verificar(token("http://127.0.0.1:8014/mcp", llave=OTRA_LLAVE, kid="k9"))
    assert len(llamadas) == 1


# ---------- scopes: 403, listas filtradas y herramientas no listadas ----------

def test_scope_insuficiente_403_con_scope(jwks):
    with srv_oauth(jwks) as s:
        solo_ventas = con_token(s, token(s.recurso, scopes=["legado:ventas"]), LISTA)
        sin_scopes = con_token(s, token(s.recurso, scopes=[]), LISTA)
    for estado, h, cuerpo in (solo_ventas, sin_scopes):
        assert estado == 403
        w = desafio(h)
        assert 'error="insufficient_scope"' in w and 'scope="legado:leer"' in w and "resource_metadata=" in w
        assert json.loads(cuerpo)["scope"] == "legado:leer"


def test_proponer_requiere_scope(jwks):
    llamada = peticion("tools/call", name="proponer_orden_compra",
                       arguments={"sku": "SKU-0009", "cantidad": 10, "motivo": "prueba"})
    with srv_oauth(jwks) as s:
        almacenista = con_token(s, token(s.recurso, sub="almacenista"), llamada)
        vendedor = con_token(s, token(s.recurso, sub="vendedor"), llamada)
        analista = con_token(s, token(s.recurso, sub="analista"), llamada)
    for estado, h, _ in (almacenista, vendedor):
        assert estado == 403 and 'scope="legado:compras:proponer legado:leer"' in desafio(h)
    r = json.loads(analista[2])["result"]
    assert analista[0] == 200 and r["structuredContent"]["propuesta"]["estado"] == "PENDING_APPROVAL"


def test_herramienta_no_listada(jwks):
    """Una herramienta que no aparece en tools/list no se ejecuta: 403 con los scopes que pide (step-up)."""
    with srv_oauth(jwks) as s:
        tok = token(s.recurso, sub="almacenista")
        lista = json.loads(con_token(s, tok, LISTA)[2])["result"]["tools"]
        assert "proponer_orden_compra" not in [t["name"] for t in lista]
        r = con_token(s, tok, peticion("tools/call", name="proponer_orden_compra",
                                       arguments={"sku": "SKU-0001", "cantidad": 1, "motivo": "x"}))
        desconocida = con_token(s, tok, peticion("tools/call", name="borrar_todo", arguments={}))
    assert r[0] == 403
    d = json.loads(desconocida[2])["result"]
    assert desconocida[0] == 200 and d["isError"] and d["structuredContent"]["error"]["tipo"] == "herramienta_desconocida"


def test_defensa_en_profundidad_sin_frontera():
    """Aunque se saltara la frontera, el handler no ejecuta una herramienta fuera del scope del contexto."""
    from mcp.server.auth.provider import AccessToken
    from conftest import con_cliente
    from herramientas import Herramientas
    ctx = ContextoOAuth.de_token(AccessToken(token="", client_id="c", scopes=["legado:leer"], subject="s"))
    h = Herramientas(ctx)
    r = con_cliente(crear_servidor(lambda: h), lambda c: c.call_tool("proponer_orden_compra",
                                                                       {"sku": "SKU-0001", "cantidad": 1, "motivo": "x"}))
    assert r.is_error and r.structured_content["error"]["tipo"] == "permiso_denegado" and not h.ctx.propuestas


ESPERADO = {
    "analista": (6, ["prvmst", "artmst", "almmst", "exidet", "vtadia", "ocpcab", "artnot"], True,
                 ["analizar_exceso_inventario", "proponer_reabasto"]),
    "almacenista": (5, ["artmst", "almmst", "exidet", "artnot"], False, ["analizar_exceso_inventario"]),
    "vendedor": (5, ["artmst", "almmst", "exidet", "vtadia", "artnot"], False, ["analizar_exceso_inventario"]),
}


@pytest.mark.parametrize("usuario", list(PERFILES))
def test_tools_list_filtrado_por_scope(jwks, usuario):
    """Cliente HTTP del SDK con el token: herramientas, resources y prompts según los scopes, no según el usuario."""
    with srv_oauth(jwks) as s:
        async def fn(c):
            artmst = await c.read_resource("legado://esquema/artmst")
            return (await c.list_tools(), await c.list_resources(), await c.list_prompts(), json.loads(artmst.contents[0].text))
        tools, recursos, prompts, artmst = cliente(s.url, token(s.recurso, sub=usuario), fn)
    n, vistas, ve_proveedor, nombres_prompts = ESPERADO[usuario]
    assert len(tools.tools) == n
    assert [r.uri.rsplit("/", 1)[1] for r in recursos.resources if "/esquema/" in r.uri] == vistas
    columnas = [c["columna"] for c in artmst["columnas"]]
    assert ("art_prv" in columnas) is ve_proveedor and ("art_cst" in columnas) is ve_proveedor
    assert [p.name for p in prompts.prompts] == nombres_prompts


def test_resources_y_prompts_fuera_de_scope_403(jwks):
    with srv_oauth(jwks) as s:
        tok = token(s.recurso, sub="vendedor")
        prv = con_token(s, tok, peticion("resources/read", uri="legado://esquema/prvmst"))
        prompt = con_token(s, tok, peticion("prompts/get", name="proponer_reabasto", arguments={"sku": "SKU-0009"}))
        propio = con_token(s, tok, peticion("resources/read", uri="legado://esquema/vtadia"))
    assert prv[0] == 403 and 'scope="legado:leer legado:proveedores"' in desafio(prv[1])
    assert prompt[0] == 403 and "legado:compras:proponer" in desafio(prompt[1])
    assert propio[0] == 200


def test_scopes_requeridos_por_operacion():
    assert scopes_requeridos("tools/list", None) == {"legado:leer"}
    assert scopes_requeridos("tools/call", "ejecutar_sql") == {"legado:leer"}
    assert scopes_requeridos("tools/call", "proponer_orden_compra") == {"legado:leer", "legado:compras:proponer"}
    assert scopes_requeridos("resources/read", "legado://esquema/ocpcab") == {"legado:leer", "legado:proveedores"}
    assert scopes_requeridos("resources/read", "legado://reglas/R-COB") == {"legado:leer"}
    assert scopes_requeridos("prompts/get", "proponer_reabasto") == set(PERFILES["analista"])


# ---------- escalada de permisos por argumentos ----------

CASOS_ESCALADA = [
    ("describir_esquema", {"usuario": "analista"}, "argumentos_invalidos"),
    ("describir_esquema", {"roles": ["compras"]}, "argumentos_invalidos"),
    ("ejecutar_sql", {"sql": "SELECT 1", "scope": "legado:proveedores"}, "argumentos_invalidos"),
    ("describir_esquema", {"tablas": ["prvmst"]}, "tabla_no_disponible"),
    ("muestrear_valores", {"tabla": "artmst", "columna": "art_prv"}, "permiso_denegado"),
    ("validar_sql", {"sql": "SELECT art_prv FROM artmst"}, "permiso_denegado"),
    ("validar_sql", {"sql": 'SELECT "ART_PRV" FROM artmst'}, "permiso_denegado"),
    ("validar_sql", {"sql": "SELECT a.* FROM artmst a"}, "permiso_denegado"),
    ("validar_sql", {"sql": "SELECT p.prv_nm FROM artmst a JOIN prvmst p ON p.prv_id = a.art_prv"}, "permiso_denegado"),
    ("validar_sql", {"sql": "SELECT * FROM legado.prvmst"}, "permiso_denegado"),
    ("validar_sql", {"sql": "SET ROLE legado_perfil_lvp"}, "escritura_bloqueada"),
    ("validar_sql", {"sql": "SELECT set_config('role', 'legado_perfil_lvp', true)"}, "funcion_prohibida"),
]


@pytest.mark.parametrize("nombre,args,tipo", CASOS_ESCALADA)
def test_escalada_por_argumentos(jwks, nombre, args, tipo):
    with srv_oauth(jwks) as s:
        r = con_token(s, token(s.recurso, sub="vendedor"), peticion("tools/call", name=nombre, arguments=args))
    res = json.loads(r[2])["result"]
    assert r[0] == 200 and res["isError"] and res["structuredContent"]["error"]["tipo"] == tipo, res["structuredContent"]


# ---------- el token no sale del servidor ----------

def test_token_no_se_reenvia_ni_se_registra(jwks, tmp_path, monkeypatch):
    from herramientas import Herramientas
    vistos = []
    original = Herramientas.llamar

    def espia(self, nombre, argumentos):
        vistos.append(repr(vars(self.ctx)) + repr(argumentos))
        return original(self, nombre, argumentos)
    monkeypatch.setattr(Herramientas, "llamar", espia)
    ruta = tmp_path / "trazas.jsonl"
    with srv_oauth(jwks, trazas=Trazas(ruta)) as s:
        tok = token(s.recurso, sub="analista")
        con_token(s, tok, LISTA)
        con_token(s, tok, peticion("tools/call", name="buscar_regla_negocio", arguments={"consulta": "R-COB"}))
        con_token(s, token(s.recurso, aud="http://otra/mcp"), LISTA)
    texto = ruta.read_text(encoding="utf-8")
    firma = tok.split(".")[2]
    assert vistos and all(firma not in v and tok not in v for v in vistos)          # ni al contexto ni a la base
    assert firma not in texto and "Bearer" not in texto                             # ni a las trazas
    lineas = [json.loads(x) for x in texto.splitlines()]
    assert lineas[0]["sujeto"] == "sub-analista" and lineas[0]["cliente_oauth"] == "legacybridge-agente"
    assert lineas[0]["scopes"] == sorted(PERFILES["analista"])
    assert lineas[-1]["estado"] == 401 and lineas[-1]["sujeto"] is None


# ---------- base de datos: un rol por perfil (A05) ----------

@pytest.fixture(scope="module")
def roles_bd(conexion):
    if not os.environ.get("PG_ADMIN_DSN"):
        pytest.skip("los roles por perfil se crean con PG_ADMIN_DSN")
    oauth.aplicar_roles_bd(os.environ["PG_ADMIN_DSN"])
    return conexion


def test_rol_de_bd_segun_scope(roles_bd):
    pool = PoolConexiones(os.environ["NLQ_LEGADO_DSN"], 2)
    try:
        for scopes, rol in ((["legado:leer"], "legado_perfil_l"), (["legado:leer", "legado:ventas"], "legado_perfil_lv"),
                            (PERFILES["analista"], "legado_perfil_lvp"), (["legado:ventas"], None)):
            assert oauth.rol_bd(scopes) == rol
            if rol is None:
                continue
            c = oauth.ConexionConRol(pool, rol)
            with c.transaction():
                assert c.execute("SELECT current_user").fetchone()[0] == rol
                assert c.execute("SELECT current_setting('default_transaction_read_only')").fetchone()[0] == "on"
        # el rol de conexión no conserva el perfil entre transacciones (SET LOCAL)
        conn = pool.tomar()
        assert conn.execute("SELECT current_user").fetchone()[0] == "copilot_nlq"
        pool.devolver(conn)
    finally:
        pool.cerrar()


def test_fk_art_prv_sin_scope_proveedores(roles_bd, jwks):
    """Cierra el hallazgo art_prv de la semana 13: aunque el SQL esquive el guard, la base niega la columna."""
    import psycopg
    pool = PoolConexiones(os.environ["NLQ_LEGADO_DSN"], 2)
    try:
        for rol, permitido in (("legado_perfil_l", False), ("legado_perfil_lv", False), ("legado_perfil_lvp", True)):
            c = oauth.ConexionConRol(pool, rol)
            for sql in ("SELECT art_prv FROM artmst LIMIT 1", "SELECT art_cst FROM artmst LIMIT 1",
                        "SELECT row_to_json(a) FROM artmst a LIMIT 1", "SELECT prv_nm FROM prvmst LIMIT 1"):
                try:
                    with c.transaction():
                        c.execute(sql).fetchall()
                    ok = True
                except psycopg.errors.InsufficientPrivilege:
                    ok = False
                assert ok is permitido, (rol, sql)
    finally:
        pool.cerrar()
    # por el servidor completo: row_to_json pasa el guard (no nombra columnas) y lo detiene la base
    with srv_oauth(jwks, conexion=roles_bd) as s:
        for usuario, esperado in (("vendedor", "permiso_denegado"), ("almacenista", "permiso_denegado"), ("analista", None)):
            r = json.loads(con_token(s, token(s.recurso, sub=usuario), peticion(
                "tools/call", name="ejecutar_sql", arguments={"sql": "SELECT row_to_json(a) FROM artmst a LIMIT 1"}))[2])["result"]
            tipo = (r["structuredContent"].get("error") or {}).get("tipo")
            assert tipo == esperado, (usuario, r["structuredContent"])
            if esperado:
                assert "La base negó el acceso" in r["structuredContent"]["error"]["mensaje"]


def test_consultas_permitidas_con_base(roles_bd, jwks):
    with srv_oauth(jwks, conexion=roles_bd) as s:
        def sql(usuario, q):
            return json.loads(con_token(s, token(s.recurso, sub=usuario), peticion(
                "tools/call", name="ejecutar_sql", arguments={"sql": q}))[2])["result"]["structuredContent"]
        assert sql("almacenista", "SELECT COUNT(*) FROM exidet")["ok"]
        assert sql("vendedor", "SELECT SUM(vta_und) FROM vtadia")["ok"]
        assert sql("almacenista", "SELECT SUM(vta_und) FROM vtadia")["error"]["tipo"] == "permiso_denegado"
        assert sql("analista", "SELECT p.prv_nm, COUNT(*) FROM artmst a JOIN prvmst p ON p.prv_id = a.art_prv GROUP BY 1")["ok"]


# ---------- de punta a punta con Keycloak real ----------

def _keycloak():
    try:
        from auth import pkce
        return pkce if pkce.SECRETOS.exists() and pkce.descubrimiento() else None
    except Exception:  # noqa: BLE001
        return None


@pytest.mark.skipif(_keycloak() is None, reason="Keycloak no está corriendo (auth/arrancar.sh)")
def test_keycloak_de_punta_a_punta():
    pkce = _keycloak()
    meta = pkce.descubrimiento()
    with ServidorHTTP(crear_servidor(fabrica_oauth(None)), emisor=meta["issuer"], recurso=pkce.RECURSO,
                      verificador=VerificadorJWT(meta["issuer"], pkce.RECURSO, meta["jwks_uri"])) as s:
        for usuario, (n, *_ ) in ESPERADO.items():
            tok = pkce.obtener_token(usuario)["access_token"]
            tools = cliente(s.url, tok, lambda c: c.list_tools())
            assert len(tools.tools) == n, usuario
        # Desde la actividad 7 el mapper del cliente agente emite la URI canónica aunque falte `resource` (Keycloak 26.8
        # pierde la audiencia al refrescar tokens offline; resultados/claude_code.md). El servidor no cambió: sigue
        # rechazando cualquier otra audiencia (test_token_otra_audiencia_401, incluido aud="legado-mcp").
        sin_resource = pkce.obtener_token("analista", resource=None)["access_token"]
        assert con_token(s, sin_resource, LISTA)[0] == 200
        tok = pkce.obtener_token("almacenista")["access_token"]
        r = con_token(s, tok, peticion("tools/call", name="proponer_orden_compra",
                                       arguments={"sku": "SKU-0001", "cantidad": 1, "motivo": "x"}))
        assert r[0] == 403
