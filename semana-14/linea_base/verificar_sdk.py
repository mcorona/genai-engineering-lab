"""The week 14 baseline (activity 1): what the installed `mcp` SDK offers for the remote server with OAuth.

No network and no API: it builds an in-memory test server (Starlette TestClient) with a fake token verifier and
checks, against the 2026-07-28 specification, what activities 2 to 5 take for granted. Each check is
(name, ok, detail). Usage:

    python semana-14/linea_base/verificar_sdk.py            # prints the table; exit code 1 if anything fails
    python semana-14/linea_base/verificar_sdk.py --json     # the same output as JSON

The SDK's known gaps (what has to be built) are reported separately in BRECHAS and do not count as failures.
"""
from __future__ import annotations

import importlib.metadata as md
import json
import sys
import time

from pydantic import BaseModel

VERSION_SDK = "2.3.0"
VERSION_PROTOCOLO = "2026-07-28"
RECURSO = "http://127.0.0.1:8014/mcp"
EMISOR = "http://127.0.0.1:8180/realms/legacybridge"
SCOPE_BASE = "legado:leer"

# What the SDK does NOT solve and is built during the week (verified in activity 1).
BRECHAS = [
    ("Validación de JWT", "TokenVerifier es un protocolo: la firma por JWKS, `iss`, `aud`, `exp` y el algoritmo fijo se "
                          "implementan con PyJWT (actividad 5)."),
    ("Scopes por herramienta", "AuthSettings.required_scopes es global. El scope por herramienta y el filtrado de "
                               "`tools/list` y `resources/list` se implementan en el servidor (actividad 5)."),
    ("`scope` en el desafío", "Los `WWW-Authenticate` de 401 y 403 no traen el parámetro `scope` (SHOULD de la "
                              "especificación). Se agrega en el servidor (actividad 5)."),
    ("Defensas del cliente", "Allowlist de servidores, pinning de descripciones por hash y prefijo por servidor no "
                             "existen en el SDK cliente: se implementan en el cliente del laboratorio (actividad 6)."),
]

_META = {"io.modelcontextprotocol/protocolVersion": VERSION_PROTOCOLO,
         "io.modelcontextprotocol/clientInfo": {"name": "linea-base", "version": "0"},
         "io.modelcontextprotocol/clientCapabilities": {}}
_H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
      "MCP-Protocol-Version": VERSION_PROTOCOLO}


class Eco(BaseModel):
    """Salida tipada de la herramienta de prueba (a nivel de módulo: el SDK resuelve las anotaciones por nombre)."""
    texto: str


def _cuerpo(metodo, **params):
    return {"jsonrpc": "2.0", "id": 1, "method": metodo, "params": {**params, "_meta": _META}}


def _verificador():
    from mcp.server.auth.provider import AccessToken

    class Falso:
        """Opaque test tokens: the token's name decides its claims."""
        async def verify_token(self, token):
            base = dict(token=token, client_id="cliente-prueba", subject="analista",
                        expires_at=int(time.time()) + 60, resource=RECURSO, scopes=[SCOPE_BASE])
            casos = {"bueno": {}, "otra_audiencia": {"resource": "http://127.0.0.1:9999/mcp"},
                     "sin_recurso": {"resource": None}, "expirado": {"expires_at": int(time.time()) - 5},
                     "sin_scope": {"scopes": ["otro"]}}
            return AccessToken(**{**base, **casos[token]}) if token in casos else None
    return Falso()


def _servidor():
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.mcpserver import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp_types import ToolAnnotations

    srv = MCPServer("linea-base-semana14", token_verifier=_verificador(),
                    auth=AuthSettings(issuer_url=EMISOR, resource_server_url=RECURSO, validate_token_resource=True,
                                      required_scopes=[SCOPE_BASE]))

    # With a return type that has a schema (a Pydantic model) the SDK publishes outputSchema and returns structuredContent;
    # with an untyped `dict` it publishes none (verified in this activity).
    @srv.tool(description="Eco de prueba.", annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))
    def eco(texto: str) -> Eco:
        return Eco(texto=texto)

    @srv.resource("legado://esquema/{vista}", description="Columnas de una vista legada.", mime_type="application/json")
    def esquema(vista: str) -> str:
        return json.dumps({"vista": vista})

    @srv.prompt(description="Plantilla de prueba.")
    def analizar(sku: str) -> str:
        return f"Analiza el SKU {sku}."

    seg = TransportSecuritySettings(allowed_hosts=["127.0.0.1:8014"], allowed_origins=["http://127.0.0.1:8014"])
    return srv.streamable_http_app(transport_security=seg, json_response=True)


def comprobaciones():
    from starlette.testclient import TestClient
    import mcp_types
    import mcp_types.version as v
    from mcp.server.transport_security import TransportSecuritySettings

    res = []

    def chk(nombre, ok, detalle=""):
        res.append((nombre, bool(ok), str(detalle)))

    chk("Versión del SDK mcp", md.version("mcp") == VERSION_SDK, md.version("mcp"))
    chk("Protocolo más reciente del SDK", v.LATEST_PROTOCOL_VERSION == VERSION_PROTOCOLO, v.LATEST_PROTOCOL_VERSION)
    chk("2026-07-28 sin handshake (moderno)", VERSION_PROTOCOLO in v.MODERN_PROTOCOL_VERSIONS
        and VERSION_PROTOCOLO not in v.HANDSHAKE_PROTOCOL_VERSIONS, f"modernas={v.MODERN_PROTOCOL_VERSIONS}")
    chk("Tool con outputSchema y anotaciones", {"output_schema", "annotations"} <= set(mcp_types.Tool.model_fields)
        and {"read_only_hint", "destructive_hint"} <= set(mcp_types.ToolAnnotations.model_fields), "")
    chk("ResourceTemplate y Prompt", hasattr(mcp_types, "ResourceTemplate") and hasattr(mcp_types, "Prompt"), "")
    chk("cacheScope y ttlMs en resources/read", {"cache_scope", "ttl_ms"} <= set(mcp_types.ReadResourceResult.model_fields), "")
    chk("Protección contra DNS rebinding activa por defecto",
        TransportSecuritySettings.model_fields["enable_dns_rebinding_protection"].default is True, "")

    app = _servidor()
    with TestClient(app, base_url="http://127.0.0.1:8014") as c:
        r = c.get("/.well-known/oauth-protected-resource/mcp")
        prm = r.json() if r.status_code == 200 else {}
        chk("RFC 9728: metadatos del recurso", r.status_code == 200 and prm.get("resource") == RECURSO
            and prm.get("authorization_servers") == [EMISOR], json.dumps(prm))

        def post(cuerpo, token=None, **extra):
            h = {**_H, "Mcp-Method": cuerpo["method"], **extra}
            if "name" in cuerpo["params"]:
                h.setdefault("Mcp-Name", cuerpo["params"]["name"])
            if token:
                h["Authorization"] = f"Bearer {token}"
            return c.post("/mcp", json=cuerpo, headers=h)

        lista = _cuerpo("tools/list")
        r = post(lista)
        www = r.headers.get("www-authenticate", "")
        chk("401 sin token con resource_metadata", r.status_code == 401 and "resource_metadata=" in www, www)
        for tok in ("otra_audiencia", "sin_recurso", "expirado", "desconocido"):
            r = post(lista, tok)
            chk(f"401 con token {tok}", r.status_code == 401, r.status_code)
        r = post(lista, "sin_scope")
        chk("403 insufficient_scope", r.status_code == 403 and 'error="insufficient_scope"' in
            r.headers.get("www-authenticate", ""), r.headers.get("www-authenticate", ""))
        r = c.post(f"/mcp?access_token=bueno", json=lista, headers={**_H, "Mcp-Method": "tools/list"})
        chk("Token en query string ignorado (401)", r.status_code == 401, r.status_code)

        r = post(lista, "bueno")
        herramientas = r.json().get("result", {}).get("tools", []) if r.status_code == 200 else []
        eco = next((t for t in herramientas if t["name"] == "eco"), {})
        chk("tools/list autorizado, sin sesión", r.status_code == 200 and "mcp-session-id" not in r.headers, r.status_code)
        chk("outputSchema y readOnlyHint publicados", "outputSchema" in eco and
            eco.get("annotations", {}).get("readOnlyHint") is True, json.dumps(eco.get("annotations")))
        r = post(_cuerpo("tools/call", name="eco", arguments={"texto": "hola"}), "bueno")
        sc = r.json().get("result", {}).get("structuredContent") if r.status_code == 200 else None
        chk("tools/call con structuredContent", sc == {"texto": "hola"}, json.dumps(sc))
        r = post(_cuerpo("resources/templates/list"), "bueno")
        chk("Plantilla de resource publicada", r.status_code == 200 and "legado://esquema/{vista}" in r.text, r.status_code)
        r = post(_cuerpo("resources/read", uri="legado://esquema/artmst"), "bueno", **{"Mcp-Name": "legado://esquema/artmst"})
        chk("resources/read", r.status_code == 200 and "artmst" in r.text, r.status_code)
        r = post(_cuerpo("prompts/get", name="analizar", arguments={"sku": "SKU-0001"}), "bueno")
        chk("prompts/get", r.status_code == 200 and "SKU-0001" in r.text, r.status_code)

        r = post(lista, "bueno", Origin="http://evil.example")
        chk("Origin hostil → 403", r.status_code == 403, r.status_code)
        r = c.post("/mcp", json=lista, headers={**_H, "Mcp-Method": "tools/call", "Authorization": "Bearer bueno"})
        cod = r.json().get("error", {}).get("code") if r.headers.get("content-type", "").startswith("application/json") else None
        chk("Mcp-Method distinto del cuerpo → 400 HeaderMismatch", r.status_code == 400 and cod == -32020, f"{r.status_code} {cod}")
        r = post(_cuerpo("tools/call", name="eco", arguments={"texto": "x"}), "bueno", **{"Mcp-Name": "otra"})
        cod = r.json().get("error", {}).get("code") if r.headers.get("content-type", "").startswith("application/json") else None
        chk("Mcp-Name distinto del cuerpo → 400 HeaderMismatch", r.status_code == 400 and cod == -32020, f"{r.status_code} {cod}")
    return res


def main():
    res = comprobaciones()
    if "--json" in sys.argv:
        print(json.dumps({"comprobaciones": [dict(nombre=n, ok=o, detalle=d) for n, o, d in res],
                          "brechas": [dict(tema=t, detalle=d) for t, d in BRECHAS]}, ensure_ascii=False, indent=1))
    else:
        for n, o, d in res:
            print(f"{'OK ' if o else 'FALLA'} {n:<52} {d[:90]}")
        print(f"\n{sum(o for _, o, _ in res)}/{len(res)} checks")
    sys.exit(0 if all(o for _, o, _ in res) else 1)


if __name__ == "__main__":
    main()
