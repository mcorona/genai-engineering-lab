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
    assert K.quedan(registro) == registro["quedan"] == 2 == len(K.solicitudes("a", "b"))
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
