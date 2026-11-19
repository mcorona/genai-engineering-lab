"""Week 19, activity 8: the judge against the verifier, on a hand-made case whose numbers are computed by hand."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comparar_jueces", S19 / "eval" / "comparar_jueces.py")
J = importlib.util.module_from_spec(spec)
spec.loader.exec_module(J)

BIEN = {"Builtin.Correctness": 1.0, "Builtin.Faithfulness": 1.0, "Builtin.Completeness": 1.0}
MAL = {"Builtin.Correctness": 0.5, "Builtin.Faithfulness": 1.0, "Builtin.Completeness": 0.5}


def caso():
    """Verifier: 6 pass, 4 fail. Judge: agrees on 8; t06 is a false fail, t07 a false pass.
    po = 0.8; pa = pb = 0.6; pe = 0.6*0.6 + 0.4*0.4 = 0.52; kappa = (0.8 - 0.52) / 0.48 = 0.5833."""
    ver = [True] * 6 + [False] * 4
    juez = [True] * 5 + [False, True] + [False] * 3
    return [{"id": f"t{i:02d}", "verificador": v, "puntajes": BIEN if j else MAL,
             "respuesta": "SKU-0009 en arn:aws:iam::123456789012:role/x", "explicacion": "La respuesta coincide."}
            for i, (v, j) in enumerate(zip(ver, juez), 1)]


def test_los_umbrales_estan_fijos_en_el_codigo():
    assert J.CRITERIO == {"Builtin.Correctness": 0.75, "Builtin.Faithfulness": 0.75}


def test_el_caso_hecho_a_mano():
    r = J.comparar(caso(), cuentas=["123456789012"])
    assert r["n"] == 10 and r["acuerdo"] == 0.8 and r["kappa"] == 0.5833
    assert r["matriz"] == {"ambos_aprueban": 5, "ambos_reprueban": 3, "falso_aprobado": 1, "falso_reprobado": 1}
    assert (r["falsos_aprobados"], r["falsos_reprobados"]) == (["t07"], ["t06"])
    assert r["promedios"]["Builtin.Correctness"] == 0.8


def test_un_ejemplo_redactado_por_cada_desacuerdo():
    r = J.comparar(caso(), cuentas=["123456789012"])
    assert set(r["ejemplos"]) == {"falso_aprobado", "falso_reprobado"}
    assert r["ejemplos"]["falso_aprobado"]["id"] == "t07"
    assert "123456789012" not in json.dumps(r["ejemplos"])


def test_veredicto_por_umbral_y_sin_puntaje_aparte():
    assert J.veredicto({"Correctness": 0.75, "Faithfulness": 0.8}) == {"aprobado": True, "fallan": []}
    assert J.veredicto({"Correctness": 1.0, "Faithfulness": 0.5})["fallan"] == ["Builtin.Faithfulness"]
    v = J.veredicto({"Builtin.Correctness": 1.0, "Builtin.Faithfulness": None})
    assert v["aprobado"] is None and v["sin_puntaje"] == ["Builtin.Faithfulness"]
    filas = caso() + [{"id": "t11", "verificador": True, "puntajes": {"Builtin.Correctness": None}}]
    r = J.comparar(filas)
    assert r["n"] == 10 and r["sin_puntaje"] == ["t11"]


def test_kappa_en_los_bordes():
    assert J.kappa([True, False], [True, False]) == 1.0
    assert J.kappa([True, False], [False, True]) == -1.0
    assert J.kappa([True, True], [True, True]) is None
    with pytest.raises(ValueError):
        J.kappa([True], [True, False])
