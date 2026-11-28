"""Week 20, activity 4, R1: the router's telemetry (ADR 0015 section 7), offline ($0, no AWS, no model).

Every paid call has its chat span, with the model that served it and the route; the discarded answer of a resend
too. The agent span carries the escalations and the last model. The route keys are in week 17's locked shape, so the
exporter drops nothing. EMF holds 10 custom metrics: 6 without dimensions, CostoUSD and Respondida by Ruta."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import capa_determinista as C  # noqa: E402
from agente import construccion as K  # noqa: E402
from agente import handler as H  # noqa: E402
from agente import metricas as M  # noqa: E402
from agente import ruteo as R  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from presupuestos.politica import Limite, Politica  # noqa: E402

NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
ALCANCE = H.alcance_desde_claims({"sub": "usuario-prueba-1", "tenant": "lab", "scope": "legado/leer"})
TAREA = "¿Cuántos artículos hay en la bodega principal de la empresa?"
ERROR = {"ok": False, "error": {"tipo": "sql_invalido", "mensaje": "x"}}


def _sql(tin=1000, tout=50):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "tu", "name": "ejecutar_sql", "input": {}}}]}}, "stopReason": "tool_use",
        "usage": {"inputTokens": tin, "outputTokens": tout}}


def _responder(estado):
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
        "toolUseId": "tu", "name": "responder",
        "input": {"estado": estado, "respuesta": "Hay 42 artículos en la bodega.", "resultados": []}}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": 1000, "outputTokens": 50}}


def _cuerpo(*resultados):
    mensajes = [{"role": "user", "content": TAREA}]
    for i, r in enumerate(resultados):
        mensajes += [{"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "ejecutar_sql",
                                                        "input": {}}]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                                   "is_error": True, "content": json.dumps(r)}]}]
    return {"model": "x", "max_tokens": 900, "system": "S", "messages": mensajes, "tools": []}


FINAL = {"estado": "respondida", "respuesta": "Hay 42 artículos", "resultados": [], "evidencia": [], "supuestos": [],
         "pregunta_aclaracion": None}


class Agente:
    """Three loop steps: Nova, then a tool error moves the task to Haiku, which abstains, so Sonnet answers."""

    def __init__(self, api, herramientas):
        self.api = api

    def resolver(self, tarea):
        self.api(_cuerpo())
        self.api(_cuerpo(ERROR))
        return SimpleNamespace(estado="respondida", motivo="responder", final=FINAL, pasos=2, tokens_in=3000,
                               tokens_out=150, costo_usd=0.001, errores_herramienta=1)


class Converse:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)

    def __call__(self, req):
        return self.respuestas.pop(0)


def _lineas(api, *, precios_por_modelo=None, ruta="fija", agente=Agente):
    lineas = []
    H.tratar_pregunta(TAREA, ALCANCE, agente_factory=agente, llamar_herramienta=lambda n, a: {"ok": True},
                      definiciones=C.definiciones_semana19(), api_modelo=api,
                      politica=Politica(tarea=Limite(usd=1.0, tokens=1_000_000)), precios=K.precios("5m"),
                      exportar=lineas.append, precios_por_modelo=precios_por_modelo, ruta=ruta)
    return [json.loads(x) for x in lineas]


def _ruteado():
    enrutador = R.Enrutador(Converse(_sql(), _responder("abstenida"), _responder("respondida")),
                            candidatos=tuple(R.Candidato(id=c, llamar_como=c, nova="amazon.nova" in c)
                                             for c in K.RUTEO_CANDIDATOS), reglas=K.RUTEO_REGLAS)
    return _lineas(enrutador, precios_por_modelo=K.PRECIOS_POR_MODELO, ruta="r1")


# --- the locked shape ---------------------------------------------------------------------------------------------

def test_the_route_keys_are_in_week_17s_locked_shape():
    assert {"lab.route.initial", "lab.route.escalated", "lab.route.reason", "lab.route.discarded",
            "gen_ai.response.model"} <= set(E.ATRIBUTOS["chat"])
    assert {"lab.route.escalations", "lab.route.final_model"} <= set(E.ATRIBUTOS["invoke_agent"])


def test_the_route_reason_is_a_fixed_vocabulary_the_router_shares():
    assert E.MOTIVOS_RUTA == (*K.RUTEO_REGLAS["senales"], "sin_presupuesto")
    assert E.validar("chat", "lab.route.reason", "error_herramienta")
    assert not E.validar("chat", "lab.route.reason", "porque sí")
    assert not E.validar("chat", "lab.route.reason", "otra_senal")      # a valid identifier outside the vocabulary
    assert not E.validar("invoke_agent", "lab.route.escalations", -1)
    assert not E.validar("invoke_agent", "lab.route.escalations", 1.5)  # a count of escalations, never a fraction


# --- the spans of a routed query ----------------------------------------------------------------------------------

def test_every_paid_call_has_its_chat_span_with_its_model_and_route():
    chats = [x for x in _ruteado() if x["tipo"] == "chat"]
    assert [x["span"] for x in chats] == [f"chat {NOVA}", f"chat {HAIKU}", f"chat {SONNET}"]
    a = [x["attrs"] for x in chats]
    assert [(x["gen_ai.request.model"], x["gen_ai.response.model"]) for x in a] == [(NOVA, NOVA), (HAIKU, HAIKU),
                                                                                   (SONNET, SONNET)]
    assert all(x["lab.route.initial"] == NOVA for x in a)
    assert [x["lab.route.escalated"] for x in a] == [False, True, True]
    assert [x.get("lab.route.reason") for x in a] == [None, "error_herramienta", "abstencion"]
    assert [x["lab.route.discarded"] for x in a] == [False, True, False]
    assert all(x["omitidos"] == [] for x in chats)


def test_the_agent_span_carries_the_escalations_and_the_last_model():
    (agente,) = [x for x in _ruteado() if x["tipo"] == "invoke_agent"]
    assert agente["omitidos"] == []
    assert agente["attrs"]["gen_ai.request.model"] == NOVA
    assert agente["attrs"]["lab.route.escalations"] == 2
    assert agente["attrs"]["lab.route.final_model"] == SONNET
    assert agente["Ruta"] == "r1"


def test_the_routed_cost_is_the_sum_of_the_calls_at_their_models_prices():
    lineas = _ruteado()
    chats = [x["attrs"]["lab.cost.usd"] for x in lineas if x["tipo"] == "chat"]
    (agente,) = [x for x in lineas if x["tipo"] == "invoke_agent"]
    assert agente["attrs"]["lab.run.cost_usd"] == pytest.approx(sum(chats))
    assert agente["attrs"]["lab.run.tokens.input"] == 3000 and agente["attrs"]["lab.run.tokens.output"] == 150


def test_an_unrouted_query_keeps_week_20s_spans():
    class Uno(Agente):
        def resolver(self, tarea):
            self.api(_cuerpo())
            return SimpleNamespace(estado="respondida", motivo="responder", final=FINAL, pasos=1, tokens_in=1000,
                                   tokens_out=50, costo_usd=0.001, errores_herramienta=0)
    api = lambda c: {"content": [], "stop_reason": "end_turn", "usage": {"input_tokens": 1000, "output_tokens": 50}}  # noqa: E731
    lineas = _lineas(api, agente=Uno)
    (chat,) = [x for x in lineas if x["tipo"] == "chat"]
    assert chat["span"] == f"chat {H.MODELO}"
    assert set(chat["attrs"]) == {"gen_ai.operation.name", "gen_ai.request.model", "lab.step",
                                  "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
                                  "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_creation.input_tokens",
                                  "lab.cost.usd"}
    (agente,) = [x for x in lineas if x["tipo"] == "invoke_agent"]
    assert not any(k.startswith("lab.route.") for k in agente["attrs"])
    assert agente["attrs"]["gen_ai.request.model"] == H.MODELO and agente["Ruta"] == "fija"


# --- EMF ------------------------------------------------------------------------------------------------------------

def test_emf_holds_ten_custom_metrics():
    assert M.metricas_posibles() == 10
    assert M.DIMENSIONES == {"Ruta": ("fija", "r1")}
    assert set(M.POR_RUTA) == {"CostoUSD", "Respondida"}


def test_the_metric_count_follows_the_declared_routes(monkeypatch):
    monkeypatch.setattr(M, "DIMENSIONES", {"Ruta": ("fija", "r1", "r2")})
    assert M.metricas_posibles() == 6 + 2 * 3


def test_the_emf_line_has_one_directive_without_dimensions_and_one_by_route():
    (agente,) = [x for x in _ruteado() if x["tipo"] == "invoke_agent"]
    sin, por_ruta = agente["_aws"]["CloudWatchMetrics"]
    assert sin["Dimensions"] == [[]] and por_ruta["Dimensions"] == [["Ruta"]]
    assert [m["Name"] for m in por_ruta["Metrics"]] == ["CostoUSD", "Respondida"]
    assert {m["Name"] for m in sin["Metrics"]} == set(M.METRICAS) - {"CostoUSD", "Respondida"}
    assert "Modelo" not in agente


def test_an_undeclared_route_is_never_emitted():
    with pytest.raises(ValueError, match="no declarado"):
        M.miembros_emf({}, latencia_ms=1, ruta="r2", ahora_ms=0)
