"""Week 19, activity 6: pre-token generation trigger (event version 2) of the Cognito pool semana19-usuarios.

ADR 0009: Cognito groups become scopes here, so the HTTP API's JWT authorizer enforces them (403 without the scope).
The scopes are the resource server's (`legacybridge/consultas`, `legacybridge/aprobaciones`).

Data scopes (resource server `legado`) are added the same way. Their names are not in the week 17 form (`legado:leer`):
the handler maps them back (agente/handler.py, SCOPES_DE_TOKEN). GAP: Cognito's allowed characters for scope names
are not verified; `compras_proponer` is chosen to avoid `:`. Check it before the deploy.
"""
from __future__ import annotations

# Data scopes come from the resource server `legado` (week 17 vocabulary: legado:leer, ... ; see agente/handler.py).
GRUPOS_A_SCOPES = {
    "analistas": ["legacybridge/consultas", "legado/leer", "legado/proveedores", "legado/ventas"],
    "aprobadores": ["legacybridge/consultas", "legacybridge/aprobaciones", "legado/leer", "legado/proveedores",
                    "legado/ventas", "legado/compras_proponer"],
}


TENANT = "legacybridge-lab"


def scopes_de_grupos(grupos: list[str]) -> list[str]:
    """Unknown groups add nothing (fail closed). Sorted and unique, as the scope claim expects."""
    return sorted({s for g in grupos for s in GRUPOS_A_SCOPES.get(g, [])})


def handler(event, context):
    if event.get("version") != "2":
        raise ValueError("el trigger espera el evento de versión 2")
    grupos = event.get("request", {}).get("groupConfiguration", {}).get("groupsToOverride", [])
    scopes = scopes_de_grupos(grupos)
    event.setdefault("response", {})
    event["response"]["claimsAndScopeOverrideDetails"] = {
        # The agent needs a tenant claim (agente/handler.py refuses tokens without one). The lab has one tenant.
        "accessTokenGeneration": {"scopesToAdd": scopes, "claimsToAddOrOverride": {"tenant": TENANT}},
    }
    return event
