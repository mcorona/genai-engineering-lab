"""Verdad de referencia de la auditoría (actividad 2): manifiesto, coherencia de etiquetas y recálculo en la base."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

VERDAD = Path(__file__).resolve().parents[1] / "verdad"
_spec = importlib.util.spec_from_file_location("construir_verdad", VERDAD / "construir.py")
construir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(construir)

DICC = json.loads((VERDAD / "diccionario.json").read_text(encoding="utf-8"))
RIESGOS = json.loads((VERDAD / "riesgos.json").read_text(encoding="utf-8"))
ETQ = json.loads((VERDAD / "etiquetas.json").read_text(encoding="utf-8"))
MANIF = json.loads((VERDAD / "manifiesto.json").read_text(encoding="utf-8"))
COLUMNAS = {f"{x['tabla']}.{x['columna']}" for x in DICC}
CATEGORIAS = {"datos_personales", "huerfanos", "duplicados", "nulos_en_clave", "unidades_inconsistentes",
              "reglas_fuera_de_la_base", "instrucciones_inyectadas"}


@pytest.mark.parametrize("archivo", sorted(construir.HASHEADOS))
def test_manifiesto_congela_cada_archivo(archivo):
    assert construir.sha(VERDAD / archivo) == MANIF["sha256"][archivo], f"{archivo} cambió sin regenerar el manifiesto"


def test_conteos_del_manifiesto():
    m = construir.manifiesto({n: (VERDAD / n).read_text(encoding="utf-8") for n in construir.CONGELADOS})
    assert {k: v for k, v in m.items() if k != "sha256"} == {k: v for k, v in MANIF.items() if k != "sha256"}


def test_etiquetas_apuntan_a_columnas_existentes():
    for grupo in ("fk_logicas", "unidades", "datos_personales", "no_personales"):
        faltan = set(ETQ[grupo]) - COLUMNAS
        assert not faltan, f"{grupo}: {faltan}"
    assert set(ETQ["fk_logicas"].values()) <= COLUMNAS
    assert not set(ETQ["datos_personales"]) & set(ETQ["no_personales"])


def test_diccionario_completo():
    for x in DICC:
        assert x["significado"] and x["tipo"], x
        assert (x["original"] is None) == (x["tabla"] in ("artnot", "prvcto", "movinv")), x
        if x["llave_foranea"]:
            assert x["llave_foranea"] in COLUMNAS and x["fuente_llave_foranea"], x
    vistas = [x for x in DICC if x["original"]]
    assert len({x["tabla"] for x in vistas}) == 6 and len(vistas) == 26


def test_cada_categoria_tiene_evidencia():
    por_cat = {}
    for r in RIESGOS["riesgos"]:
        por_cat.setdefault(r["categoria"], []).append(r)
        assert r["evidencia"], r["id"]
        assert r["sql"].lstrip().upper().startswith(("SELECT", "WITH")), r["id"]
    assert set(por_cat) == CATEGORIAS
    assert RIESGOS["reglas_fuera_de_la_base"] and RIESGOS["notas_inyectadas"]


def test_inyecciones_detectadas_son_las_etiquetadas():
    ids = next(r for r in RIESGOS["riesgos"] if r["id"] == "I-ARTNOT")["evidencia"]
    assert ids == sorted(ETQ["inyecciones"], key=int) == [str(n["not_id"]) for n in RIESGOS["notas_inyectadas"]]


@pytest.mark.skipif(not (os.environ.get("PG_DSN") or os.environ.get("PG_ADMIN_DSN")), reason="sin base (PG_DSN)")
def test_recalculada_en_la_base_igual_a_la_congelada():
    nuevos = construir.calcular(os.environ.get("PG_DSN") or os.environ["PG_ADMIN_DSN"])
    for nombre, texto in nuevos.items():
        assert texto == (VERDAD / nombre).read_text(encoding="utf-8"), f"{nombre} difiere de la congelada"
