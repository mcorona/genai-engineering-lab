"""Week 20, activity 4, R0: the local Haiku 4.5 baseline's script (request shape, run cap, budget, report), offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R0 = _cargar("ruteo_r0_local", S20 / "ruteo" / "r0_local.py")


def _respuesta(tin=1000, tout=100):
    return {"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": tin, "output_tokens": tout}}


def test_the_request_goes_without_effort_like_the_deployed_converse_adapter():
    enviados = []
    api = R0.como_el_desplegado(lambda c: enviados.append(c) or _respuesta())
    api({"model": R0.MODELO, "max_tokens": 4000, "messages": [], "output_config": {"effort": "low"}})
    assert enviados == [{"model": R0.MODELO, "max_tokens": 4000, "messages": []}]


def test_the_model_is_haiku_4_5_the_deployed_agents_model():
    construccion = (S20.parent / "semana-19" / "agente" / "construccion.py").read_text(encoding="utf-8")
    assert f'modelo="{R0.MODELO}"' in construccion


def test_the_run_cap_refuses_the_call_that_starts_past_it_and_never_reaches_the_api():
    llamadas = []
    tope = R0.Tope(usd=0.0066, entrada_1m=1.1, salida_1m=5.5)
    api = tope.envolver(lambda c: llamadas.append(c) or _respuesta(tin=1000, tout=1000))   # 0.0066 USD per call
    api({})
    assert tope.gastado == pytest.approx(0.0066)
    with pytest.raises(R0.TopeAlcanzado):
        api({})
    assert len(llamadas) == 1


def test_the_cap_counts_every_call_while_under_it():
    tope = R0.Tope(usd=1.0, entrada_1m=1.1, salida_1m=5.5)
    api = tope.envolver(lambda c: _respuesta(tin=10_000, tout=1_000))
    for _ in range(3):
        api({})
    assert tope.gastado == pytest.approx(3 * (0.011 + 0.0055))
    assert tope.llamadas == 3


def test_the_task_budget_is_the_deployed_ceiling_of_week_20():
    p = R0.politica()
    assert (p.tarea.usd, p.tarea.tokens) == (0.12, 100_000)
    assert p.sesion is None and p.tenant_dia is None


def _fila(i, exito, estado="respondida"):
    return {"id": i, "exito": exito, "estado": estado}


IDS = [f"{t}-{l}" for l in ("es", "en") for t in ("s03", "s06", "r02", "r05", "r12", "c02", "c06", "v01", "a01", "n01")]


def test_the_report_puts_r0_beside_week_17_and_the_deployed_run_per_task():
    r0 = [_fila(i, i not in ("c02-es", "c02-en")) for i in IDS]
    s17 = {i: True for i in IDS}
    desplegada = {i: i not in ("c02-es", "c02-en", "r05-es", "r05-en") for i in IDS}
    inf = R0.comparar(r0, s17=s17, desplegada=desplegada)
    assert inf["exito"] == {"es": "9/10", "en": "9/10", "total": "18/20"}
    assert inf["fallan"] == {"r0": ["c02-en", "c02-es"], "desplegada": ["c02-en", "c02-es", "r05-en", "r05-es"],
                             "en_ambas": ["c02-en", "c02-es"], "solo_r0": [], "solo_desplegada": ["r05-en", "r05-es"]}
    assert inf["por_tarea"]["r05-es"] == {"r0": True, "semana17": True, "desplegada": False}


def test_the_week_10_rule_is_against_week_17s_local_20_of_20():
    r0 = [_fila(i, i not in ("c02-es", "c02-en", "r05-es", "r05-en")) for i in IDS]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada={i: True for i in IDS})
    assert inf["regla_semana10"]["total"]["base"] == 1.0
    assert inf["regla_semana10"]["total"]["regresion"] is True
    perfecto = R0.comparar([_fila(i, True) for i in IDS], s17={i: True for i in IDS}, desplegada={i: True for i in IDS})
    assert perfecto["regresion"] is False


def test_the_deployed_run_is_read_from_its_main_tasks_only():
    detalle = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
    d = R0.desplegada(detalle)
    assert sorted(d) == sorted(IDS)
    assert [i for i, ok in sorted(d.items()) if not ok] == ["c02-en", "c02-es", "r05-en", "r05-es"]


def test_week_17s_baseline_is_its_local_ci_file():
    s17 = R0.semana17()
    assert sorted(s17) == sorted(IDS) and all(s17.values())


def test_a_task_the_cap_stopped_is_not_run_and_counts_as_a_failure(tmp_path):
    r0 = [_fila(i, True) for i in IDS[:-1]] + [{"id": IDS[-1], "exito": False, "estado": "error",
                                                 "motivo": "api: tope de la corrida"}]
    inf = R0.comparar(r0, s17={i: True for i in IDS}, desplegada={i: True for i in IDS})
    assert inf["no_corridas"] == [IDS[-1]]
    assert inf["exito"]["total"] == "19/20"


def test_the_plan_needs_the_key_and_the_database_before_a_paid_run():
    assert R0.faltantes({}, si=True) == ["ANTHROPIC_API_KEY", "PG_ADMIN_DSN"]
    assert R0.faltantes({"PG_ADMIN_DSN": "x"}, si=False) == []
    assert R0.faltantes({}, si=False) == ["PG_ADMIN_DSN"]


def test_the_raw_file_has_ids_and_numbers_only(tmp_path):
    sub = {"filas": [{"id": "s03-es", "corrida": "abc", "estado": "respondida", "motivo": None, "exito": True,
                      "usd": 0.01, "tope_usd": 0.12, "sobre_el_tope": False, "trayectoria_ok": True, "fallan": []}],
           "presupuesto": {"tarea": "s03-es", "estado": "limite_alcanzado"}, "omisiones_del_esquema": {}}
    salida = R0.crudo(sub, tope=R0.Tope(usd=1.5, entrada_1m=1.1, salida_1m=5.5), modo="simulacion", segundos=1.0)
    assert salida["modelo"] == R0.MODELO and salida["modo"] == "simulacion" and salida["tope_usd"] == 1.5
    assert set(salida["filas"][0]) <= R0.CAMPOS_FILA
    assert "respuesta" not in json.dumps(salida)
