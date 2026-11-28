"""Week 20, activity 4, R1: the in-house router behind `modelo.invocar` (ADR 0015), offline ($0, no AWS, no model).

Each rule escalates on its signal and only then; the escalation lasts for the rest of the task and never goes back
down; at most max_escalamientos; the guardrail's intervention and max_tokens never escalate; a new task starts again
on the cheapest model; a response signal sends the same request again only if the budget allows it."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import ruteo as R  # noqa: E402

NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
GUARD = {"guardrailIdentifier": "gid", "guardrailVersion": "3"}
ARN = {NOVA: "arn:perfil/nova", HAIKU: "arn:perfil/haiku", SONNET: "arn:perfil/sonnet"}


def _texto(t="ok"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": t}]}}, "stopReason": "end_turn",
            "usage": {"inputTokens": 100, "outputTokens": 10}}


def _herramienta(nombre="ejecutar_sql", entrada=None, tin=100, tout=10):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "tu", "name": nombre, "input": entrada or {}}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": tin, "outputTokens": tout}}


def _responder(estado="respondida", respuesta="Hay 42 artículos en el inventario de la empresa."):
    return _herramienta("responder", {"estado": estado, "respuesta": respuesta, "resultados": []})


class Modelos:
    """A fake Converse: answers by the modelId it is called with; records every request."""

    def __init__(self, **respuestas):
        self.respuestas = {ARN[NOVA]: respuestas.get("nova", [_herramienta()]),
                           ARN[HAIKU]: respuestas.get("haiku", [_herramienta()]),
                           ARN[SONNET]: respuestas.get("sonnet", [_herramienta()])}
        self.peticiones: list[dict] = []

    def __call__(self, req):
        self.peticiones.append(req)
        cola = self.respuestas[req["modelId"]]
        return cola.pop(0) if len(cola) > 1 else cola[0]

    def modelos(self):
        inverso = {v: k for k, v in ARN.items()}
        return [inverso[p["modelId"]] for p in self.peticiones]


def _enrutador(modelos, cache="off", reglas=None, permitir=None):
    candidatos = tuple(R.Candidato(id=c, llamar_como=ARN[c], cache="off" if cache == "off" else K.CACHE_POR_MODELO[c],
                                   nova="amazon.nova" in c) for c in K.RUTEO_CANDIDATOS)
    e = R.Enrutador(modelos, candidatos=candidatos, reglas=reglas or K.RUTEO_REGLAS, guardrail=GUARD)
    if permitir is not None:
        e.permitir = permitir
    return e


TAREA = "¿Cuántos artículos hay en el inventario de la bodega principal?"


def _cuerpo(*resultados, pasos=None, tarea=TAREA):
    """A loop body: the task, then one (assistant tool_use, user tool_result) pair per result."""
    mensajes = [{"role": "user", "content": tarea}]
    for i, r in enumerate(resultados):
        mensajes.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "ejecutar_sql",
                                                           "input": {}}]})
        mensajes.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                                      "is_error": not r.get("ok", False),
                                                      "content": json.dumps(r, ensure_ascii=False)}]})
    return {"model": "x", "max_tokens": 900, "system": "SISTEMA", "messages": mensajes,
            "tools": [{"name": "ejecutar_sql", "description": "d", "input_schema": {"type": "object"}}]}


OK = {"ok": True, "filas": [[42]]}


def _paso(e, *resultados):
    return e(_cuerpo(*resultados))


# --- no signal --------------------------------------------------------------------------------------------------

def test_without_a_signal_the_whole_task_stays_on_nova_lite():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, OK)
    _paso(e, OK, OK)
    assert m.modelos() == [NOVA, NOVA, NOVA]
    assert e.escalamientos == 0
    assert [x["ruta"] for x in e.ultimas_llamadas] == [{"inicial": NOVA, "escalado": False, "motivo": None}]


# --- request signals: the next call goes to the next model ----------------------------------------------------

@pytest.mark.parametrize("resultado, motivo", [
    ({"ok": False, "error": {"tipo": "sql_invalido", "mensaje": "x"}}, "error_herramienta"),
    ({"ok": True, "filas": []}, "resultado_vacio"),
    ({"ok": False, "error": {"tipo": "guardrail", "mensaje": "Bloqueado"}}, "bloqueo_capa"),
    ({"ok": False, "error": {"tipo": "herramienta_desconocida", "mensaje": "x"}}, "bloqueo_capa"),
    ({"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje": "x"}}, "respuesta_invalida"),
])
def test_each_request_signal_sends_the_next_call_to_haiku_and_says_why(resultado, motivo):
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, resultado)
    assert m.modelos() == [NOVA, HAIKU]
    assert e.ultimas_llamadas[-1]["ruta"] == {"inicial": NOVA, "escalado": True, "motivo": motivo}


def test_step_pressure_escalates_at_the_seventh_model_turn_and_only_once():
    m = Modelos()
    e = _enrutador(m)
    for n in range(9):
        _paso(e, *([OK] * n))
    assert m.modelos() == [NOVA] * 7 + [HAIKU, HAIKU]
    assert e.escalamientos == 1


def test_token_pressure_escalates_once_the_task_has_seen_50000_tokens():
    m = Modelos(nova=[_herramienta(tin=24_000, tout=1_000)])
    e = _enrutador(m)
    _paso(e)
    _paso(e, OK)                 # 50,000 seen after this call
    _paso(e, OK, OK)
    _paso(e, OK, OK, OK)
    assert m.modelos() == [NOVA, NOVA, HAIKU, HAIKU]
    assert e.ultimas_llamadas[-1]["ruta"]["motivo"] is None
    assert e.motivos == ["presion_tokens"]


def test_a_successful_result_with_rows_is_not_a_signal():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, {"ok": True, "filas": [["a"]], "columnas": ["x"]})
    assert m.modelos() == [NOVA, NOVA]


# --- response signals: the same request goes to the next model -------------------------------------------------

@pytest.mark.parametrize("respuesta_nova, motivo", [
    (_texto("<thinking>no sé</thinking>"), "respuesta_vacia"),
    ({"output": {"message": {"role": "assistant", "content": []}}, "stopReason": "end_turn",
      "usage": {"inputTokens": 1, "outputTokens": 0}}, "respuesta_vacia"),
    (_responder("abstenida", "La base de datos no tiene ese dato."), "abstencion"),
    (_responder("requiere_aclaracion", "¿De qué bodega hablas?"), "abstencion"),
    (_responder("respondida", "There are 42 items in the main warehouse inventory of the company."), "idioma"),
])
def test_each_response_signal_resends_the_same_request_to_haiku_and_the_loop_sees_only_haikus_answer(
        respuesta_nova, motivo):
    m = Modelos(nova=[respuesta_nova], haiku=[_responder()])
    e = _enrutador(m)
    resp = _paso(e)
    assert m.modelos() == [NOVA, HAIKU]
    assert m.peticiones[0]["messages"] == m.peticiones[1]["messages"]
    assert resp["content"][0]["input"]["estado"] == "respondida"
    nova, haiku = e.ultimas_llamadas
    assert nova["descartada"] is True and haiku["descartada"] is False
    assert haiku["ruta"] == {"inicial": NOVA, "escalado": True, "motivo": motivo}


def test_the_language_signal_reads_the_task_before_the_evals_english_output_keys():
    tarea = TAREA + "\n\nOutput keys to report if you can answer:\n- total: the number of items (numero)"
    m = Modelos(nova=[_responder()])
    e = _enrutador(m)
    e(_cuerpo(tarea=tarea))
    assert m.modelos() == [NOVA]


def test_an_english_task_answered_in_spanish_escalates():
    m = Modelos(nova=[_responder()], haiku=[_responder("respondida", "There are 42 items in the main warehouse.")])
    e = _enrutador(m)
    e(_cuerpo(tarea="How many items are there in the inventory of the main warehouse?"))
    assert m.modelos() == [NOVA, HAIKU] and e.motivos == ["idioma"]


def test_the_loop_counts_the_tokens_of_every_paid_call_of_its_step():
    m = Modelos(nova=[_responder("abstenida")], haiku=[_responder()])
    resp = _paso(_enrutador(m))
    assert resp["usage"]["input_tokens"] == 200 and resp["usage"]["output_tokens"] == 20


# --- never a signal ---------------------------------------------------------------------------------------------

def test_the_guardrails_intervention_never_escalates():
    bloqueada = dict(_texto("Lo siento, no puedo ayudar con eso."), stopReason="guardrail_intervened")
    m = Modelos(nova=[bloqueada])
    _paso(_enrutador(m))
    assert m.modelos() == [NOVA]


def test_the_guardrails_intervention_never_escalates_even_with_an_abstention_in_it():
    bloqueada = dict(_responder("abstenida", "No puedo responder eso."), stopReason="guardrail_intervened")
    m = Modelos(nova=[bloqueada])
    _paso(_enrutador(m))
    assert m.modelos() == [NOVA]


def test_max_tokens_never_escalates():
    cortada = dict(_texto("SELECT"), stopReason="max_tokens")
    m = Modelos(nova=[cortada])
    _paso(_enrutador(m))
    assert m.modelos() == [NOVA]


# --- scope, maximum, reset ----------------------------------------------------------------------------------------

ERROR = {"ok": False, "error": {"tipo": "sql_invalido", "mensaje": "x"}}


def test_an_escalation_lasts_for_the_rest_of_the_task_and_never_goes_back_down():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, ERROR)
    _paso(e, ERROR, OK)
    _paso(e, ERROR, OK, OK)
    assert m.modelos() == [NOVA, HAIKU, HAIKU, HAIKU]


def test_at_most_two_escalations_then_signals_are_recorded_and_ignored():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, ERROR)
    _paso(e, ERROR, ERROR)
    _paso(e, ERROR, ERROR, ERROR)
    assert m.modelos() == [NOVA, HAIKU, SONNET, SONNET]
    assert e.escalamientos == 2
    assert e.motivos == ["error_herramienta", "error_herramienta"]
    assert e.ignoradas == ["error_herramienta"]


def test_sonnet_answering_abstention_stands():
    m = Modelos(nova=[_responder("abstenida")], haiku=[_responder("abstenida")], sonnet=[_responder("abstenida")])
    resp = _paso(_enrutador(m))
    assert m.modelos() == [NOVA, HAIKU, SONNET]
    assert resp["content"][0]["input"]["estado"] == "abstenida"


def test_a_new_task_starts_again_on_nova_lite():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, ERROR)
    _paso(e)                       # one message: a new task
    assert m.modelos() == [NOVA, HAIKU, NOVA]
    assert e.escalamientos == 0


def test_asking_which_model_comes_next_twice_does_not_escalate_twice():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    cuerpo = _cuerpo(ERROR)
    assert e.siguiente(cuerpo) == e.siguiente(cuerpo) == HAIKU
    e(dict(cuerpo, max_tokens=500))
    assert m.modelos() == [NOVA, HAIKU] and e.escalamientos == 1


# --- the budget ---------------------------------------------------------------------------------------------------

def test_a_resend_the_budget_refuses_keeps_the_cheap_answer_and_says_so():
    preguntas = []
    m = Modelos(nova=[_responder("abstenida")])
    e = _enrutador(m, permitir=lambda modelo, cuerpo, ya: preguntas.append(modelo) or None)
    resp = _paso(e)
    assert m.modelos() == [NOVA] and preguntas == [HAIKU]
    assert resp["content"][0]["input"]["estado"] == "abstenida"
    assert e.ultimas_llamadas[-1]["ruta"]["motivo"] == "sin_presupuesto"


def test_a_resend_goes_with_the_max_tokens_the_budget_gives_at_the_next_models_price():
    m = Modelos(nova=[_responder("abstenida")], haiku=[_responder()])
    _paso(_enrutador(m, permitir=lambda modelo, cuerpo, ya: 321))
    assert m.peticiones[1]["inferenceConfig"]["maxTokens"] == 321


def test_each_call_reports_its_model_and_usage_for_the_budget():
    m = Modelos(nova=[_responder("abstenida")], haiku=[_responder()])
    resp = _paso(_enrutador(m))
    assert [(x["modelo"], x["usage"]["input_tokens"]) for x in resp["_llamadas"]] == [(NOVA, 100), (HAIKU, 100)]


# --- the requests per model ---------------------------------------------------------------------------------------

def test_nova_gets_its_reduced_request_and_claude_its_own():
    m = Modelos()
    e = _enrutador(m)
    _paso(e)
    _paso(e, ERROR)
    nova, haiku = m.peticiones
    assert nova["inferenceConfig"].get("temperature") == 0 and "additionalModelRequestFields" in nova
    assert "temperature" not in haiku["inferenceConfig"] and "additionalModelRequestFields" not in haiku
    assert nova["guardrailConfig"] == haiku["guardrailConfig"] == GUARD


def test_each_model_gets_its_own_cache_mode_and_nova_never_a_ttl():
    m = Modelos()
    e = _enrutador(m, cache="historial")
    _paso(e)
    _paso(e, ERROR)
    nova, haiku = m.peticiones
    assert any("cachePoint" in b for b in nova["system"])            # historial+sistema: the fixed prefix
    assert not any("cachePoint" in b for b in haiku["system"])       # historial: Haiku's minimum is 4,096
    assert '"ttl"' not in json.dumps(nova)


def test_with_the_cache_off_no_model_gets_a_point():
    m = Modelos()
    e = _enrutador(m, cache="off")
    _paso(e)
    _paso(e, ERROR)
    assert "cachePoint" not in json.dumps(m.peticiones)


# --- the language detector ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto, idioma", [
    ("¿Cuántos artículos hay en la bodega de la empresa?", "es"),
    ("How many items are there in the main warehouse of the company?", "en"),
    ("42", None),
    ("SELECT COUNT(*) FROM artmst WHERE activo = 1 AND bodega IN (1, 2)", None),
])
def test_the_language_detector(texto, idioma):
    assert R.idioma_de(texto) == idioma
