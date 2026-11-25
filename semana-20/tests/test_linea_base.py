"""Week 20, activity 1: the baseline checks and the prices reader, without AWS."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]


def _modulo(nombre):
    spec = importlib.util.spec_from_file_location(f"lb_{nombre}", S20 / "linea_base" / f"{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


verificar = _modulo("verificar")
precios = _modulo("precios")


def _fila(id_, fase="principal", costo=0.03, exito=True, estado="respondida", pasos=5, lat=20.0):
    return {"id": id_, "fase": fase, "costo_usd": costo, "exito": exito, "estado": estado, "pasos": pasos,
            "latencia_s": lat, "tokens_entrada": 20000, "tokens_salida": 1000, "tokens_cache_lectura": 0,
            "tokens_cache_escritura": 0}


def test_las_cifras_del_plan_salen_del_archivo_de_la_semana_19():
    calculadas = verificar.cifras(verificar.filas())
    assert verificar.comparar(calculadas)["ok"], verificar.comparar(calculadas)["distintas"]


def test_una_cifra_distinta_hace_fallar_la_comparacion():
    plan = {**verificar.PLAN, "exitos": 10}
    r = verificar.comparar(verificar.cifras(verificar.filas()), plan)
    assert not r["ok"] and r["distintas"] == {"exitos": {"plan": 10, "calculada": 9}}


def test_las_filas_de_calentamiento_cuentan_en_el_costo_pero_no_en_el_exito():
    fs = [_fila("w", fase="calentamiento", lat=50.0, exito=False), _fila("a"),
          _fila("b", costo=None, exito=False, estado="no_corrida", pasos=None)]
    c = verificar.cifras(fs)
    assert (c["con_costo"], c["latencia_max"], c["exitos"], c["tareas"]) == (2, 50.0, 1, 2)


def test_las_fallas_se_agrupan_por_causa():
    fs = [_fila("a", exito=False, estado="limite_alcanzado"), _fila("b", exito=False, estado="no_corrida"),
          _fila("c", exito=False, estado="abstenida"), _fila("d", exito=False), _fila("e")]
    assert verificar.fallas(fs) == {"presupuesto_tarea": ["a"], "tope_del_script": ["b"], "abstenida": ["c"],
                                    "respuesta_incorrecta": ["d"]}


def test_la_compuerta_sigue_abierta_mientras_la_semana_19_diga_regresion(tmp_path):
    md = tmp_path / "eval_aws.md"
    md.write_text("x\n**Regression: yes.**\n", encoding="utf-8")
    assert verificar.compuerta(md, tmp_path / "no.json")["estado"] == "abierta"
    md.write_text("x\n**Regression: no.**\n", encoding="utf-8")
    assert verificar.compuerta(md, tmp_path / "no.json")["estado"] == "cerrada"


def _corrida(tmp_path, regresion, motivos=("responder",)):
    ruta = tmp_path / "crudo_eval.json"
    ruta.write_text(json.dumps({"resumen": {"comparacion": {"regresion": regresion},
                                            "exito": {"total": {"exito": 16, "n": 20}}},
                                "filas": [{"motivo": m} for m in motivos]}), encoding="utf-8")
    return ruta


def test_la_corrida_corregida_decide_la_compuerta(tmp_path):
    md = tmp_path / "eval_aws.md"
    md.write_text("**Regression: yes.**", encoding="utf-8")
    assert verificar.compuerta(md, _corrida(tmp_path, False))["estado"] == "cerrada"
    r = verificar.compuerta(md, _corrida(tmp_path, True, ("responder", "presupuesto_tarea")))
    assert r["estado"] == "aceptada_sin_pasar" and r["decision"]["por"] == "Manuel"
    assert (r["exitos"], r["tareas"], r["cortes_por_presupuesto"]) == (16, 20, 1)


def test_la_compuerta_del_repositorio_refleja_la_corrida_de_la_semana_20():
    r = verificar.compuerta()
    assert r["corrida_corregida"] and (r["exitos"], r["tareas"]) == (16, 20)
    assert r["regresion"] and r["estado"] == "aceptada_sin_pasar" and r["cortes_por_presupuesto"] == 0


def test_precios_de_haiku_y_sus_razones(tmp_path):
    def f(uso, usd):
        return {"modelo": "Claude Haiku 4.5", "uso": f"USE1-MP:{uso}", "precios": [{"usd": usd}]}
    filas = [f("USE1_InputTokenCount-Units", 1.1), f("USE1_OutputTokenCount-Units", 5.5),
             f("USE1_CacheReadInputTokenCount-Units", 0.11), f("USE1_CacheWriteInputTokenCount-Units", 1.375),
             f("USE1_CacheWrite1hInputTokenCount-Units", 2.2), f("USE1_InputTokenCount_Batch-Units", 0.55),
             f("USE1_OutputTokenCount_Batch-Units", 2.75)]
    ruta = tmp_path / "precios.json"
    ruta.write_text(json.dumps({"fecha": "2026-11-23", "precios": filas}), encoding="utf-8")
    r = verificar.precios(ruta)
    assert r["ok"] and r["razones"] == {"cache_lectura/entrada": 0.1, "cache_escritura_5m/entrada": 1.25,
                                        "cache_escritura_1h/entrada": 2.0, "lote_entrada/entrada": 0.5,
                                        "lote_salida/salida": 0.5}
    ruta.write_text(json.dumps({"fecha": "2026-11-23", "precios": filas[:2]}), encoding="utf-8")
    assert not verificar.precios(ruta)["ok"]


def test_sin_archivo_de_precios_no_pasa(tmp_path):
    assert not verificar.precios(tmp_path / "no.json")["ok"]


def _producto(sku, attrs, usd="1.0"):
    return {"product": {"sku": sku, "attributes": attrs},
            "terms": {"OnDemand": {"t": {"priceDimensions": {"d": {"unit": "1M tokens", "pricePerUnit": {"USD": usd},
                                                                    "description": "x"}}}}}}


def test_el_lector_de_precios_elige_las_filas_de_la_semana_y_quita_duplicados():
    fm = [_producto("A", {"model": "Claude Haiku 4.5", "usagetype": "USE1-MP:USE1_InputTokenCount-Units"}),
          _producto("A", {"model": "Claude Haiku 4.5", "usagetype": "USE1-MP:USE1_InputTokenCount-Units"}),
          _producto("B", {"model": "Claude Opus 4.5", "usagetype": "USE1-MP:x"})]
    br = [_producto("C", {"usagetype": "USE1-NovaMicro-input-tokens"}),
          _producto("D", {"usagetype": "USE1-NovaMicro-input-tokens-custom-model"})]
    cw = [_producto("E", {"usagetype": "CW:MetricMonitorUsage"}), _producto("F", {"usagetype": "CW:Otra"})]
    xr = [_producto("G", {"usagetype": "USE1-XRay-TracesStored"})]
    assert sorted(f["sku"] for f in precios.elegir(fm, br, cw, xr)) == ["A", "C", "E", "G"]


def test_nova_2_lite_y_los_dashboards_globales_entran_y_la_dimension_en_cny_no():
    br = [_producto("N2", {"usagetype": "USE1-Nova2.0Lite-input-tokens"}),
          _producto("X", {"usagetype": "USE1-Nova2X0Lite-input-tokens"})]
    gratis = _producto("D0", {"usagetype": "Global-DashboardsUsageHour-Basic"}, usd="0")
    gratis["terms"]["OnDemand"]["t"]["priceDimensions"]["cny"] = {"unit": "Dashboards", "pricePerUnit": {"CNY": "0"}}
    cw = [gratis, _producto("D1", {"usagetype": "DashboardsUsageHour-Basic"}, usd="3.0")]
    filas = precios.elegir([], br, cw, [])
    assert sorted(f["sku"] for f in filas) == ["D0", "D1", "N2"]
    assert [d["usd"] for f in filas if f["sku"] == "D0" for d in f["precios"]] == [0.0]


def test_las_cuotas_salen_por_nombre():
    q = [{"QuotaName": "Cross-region model inference tokens per minute for Amazon Nova Micro", "Value": 8e6,
          "QuotaCode": "L-1"},
         {"QuotaName": "Cross-region model inference requests per minute for Amazon Nova Micro", "Value": 400.0,
          "QuotaCode": "L-2"},
         {"QuotaName": "Minimum number of records per batch inference job for Nova Micro V1", "Value": 100.0,
          "QuotaCode": "L-3"}]
    r = precios.elegir_cuotas(q)
    assert r["candidatos"]["Amazon Nova Micro"] == {"tpm": 8e6, "rpm": 400.0, "codigos": ["L-1", "L-2"]}
    assert r["candidatos"]["Anthropic Claude Haiku 4.5"]["tpm"] is None
    assert r["lote"]["Nova Micro V1"] == {"min_registros": 100.0}


def test_el_lector_de_precios_simula_por_omision(capsys):
    assert precios.main([]) == 0
    assert "Simulation" in capsys.readouterr().out


@pytest.mark.parametrize("archivo", ["precios.json", "linea_base_verificacion.json"])
def test_los_resultados_versionados_no_tienen_la_cuenta(archivo):
    ruta = S20 / "resultados" / archivo
    if not ruta.exists():
        pytest.skip("se genera en la Mac")
    import re
    assert not re.search(r"\b\d{12}\b", ruta.read_text(encoding="utf-8"))
