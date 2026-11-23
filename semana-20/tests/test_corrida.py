"""Week 20, activity 1: the corrected run's caps and its check of the deployed budget, without AWS."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("corrida20", S20 / "linea_base" / "corrida.py")
corrida = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corrida)


@pytest.fixture(scope="module")
def E():
    return corrida._eval_aws()


def test_el_tope_por_tarea_del_script_es_el_techo_que_corre_el_agente(E):
    lim = E.C.limite_de_tarea()
    assert (lim.usd, lim.tokens) == (0.12, 100_000)


def test_el_tope_cuenta_solo_las_corridas_de_esta_carpeta(E, tmp_path):
    (tmp_path / "crudo_eval_descartada_1.json").write_text(json.dumps({"gasto": {"usd": 0.5, "tokens": 300_000}}))
    (tmp_path / "otra.json").write_text(json.dumps({"gasto": {"usd": 9.0, "tokens": 9}}))
    t = corrida.tope(E, tmp_path)
    assert (t.usd, t.gastado_usd, t.gastado_tokens) == (2.50, 0.5, 300_000)
    assert t.cabe_otra()
    t.sumar(1.89, 0)
    assert not t.cabe_otra()   # 2.39 spent plus a task at the 0.12 ceiling is over 2.50


def test_el_plan_cabe_en_el_tope_aunque_todas_las_tareas_llegaran_al_techo(E):
    p = corrida.plan(E, E.tareas_ci(), E.tareas_de_calentamiento())
    assert len(p["tareas"]) == 20 and p["esperado_usd_modelo"] < corrida.TOPE_USD
    assert 22 * p["presupuesto_del_agente"]["tokens"] <= corrida.TOPE_TOKENS


def test_sin_el_techo_desplegado_no_se_manda_nada():
    corrida.exigir_presupuesto({"PRESUPUESTO_TAREA": "techo_semana20"})
    for variables in ({}, {"PRESUPUESTO_TAREA": "semana17"}):
        with pytest.raises(SystemExit):
            corrida.exigir_presupuesto(variables)


def test_una_corrida_previa_se_conserva(tmp_path):
    (tmp_path / "crudo_eval.json").write_text("{}")
    assert corrida.descartar_previa(tmp_path).name == "crudo_eval_descartada_1.json"
    assert corrida.descartar_previa(tmp_path) is None
