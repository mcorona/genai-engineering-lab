"""Week 19, activity 6: the agent loop (semana-13/agente/loop.py) talks Anthropic Messages format; the agent Lambda
calls Bedrock Converse. This adapter translates both ways, so the loop is reused as it is (its `api=` parameter).

Pure functions: no AWS here. The Lambda passes the real Converse call (with the guardrail config of the activity 5
adapter) as `llamar`.
"""
from __future__ import annotations

from typing import Any, Callable

# Anthropic stop reasons -> the loop's stop reasons (the loop reads "tool_use", "end_turn" and "max_tokens").
_STOP = {"tool_use": "tool_use", "end_turn": "end_turn", "max_tokens": "max_tokens",
         "stop_sequence": "end_turn", "guardrail_intervened": "end_turn", "content_filtered": "end_turn"}


def _bloque_a_converse(b: dict) -> dict:
    tipo = b.get("type")
    if tipo == "text":
        return {"text": b.get("text", "")}
    if tipo == "tool_use":
        return {"toolUse": {"toolUseId": b["id"], "name": b["name"], "input": b.get("input") or {}}}
    if tipo == "tool_result":
        return {"toolResult": {"toolUseId": b["tool_use_id"],
                               "content": [{"text": str(b.get("content", ""))}],
                               "status": "error" if b.get("is_error") else "success"}}
    raise ValueError(f"bloque no soportado: {tipo}")


def _mensaje_a_converse(m: dict) -> dict:
    contenido = m["content"]
    bloques = [{"text": contenido}] if isinstance(contenido, str) else [_bloque_a_converse(b) for b in contenido]
    return {"role": m["role"], "content": bloques}


def peticion_a_converse(cuerpo: dict, *, modelo_id: str, guardrail: dict | None = None) -> dict:
    """The loop's body (Anthropic format) -> Converse request. `output_config.effort` has no Converse equivalent for
    this model and is dropped on purpose; the loop's own limits still apply."""
    req: dict[str, Any] = {
        "modelId": modelo_id,
        "system": [{"text": cuerpo["system"]}],
        "messages": [_mensaje_a_converse(m) for m in cuerpo["messages"]],
        "inferenceConfig": {"maxTokens": cuerpo["max_tokens"]},
    }
    herramientas = cuerpo.get("tools") or []
    if herramientas:
        req["toolConfig"] = {"tools": [{"toolSpec": {
            "name": h["name"], "description": h.get("description", ""),
            "inputSchema": {"json": h.get("input_schema", {"type": "object"})}}} for h in herramientas]}
    if guardrail:
        req["guardrailConfig"] = guardrail
    return req


def respuesta_a_anthropic(resp: dict) -> dict:
    """Converse response -> the Anthropic-shaped dict the loop reads (content blocks, stop_reason, usage)."""
    bloques = []
    for b in resp["output"]["message"]["content"]:
        if "text" in b:
            bloques.append({"type": "text", "text": b["text"]})
        elif "toolUse" in b:
            t = b["toolUse"]
            bloques.append({"type": "tool_use", "id": t["toolUseId"], "name": t["name"], "input": t.get("input") or {}})
    uso = resp.get("usage", {})
    return {"content": bloques,
            "stop_reason": _STOP.get(resp.get("stopReason"), "end_turn"),
            "usage": {"input_tokens": uso.get("inputTokens", 0), "output_tokens": uso.get("outputTokens", 0)}}


def api_converse(llamar: Callable[[dict], dict], *, modelo_id: str, guardrail: dict | None = None) -> Callable[[dict], dict]:
    """The `api=` the loop receives: translate, call Converse through `llamar`, translate back."""
    def api(cuerpo: dict) -> dict:
        return respuesta_a_anthropic(llamar(peticion_a_converse(cuerpo, modelo_id=modelo_id, guardrail=guardrail)))
    return api
