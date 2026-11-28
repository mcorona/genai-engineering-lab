"""Week 20, activity 4, R1: the Converse request for Nova Lite (ADR 0015), offline ($0, no AWS, no model).

Nova reads only `type`, `properties` and `required` at the top level of a tool's schema, and calls tools best with
greedy decoding (Nova tool troubleshooting, read 2026-11-27). Nova takes only the 5-minute TTL, so the `ttl` field is
never sent. The Claude request does not change (the week 19 snapshot)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente.converse_adaptador import esquema_para_nova, peticion_a_converse  # noqa: E402

SNAPSHOT = json.loads((S19 / "tests" / "snapshots" / "converse_semana19.json").read_text(encoding="utf-8"))
GUARD = {"guardrailIdentifier": "gid", "guardrailVersion": "3"}
NOVA = "us.amazon.nova-lite-v1:0"


def _definiciones():
    _, m = K.cargar_bucle_semana13()
    from agente import capa_determinista as C
    return C.definiciones_semana19() + [m.herramienta_responder()]


def _cuerpo():
    return {"model": "x", "max_tokens": 900, "system": "SISTEMA", "output_config": {"effort": "low"},
            "tools": _definiciones(), "messages": [{"role": "user", "content": "¿cuántos artículos hay?"}]}


def _refs(objeto) -> list:
    if isinstance(objeto, dict):
        return (["$ref"] if "$ref" in objeto else []) + [r for v in objeto.values() for r in _refs(v)]
    if isinstance(objeto, list):
        return [r for v in objeto for r in _refs(v)]
    return []


def test_every_tool_schema_sent_to_nova_has_only_the_three_top_level_keys():
    req = peticion_a_converse(_cuerpo(), modelo_id="arn-del-perfil-nova", guardrail=GUARD, nova=True)
    for herramienta in req["toolConfig"]["tools"]:
        esquema = herramienta["toolSpec"]["inputSchema"]["json"]
        assert set(esquema) <= {"type", "properties", "required"}, herramienta["toolSpec"]["name"]
        assert esquema["type"] == "object"


def test_the_responder_schema_keeps_its_fields_with_the_references_inlined():
    responder = next(d for d in _definiciones() if d["name"] == "responder")["input_schema"]
    reducido = esquema_para_nova(responder)
    assert _refs(reducido) == [] and "$defs" not in json.dumps(reducido)
    assert set(reducido["properties"]) == set(responder["properties"])
    assert reducido["required"] == responder["required"]
    resultado = reducido["properties"]["resultados"]["items"]
    assert set(resultado["properties"]) == {"clave", "sql", "valor"}


def test_the_reduction_does_not_touch_the_loops_definitions():
    cuerpo = _cuerpo()
    antes = json.dumps(cuerpo["tools"], sort_keys=True)
    peticion_a_converse(cuerpo, modelo_id="m", nova=True)
    assert json.dumps(cuerpo["tools"], sort_keys=True) == antes


def test_nova_is_called_with_greedy_decoding():
    req = peticion_a_converse(_cuerpo(), modelo_id="m", nova=True)
    assert req["inferenceConfig"] == {"maxTokens": 900, "temperature": 0}
    assert req["additionalModelRequestFields"] == {"inferenceConfig": {"topK": 1}}


def test_nova_keeps_the_guardrail_the_system_prompt_and_the_tool_result_status():
    cuerpo = dict(_cuerpo(), messages=[
        {"role": "user", "content": "pregunta"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "describir_esquema", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x", "is_error": True}]}])
    req = peticion_a_converse(cuerpo, modelo_id="m", guardrail=GUARD, nova=True)
    assert req["guardrailConfig"] == GUARD and req["system"] == [{"text": "SISTEMA"}]
    assert req["messages"][2]["content"][0]["toolResult"]["status"] == "error"


@pytest.mark.parametrize("modo", ["sistema", "historial", "historial+sistema"])
def test_nova_cache_points_never_carry_a_ttl_and_never_go_in_the_tools(modo):
    cuerpo = dict(_cuerpo(), messages=[
        {"role": "user", "content": "pregunta"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "describir_esquema", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}])
    req = peticion_a_converse(cuerpo, modelo_id="m", cache=modo, nova=True)
    texto = json.dumps(req)
    assert '"ttl"' not in texto
    assert all("cachePoint" not in t for t in req["toolConfig"]["tools"])


def test_nova_refuses_the_one_hour_ttl():
    with pytest.raises(ValueError):
        peticion_a_converse(_cuerpo(), modelo_id="m", cache="historial", ttl="1h", nova=True)


def test_the_claude_request_is_still_week_19s_byte_for_byte():
    req = peticion_a_converse(SNAPSHOT["cuerpo"], modelo_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                              guardrail=GUARD, nova=False)
    assert json.dumps(req, sort_keys=True) == json.dumps(SNAPSHOT["peticion"], sort_keys=True)
