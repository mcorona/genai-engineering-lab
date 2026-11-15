"""Activity 1: the SDK baseline and the threat matrix. No network, no database and no API."""
import re
import sys
from pathlib import Path

import pytest

S14 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S14 / "linea_base"))
import verificar_sdk  # noqa: E402

OBLIGATORIAS = {
    "A01": "tool poisoning", "A02": "rug pull", "A03": "shadowing", "A04": "artnot", "A05": "confused deputy",
    "A06": "passthrough", "A07": "audience", "A08": "dns rebinding", "A09": "tenant", "A10": "write",
}
REF = re.compile(r"`([\w./-]+\.py)::([\w-]+)`")


def _matriz():
    texto = (S14 / "seguridad" / "amenazas.md").read_text(encoding="utf-8")
    seccion = texto.split("## Matrix", 1)[1].split("\n## ", 1)[0]
    filas = []
    for linea in seccion.splitlines():
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if len(celdas) == 6 and re.fullmatch(r"A\d\d", celdas[0]):
            filas.append(dict(zip(["id", "amenaza", "mitigacion", "pruebas", "actividad", "estado"], celdas)))
    return filas


def test_sdk_linea_base():
    fallas = [(n, d) for n, ok, d in verificar_sdk.comprobaciones() if not ok]
    assert not fallas, fallas


def test_matriz_de_amenazas():
    filas = _matriz()
    ids = {f["id"] for f in filas}
    assert set(OBLIGATORIAS) <= ids, f"faltan {set(OBLIGATORIAS) - ids}"
    assert len(ids) == len(filas), "IDs repetidos"
    for f in filas:
        if f["id"] in OBLIGATORIAS:
            assert OBLIGATORIAS[f["id"]] in f["amenaza"].lower(), (f["id"], f["amenaza"])
        assert len(f["mitigacion"]) > 40, f["id"]
        refs = REF.findall(f["pruebas"])
        assert refs, f"{f['id']} sin prueba referenciada"
        assert all(a.strip().isdigit() and 1 <= int(a) <= 8 for a in f["actividad"].split(",")), f["id"]
        assert f["estado"] in {"planned", "covered"}, f["id"]


@pytest.mark.parametrize("fila", _matriz(), ids=lambda f: f["id"])
def test_cubiertas_existen(fila):
    """A 'covered' row can only cite tests that exist (a pytest function or a category of the suite)."""
    if fila["estado"] != "covered":
        pytest.skip("planned")
    for archivo, nombre in REF.findall(fila["pruebas"]):
        ruta = S14 / archivo
        assert ruta.exists(), archivo
        fuente = ruta.read_text(encoding="utf-8")
        assert re.search(rf"def {re.escape(nombre)}\b|[\"']{re.escape(nombre)}[\"']", fuente), f"{archivo}::{nombre}"
