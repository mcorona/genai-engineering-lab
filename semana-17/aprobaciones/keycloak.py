"""Week 17, activity 6 (closed in activity 10): the approver roles in a REAL Keycloak, and real tokens through the approvals verifier ($0).

    semana-14/auth/arrancar.sh                                          # the week 14 realm, ephemeral (Docker; in CI too)
    cd semana-17 && uv run --group semana17 python -m aprobaciones.keycloak

1. imports `realm_aprobadores.json` into the `legacybridge` realm (admin REST `partialImport`, existing resources skipped) and gives the
   `gerente` approver a random, non-temporary password for this run (never printed);
2. gets an access token for `gerente` from the `legacybridge-aprobaciones` client with authorization code + PKCE (week 14's
   `auth/pkce.py`, no browser), and one for `analista` from the same client;
3. verifies them with `identidad.VerificadorAprobador` against the realm's JWKS: `gerente` carries `legado-aprobador-gerente` and the
   approvals audience; `analista` verifies but has no approver level; `analista`'s MCP token (week 14's audience) is refused here.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import jwt

S17 = Path(__file__).resolve().parents[1]
S14 = S17.parent / "semana-14"
for p in (str(S17), str(S14)):
    if p not in sys.path:
        sys.path.insert(0, p)

from aprobaciones import maquina as M  # noqa: E402
from aprobaciones.identidad import AUDIENCIA, ErrorToken, VerificadorAprobador  # noqa: E402
from auth import pkce  # noqa: E402

KC = pkce.KC_URL
REALM = pkce.REALM
CLIENTE = "legacybridge-aprobaciones"
REDIRECT = "http://127.0.0.1:8765/callback"


def _secretos_kc() -> dict:
    out = {}
    for linea in (S14 / "auth" / ".secretos.env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.startswith("#"):
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _admin_token(s: dict) -> str:
    datos = urllib.parse.urlencode({"grant_type": "password", "client_id": "admin-cli", "username": s["KC_BOOTSTRAP_ADMIN_USERNAME"],
                                    "password": s["KC_BOOTSTRAP_ADMIN_PASSWORD"]}).encode()
    with urllib.request.urlopen(f"{KC}/realms/master/protocol/openid-connect/token", data=datos, timeout=20) as r:
        return json.load(r)["access_token"]


def _admin(metodo: str, ruta: str, token: str, cuerpo=None):
    req = urllib.request.Request(f"{KC}/admin/realms/{REALM}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 method=metodo, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        texto = r.read().decode()
        return r.status, (json.loads(texto) if texto.strip().startswith(("{", "[")) else None)


def preparar() -> str:
    """Imports the approvers and sets a run password for `gerente`. Returns that password (kept in memory only)."""
    s = _secretos_kc()
    t = _admin_token(s)
    datos = json.loads((S17 / "aprobaciones" / "realm_aprobadores.json").read_text(encoding="utf-8"))
    datos.pop("nota", None)
    _admin("POST", "/partialImport", t, datos)
    # Keycloak 26 puts `sub` in the token through the `basic` client scope: a client imported before the file said so gets it here
    _, clientes = _admin("GET", f"/clients?clientId={CLIENTE}", t)
    _, alcances = _admin("GET", "/client-scopes", t)
    basico = next(c["id"] for c in alcances if c["name"] == "basic")
    _admin("PUT", f"/clients/{clientes[0]['id']}/default-client-scopes/{basico}", t)
    clave = secrets.token_urlsafe(18)
    _, usuarios = _admin("GET", "/users?username=gerente&exact=true", t)
    _admin("PUT", f"/users/{usuarios[0]['id']}/reset-password", t, {"type": "password", "value": clave, "temporary": False})
    _admin("PUT", f"/users/{usuarios[0]['id']}", t, {"requiredActions": [], "firstName": "Gerente", "lastName": "Compras",
                                                     "email": "gerente@legacybridge.invalid", "emailVerified": True})
    return clave


def token_de(usuario: str, clave: str) -> str:
    aut = pkce.autorizar(usuario, clave, ["openid"], resource=None, redirect=REDIRECT, cliente=CLIENTE)
    return pkce.canjear(aut, resource=None)["access_token"]


def main() -> int:
    clave_gerente = preparar()
    verificador = VerificadorAprobador(jwt.PyJWKClient(f"{pkce.EMISOR}/protocol/openid-connect/certs"), emisor=pkce.EMISOR, audiencia=AUDIENCIA)
    out = {"emisor": pkce.EMISOR, "audiencia": AUDIENCIA}
    g = verificador.verificar(token_de("gerente", clave_gerente))
    out["gerente"] = {"roles_de_aprobador": [r for r in g.roles if r.startswith("legado-aprobador-")], "nivel": M.nivel_de(g.roles),
                      "puede_aprobar_56462_mxn": M.alcanza(g.roles, M.nivel_requerido(56_462))}
    a = verificador.verificar(token_de("analista", pkce.password("analista")))
    out["analista"] = {"nivel": M.nivel_de(a.roles), "roles_de_aprobador": [r for r in a.roles if r.startswith("legado-aprobador-")]}
    try:
        verificador.verificar(pkce.obtener_token("analista", scopes=["legado:leer"])["access_token"])
        out["token_del_mcp"] = "aceptado"
    except ErrorToken as e:
        out["token_del_mcp"] = f"rechazado ({str(e).split(':')[0]})"
    out["sujetos_distintos"] = g.sub != a.sub
    out["ok"] = (out["gerente"]["nivel"] == "gerente" and out["gerente"]["puede_aprobar_56462_mxn"] and out["analista"]["nivel"] is None
                 and out["token_del_mcp"].startswith("rechazado") and out["sujetos_distintos"])
    destino = Path(os.environ.get("SALIDA_KEYCLOAK") or S17 / "resultados" / "aprobaciones_keycloak.json")
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
