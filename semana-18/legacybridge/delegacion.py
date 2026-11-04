"""LegacyBridge v1, multi-agent mode: the purchasing step delegated to a specialist that holds NO credentials.

`HerramientasDelegadas` adds one tool, `delegar_compras`, to the MCP client's catalogue. It sits BELOW the week 17 layers (the agent wraps
it like any tool source), so the call gets its `execute_tool` span, goes through the tool guardrails, and its result through the
"data is not instructions" guardrail. The specialist only drafts: it returns {"sku", "cantidad", "motivo"} or {"sin_propuesta": ...}. The
supervisor registers the proposal itself through MCP with the user's token (`proponer_orden_compra`), so the approval step of activity 6
still decides. This is the boundary week 15 named as the reason to use more than one agent: a step that must never hold credentials.

`especialista` is a callable `texto -> (respuesta, uso)`: week 15's A2A client (`ClienteA2A.enviar`, audience of its own, no token
passthrough) in v1, a deterministic double in the tests.
"""
from __future__ import annotations

import json

DELEGAR = "delegar_compras"
DEFINICION = {
    "name": DELEGAR,
    "description": ("Ask the purchasing specialist to DRAFT a purchase-order proposal from facts you already queried. It has no access to "
                    "any data or tool: give it the SKU, the stock facts and the business rule. It returns a draft (sku, quantity, reason) or "
                    "says no proposal is warranted. Registering a proposal is a separate step, with its own tool."),
    "input_schema": {"type": "object", "additionalProperties": False, "required": ["sku", "hechos", "regla"],
                     "properties": {"sku": {"type": "string", "maxLength": 32},
                                    "hechos": {"type": "string", "maxLength": 2000, "description": "stock, demand and open orders you measured"},
                                    "regla": {"type": "string", "maxLength": 2000, "description": "the business rule that applies, as you read it"}}},
}
MAX_RESPUESTA = 4000


class HerramientasDelegadas:
    def __init__(self, base, especialista):
        self._base, self.especialista = base, especialista
        self.delegaciones: list[dict] = []

    def __getattr__(self, nombre):
        return getattr(self._base, nombre)

    def definiciones(self) -> list[dict]:
        return [*self._base.definiciones(), DEFINICION]

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        if nombre != DELEGAR:
            return self._base.llamar(nombre, argumentos)
        a = argumentos or {}
        texto = (f"SKU: {a.get('sku', '')}\nFacts: {a.get('hechos', '')}\nRule: {a.get('regla', '')}\n"
                 "Return only JSON: {\"sku\", \"cantidad\", \"motivo\"} or {\"sin_propuesta\": reason}.")
        try:
            respuesta, uso = self.especialista(texto)
        except Exception as e:     # noqa: BLE001  the specialist is another service: its failure is a tool error, not a crash
            return {"ok": False, "error": {"tipo": "especialista_no_disponible", "mensaje": type(e).__name__}}
        self.delegaciones.append({"uso": uso or {}})
        try:
            borrador = json.loads(respuesta[respuesta.index("{"): respuesta.rindex("}") + 1])
        except (ValueError, TypeError):
            borrador = {"texto": str(respuesta)[:MAX_RESPUESTA]}
        # the remote agent's answer is DATA from another service: the same envelope week 14 uses for tool results
        return {"ok": True, "fuente": "a2a:compras", "untrusted_data": borrador}
