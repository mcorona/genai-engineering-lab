"""Week 19, activity 6: pre-token generation trigger (event version 2) of the Cognito pool semana19-usuarios.

ADR 0009: Cognito groups become scopes here, so the HTTP API's JWT authorizer enforces them (403 without the scope).
The scopes are the resource server's (`legacybridge/consultas`, `legacybridge/aprobaciones`).

GAP (not solved here): the data scopes of week 17 (`legado:leer`, ...) that the deterministic layer needs are not in the
token yet. Without them the agent's data tools are refused (fail closed). They need their own resource server decision.
"""
from __future__ import annotations

GRUPOS_A_SCOPES = {
    "analistas": ["legacybridge/consultas"],
    "aprobadores": ["legacybridge/consultas", "legacybridge/aprobaciones"],
}


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
        "accessTokenGeneration": {"scopesToAdd": scopes} if scopes else {},
    }
    return event
