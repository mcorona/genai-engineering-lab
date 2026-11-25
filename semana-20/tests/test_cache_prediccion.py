"""Week 20, activity 3, step 3: the caching prediction (quote v3), versioned before the run, and the comparison that
reads it ($0)."""
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

from costos import modelo as M  # noqa: E402

PRED = _cargar("cache_prediccion", S20 / "cache" / "prediccion.py")
CORR = _cargar("cache_corrida_pred", S20 / "cache" / "corrida.py")
MEDICION = json.loads((S20 / "resultados" / "cache_medicion.json").read_text(encoding="utf-8"))
PREDICCION = json.loads((S20 / "resultados" / "cache_prediccion.json").read_text(encoding="utf-8"))
PRECIOS = M.cargar_precios()


@pytest.fixture(scope="module")
def LB():
    return CORR.linea_base()


@pytest.mark.parametrize("modo", ["sistema", "historial+sistema"])
def test_el_punto_del_sistema_no_cachea_nada_en_haiku_45(modo):
    """The system point is sent (the adapter puts it) and caches nothing: its prefix is under the minimum."""
    for f in MEDICION["filas"]:
        con = M.cache_por_paso(f["entrada_por_paso"], modo=modo, prefijo_fijo=f["prefijo_fijo_tokens"])
        sin_sistema = M.cache_por_paso(f["entrada_por_paso"], modo=modo.replace("+sistema", "") if "+" in modo else "off")
        assert con == sin_sistema


# --- step 3: the prediction, versioned before the run --------------------------------------------------------

def test_la_prediccion_versionada_no_cambia():
    """Committed before the live run; the report compares against it and never rewrites it."""
    assert PRED.predecir(MEDICION) == PREDICCION


def test_sin_cache_el_modelo_reproduce_la_corrida_corregida():
    lb = PREDICCION["linea_base"]
    assert lb["modelo_sin_cache"] == lb["corrida_corregida_real"]
    assert lb["corrida_corregida_real"]["mediana"] == pytest.approx(0.034, abs=0.0005)


def test_los_escenarios_estan_en_orden_y_el_peor_cuesta_mas_que_no_cachear():
    e = PREDICCION["escenarios"]
    base = PREDICCION["linea_base"]["modelo_sin_cache"]["total"]
    assert e["optimista"]["total"] < e["pesimista"]["total"] < base < e["peor"]["total"]
    assert 0 < PREDICCION["equilibrio_p_acierto"] < e["pesimista"]["p_acierto"]
    assert PREDICCION["ttl_1h_optimista"]["total"] > e["optimista"]["total"]


def test_cache_por_paso_caso_a_mano():
    """Steps of 3,000 / 5,000 / 6,000 tokens, hits always: step 1 uncached; step 2 writes 5,000 (the step before did
    not write); step 3 reads 5,000 and writes 1,000. USD with 100 output tokens:
    (3,000x1.1 + 5,000x0.11 + 6,000x1.375 + 100x5.5) / 1e6 = (3,300 + 550 + 8,250 + 550) / 1e6 = 0.01265."""
    pasos = M.cache_por_paso([3000, 5000, 6000])
    assert pasos == [{"sin_cache": 3000, "lectura": 0.0, "escritura": 0.0},
                     {"sin_cache": 0.0, "lectura": 0.0, "escritura": 5000.0},
                     {"sin_cache": 0.0, "lectura": 5000.0, "escritura": 1000.0}]
    assert M.costo_cache_usd(pasos, 100, PRECIOS) == pytest.approx(0.01265, abs=1e-12)
    fallo = M.cache_por_paso([3000, 5000, 6000], p_acierto=0.0)
    assert fallo[2] == {"sin_cache": 0.0, "lectura": 0.0, "escritura": 6000.0}
    assert M.cache_por_paso([3000, 4000]) == [{"sin_cache": 3000, "lectura": 0.0, "escritura": 0.0},
                                              {"sin_cache": 4000, "lectura": 0.0, "escritura": 0.0}]


def test_la_cotizacion_v3_usa_la_prediccion_y_sus_precios_medidos():
    for clave, valor in (("haiku45_cache_lectura_1m", 0.11), ("haiku45_cache_escritura_5m_1m", 1.375),
                         ("haiku45_cache_escritura_1h_1m", 2.2)):
        assert PRECIOS[clave]["valor"] == valor and PRECIOS[clave]["marca"] == "M" and "SKU" in PRECIOS[clave]["fuente"]
    v3 = M.modelo(M.Parametros(version="v3"))
    modelo_v3 = sum(l["costo_usd"] for l in v3["por_consulta"] if l["precio_clave"].startswith("haiku45"))
    assert modelo_v3 == pytest.approx(PREDICCION["v3_por_consulta"]["usd"], rel=1e-5)   # means rounded to 0.1 token
    v2 = M.modelo(M.Parametros(version="v2"))
    assert v3["costo_por_consulta_usd"] < v2["costo_por_consulta_usd"]


def test_la_corrida_reusa_la_corregida_con_sus_topes_y_su_carpeta(LB):
    c = CORR.corrida(LB)
    assert c.salida.name == "cache" and c.detalle.name == "cache_detalle.jsonl"
    assert c.exigir == {"PRESUPUESTO_TAREA": "techo_semana20", "CACHE_PROMPT": "historial"}
    peor = PREDICCION["escenarios"]["peor"]["con_calentamiento_usd"]
    assert peor + 0.12 <= c.tope_usd       # the worst case plus one task at the ceiling fits under the cap
    assert 22 * 100_000 <= c.tope_tokens


def test_la_comparacion_lee_la_prediccion_sin_cambiarla():
    corregida = [json.loads(x) for x in (S20 / "resultados" / "corrida_corregida_detalle.jsonl").read_text().splitlines()]
    falsa = [{**l, "costo_usd": round(l["costo_usd"] * 0.6, 7), "tokens_cache_lectura": 1, "tokens_cache_escritura": 1,
              "aciertos_cache": {"posibles": 2, "leyeron": 1, "tasa": 0.5}, "latencia_primer_paso_ms": 1000.0,
              "latencia_pasos_siguientes_ms_mediana": 700.0} for l in corregida]
    antes = json.dumps(PREDICCION, sort_keys=True)
    c = CORR.comparar(falsa, corregida, PREDICCION, M.percentil)
    assert json.dumps(PREDICCION, sort_keys=True) == antes
    assert len(c["tareas"]) == 20 and c["aciertos"]["tasa"] == 0.5
    assert c["costo"]["cache"]["total"] == pytest.approx(0.6 * c["costo"]["corregida"]["total"], rel=1e-4)
    assert c["exito"]["cache"] == c["exito"]["corregida"] == 16
    assert c["latencia"]["caliente"]["primer_paso_ms_mediana"] == 1000.0
