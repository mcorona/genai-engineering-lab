"""Week 20, activity 4, R1: RUTEO in the agent Lambda's construction (ADR 0015 sections 5 and 6), offline ($0, no AWS,
no model).

With RUTEO absent or off, the deps are today's. With r1, the loop's `api` is the in-house router over the three
candidates, each called by the profile ARN the stack passes, with its own cache mode; the budget prices each call at
its model and the metrics' route is r1. Unknown values and missing ARNs fail closed, and so does a 1-hour TTL, which
Nova does not take."""
from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import handler as H  # noqa: E402
from agente import ruteo as R  # noqa: E402

NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
ARN = {NOVA: "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/nova",
       HAIKU: "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/haiku",
       SONNET: "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/sonnet"}
ENTORNO = {"MODELO": ARN[HAIKU], "FUNCION_HERRAMIENTAS": "fn-herramientas", "GUARDRAIL_ID": "gid-prueba",
           "GUARDRAIL_VERSION": "1", "GRUPO_SPANS": "/semana19/agente/spans"}
R1 = {**ENTORNO, K.RUTEO: "r1", "MODELO_NOVA_LITE": ARN[NOVA], "MODELO_SONNET_46": ARN[SONNET]}
CLAIMS = {"sub": "sub-aaaa-1111", "tenant": "tenant-norte", "scope": "legado/leer"}


class Converse:
    """Two calls: a SQL read, then the answer."""

    def __init__(self):
        self.pedidos = []

    def converse(self, **req):
        self.pedidos.append(copy.deepcopy(req))
        n = len(self.pedidos)
        if n == 1:
            bloque = {"toolUse": {"toolUseId": "tooluse_1", "name": "ejecutar_sql",
                                  "input": {"sql": "SELECT COUNT(*) FROM legado.prvmst"}}}
        else:
            bloque = {"toolUse": {"toolUseId": f"tooluse_{n}", "name": "responder", "input": {
                "estado": "respondida", "respuesta": "Hay 12 proveedores", "resultados": [], "evidencia": [],
                "supuestos": [], "pregunta_aclaracion": None}}}
        return {"output": {"message": {"role": "assistant", "content": [bloque]}}, "stopReason": "tool_use",
                "usage": {"inputTokens": 3000, "outputTokens": 100}}


class LambdaConError:
    """The tools Lambda: the first read fails, so the router escalates on `error_herramienta`."""

    def __init__(self):
        self.n = 0

    def invoke(self, FunctionName, Payload):
        self.n += 1
        cuerpo = {"error": "sql_invalido", "mensaje": "x"} if self.n == 1 else {"filas": [[12]], "truncado": False}
        return {"Payload": io.BytesIO(json.dumps(cuerpo).encode())}


def _construir(entorno, converse=None, lineas=None):
    return K.construir(cliente_converse=converse or Converse(), cliente_lambda=LambdaConError(), entorno=entorno,
                       exportar=(lineas if lineas is not None else []).append)


# --- off is today's ---------------------------------------------------------------------------------------------------

def test_without_ruteo_the_deps_are_todays():
    for entorno in (ENTORNO, {**ENTORNO, K.RUTEO: "off"}):
        deps = _construir(entorno)
        assert not isinstance(deps["api_modelo"], R.Enrutador)
        assert deps["precios_por_modelo"] is None and deps["ruta"] == "fija"


def test_an_unknown_ruteo_fails_closed():
    with pytest.raises(RuntimeError, match="RUTEO desconocido"):
        _construir({**ENTORNO, K.RUTEO: "r2"})


# --- r1: what the stack must pass -------------------------------------------------------------------------------------

@pytest.mark.parametrize("falta", ["MODELO_NOVA_LITE", "MODELO_SONNET_46"])
def test_r1_without_a_candidates_profile_arn_fails_closed(falta):
    with pytest.raises(RuntimeError, match=falta):
        K.exigir_entorno({k: v for k, v in R1.items() if k != falta})


def test_off_does_not_ask_for_the_candidates_arns():
    K.exigir_entorno(ENTORNO)


def test_r1_with_the_one_hour_ttl_is_a_configuration_error():
    with pytest.raises(RuntimeError, match="Nova"):
        _construir({**R1, K.CACHE_TTL: "1h"})


def test_each_candidate_is_called_by_the_arn_the_stack_passes():
    deps = _construir(R1)
    api = deps["api_modelo"]
    assert isinstance(api, R.Enrutador)
    assert [(c.id, c.llamar_como, c.nova) for c in api.candidatos] == [(NOVA, ARN[NOVA], True),
                                                                       (HAIKU, ARN[HAIKU], False),
                                                                       (SONNET, ARN[SONNET], False)]
    assert api.reglas == K.RUTEO_REGLAS
    assert api.guardrail == {"guardrailIdentifier": "gid-prueba", "guardrailVersion": "1"}
    assert deps["precios_por_modelo"] == K.PRECIOS_POR_MODELO and deps["ruta"] == "r1"


def test_the_cache_mode_per_model_applies_only_when_caching_is_on():
    assert [c.cache for c in _construir(R1)["api_modelo"].candidatos] == ["off", "off", "off"]
    con = _construir({**R1, K.CACHE_PROMPT: "historial"})["api_modelo"]
    assert {c.id: c.cache for c in con.candidatos} == K.CACHE_POR_MODELO


# --- one routed query, end to end through the week 13 loop --------------------------------------------------------------

def test_a_routed_query_starts_on_nova_and_moves_to_haiku_after_a_tool_error():
    converse, lineas = Converse(), []
    deps = _construir({**R1, K.CACHE_PROMPT: "historial"}, converse, lineas)
    res = H.tratar_pregunta("¿Cuántos proveedores hay?", H.alcance_desde_claims(CLAIMS), **deps)
    assert res.estado == "respondida"
    assert [p["modelId"] for p in converse.pedidos] == [ARN[NOVA], ARN[HAIKU]]
    nova, haiku = converse.pedidos
    assert nova["inferenceConfig"]["temperature"] == 0 and "additionalModelRequestFields" in nova
    assert any("cachePoint" in b for b in nova["system"])          # historial+sistema on Nova
    assert not any("cachePoint" in b for b in haiku["system"])     # historial on Haiku 4.5
    assert "temperature" not in haiku["inferenceConfig"]
    spans = [json.loads(x) for x in lineas]
    assert [x["span"] for x in spans if x["tipo"] == "chat"] == [f"chat {NOVA}", f"chat {HAIKU}"]
    (agente,) = [x for x in spans if x["tipo"] == "invoke_agent"]
    assert agente["Ruta"] == "r1" and agente["omitidos"] == []
    assert agente["attrs"]["lab.route.escalations"] == 1 and agente["attrs"]["lab.route.final_model"] == HAIKU
