"""Week 19, activity 6: pre-token generation trigger (event version 2) of the Cognito pool semana19-usuarios.

ADR 0009: Cognito groups become scopes here, so the HTTP API's JWT authorizer enforces them (403 without the scope).
The scopes are the resource server's (`legacybridge/consultas`, `legacybridge/aprobaciones`).

Data scopes (resource server `legado`) are added the same way. Their names are not in the week 17 form (`legado:leer`):
the handler maps them back (agente/handler.py, SCOPES_DE_TOKEN). GAP: Cognito's allowed characters for scope names
are not verified; `compras_proponer` is chosen to avoid `:`. Check it before the deploy.
"""
from __future__ import annotations

# Data scopes come from the resource server `legado` (week 17 vocabulary: legado:leer, ... ; see agente/handler.py).
# Separation of duties (Manuel's decision, activity 6): `compradores` propose orders and cannot approve; each approval
# group decides up to its level of the policy (semana-08/corpus/ordenes_de_compra.md) and cannot propose.
_LECTURA = ["legacybridge/consultas", "legado/leer", "legado/proveedores", "legado/ventas"]
_APROBAR = [*_LECTURA, "legacybridge/aprobaciones"]
GRUPOS_A_SCOPES = {
    "analistas": _LECTURA,
    "compradores": [*_LECTURA, "legado/compras_proponer"],
    "aprobadores-comprador": _APROBAR,
    "aprobadores-gerente": _APROBAR,
    "aprobadores-director": _APROBAR,
}
# Approval level of each approval group: the values of po_level_rank in the database (comprador 1, gerente 2, director 3).
GRUPOS_A_NIVEL = {"aprobadores-comprador": "comprador", "aprobadores-gerente": "gerente", "aprobadores-director": "director"}
RANGO = {"comprador": 1, "gerente": 2, "director": 3}
CLAIM_NIVEL = "nivel_aprobacion"   # read by computo/aprobacion.py from the authorizer's claims, never from the request


TENANT = "legacybridge-lab"


def scopes_de_grupos(grupos: list[str]) -> list[str]:
    """Unknown groups add nothing (fail closed). Sorted and unique, as the scope claim expects."""
    return sorted({s for g in grupos for s in GRUPOS_A_SCOPES.get(g, [])})


def nivel_de_grupos(grupos: list[str]) -> str | None:
    """The highest approval level among the groups, or None (no approval group: the claim is not added)."""
    niveles = [GRUPOS_A_NIVEL[g] for g in grupos if g in GRUPOS_A_NIVEL]
    return max(niveles, key=RANGO.__getitem__) if niveles else None


def handler(event, context):
    if event.get("version") != "2":
        raise ValueError("el trigger espera el evento de versión 2")
    grupos = event.get("request", {}).get("groupConfiguration", {}).get("groupsToOverride", [])
    scopes = scopes_de_grupos(grupos)
    # The agent needs a tenant claim (agente/handler.py refuses tokens without one). The lab has one tenant.
    claims = {"tenant": TENANT}
    nivel = nivel_de_grupos(grupos)
    if nivel is not None:
        claims[CLAIM_NIVEL] = nivel
    event.setdefault("response", {})
    event["response"]["claimsAndScopeOverrideDetails"] = {
        "accessTokenGeneration": {"scopesToAdd": scopes, "claimsToAddOrOverride": claims},
    }
    return event
