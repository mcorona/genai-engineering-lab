"""Week 20, activity 4, step 4: the R1 prediction (quote v3 for routing), versioned before the live run ($0).

The cache split per model follows ADR 0015 section 3; with Haiku 4.5 alone it is activity 3's model. The ADR's two
hand-worked figures come out of it. The versioned prediction is what predecir() computes today."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
sys.path.insert(0, str(RAIZ / "semana-19"))

from agente import construccion as K  # noqa: E402
from costos import modelo as M  # noqa: E402


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo          # @dataclass reads its module
    spec.loader.exec_module(modulo)
    return modulo


P = _cargar("ruteo_prediccion", S20 / "ruteo" / "prediccion.py")
NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
VERSIONADA = S20 / "resultados" / "ruteo" / "r1_prediccion.json"


def _llamadas(totales, salidas, modelos, descartadas=None):
    descartadas = descartadas or [False] * len(modelos)
    return [P.Llamada(paso=p, entrada=t, salida=s, modelo=m, descartada=d)
            for p, t, s, m, d in zip(range(len(totales)), totales, salidas, modelos, descartadas)]


def test_haiku_alone_is_activity_3s_cache_model():
    filas = P.cargar_tareas()
    for f in filas:
        totales = [x["total"] for x in f["pasos"]]
        mio = P.dividir(_llamadas(totales, [x["salida"] for x in f["pasos"]], [HAIKU] * len(totales)),
                        modo_cache="historial", prefijo_fijo=f["prefijo_fijo"], acierta=True, calientes=set())
        suyo = M.cache_por_paso(totales, p_acierto=1.0, modo="historial")
        assert [(round(x["lectura"]), round(x["escritura"]), round(x["sin_cache"])) for x in mio] == \
               [(round(x["lectura"]), round(x["escritura"]), round(x["sin_cache"])) for x in suyo], f["id"]


def test_the_adrs_hand_worked_budget_case_without_cache():
    llamadas = [P.Llamada(0, 2952, 149, NOVA), P.Llamada(1, 4268, 180, NOVA), P.Llamada(2, 4548, 107, HAIKU),
                P.Llamada(3, 4733, 275, HAIKU, descartada=True), P.Llamada(3, 4733, 275, SONNET),
                P.Llamada(4, 5133, 492, SONNET)]
    pasos = P.dividir(llamadas, modo_cache="off", prefijo_fijo=2547, acierta=True, calientes=set())
    assert round(P.costo(llamadas, pasos), 7) == 0.0580356


def test_an_escalation_to_sonnet_rewrites_the_tasks_prefix_on_the_new_model():
    """ADR 0015 section 3: escalating to Sonnet 4.6 at call 4 writes 4,733 tokens at 4.125, 0.0195236 USD."""
    llamadas = _llamadas([2952, 4268, 4548, 4733], [0, 0, 0, 0], [HAIKU, HAIKU, HAIKU, SONNET])
    pasos = P.dividir(llamadas, modo_cache="historial", prefijo_fijo=2547, acierta=True, calientes=set())
    assert pasos[3] == {"sin_cache": 0, "lectura": 0, "escritura": 4733}
    assert round(4733 * K.PRECIOS_POR_MODELO[SONNET].cache_escritura_1m / 1e6, 7) == 0.0195236


def test_nova_and_sonnet_read_the_warm_fixed_prefix_and_nova_writes_for_free():
    llamadas = _llamadas([2952, 4268], [10, 10], [NOVA, NOVA])
    frio = P.dividir(llamadas, modo_cache="historial", prefijo_fijo=2547, acierta=True, calientes=set())
    assert frio[0] == {"sin_cache": 2952 - 2547, "lectura": 0, "escritura": 2547}   # the system point, first use
    assert frio[1] == {"sin_cache": 0, "lectura": 2547, "escritura": 4268 - 2547}   # the previous call's point
    caliente = P.dividir(llamadas[:1], modo_cache="historial", prefijo_fijo=2547, acierta=True, calientes={NOVA})
    assert caliente[0] == {"sin_cache": 2952 - 2547, "lectura": 2547, "escritura": 0}
    assert K.PRECIOS_POR_MODELO[NOVA].cache_escritura_1m == 0.0


def test_with_no_hit_every_cached_call_writes_its_whole_prefix():
    llamadas = _llamadas([5000, 6000, 7000], [0, 0, 0], [HAIKU] * 3)
    pasos = P.dividir(llamadas, modo_cache="historial", prefijo_fijo=2547, acierta=False, calientes=set())
    assert [x["lectura"] for x in pasos] == [0, 0, 0] and [x["escritura"] for x in pasos] == [0, 6000, 7000]


@pytest.mark.parametrize("escenario", sorted(P.ESCENARIOS))
def test_each_scenario_is_a_route_the_router_can_take(escenario):
    for f in P.cargar_tareas():
        llamadas = P.ESCENARIOS[escenario](f["pasos"])
        modelos = [x.modelo for x in llamadas]
        indices = [K.RUTEO_CANDIDATOS.index(m) for m in modelos]
        assert indices == sorted(indices)                                    # never back down
        assert indices[-1] - indices[0] <= K.RUTEO_REGLAS["max_escalamientos"]
        assert sorted({x.paso for x in llamadas}) == list(range(len(f["pasos"])))
        assert sum(x.descartada for x in llamadas) <= K.RUTEO_REGLAS["max_escalamientos"]
        assert not llamadas[-1].descartada


def test_the_versioned_prediction_is_todays():
    assert json.loads(VERSIONADA.read_text(encoding="utf-8")) == json.loads(json.dumps(P.predecir()))


def test_the_prediction_bounds_the_run_and_names_its_unknowns():
    pr = P.predecir()
    e = pr["escenarios"]
    assert e["solo_nova"]["total"] < e["nova_y_haiku_desde_el_paso_2"]["total"] < e["peor"]["total"]
    assert e["peor"]["total"] == max(x["total"] for x in e.values())
    assert pr["exito"].startswith("N")
    c = pr["corrida"]
    assert c["tareas"] == 20 and c["maximo_con_el_techo_usd"] <= c["maximo_por_las_reglas_usd"]
    assert c["maximo_con_el_techo_usd"] <= c["tope_usd"] <= c["maximo_con_el_techo_usd"] + 0.25
    assert c["maximo_con_el_techo_usd"] <= c["techo_por_tarea_usd"] * c["tareas"]
    assert pr["referencia_haiku"]["real_actividad_3_usd"] == 0.505822
