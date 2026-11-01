"""Actividad 9 ($0): la matriz de decisión es consistente con su evidencia y el documento está al día."""
import json
import subprocess
import sys

import pytest
from conftest import S15

sys.path.insert(0, str(S15 / "eval"))
import matriz as m  # noqa: E402

RES = S15 / "resultados"


def _celdas():
    for c in m.CRITERIOS:
        for o in m.OPCIONES:
            v = m.P[c][o]
            yield from ((c, o, k, x) for k, x in v.items()) if isinstance(v, dict) else [(c, o, None, v)]


def test_cada_celda_tiene_puntaje_estado_y_evidencia():
    n = 0
    for c, o, k, (puntaje, estado, nota, evidencia) in _celdas():
        n += 1
        assert puntaje in range(1, 6) and estado in ("M", "D", "N") and nota, (c, o, k)
        if estado in ("M", "D"):                                   # lo medido o documentado enlaza su evidencia
            assert evidencia, (c, o, k)
        for e in evidencia:
            assert (RES / m.EV[e]).resolve().exists(), (c, o, e)   # y la evidencia existe en el repositorio
    assert n == 5 * (8 + 4 + 3)                                     # 8 criterios fijos + 4 proveedores + 3 plataformas


def test_el_costo_sale_de_lo_medido():
    assert {o: m.P["costo"][o][0] for o in m.OPCIONES} == {o: m.puntaje_costo(o) for o in m.OPCIONES}
    assert m.puntaje_costo("propio") == 5 and m.puntaje_costo("adk") == 2   # $0.0027 el más barato; ADK +70 %


@pytest.mark.parametrize("esc", list(m.ESCENARIOS))
def test_pesos_suman_100_por_escenario(esc):
    e = m.ESCENARIOS[esc]
    assert set(e["pesos"]) == set(m.CRITERIOS) and sum(e["pesos"].values()) == 100
    assert e["proveedor"] in ("anthropic", "openai", "gemini", "multi") and e["nube"] in ("aws", "gcp", "ninguna")


def test_documento_al_dia_con_los_datos():
    texto = (RES / "matriz_decision.md").read_text(encoding="utf-8")
    assert m.renderizar(texto) == texto, "corre: python eval/matriz.py"
    for k in m.BLOQUES:
        assert f"<!-- tabla:{k} -->" in texto


def test_pesos_de_un_cliente(tmp_path):
    cfg = {"proveedor": "multi", "nube": "aws", "pesos": dict.fromkeys(m.CRITERIOS, 10)}
    (tmp_path / "c.json").write_text(json.dumps(cfg))
    r = subprocess.run([sys.executable, str(S15 / "eval" / "matriz.py"), "--pesos", str(tmp_path / "c.json")],
                       capture_output=True, text=True, check=True)
    assert len(r.stdout.strip().splitlines()) == 5
    malo = {**cfg, "pesos": {**cfg["pesos"], "costo": 11}}
    with pytest.raises(AssertionError):
        m.evaluar(malo["pesos"], "multi", "aws")
