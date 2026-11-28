"""Week 20, activity 4, R1: the task budget with the router (ADR 0015 section 4), offline ($0, no AWS, no model).

Each call is priced at the model that served it, the discarded call of a resend included; max_tokens is what the
rest of the budget buys at the next model's prices; a resend the budget cannot pay for is not sent."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import ruteo as R  # noqa: E402
from agente.presupuesto import Presupuesto, holgura  # noqa: E402
from presupuestos.politica import Gasto, Limite, Politica, decidir  # noqa: E402

NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
P = K.PRECIOS_POR_MODELO


def _uso(tin, tout):
    return {"inputTokens": tin, "outputTokens": tout}


def _herramienta(tin, tout):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "tu", "name": "ejecutar_sql", "input": {}}}]}}, "stopReason": "tool_use",
        "usage": _uso(tin, tout)}


def _responder(estado, tin, tout):
    return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
        "toolUseId": "tu", "name": "responder",
        "input": {"estado": estado, "respuesta": "Hay 42 artículos en la bodega.", "resultados": []}}}]}},
        "stopReason": "tool_use", "usage": _uso(tin, tout)}


class Guion:
    """A fake Converse that answers, in order, the responses of a script; records each request."""

    def __init__(self, *respuestas):
        self.respuestas, self.peticiones = list(respuestas), []

    def __call__(self, req):
        self.peticiones.append(req)
        return self.respuestas.pop(0)


def _router(llamar):
    candidatos = tuple(R.Candidato(id=c, llamar_como=c, nova="amazon.nova" in c) for c in K.RUTEO_CANDIDATOS)
    return R.Enrutador(llamar, candidatos=candidatos, reglas=K.RUTEO_REGLAS)


def _cuerpo(*resultados):
    mensajes = [{"role": "user", "content": "¿Cuántos artículos hay en la bodega principal de la empresa?"}]
    for i, r in enumerate(resultados):
        mensajes += [{"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "ejecutar_sql",
                                                        "input": {}}]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                                   "is_error": not r["ok"], "content": json.dumps(r)}]}]
    return {"model": "x", "max_tokens": 4000, "system": "S", "messages": mensajes, "tools": []}


OK = {"ok": True, "filas": [[1]]}
ERROR = {"ok": False, "error": {"tipo": "sql_invalido", "mensaje": "x"}}
TECHO = Politica(tarea=Limite(usd=0.12, tokens=100_000))


def _presupuesto(politica=TECHO):
    return Presupuesto(politica, "claude-haiku-4-5-20251001", K.precios("5m"), precios_por_modelo=P)


def test_the_adrs_hand_worked_case_through_the_router_and_the_budget():
    guion = Guion(_herramienta(2952, 149), _herramienta(4268, 180), _herramienta(4548, 107),
                  _responder("abstenida", 4733, 275), _responder("respondida", 4733, 275), _responder("respondida", 5133, 492))
    presupuesto = _presupuesto()
    api = presupuesto.envolver(_router(guion))
    api(_cuerpo())
    api(_cuerpo(OK))
    api(_cuerpo(OK, ERROR))                 # error_herramienta: call 3 on Haiku 4.5
    api(_cuerpo(OK, ERROR, OK))             # Haiku abstains: the same request again on Sonnet 4.6
    api(_cuerpo(OK, ERROR, OK, OK))
    assert round(presupuesto.gastado.usd, 7) == 0.0580356
    assert presupuesto.gastado.tokens == 27_845
    assert [x["modelo"] for x in presupuesto.por_llamada] == [NOVA, NOVA, HAIKU, HAIKU, SONNET, SONNET]
    assert [x["descartada"] for x in presupuesto.por_llamada] == [False, False, False, True, False, False]
    assert round(sum(x["usd"] for x in presupuesto.por_llamada), 7) == 0.0580356


def test_max_tokens_is_what_the_rest_of_the_budget_buys_at_the_next_models_prices():
    guion = Guion(_herramienta(1000, 100), _herramienta(1000, 100))
    api = _presupuesto().envolver(_router(guion))
    api(_cuerpo())
    cuerpo = _cuerpo(ERROR)
    api(cuerpo)
    pedido = guion.peticiones[1]["inferenceConfig"]["maxTokens"]
    assert pedido == 4000                     # Haiku: 0.12 USD still buys more than the loop's 4,000
    poca = Politica(tarea=Limite(usd=0.03, tokens=100_000))
    guion = Guion(_herramienta(1000, 100), _herramienta(1000, 100), _herramienta(1000, 100))
    p = _presupuesto(poca)
    api = p.envolver(_router(guion))
    api(_cuerpo())
    api(_cuerpo(ERROR))                       # Haiku
    api(_cuerpo(ERROR, ERROR))                # Sonnet: fewer output tokens for the same dollars
    est = P[SONNET].estimar_entrada(len(json.dumps(_cuerpo(ERROR, ERROR), ensure_ascii=False)) // 3, 0)
    restante = Gasto(usd=0.03 - p.por_llamada[0]["usd"] - p.por_llamada[1]["usd"], tokens=100_000 - 2200)
    esperado = math.floor((restante.usd - est * 3.3 / 1e6) / (16.5 / 1e6))
    assert guion.peticiones[2]["inferenceConfig"]["maxTokens"] == min(4000, esperado) < 4000


def test_a_resend_the_rest_of_the_budget_cannot_pay_at_the_next_model_is_not_sent():
    poca = Politica(tarea=Limite(usd=0.0072, tokens=100_000))   # Haiku's 1,300 minimum output costs 0.00715
    guion = Guion(_responder("abstenida", 1000, 100))
    p = _presupuesto(poca)
    resp = p.envolver(_router(guion))(_cuerpo())
    assert len(guion.peticiones) == 1
    assert resp["content"][0]["input"]["estado"] == "abstenida"
    assert p.por_llamada[0]["ruta"]["motivo"] == "sin_presupuesto"


def test_the_discarded_call_is_paid_and_counted():
    guion = Guion(_responder("abstenida", 1000, 100), _responder("respondida", 1000, 100))
    p = _presupuesto()
    p.envolver(_router(guion))(_cuerpo())
    assert p.gastado.usd == pytest.approx(P[NOVA].usd(1000, 100) + P[HAIKU].usd(1000, 100))
    assert p.gastado.tokens == 2200 and p.llamadas == 2


def test_when_nothing_fits_at_the_models_price_the_task_stops_on_the_budget():
    guion = Guion(_herramienta(1000, 100))
    p = _presupuesto(Politica(tarea=Limite(usd=0.0001, tokens=100_000)))
    resp = p.envolver(_router(guion))(_cuerpo())
    assert guion.peticiones == [] and resp["stop_reason"] == "max_tokens"
    assert p.motivo == "presupuesto_usd"


def test_the_cached_prefix_is_estimated_as_a_read_only_on_the_model_that_wrote_it():
    leido = {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "tu", "name": "ejecutar_sql", "input": {}}}]}}, "stopReason": "tool_use",
        "usage": {"inputTokens": 10, "outputTokens": 10, "cacheReadInputTokens": 0, "cacheWriteInputTokens": 3000}}
    p = _presupuesto()
    api = p.envolver(_router(Guion(leido, _herramienta(10, 10))))
    api(_cuerpo())
    assert p.estimacion_cacheada(NOVA) == 3000 and p.estimacion_cacheada(HAIKU) == 0


@pytest.mark.parametrize("est_in, usd, tokens", [(3000, 0.12, 100_000), (20_000, 0.05, 100_000),
                                                 (3000, 0.012, 100_000), (90_000, 0.12, 95_000), (3000, 0.001, 100_000)])
def test_the_output_room_at_haikus_price_is_week_17s_decision(est_in, usd, tokens):
    d = decidir(TECHO, "claude-haiku-4-5-20251001", est_in, {"tarea": Gasto(usd=usd, tokens=tokens)})
    sal, dim = holgura(TECHO, P[HAIKU], est_in, Gasto(usd=usd, tokens=tokens))
    assert sal == d.max_tokens
    assert (dim is None) == (d.accion == "allow")
    if d.accion == "stop":
        assert dim == d.motivo


def test_the_unrouted_budget_is_unchanged():
    p = Presupuesto(TECHO, "claude-haiku-4-5-20251001", K.precios("5m"))
    llamadas = []
    api = p.envolver(lambda c: llamadas.append(c) or {"content": [], "stop_reason": "end_turn",
                                                      "usage": {"input_tokens": 1000, "output_tokens": 100}})
    api(_cuerpo())
    assert p.gastado.usd == pytest.approx(K.precios("5m").usd(1000, 100))
    assert "modelo" not in p.por_llamada[0]
