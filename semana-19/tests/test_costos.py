"""Week 19, activity 2: offline tests of the cost model ($0, no AWS, no model)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
COSTOS = S19 / "costos"


def cargar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    spec.loader.exec_module(m)
    return m


modelo = cargar(COSTOS / "modelo.py", "modelo_s19")
PRECIOS = json.loads((COSTOS / "precios.json").read_text(encoding="utf-8"))["precios"]


def correr(**kw):
    return modelo.modelo(modelo.Parametros(**kw))


def test_la_suma_de_partidas_da_el_total():
    r = correr(perfil="lab", consultas_dia=100, horas_dia=8)
    fijas_h = sum(l["costo_usd"] for l in r["fijas_por_hora"] if l["costo_usd"] is not None)
    fijas_m = sum(l["costo_usd"] for l in r["fijas_por_mes"] if l["costo_usd"] is not None)
    cons = sum(l["costo_usd"] for l in r["por_consulta"] if l["costo_usd"] is not None)
    assert r["costo_por_hora_usd"] == pytest.approx(fijas_h)
    assert r["costo_por_consulta_usd"] == pytest.approx(cons)
    assert r["total_mes_usd"] == pytest.approx(fijas_m + fijas_h * 30 * 8 + cons * r["consultas_mes"])


def test_cambiar_un_precio_cambia_el_resultado_de_forma_predecible(monkeypatch):
    base = correr(perfil="lab", consultas_dia=0, horas_dia=24)
    original = modelo.cargar_precios

    def con_rds_doble():
        p = json.loads(json.dumps(original()))
        p["rds_t4g_micro_hora"]["valor"] = p["rds_t4g_micro_hora"]["valor"] * 2
        return p

    monkeypatch.setattr(modelo, "cargar_precios", con_rds_doble)
    doble = correr(perfil="lab", consultas_dia=0, horas_dia=24)
    # Only the RDS instance changes: 0.016 USD per hour, 24 h per day, 30 days.
    assert doble["total_mes_usd"] - base["total_mes_usd"] == pytest.approx(0.016 * 24 * 30)


@pytest.mark.parametrize("consultas", [0, 1, 50, 500])
def test_prod_nunca_cuesta_menos_que_lab(consultas):
    lab = correr(perfil="lab", consultas_dia=consultas, horas_dia=8)
    prod = correr(perfil="prod", consultas_dia=consultas, horas_dia=8)
    assert prod["total_mes_usd"] >= lab["total_mes_usd"]


def test_cero_consultas_es_solo_el_costo_fijo():
    r = correr(perfil="lab", consultas_dia=0, horas_dia=8)
    assert r["consultas_mes"] == 0
    assert r["total_mes_usd"] == pytest.approx(r["costo_fijo_mes_usd"])


def test_creditos_no_dejan_numeros_negativos():
    r = correr(perfil="lab", consultas_dia=10, horas_dia=1, creditos_usd=10_000.0)
    assert r["total_mes_neto_usd"] == 0.0
    assert r["creditos_aplicados_usd"] <= r["total_mes_usd"]


def test_partidas_n_no_suman_y_marcan_parcial():
    lab = correr(perfil="lab", consultas_dia=10, horas_dia=8, version="v1")
    prod = correr(perfil="prod", consultas_dia=10, horas_dia=8, version="v1")
    # v1, lab: everything measured. Prod: only RDS Multi-AZ stays N, and it is not added to the total.
    assert lab["parcial"] is False and lab["partidas_no_medidas"] == []
    assert prod["parcial"] is True
    assert prod["partidas_no_medidas"] == ["RDS Multi-AZ, additional instance"]
    # v2 lists ApplyGuardrail as N (price and units not measured), outside the total.
    v2 = correr(perfil="lab", consultas_dia=10, horas_dia=8)
    assert v2["parcial"] is True and v2["partidas_no_medidas"] == ["ApplyGuardrail, text units"]
    assert all(l["costo_usd"] is None for g in ("fijas_por_hora", "fijas_por_mes", "por_consulta") for l in prod[g] if l["marca"] == "N")


def test_todo_precio_tiene_fuente_y_marca_valida():
    for clave, p in PRECIOS.items():
        assert p.get("fuente"), f"{clave} has no source"
        assert p["marca"] in {"M", "D", "N"}, f"{clave} has an invalid mark"
        assert p.get("fecha"), f"{clave} has no date"
        if p["valor"] is None:
            assert p["marca"] == "N", f"{clave} has no value, so it must be N"


def test_el_modelo_solo_usa_precios_con_fuente():
    usados = {l["precio_clave"] for g in ("fijas_por_hora", "fijas_por_mes", "por_consulta")
              for l in correr(perfil="prod", consultas_dia=5, horas_dia=8)[g]}
    assert usados <= set(PRECIOS), "the model uses a price key that does not exist"


def test_percentiles_en_orden():
    p50 = modelo.tokens_s13("tokens_in", "p50")
    p95 = modelo.tokens_s13("tokens_in", "p95")
    mx = modelo.tokens_s13("tokens_in", "max")
    assert 0 < p50 <= p95 <= mx


def test_perfiles_conocidos_y_error_si_no_existe():
    assert set(modelo.PERFILES) == {"lab", "prod"}
    with pytest.raises(ValueError):
        correr(perfil="qa")


def test_estimacion_base_de_la_actividad_3_es_kms_mas_endpoints_mas_presupuesto():
    lab = modelo.estimacion_base_hora("lab")
    assert lab["parcial"] is False
    assert lab["por_hora_usd"] == pytest.approx(2 / 730 + 2 * 0.01)
    presupuesto = [l for l in lab["lineas"] if l["partida"].startswith("AWS Budgets")][0]
    assert presupuesto["costo_usd"] == 0.0


def test_v1_se_conserva_y_v2_usa_los_tokens_del_agente_desplegado():
    """Activity 8, step 4: v1 (p95 of week 13) is kept as it was; v2 takes the mean of the deployed agent's 57 tasks,
    the same tasks Cost Explorer billed, so its model cost per query equals the spans' mean."""
    v1 = correr(perfil="lab", version="v1")
    assert round(v1["costo_por_consulta_usd"], 8) == 0.07989162 and v1["parametros"]["percentil_tokens"] == "p95"
    v2 = correr(perfil="lab")
    assert v2["parametros"]["version"] == "v2" and v2["parametros"]["percentil_tokens"] == "media"
    filas = modelo.filas_desplegado()
    assert len(filas) == 57
    media = sum(f["costo_usd"] for f in filas) / len(filas)
    haiku = sum(l["costo_usd"] for l in v2["por_consulta"] if l["partida"].startswith("Haiku"))
    assert haiku == pytest.approx(media, rel=1e-6)
    assert v2["costo_por_hora_usd"] == v1["costo_por_hora_usd"]   # the per-hour part did not change
    with pytest.raises(ValueError):
        correr(version="v4")


def test_tokens_del_desplegado_por_estadistico(tmp_path):
    (tmp_path / "crudo_eval.json").write_text(json.dumps({"calentamiento": [{"tokens_entrada": 100, "tokens_salida": 10}],
        "filas": [{"tokens_entrada": 300, "tokens_salida": 30}, {"estado": "no_corrida"}]}), encoding="utf-8")
    (tmp_path / "aprobacion_e2e.json").write_text(json.dumps({"tareas": [{"tokens_entrada": 200, "tokens_salida": 20}]}),
                                                  encoding="utf-8")
    assert modelo.tokens_desplegado("tokens_in", "media", tmp_path) == 200
    assert modelo.tokens_desplegado("tokens_out", "max", tmp_path) == 30
    assert modelo.tokens_desplegado("tokens_in", "p50", tmp_path) == 200
