"""Week 20, activity 3, step 1: the cacheable prefix measured offline ($0)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S20.parent / "semana-19"))


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MED = _cargar("cache_medir", S20 / "cache" / "medir.py")
MEDICION = json.loads((S20 / "resultados" / "cache_medicion.json").read_text(encoding="utf-8"))


# --- step 1: the measurement --------------------------------------------------------------------------------

def test_la_medicion_versionada_es_la_que_da_el_script():
    assert MED.medir() == MEDICION


def test_el_prefijo_fijo_no_alcanza_el_minimo_de_haiku_45_ni_en_la_cota_alta():
    f = MEDICION["prefijo_fijo"]
    assert f["sistema_igual_a_prompt_management_en"] is True
    assert f["herramientas"][-1] == "responder" and "validar_sql" not in f["herramientas"]
    assert max(f["tokens_razon_mediana"], f["tokens_razon_minima"], f["tokens_a_2_7_actividad1"]) < 4096
    assert f["alcanza_el_minimo"] is False


def test_cada_tarea_suma_su_entrada_real_y_el_minimo_llega_en_el_paso_medido():
    for f in MEDICION["filas"]:
        assert sum(f["entrada_por_paso"]) == f["tokens_entrada"] and len(f["entrada_por_paso"]) == f["pasos"]
        cruce = next((k + 1 for k, t in enumerate(f["entrada_por_paso"]) if t >= 4096), None)
        assert cruce == f["paso_que_alcanza_el_minimo"]
    d = MEDICION["paso_que_alcanza_el_minimo"]
    assert sum(d["por_paso"].values()) + d["nunca"] == d["tareas"] == 20


def test_los_tiempos_caben_en_el_ttl_de_5_minutos():
    assert MEDICION["tiempos"]["segundos_por_paso_max"] < 300
