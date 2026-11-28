"""Week 19, activity 6: the agent loop (semana-13/agente/loop.py) talks Anthropic Messages format; the agent Lambda
calls Bedrock Converse. This adapter translates both ways, so the loop is reused as it is (its `api=` parameter).

Pure functions: no AWS here. The Lambda passes the real Converse call (with the guardrail config of the activity 5
adapter) as `llamar`.

Week 20, activity 3: the prompt cache points (`cache=`, the CACHE_PROMPT value; ADR 0014). Bedrock reads the cache
in the order tools -> system -> messages and checks the minimum (4,096 tokens on Haiku 4.5) on the whole prefix
before each point; a point under it is not cached and the call still succeeds (prompt-caching docs, read 2026-11-25).
- "off": no point; the request is week 19's, byte for byte (tests/snapshots/converse_semana19.json).
- "sistema": one point after the system prompt, so it covers the tools and the system prompt. About 2,800 tokens:
  it never caches on Haiku 4.5 (kept for models with a lower minimum, such as Haiku 5.5's 512).
- "historial": a point at the end of the last message, from the second call on, and one at the end of the message
  the previous call ended with (where that call put its point), so a step reads what the step before wrote without
  relying on Bedrock's 20-block lookback. Never on the first call: that prefix (system, tools and the question) is the
  only one two users could share; every later one holds this query's own toolUseIds.
- "historial+sistema": both. At most 3 of the 4 points a request may carry.
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


MODOS_CACHE = ("off", "sistema", "historial", "historial+sistema")
TTLS_CACHE = ("5m", "1h")
MAX_PUNTOS_CACHE = 4     # per request (prompt-caching docs)


def punto_de_cache(ttl: str = "5m") -> dict:
    """A Converse cache point block. The 5-minute TTL is the default and goes without `ttl`."""
    if ttl not in TTLS_CACHE:
        raise ValueError(f"TTL de caché desconocido: {ttl}")
    return {"cachePoint": {"type": "default"} if ttl == "5m" else {"type": "default", "ttl": ttl}}


def posiciones_de_cache(n_mensajes: int) -> list[int]:
    """Indexes of the messages that end with a history cache point: the last one and the one two before it (the
    previous call's last message), each only when a model turn comes before it. Empty on the first call."""
    return [i for i in (n_mensajes - 3, n_mensajes - 1) if i >= 2]


def _con_cache(req: dict, modo: str, ttl: str) -> dict:
    if modo not in MODOS_CACHE:
        raise ValueError(f"modo de caché desconocido: {modo}")
    if modo in ("sistema", "historial+sistema"):
        req["system"].append(punto_de_cache(ttl))
    if modo in ("historial", "historial+sistema"):
        for i in posiciones_de_cache(len(req["messages"])):
            req["messages"][i]["content"].append(punto_de_cache(ttl))
    return req


# Week 20, activity 4 (ADR 0015): Nova reads only these keys at the top level of a tool's schema; `$schema`,
# `description`, `title` and `additionalProperties` there can make it ignore the tool (Nova tool troubleshooting,
# read 2026-11-27). Nova also calls tools best with greedy decoding (same page), and takes only the 5-minute TTL.
CLAVES_NOVA = ("type", "properties", "required")


def _sin_referencias(objeto, definiciones: dict):
    if isinstance(objeto, dict):
        if "$ref" in objeto:
            return _sin_referencias(definiciones[objeto["$ref"].rsplit("/", 1)[-1]], definiciones)
        return {k: _sin_referencias(v, definiciones) for k, v in objeto.items() if k != "$defs"}
    if isinstance(objeto, list):
        return [_sin_referencias(v, definiciones) for v in objeto]
    return objeto


def esquema_para_nova(esquema: dict) -> dict:
    """A tool's JSON schema as Nova reads it: the `$defs` references inlined, and only `type`, `properties` and
    `required` at the top level. A new dict: the loop's definitions are never changed."""
    plano = _sin_referencias(esquema, esquema.get("$defs", {}))
    return {k: plano[k] for k in CLAVES_NOVA if k in plano}


def peticion_a_converse(cuerpo: dict, *, modelo_id: str, guardrail: dict | None = None, cache: str = "off",
                        ttl: str = "5m", nova: bool = False) -> dict:
    """The loop's body (Anthropic format) -> Converse request. `output_config.effort` has no Converse equivalent for
    this model and is dropped on purpose; the loop's own limits still apply. The request's lists are built here, so
    the cache points never touch the loop's history. `nova`: the request for a Nova model (ADR 0015): the tools'
    schemas reduced, greedy decoding, and the 5-minute TTL only."""
    if nova and ttl != "5m":
        raise ValueError(f"Nova solo admite el TTL de 5 minutos, no {ttl}")
    req: dict[str, Any] = {
        "modelId": modelo_id,
        "system": [{"text": cuerpo["system"]}],
        "messages": [_mensaje_a_converse(m) for m in cuerpo["messages"]],
        "inferenceConfig": {"maxTokens": cuerpo["max_tokens"]},
    }
    herramientas = cuerpo.get("tools") or []
    if herramientas:
        esquema = esquema_para_nova if nova else (lambda e: e)
        req["toolConfig"] = {"tools": [{"toolSpec": {
            "name": h["name"], "description": h.get("description", ""),
            "inputSchema": {"json": esquema(h.get("input_schema", {"type": "object"}))}}} for h in herramientas]}
    if guardrail:
        req["guardrailConfig"] = guardrail
    if nova:
        req["inferenceConfig"]["temperature"] = 0
        req["additionalModelRequestFields"] = {"inferenceConfig": {"topK": 1}}
    return req if cache == "off" else _con_cache(req, cache, ttl)


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
            # Cache tokens (activity 8): Converse reports them only when a cachePoint is sent; absent means 0.
            "usage": {"input_tokens": uso.get("inputTokens", 0), "output_tokens": uso.get("outputTokens", 0),
                      "cache_read_input_tokens": uso.get("cacheReadInputTokens", 0),
                      "cache_creation_input_tokens": uso.get("cacheWriteInputTokens", 0)}}


def api_converse(llamar: Callable[[dict], dict], *, modelo_id: str, guardrail: dict | None = None) -> Callable[[dict], dict]:
    """The `api=` the loop receives: translate, call Converse through `llamar`, translate back."""
    def api(cuerpo: dict) -> dict:
        return respuesta_a_anthropic(llamar(peticion_a_converse(cuerpo, modelo_id=modelo_id, guardrail=guardrail)))
    return api
