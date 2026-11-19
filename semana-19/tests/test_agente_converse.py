"""Week 19, activity 6: the Converse adapter for the reused agent loop, offline ($0, no AWS, no model)."""
from __future__ import annotations

import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente.converse_adaptador import api_converse, peticion_a_converse, respuesta_a_anthropic  # noqa: E402

GUARD = {"guardrailIdentifier": "teps1un80k04", "guardrailVersion": "3"}
CUERPO = {
    "model": "x", "max_tokens": 900, "system": "SISTEMA", "output_config": {"effort": "low"},
    "tools": [{"name": "describir_esquema", "description": "d", "input_schema": {"type": "object", "properties": {}}}],
    "messages": [
        {"role": "user", "content": "pregunta"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "describir_esquema", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{\"ok\": true}", "is_error": False}]},
    ],
}


def test_peticion_lleva_modelo_guardrail_sistema_y_herramientas():
    req = peticion_a_converse(CUERPO, modelo_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", guardrail=GUARD)
    assert req["modelId"].startswith("us.anthropic.claude-haiku-4-5")
    assert req["guardrailConfig"] == GUARD
    assert req["system"] == [{"text": "SISTEMA"}]
    assert req["inferenceConfig"] == {"maxTokens": 900}
    assert req["toolConfig"]["tools"][0]["toolSpec"]["name"] == "describir_esquema"


def test_effort_no_pasa_a_converse():
    req = peticion_a_converse(CUERPO, modelo_id="m")
    assert "output_config" not in str(req) and "effort" not in str(req)


def test_bloques_tool_use_y_tool_result_se_traducen():
    req = peticion_a_converse(CUERPO, modelo_id="m")
    assistant = req["messages"][1]["content"][0]["toolUse"]
    assert assistant == {"toolUseId": "t1", "name": "describir_esquema", "input": {}}
    resultado = req["messages"][2]["content"][0]["toolResult"]
    assert resultado["toolUseId"] == "t1" and resultado["status"] == "success"


def test_tool_result_con_error_marca_status_error():
    cuerpo = dict(CUERPO, messages=[{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t9", "content": "{}", "is_error": True}]}])
    assert peticion_a_converse(cuerpo, modelo_id="m")["messages"][0]["content"][0]["toolResult"]["status"] == "error"


def test_respuesta_con_herramienta_vuelve_en_formato_del_bucle():
    resp = {"output": {"message": {"role": "assistant", "content": [
                {"text": "voy"}, {"toolUse": {"toolUseId": "t2", "name": "ejecutar_sql", "input": {"sql": "SELECT 1"}}}]}},
            "stopReason": "tool_use", "usage": {"inputTokens": 120, "outputTokens": 30}}
    d = respuesta_a_anthropic(resp)
    assert d["stop_reason"] == "tool_use"
    assert d["content"][1] == {"type": "tool_use", "id": "t2", "name": "ejecutar_sql", "input": {"sql": "SELECT 1"}}
    assert d["usage"] == {"input_tokens": 120, "output_tokens": 30, "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0}


def test_tokens_de_cache_de_converse_llegan_al_bucle():
    resp = {"output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}, "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 2, "cacheReadInputTokens": 700, "cacheWriteInputTokens": 90}}
    assert respuesta_a_anthropic(resp)["usage"] == {"input_tokens": 10, "output_tokens": 2,
                                                   "cache_read_input_tokens": 700, "cache_creation_input_tokens": 90}


def test_max_tokens_y_end_turn_se_mapean():
    assert respuesta_a_anthropic({"output": {"message": {"content": []}}, "stopReason": "max_tokens"})["stop_reason"] == "max_tokens"
    assert respuesta_a_anthropic({"output": {"message": {"content": []}}, "stopReason": "end_turn"})["stop_reason"] == "end_turn"


def test_api_envia_una_sola_llamada_y_devuelve_formato_bucle():
    llamadas = []

    def llamar(req):
        llamadas.append(req)
        return {"output": {"message": {"content": [{"text": "ok"}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": 1, "outputTokens": 1}}

    api = api_converse(llamar, modelo_id="m", guardrail=GUARD)
    d = api(CUERPO)
    assert len(llamadas) == 1 and llamadas[0]["guardrailConfig"] == GUARD
    assert d["content"] == [{"type": "text", "text": "ok"}]
