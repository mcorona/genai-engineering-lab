"""Week 19, activity 6: the week 17 budget applied to the agent's calls, offline ($0, no model)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente.presupuesto import Precios, Presupuesto  # noqa: E402
from presupuestos.politica import Limite, Politica  # noqa: E402

PRECIOS = Precios(entrada_1m=1.1, salida_1m=5.5)
# The agent runs Haiku 4.5. Its price is in week 7's table (semana-07/prices.json, key anthropic:<this id>).
MODELO = "claude-haiku-4-5-20251001"


def _pol(usd=1.0, tokens=10_000_000):
    return Politica(tarea=Limite(usd=usd, tokens=tokens))


def _respuesta(tin, tout):
    return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": tin, "output_tokens": tout}}


def test_llamada_dentro_de_presupuesto_pasa_y_acumula_gasto():
    llamadas = []

    def api(c):
        llamadas.append(c)
        return _respuesta(1000, 500)

    p = Presupuesto(_pol(), MODELO, PRECIOS)
    res = p.envolver(api)({"messages": [], "max_tokens": 900})
    assert res["stop_reason"] == "end_turn" and len(llamadas) == 1
    assert p.gastado.tokens == 1500 and p.motivo is None
    assert p.gastado.usd == pytest.approx(1000 * 1.1 / 1e6 + 500 * 5.5 / 1e6)


def test_tope_de_tokens_corta_sin_llamar_al_modelo():
    llamadas = []
    p = Presupuesto(_pol(tokens=2000), MODELO, PRECIOS)
    envuelta = p.envolver(lambda c: llamadas.append(c) or _respuesta(1000, 500))
    envuelta({"messages": []})            # fits; uses 1500 of the 2000 tokens
    res = envuelta({"messages": []})      # the next call does not fit
    assert res["content"] == [] and res["stop_reason"] == "max_tokens"
    assert p.motivo == "presupuesto_tokens"
    assert len(llamadas) == 1, "no model call once the budget is out"


def test_tope_de_usd_corta_y_nombra_el_motivo():
    llamadas = []
    p = Presupuesto(_pol(usd=0.0001), MODELO, PRECIOS)
    res = p.envolver(lambda c: llamadas.append(c) or _respuesta(0, 0))({"messages": ["x" * 3000]})
    assert res["stop_reason"] == "max_tokens"
    assert p.motivo == "presupuesto_usd"
    assert llamadas == []


def test_parada_por_presupuesto_no_llama_y_deja_el_motivo_para_la_lambda():
    """The wrapper answers the stop; running the loop itself with it is covered when the agent Lambda is tested."""
    p = Presupuesto(_pol(usd=0.0001), MODELO, PRECIOS)
    envuelta = p.envolver(lambda c: pytest.fail("no debe llamar al modelo"))
    res = envuelta({"messages": ["x" * 3000]})
    assert res["stop_reason"] == "max_tokens" and res["content"] == []
    assert p.motivo in {"presupuesto_usd", "presupuesto_tokens"}
