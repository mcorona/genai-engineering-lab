"""Week 19, activity 8, step 4: the Cost Explorer requests and the split of the charges, offline."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("costo_real", S19 / "eval" / "costo_real.py")
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)


def test_la_ventana_cubre_los_dias_utc_de_la_corrida():
    import datetime as dt
    utc = lambda *x: dt.datetime(*x, tzinfo=dt.timezone.utc).timestamp()  # noqa: E731
    # 23:50 to 00:20 UTC: two days, End is exclusive.
    assert K.dias_de(utc(2026, 11, 19, 23, 50), utc(2026, 11, 20, 0, 20)) == ("2026-11-19", "2026-11-21")
    assert K.dias_de(utc(2026, 11, 19, 16, 0), utc(2026, 11, 19, 17, 0)) == ("2026-11-19", "2026-11-20")
    crudo = {"calentamiento": [{"inicio": 100, "fin": 140}], "filas": [{"inicio": 150, "fin": 400}, {"estado": "no_corrida"}]}
    assert K.ventana(crudo, [{"inicio": 500, "fin": 900}]) == (100, 900)


def test_las_dos_solicitudes_pasan_la_validacion_de_botocore():
    import botocore.session
    from botocore.validate import ParamValidator
    op = botocore.session.get_session().get_service_model("ce").operation_model("GetCostAndUsage")
    a, b = K.solicitudes("2026-11-19", "2026-11-21")
    for p in (a, b):
        r = ParamValidator().validate(p, op.input_shape)
        assert not r.has_errors(), r.generate_report()
    assert a["Filter"]["Tags"] == {"Key": "proyecto", "Values": ["semana19"], "MatchOptions": ["EQUALS"]}
    assert [g["Key"] for g in b["GroupBy"]] == ["SERVICE", "RECORD_TYPE"] and "Filter" not in b


def test_el_registro_limita_las_llamadas_a_tres():
    registro = json.loads((S19 / "resultados" / "eval_aws" / "cost_explorer.json").read_text(encoding="utf-8"))
    assert len(registro["llamadas"]) <= 3 and K.quedan(registro) == registro["quedan"]
    assert [l["operacion"] for l in registro["llamadas"]] == ["ListCostAllocationTags", "GetCostAndUsage", "GetCostAndUsage"]
    assert K.quedan(registro) < len(K.solicitudes("a", "b"))   # no call is left: --si refuses
    assert K.quedan({"llamadas": [{}, {}]}) == 1


def respuesta_b():
    def g(servicio, tipo, usd):
        return {"Keys": [servicio, tipo], "Metrics": {"UnblendedCost": {"Amount": str(usd), "Unit": "USD"}}}
    return {"ResultsByTime": [
        {"TimePeriod": {"Start": "2026-11-19", "End": "2026-11-20"}, "Estimated": True, "Groups": [
            g("Amazon Virtual Private Cloud", "Usage", 0.72), g("Amazon Relational Database Service", "Usage", 0.46),
            g("Claude Haiku 4.5 (Amazon Bedrock Edition)", "Usage", 0.60), g("Amazon Bedrock", "Usage", 0.10),
            g("AWS Lambda", "Usage", 0.02), g("Amazon Virtual Private Cloud", "Credit", -0.72),
            g("Claude Haiku 4.5 (Amazon Bedrock Edition)", "Credit", -0.60)]}]}


def test_el_desglose_separa_fijo_por_consulta_y_creditos():
    b = K.por_servicio(respuesta_b(), con_tipo=True)
    assert b["estimado"] is True
    d = K.desglose(b, tareas=24)
    assert d["uso_fijo_usd"] == 1.18 and d["uso_por_consulta_usd"] == 0.72 and d["creditos_usd"] == -1.32
    assert d["neto_usd"] == 0.58 and d["partida_dominante"] == "Amazon Virtual Private Cloud"
    assert d["costo_por_consulta_usd_cota"] == round(0.72 / 24, 6)
    assert list(d["por_servicio_usd"])[:2] == ["Amazon Virtual Private Cloud", "Claude Haiku 4.5 (Amazon Bedrock Edition)"]


def test_por_etiqueta_agrupa_solo_por_servicio():
    r = {"ResultsByTime": [{"TimePeriod": {"Start": "2026-11-19"}, "Estimated": False, "Groups": [
        {"Keys": ["Amazon Relational Database Service"], "Metrics": {"UnblendedCost": {"Amount": "0.46"}}}]}]}
    assert K.por_servicio(r, con_tipo=False) == {
        "dias": {"2026-11-19": {"Amazon Relational Database Service": {"Todo": 0.46}}}, "estimado": False}


def test_el_periodo_se_extiende_hasta_el_teardown_pero_no_corta_la_corrida():
    import pytest
    assert K.periodo("2026-11-19", "2026-11-20", None) == ("2026-11-19", "2026-11-20")
    assert K.periodo("2026-11-19", "2026-11-20", "2026-11-21") == ("2026-11-19", "2026-11-21")
    with pytest.raises(ValueError):
        K.periodo("2026-11-19", "2026-11-20", "2026-11-19")
    with pytest.raises(ValueError):
        K.periodo("2026-11-19", "2026-11-20", "mañana")


def test_las_tareas_cuentan_todas_las_corridas_del_periodo_y_la_aprobacion(tmp_path):
    def crudo(nombre, calentamiento, filas):
        (tmp_path / nombre).write_text(json.dumps({"calentamiento": calentamiento, "filas": filas}), encoding="utf-8")
    hecha, abortada = {"estado": "respondida"}, {"estado": "no_corrida"}
    crudo("crudo_eval.json", [hecha, hecha], [hecha] * 17 + [abortada] * 3)
    crudo("crudo_eval_descartada_1.json", [hecha], [hecha] * 20)
    crudo("crudo_eval_descartada_2.json", [hecha], [hecha] * 12 + [abortada] * 8)
    (tmp_path / "aprobacion_e2e.json").write_text(json.dumps({"tareas": [{}, {}]}), encoding="utf-8")
    t = K.tareas_de_las_corridas(tmp_path)
    assert t["por_archivo"] == {"crudo_eval.json": 19, "crudo_eval_descartada_1.json": 21,
                                "crudo_eval_descartada_2.json": 13, "aprobacion_e2e.json": 2}
    assert t["total"] == 55


def test_las_tareas_del_repo_incluyen_las_corridas_descartadas():
    t = K.tareas_de_las_corridas(K.CARPETA)
    assert {"crudo_eval.json", "crudo_eval_descartada_1.json", "crudo_eval_descartada_2.json"} <= set(t["por_archivo"])
    assert t["total"] > t["por_archivo"]["crudo_eval.json"]


def test_las_horas_de_la_pila_son_las_que_cae_dentro_del_periodo():
    import datetime as dt
    utc = lambda *x: dt.datetime(*x, tzinfo=dt.timezone.utc)  # noqa: E731
    resumenes = [{"StackName": "semana19-base", "CreationTime": utc(2026, 11, 16, 4, 56), "DeletionTime": utc(2026, 11, 20, 2, 0)},
                 {"StackName": "semana19-datos", "CreationTime": utc(2026, 11, 16, 4, 57), "DeletionTime": utc(2026, 11, 20, 1, 55)},
                 {"StackName": "semana19-base", "CreationTime": utc(2026, 11, 10, 0, 0), "DeletionTime": utc(2026, 11, 11, 0, 0)}]
    assert K.horas_de_pila(resumenes, "semana19-base", "2026-11-19", "2026-11-21") == 26.0
    assert K.horas_de_pila(resumenes, "semana19-base", "2026-11-19", "2026-11-20") == 24.0
    sigue = [{"StackName": "semana19-base", "CreationTime": utc(2026, 11, 19, 12, 0)}]
    assert K.horas_de_pila(sigue, "semana19-base", "2026-11-19", "2026-11-20") == 12.0


def test_la_comparacion_marca_el_error_fuera_de_veinte_por_ciento():
    d = {"costo_por_consulta_usd_cota": 0.05, "uso_fijo_usd": 1.3}
    pred = {"lab": {"costo_por_consulta_usd": 0.08, "costo_por_hora_usd": 0.05},
            "prod": {"costo_por_consulta_usd": 0.05, "costo_por_hora_usd": 0.093}}
    c = K.comparar(d, 26.0, pred)
    assert c["filas"]["lab.por_consulta"] == {"predicho_usd": 0.08, "real_usd": 0.05, "error": -0.375, "fuera_de_umbral": True}
    assert c["filas"]["lab.por_hora"]["real_usd"] == 0.05 and c["filas"]["lab.por_hora"]["error"] == 0.0
    assert c["filas"]["prod.por_consulta"]["fuera_de_umbral"] is False and c["corregir_modelo"] is True
    assert K.comparar(d, 0.0, pred)["filas"]["lab.por_hora"]["real_usd"] is None
    # prod was never deployed: its per-hour row does not apply and never asks for a correction.
    ph = c["filas"]["prod.por_hora"]
    assert ph["real_usd"] is None and ph["error"] is None and ph["fuera_de_umbral"] is False and "no_aplica" in ph
    # With the model part known, both errors are reported and either one beyond 20% flags the row.
    c = K.comparar(d | {"costo_por_consulta_modelo_usd": 0.045}, 26.0, {"lab": pred["prod"]})
    f = c["filas"]["lab.por_consulta"]
    assert (f["error"], f["error_modelo"], f["fuera_de_umbral"]) == (0.0, -0.1, False)


def test_la_prediccion_es_la_del_modelo_de_la_actividad_2():
    p = K.prediccion_del_modelo()
    assert round(p["lab"]["costo_por_consulta_usd"], 8) == 0.07989162 and round(p["lab"]["costo_por_hora_usd"], 6) == 0.04189
    assert round(p["prod"]["costo_por_hora_usd"], 6) == 0.09326


def test_las_corridas_de_otra_actividad_y_lo_ajeno_no_se_cargan_a_las_tareas():
    def g(servicio, tipo, usd):
        return {"Keys": [servicio, tipo], "Metrics": {"UnblendedCost": {"Amount": str(usd), "Unit": "USD"}}}
    r = {"ResultsByTime": [{"TimePeriod": {"Start": "2026-11-19"}, "Estimated": True, "Groups": [
        g(K.MODELO, "Usage", 1.0), g("Amazon Bedrock", "Usage", 0.2), g("AWS Cost Explorer", "Usage", 0.02),
        g("Amazon Bedrock AgentCore", "Usage", 0.001), g("Amazon Virtual Private Cloud", "Usage", 0.7)]}]}
    d = K.desglose(K.por_servicio(r, con_tipo=True), 10, {"crudo_directo.json": 0.25, "crudo_gateway.json": 0.15}, 0.6)
    assert d["modelo_atribuible_usd"] == 0.6 and d["costo_por_consulta_modelo_usd"] == 0.06
    assert d["uso_por_consulta_usd"] == 0.8 and d["costo_por_consulta_usd_cota"] == 0.08
    assert d["fuera_usd"] == {"AWS Cost Explorer": 0.02, "Amazon Bedrock AgentCore": 0.001}
    assert d["conciliacion"] == {"spans_usd": 0.6, "cost_explorer_usd": 0.6, "diferencia_usd": 0.0}
    assert d["neto_usd"] == 1.921


def test_el_costo_real_del_repo_concilia_con_los_spans_y_compara_las_dos_versiones():
    r = json.loads(K.SALIDA.read_text(encoding="utf-8"))
    d = r["desglose"]
    assert set(d["otras_corridas_modelo_usd"]) == {"crudo_directo.json", "crudo_gateway.json"}
    assert abs(d["conciliacion"]["diferencia_usd"]) < 0.01
    assert d["tareas"] == r["tareas"]["total"] == K.tareas_de_las_corridas(K.CARPETA)["total"] == 57
    assert set(r["comparacion"]) == {"v1", "v2"}
    assert r["comparacion"]["v1"]["filas"]["lab.por_consulta"]["error_modelo"] < -0.2      # why v2 exists
    assert abs(r["comparacion"]["v2"]["filas"]["lab.por_consulta"]["error_modelo"]) <= 0.2


def test_el_informe_se_genera_solo_desde_el_json():
    r = json.loads(K.SALIDA.read_text(encoding="utf-8"))
    md = K.informe_md(r)
    assert md.rstrip("\n") == (S19 / "resultados" / "costo_real.md").read_text(encoding="utf-8").rstrip("\n")
    assert "Reconciliation" in md and "| v2 | lab.por_consulta |" in md and "n/a" in md
