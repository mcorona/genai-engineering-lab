"""Week 20, activity 2: the small run's script, its prices and its three-way reconciliation, offline ($0)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S20.parent / "semana-19"))
spec = importlib.util.spec_from_file_location("atribucion_corrida", S20 / "atribucion" / "corrida.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

DETALLE = [json.loads(x) for x in (S20 / "resultados" / "corrida_corregida_detalle.jsonl").read_text().splitlines()]


def test_los_precios_son_los_de_la_lista_de_precios_de_la_actividad_1():
    assert A.precios_por_millon() == {"entrada": 1.1, "salida": 5.5, "cache_lectura": 0.11, "cache_escritura": 1.375}


def test_el_costo_desde_los_spans_reproduce_el_de_la_linea_base():
    precios = A.precios_por_millon()
    for f in DETALLE:
        assert A.costo_desde_spans(f, precios) == pytest.approx(f["costo_usd"], abs=1e-7), f["id"]


def test_las_cuatro_tareas_pasaron_en_la_linea_base_y_caben_en_el_tope():
    por_id = {f["id"]: f for f in DETALLE}
    assert all(por_id[i]["exito"] and por_id[i]["fase"] == "principal" for i in A.TAREAS)
    assert {i: por_id[i]["costo_usd"] for i in A.TAREAS} == pytest.approx(A.COSTO_LINEA_BASE)
    assert {por_id[i]["idioma"] for i in A.TAREAS} == {"es", "en"}
    assert sum(A.COSTO_LINEA_BASE.values()) < A.TOPE_USD / 3
    assert A.TOPE_TOKENS == 100_000 * len(A.TAREAS)


def test_la_consulta_emf_pide_la_suma_de_cada_metrica_con_sus_dimensiones():
    from agente import metricas as M
    q = A.consulta_metricas(1_000.0, 1_500.0)
    assert [x["Label"] for x in q["MetricDataQueries"]] == list(M.METRICAS)
    m = q["MetricDataQueries"][0]["MetricStat"]
    assert m["Stat"] == "Sum" and m["Metric"]["Namespace"] == "LegacyBridge"
    assert m["Metric"]["Dimensions"] == [{"Name": "Modelo", "Value": "claude-haiku-4-5-20251001"},
                                         {"Name": "Ruta", "Value": "fija"}]
    assert m["Period"] >= 500 and m["Period"] % 60 == 0       # one period covers the whole window


def test_la_ventana_se_abre_con_margen():
    filas = [{"inicio": 100.0, "fin": 150.0}, {"inicio": 160.0, "fin": 210.0}, {"estado": "no_corrida"}]
    assert A.ventana(filas) == (100.0 - A.MARGEN_EMF_S, 210.0 + A.MARGEN_EMF_S)


def test_cost_explorer_agrupa_por_componente_un_dia():
    q = A.consulta_cost_explorer("2026-11-24")
    assert q["TimePeriod"] == {"Start": "2026-11-24", "End": "2026-11-25"} and q["Granularity"] == "DAILY"
    assert {"Type": "TAG", "Key": "componente"} in q["GroupBy"]


def test_conciliar_compara_spans_recalculados_con_emf():
    precios = A.precios_por_millon()
    filas = [{"id_tarea": "s03-es", "tokens_entrada": 11794, "tokens_salida": 837, "costo_usd": 0.0175769},
             {"id_tarea": "x", "estado": "no_corrida"}]
    c = A.conciliar(filas, precios, {"CostoUSD": 0.0175769}, None)
    assert c["spans_usd"] == pytest.approx(0.0175769) and c["emf_menos_spans_usd"] == pytest.approx(0)
    assert len(c["tareas"]) == 1 and "cost_explorer" not in c


def test_sin_perfil_de_aplicacion_no_se_manda_nada():
    with pytest.raises(SystemExit, match="perfil de inferencia de aplicación"):
        A.exigir_agente({"MODELO": "us.anthropic.claude-haiku-4-5-20251001-v1:0"})
    A.exigir_agente({"MODELO": "arn:aws:bedrock:us-east-1:111122223333:application-inference-profile/a1b2c3d4e5f6"})
