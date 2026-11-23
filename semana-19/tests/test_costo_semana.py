"""Week 19, activity 10, step 5: the week's Cost Explorer script, offline (a fake client)."""
import importlib.util
import json
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("costo_semana", S19 / "costos" / "costo_semana.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

RESP = {"ResultsByTime": [{"TimePeriod": {"Start": "2026-11-13"}, "Estimated": True, "Groups": [
    {"Keys": ["Amazon Bedrock", "Usage"], "Metrics": {"UnblendedCost": {"Amount": "3.5"}}},
    {"Keys": ["Amazon Relational Database Service", "Usage"], "Metrics": {"UnblendedCost": {"Amount": "1.25"}}},
    {"Keys": ["Amazon Bedrock", "Credit"], "Metrics": {"UnblendedCost": {"Amount": "-3.5"}}},
    {"Keys": ["Amazon Relational Database Service", "Credit"], "Metrics": {"UnblendedCost": {"Amount": "-1.25"}}}]}]}


class Falso:
    def __init__(self):
        self.n = 0

    def get_cost_and_usage(self, **kw):
        self.n += 1
        assert kw == C.solicitud()
        return RESP


def test_la_solicitud_cubre_la_semana_por_servicio_y_tipo_sin_filtro_de_etiqueta():
    s = C.solicitud()
    assert s["TimePeriod"] == {"Start": "2026-11-13", "End": "2026-11-24"}
    assert s["Granularity"] == "MONTHLY" and "Filter" not in s
    assert [g["Key"] for g in s["GroupBy"]] == ["SERVICE", "RECORD_TYPE"]


def test_bruto_creditos_y_neto():
    r = C.resumen(RESP)
    assert r["bruto_usd"] == pytest.approx(4.75)
    assert r["otros_tipos_usd"] == {"Credit": -4.75}
    assert r["neto_usd"] == pytest.approx(0.0)
    assert list(r["uso_por_servicio_usd"])[0] == "Amazon Bedrock"
    assert r["estimado"] == [True]


def test_una_sola_llamada_registrada_antes(tmp_path):
    reg = tmp_path / "llamadas.json"
    f = Falso()
    C.correr(f, reg)
    assert f.n == 1 and len(json.loads(reg.read_text())) == 1
    with pytest.raises(SystemExit):
        C.correr(Falso(), reg)


def test_simulacion_no_llama(capsys):
    assert C.main([]) == 0
    assert "Simulación" in capsys.readouterr().out
