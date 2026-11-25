"""Activity 9, step 4.7: the Cost Explorer script, offline (a fake client; no AWS call)."""
import importlib.util
import json
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("costo_actividad9", S19 / "seguridad" / "costo_actividad9.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def _resp(grupos):
    return {"ResultsByTime": [{"TimePeriod": {"Start": dia}, "Groups": [
        {"Keys": claves, "Metrics": {"UnblendedCost": {"Amount": str(usd)}}} for claves, usd in g]}
        for dia, g in grupos.items()]}


A = _resp({"2026-11-21": [(["Amazon Relational Database Service"], 0.10)],
           "2026-11-22": [(["Amazon Relational Database Service"], 0.05), (["AWS Key Management Service"], 0.02)]})
B = _resp({"2026-11-21": [(["Amazon Bedrock", "Usage"], 0.20), (["Amazon Bedrock", "Credit"], -0.20),
                          (["Amazon Relational Database Service", "Usage"], 0.10)],
           "2026-11-22": [(["Claude Haiku (Amazon Bedrock Edition)", "Usage"], 0.30),
                          (["Amazon Relational Database Service", "Usage"], 0.05),
                          (["Amazon Relational Database Service", "Credit"], -0.15)]})


class Falso:
    def __init__(self):
        self.solicitudes = []

    def get_cost_and_usage(self, **kw):
        self.solicitudes.append(kw)
        return A if "Filter" in kw else B


def test_las_dos_solicitudes_cubren_los_dias_utc_de_la_corrida():
    s = C.solicitudes()
    assert set(s) == {"A", "B"}
    for q in s.values():
        assert q["TimePeriod"] == {"Start": "2026-11-21", "End": "2026-11-23"}
        assert q["Granularity"] == "DAILY" and q["Metrics"] == ["UnblendedCost"]
    assert s["A"]["Filter"] == {"Tags": {"Key": "proyecto", "Values": ["semana19"]}}
    assert "Filter" not in s["B"]
    assert [g["Key"] for g in s["B"]["GroupBy"]] == ["SERVICE", "RECORD_TYPE"]


def test_resumen_separa_uso_y_creditos():
    r = C.resumen(A, B)
    assert r["etiquetado_proyecto_usd"] == pytest.approx(0.17)
    assert r["uso_total_de_la_cuenta_usd"] == pytest.approx(0.65)
    assert r["creditos_usd"] == pytest.approx(-0.35)
    assert r["neto_usd"] == pytest.approx(0.30)
    assert list(r["uso_por_servicio_usd"])[0] == "Claude Haiku (Amazon Bedrock Edition)"
    assert r["dentro_de_la_cota"] and r["dentro_del_tope"]


def test_registra_cada_llamada_antes_y_no_pasa_de_dos(tmp_path):
    reg = tmp_path / "cost_explorer.json"
    f = Falso()
    C.correr(f, reg)
    assert len(f.solicitudes) == 2
    assert [x["consulta"] for x in json.loads(reg.read_text())] == ["A", "B"]
    with pytest.raises(SystemExit):
        C.correr(Falso(), reg)


def test_simulacion_no_crea_cliente(capsys):
    assert C.main([]) == 0
    assert "Simulation" in capsys.readouterr().out
