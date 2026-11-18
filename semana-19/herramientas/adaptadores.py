"""Week 19, activity 7: one input adapter per event format of the tools Lambda (the tools exist once, in handler.py).

  directo   {"herramienta": ..., ...}: the agent Lambda's lambda.invoke (agente/construccion.py)
  gateway   the tool's arguments as the event; the tool's name in context.client_context.custom
            ["bedrockAgentCoreToolName"] as `<target>___<tool>`
            (bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html, read 2026-11-18)
  agentes   Bedrock Agents action group, function details: messageVersion, actionGroup, function, parameters
            [{name, type, value}] with the values as text, sessionAttributes
            (bedrock/latest/userguide/agents-lambda.html, read 2026-11-18)

Every adapter returns the internal call of herramientas/contrato.py. The requester of a proposal comes from the
gateway's arguments (the agent Lambda puts the token's subject there and the gateway's Cedar policy checks it is the
caller's `sub`) or, for Bedrock Agents, from the session attributes set by the caller of InvokeAgent (the action group
receives no user token: a gap the comparison documents).
"""
from __future__ import annotations

import json
from typing import Any

from herramientas import contrato

CLAVE_NOMBRE_GATEWAY = "bedrockAgentCoreToolName"


def _custom(context: Any) -> dict:
    cliente = getattr(context, "client_context", None)
    custom = getattr(cliente, "custom", None) if cliente is not None else None
    return custom if isinstance(custom, dict) else {}


def formato(event: Any, context: Any) -> str:
    if CLAVE_NOMBRE_GATEWAY in _custom(context):
        return "gateway"
    if isinstance(event, dict) and {"messageVersion", "actionGroup", "function"} <= set(event):
        return "agentes"
    return "directo"


def desde_gateway(event: dict, context: Any) -> dict:
    nombre = contrato.nombre_local(_custom(context)[CLAVE_NOMBRE_GATEWAY])
    args = dict(event or {})
    solicitante = args.pop(contrato.SOLICITANTE, None) if nombre == "proponer_orden_compra" else None
    return contrato.entrada_de_herramienta(nombre, args, solicitante)


_TIPOS = {"string": str, "integer": int, "number": float}


def _valor(parametro: dict):
    tipo, valor = parametro.get("type", "string"), parametro.get("value")
    if tipo == "boolean":
        return str(valor).lower() == "true"
    if tipo in _TIPOS:
        return _TIPOS[tipo](valor)
    if tipo == "array":   # Bedrock Agents sends an array as text: JSON, or the model's bare "[a, b]"
        texto = str(valor).strip()
        try:
            lista = json.loads(texto)
        except json.JSONDecodeError:
            if not (texto.startswith("[") and texto.endswith("]")):
                raise ValueError("arreglo mal formado") from None
            lista = [x.strip().strip("'\"") for x in texto[1:-1].split(",") if x.strip()]
        if not isinstance(lista, list) or not all(isinstance(x, str) for x in lista):
            raise ValueError("arreglo mal formado")
        return lista
    raise ValueError(f"tipo de parámetro no admitido: {tipo}")


def desde_agentes(event: dict) -> dict:
    nombre = event["function"]
    if nombre not in contrato.HERRAMIENTAS:
        raise ValueError("herramienta desconocida")
    args = {p["name"]: _valor(p) for p in event.get("parameters") or []}
    solicitante = (event.get("sessionAttributes") or {}).get(contrato.SOLICITANTE) \
        if nombre == "proponer_orden_compra" else None
    return contrato.entrada_de_herramienta(nombre, args, solicitante)


def respuesta_agentes(event: dict, resultado: dict) -> dict:
    """The function-details response. A tool error goes back as a normal body (the model reads it and may correct its
    call, as on the direct path); FAILURE would end the session with a DependencyFailedException."""
    return {"messageVersion": "1.0",
            "response": {"actionGroup": event["actionGroup"], "function": event["function"],
                         "functionResponse": {"responseBody": {"TEXT": {
                             "body": json.dumps(resultado, ensure_ascii=False, default=str)}}}}}
