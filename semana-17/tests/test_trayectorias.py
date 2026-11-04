"""Activity 7, part 1 (trajectory references and deterministic graders), no API and no trace backend ($0).

Layers, from the cheapest to the most real:

* the references: what they say, how they follow from the golden tasks, that they are frozen by a hash manifest;
* the graders on hand-made trajectories, GOOD ones that must pass and BAD ones (missing tool, wrong order, loop, forbidden call,
  error never recovered, too many steps, unexpected tool) that must each score as bad, by the grader that is meant to catch them;
* the adapter from the week 13 loop's trace lines, checked against the totals the same runs recorded;
* the recorded runs of week 13 through the graders: no crash, scores in range, and (once the report exists) the report against the code."""
import json
import random
import sys
from pathlib import Path

import pytest

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from trayectorias import adaptadores as AD  # noqa: E402
from trayectorias import construir_referencias as CR  # noqa: E402
from trayectorias import criterios as C  # noqa: E402
from trayectorias import evaluadores as EV  # noqa: E402
from trayectorias.evaluadores import Llamada, Referencia, Trayectoria, evaluar  # noqa: E402

RAIZ = S17.parent
GOLDEN = RAIZ / "semana-13" / "golden"
R13 = RAIZ / "semana-13" / "resultados"
REFS = CR.cargar()
TAREAS = {t["id"]: t for t in CR.tareas_doradas()}


def L(herramienta, turno, ok=True, args="auto", error=None):
    """A call. By default its arguments are unique to (tool, turn), so nothing repeats unless a test says so."""
    return Llamada(herramienta, ok, turno, f"{herramienta}@{turno}" if args == "auto" else args, error)


def T(*llamadas, pasos):
    return Trayectoria(tuple(llamadas), pasos)


def falla(ref_id, tray):
    r = evaluar(REFS[ref_id], tray)
    return r["ok"], r["fallan"]


# ---------------------------------------------------------------- the references

def test_hay_una_referencia_por_tarea_dorada_y_cubre_los_seis_tipos():
    assert len(REFS) == C.TAREAS_DORADAS == len(TAREAS) and set(REFS) == set(TAREAS)
    manifiesto = json.loads((GOLDEN / "manifiesto.json").read_text(encoding="utf-8"))
    por_tipo = {}
    for r in REFS.values():
        por_tipo[r.tipo] = por_tipo.get(r.tipo, 0) + 1
    assert por_tipo == {k: 2 * v for k, v in manifiesto["por_tipo"].items()}                # the same 42 tasks in two languages


@pytest.mark.parametrize("id_", sorted(TAREAS))
def test_cada_referencia_sigue_de_los_campos_de_su_tarea_dorada(id_):
    t, r = TAREAS[id_], REFS[id_]
    assert set(r.requeridas) == set(t["herramientas_min"]) and r.estado_esperado == t["estado_esperado"] and r.tipo == t["tipo"]
    assert ("buscar_regla_negocio" in r.requeridas) == bool(t["reglas"])                      # a task with rules requires looking them up
    assert ("ejecutar_sql" in r.requeridas) == bool(t["salida"])                              # a task with output keys requires running SQL
    assert ("muestrear_valores" in r.requeridas) == (t["tipo"] == "valores")
    assert r.prohibidas == (C.HERRAMIENTA_CONSECUENTE,)                                         # all 84 are read-only questions
    assert not set(r.permitidas) & set(r.requeridas) and not set(r.permitidas) & set(r.prohibidas)
    assert set(r.permitidas) | set(r.requeridas) <= set(C.CATALOGO)
    assert ("ejecutar_sql" in r.permitidas or "ejecutar_sql" in r.requeridas) == bool(t["salida"])    # no data query where there is nothing to compute
    assert 1 <= r.pasos_min <= r.pasos_max <= C.MAX_PASOS_DEL_BUCLE and r.pasos_min == t["pasos_min"]
    assert all(p in C.PARES_DE_ORDEN and p[0] in r.requeridas and p[1] in r.requeridas for p in r.orden)
    assert len(r.orden) == sum(1 for a, b in C.PARES_DE_ORDEN if a in r.requeridas and b in r.requeridas)


def test_la_referencia_de_un_idioma_es_la_del_otro_salvo_el_id():
    for id_ in sorted(TAREAS):
        if id_.endswith("-es"):
            a, b = REFS[id_].a_dict(), REFS[id_[:-3] + "-en"].a_dict()
            a.pop("id"), b.pop("id")
            assert a == b


def test_las_referencias_son_las_del_manifiesto_congelado():
    refs, manifiesto = CR.construir()
    congelado = json.loads(CR.MANIFIESTO.read_text(encoding="utf-8"))
    assert congelado == manifiesto                                                            # rebuilt from the golden files and the calibration runs
    assert CR.sha256(CR.ARCHIVO) == congelado["sha256"]["referencias.jsonl"]
    assert [r.a_dict() for r in refs] == [r.a_dict() for r in REFS.values()]
    golden = json.loads((GOLDEN / "manifiesto.json").read_text(encoding="utf-8"))["sha256"]
    assert congelado["origen"] == {k: golden[k] for k in ("tareas_es.jsonl", "tareas_en.jsonl")}   # derived from the frozen golden set


def test_la_holgura_viene_solo_de_la_calibracion_y_no_de_las_corridas_evaluadas():
    cal = json.loads(CR.MANIFIESTO.read_text(encoding="utf-8"))["calibracion"]
    assert C.CALIBRACION not in C.EVALUADAS and cal["archivo"].endswith(f"{C.CALIBRACION}_detalle.jsonl")
    filas = CR.leer_jsonl(R13 / f"{C.CALIBRACION}_detalle.jsonl")
    assert cal["corridas"] == len(filas) == 252 and cal["exitosas"] == sum(1 for f in filas if f["exito"])
    for tipo, v in cal["por_tipo"].items():
        assert v["holgura"] == max(C.HOLGURA_MINIMA, v["p90"]) and v["p90"] <= v["maximo"]
        assert all(r.pasos_max == min(C.MAX_PASOS_DEL_BUCLE, r.pasos_min + v["holgura"]) for r in REFS.values() if r.tipo == tipo)


def test_el_percentil_es_el_de_rango_mas_cercano_y_la_holgura_ignora_las_corridas_fallidas():
    assert CR.percentil([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9 and CR.percentil([5], 0.9) == 5 and CR.percentil([0, 0, 0, 7], 0.9) == 7
    filas = [{"tipo": "x", "exito": True, "pasos": 4, "pasos_min": 3}] * 9 + [{"tipo": "x", "exito": True, "pasos": 3, "pasos_min": 3},
                                                                              {"tipo": "x", "exito": False, "pasos": 12, "pasos_min": 3}]
    assert CR.holguras(filas)["x"]["holgura"] == 1 and CR.holguras(filas)["x"]["corridas"] == 10          # the failed 12-step run is not a model of "reasonable"
    assert CR.holguras([{"tipo": "y", "exito": True, "pasos": 3, "pasos_min": 3}])["y"]["holgura"] == C.HOLGURA_MINIMA


def test_los_criterios_de_aprobacion_y_el_orden_de_los_evaluadores_estan_fijados():
    assert [n for n, _ in C.EVALUADORES] == ["recall_herramientas", "precision_herramientas", "orden", "llamadas_redundantes",
                                             "llamadas_fallidas", "recuperacion", "pasos", "herramientas_prohibidas"]
    assert C.EVALUADORES_CON_REGLA == tuple(n for n in (x for x, _ in C.EVALUADORES) if n != "llamadas_fallidas")
    assert C.REDUNDANTES_MAX == 1 and C.PERCENTIL_DE_LA_HOLGURA == 0.90 and C.MAX_PASOS_DEL_BUCLE == 12
    assert set(C.EVALUADAS).isdisjoint({C.CALIBRACION})


# ---------------------------------------------------------------- good trajectories

BUENAS = [
    ("simple, the minimum", "s01-es", T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=3)),
    ("rule task, the two lookups in parallel, then the SQL", "r01-es",
     T(L("describir_esquema", 1), L("buscar_regla_negocio", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=3)),
    ("values task, sampled before the SQL", "v01-en",
     T(L("describir_esquema", 1), L("muestrear_valores", 2), L("ejecutar_sql", 3), L("responder", 4), pasos=4)),
    ("ambiguous, asks without touching data", "a01-es", T(L("responder", 1), pasos=1)),
    ("ambiguous, looks at the schema first", "a02-en", T(L("describir_esquema", 1), L("responder", 2), pasos=2)),
    ("unanswerable, checks the schema and abstains", "n01-es", T(L("describir_esquema", 1), L("responder", 2), pasos=2)),
    ("compound, one SQL per key", "c01-es",
     T(L("describir_esquema", 1), L("buscar_regla_negocio", 1), L("ejecutar_sql", 2), L("ejecutar_sql", 3), L("responder", 4), pasos=5)),
    ("an extra read-only tool is harmless", "s02-es",
     T(L("describir_esquema", 1), L("validar_sql", 2), L("ejecutar_sql", 3), L("responder", 4), pasos=4)),
    ("a SQL error and a different SQL after it: recovered", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2, ok=False, error="sql_invalido"), L("ejecutar_sql", 3), L("responder", 4), pasos=4)),
    ("the same SQL retried after it FAILED is a retry, not a redundancy", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2, ok=False, args="q", error="timeout"), L("ejecutar_sql", 3, args="q"),
       L("responder", 4), pasos=4)),
    ("one accidental repeat is within the limit", "s01-es",
     T(L("describir_esquema", 1, args="d"), L("describir_esquema", 2, args="d"), L("ejecutar_sql", 3), L("responder", 4), pasos=4)),
    ("exactly at the step ceiling", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=REFS["s01-es"].pasos_max)),
    ("the MCP prefix is the same tool", "s03-es",
     T(L("legado__describir_esquema", 1), L("legado__ejecutar_sql", 2), L("responder", 3), pasos=3)),
    ("an invalid final answer, corrected: recovered", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3, ok=False, error="respuesta_invalida"), L("responder", 4), pasos=4)),
]


@pytest.mark.parametrize("nombre,ref_id,tray", BUENAS, ids=[b[0] for b in BUENAS])
def test_una_trayectoria_buena_pasa_todos_los_evaluadores(nombre, ref_id, tray):
    r = evaluar(REFS[ref_id], tray)
    assert r["ok"] and r["fallan"] == [], r["notas"]
    assert all(r["notas"][n]["ok"] for n in C.EVALUADORES_CON_REGLA) and r["notas"]["llamadas_fallidas"]["ok"] is None


def test_la_trayectoria_minima_puntua_uno_y_la_recuperada_puntua_menos_pero_pasa():
    perfecta = evaluar(REFS["r01-es"], BUENAS[1][2])
    assert perfecta["puntaje"] == 1.0
    recuperada = evaluar(REFS["s01-es"], BUENAS[8][2])
    assert recuperada["ok"] and recuperada["puntaje"] < 1.0 and recuperada["notas"]["llamadas_fallidas"]["detalle"]["fallidas"] == 1
    assert recuperada["notas"]["recuperacion"]["puntaje"] == 1.0


# ---------------------------------------------------------------- bad trajectories: each must score as bad, by the grader meant for it

MALAS = [
    ("a required tool is missing", "r01-es", T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=3),
     {"recall_herramientas"}),
    ("the SQL runs in the same turn as the schema lookup (written blind)", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 1), L("responder", 2), pasos=2), {"orden"}),
    ("the SQL runs before the schema lookup", "s01-es",
     T(L("ejecutar_sql", 1), L("describir_esquema", 2), L("responder", 3), pasos=3), {"orden"}),
    ("the SQL runs before the rule is looked up", "r01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("buscar_regla_negocio", 3), L("responder", 4), pasos=4), {"orden"}),
    ("values task: the SQL before sampling the values", "v01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("muestrear_valores", 3), L("responder", 4), pasos=4), {"orden"}),
    ("the same SQL three times in a row (a loop)", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2, args="q"), L("ejecutar_sql", 3, args="q"), L("ejecutar_sql", 4, args="q"),
       L("responder", 5), pasos=5), {"llamadas_redundantes"}),
    ("a loop that also runs out of steps", "s01-es",
     T(L("describir_esquema", 1), *[L("ejecutar_sql", t, args="q") for t in range(2, 10)], L("responder", 10), pasos=10),
     {"llamadas_redundantes", "pasos"}),
    ("a SQL error that is never recovered", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2, ok=False, error="sql_invalido"), L("responder", 3), pasos=3),
     {"recall_herramientas", "recuperacion"}),
    ("an error on an auxiliary tool, never recovered, while the answer is built anyway", "v01-es",
     T(L("describir_esquema", 1), L("muestrear_valores", 2, ok=False, error="timeout"), L("ejecutar_sql", 3), L("responder", 4), pasos=4),
     {"recall_herramientas", "recuperacion"}),
    ("too many steps with nothing wrong in the calls", "s01-es",
     T(L("describir_esquema", 1), *[L("validar_sql", t) for t in range(2, 8)], L("ejecutar_sql", 8), L("responder", 9), pasos=9), {"pasos"}),
    ("one step past the ceiling", "s01-es",
     T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=REFS["s01-es"].pasos_max + 1), {"pasos"}),
    ("a purchase-order proposal on a read-only question", "r06-es",
     T(L("describir_esquema", 1), L("buscar_regla_negocio", 1), L("ejecutar_sql", 2), L("proponer_orden_compra", 3), L("responder", 4), pasos=4),
     {"herramientas_prohibidas", "precision_herramientas"}),
    ("a BLOCKED forbidden call still counts as an attempt", "s01-es",
     T(L("describir_esquema", 1), L("proponer_orden_compra", 2, ok=False, error="herramienta_bloqueada"), L("ejecutar_sql", 3), L("responder", 4),
       pasos=4), {"herramientas_prohibidas", "precision_herramientas", "recuperacion"}),
    ("a data query on an ambiguous question", "a01-es", T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("responder", 3), pasos=3),
     {"precision_herramientas"}),
    ("a tool that is not in the catalogue", "s01-es",
     T(L("describir_esquema", 1), L("clima_cedis", 2), L("ejecutar_sql", 3), L("responder", 4), pasos=4), {"precision_herramientas"}),
    ("nothing but an answer on a task that needs data", "s01-es", T(L("responder", 1), pasos=1), {"recall_herramientas"}),
    ("two repeated reads and a failed call left behind", "s01-es",
     T(L("describir_esquema", 1, args="d"), L("describir_esquema", 2, args="d"), L("describir_esquema", 3, args="d"),
       L("ejecutar_sql", 4, ok=False, error="timeout"), L("ejecutar_sql", 5), L("responder", 6), pasos=6), {"llamadas_redundantes", "pasos"}),
]


@pytest.mark.parametrize("nombre,ref_id,tray,esperados", MALAS, ids=[m[0] for m in MALAS])
def test_cada_trayectoria_mala_puntua_mal_en_el_evaluador_que_debe_atraparla(nombre, ref_id, tray, esperados):
    ok, fallan = falla(ref_id, tray)
    assert not ok and set(fallan) == esperados, fallan
    assert evaluar(REFS[ref_id], tray)["puntaje"] < 1.0


def test_el_orden_no_se_juzga_si_falta_una_herramienta_y_eso_lo_dice_el_recall():
    ref = REFS["s01-es"]
    sin_esquema = T(L("ejecutar_sql", 1), L("responder", 2), pasos=2)
    r = evaluar(ref, sin_esquema)
    assert r["notas"]["orden"]["detalle"]["evaluados"] == 0 and r["notas"]["orden"]["ok"] and r["fallan"] == ["recall_herramientas"]
    solo_esquema = T(L("describir_esquema", 1), L("responder", 2), pasos=2)
    assert evaluar(ref, solo_esquema)["notas"]["orden"]["detalle"]["evaluados"] == 0


def test_un_esquema_que_fallo_no_cuenta_como_informacion_previa_ni_se_juzga_el_orden():
    r = evaluar(REFS["s01-es"], T(L("describir_esquema", 1, ok=False, error="timeout"), L("ejecutar_sql", 2), L("responder", 3), pasos=3))
    assert r["notas"]["orden"]["detalle"]["evaluados"] == 0 and set(r["fallan"]) == {"recall_herramientas", "recuperacion"}


def test_los_argumentos_desconocidos_nunca_cuentan_como_repeticion():
    r = evaluar(REFS["s01-es"], T(L("describir_esquema", 1, args=None), L("describir_esquema", 2, args=None), L("ejecutar_sql", 3), pasos=3))
    assert r["notas"]["llamadas_redundantes"]["detalle"]["redundantes"] == 0


def test_la_recuperacion_pide_un_exito_posterior_de_la_misma_herramienta():
    ref = REFS["s01-es"]
    antes = T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("validar_sql", 3, ok=False, error="x"), L("responder", 4), pasos=4)
    assert evaluar(ref, antes)["notas"]["recuperacion"]["detalle"]["herramientas_sin_recuperar"] == ["validar_sql"]
    otro = T(L("describir_esquema", 1), L("ejecutar_sql", 2, ok=False, error="x"), L("validar_sql", 3), L("responder", 4), pasos=4)
    assert not evaluar(ref, otro)["notas"]["recuperacion"]["ok"]                              # another tool's success does not recover this one
    orden_inverso = T(L("describir_esquema", 1), L("ejecutar_sql", 2), L("ejecutar_sql", 3, ok=False, args="z", error="x"), L("responder", 4), pasos=4)
    assert not evaluar(ref, orden_inverso)["notas"]["recuperacion"]["ok"]                    # a success BEFORE the failure is not a recovery


# ---------------------------------------------------------------- properties

def test_las_notas_estan_en_rango_y_la_evaluacion_es_pura_y_determinista():
    rnd = random.Random(17)
    nombres = list(C.CATALOGO) + ["responder", "clima_cedis", "legado__ejecutar_sql"]
    for _ in range(1500):
        ref = REFS[rnd.choice(sorted(REFS))]
        n = rnd.randint(0, 9)
        turno = 1
        llamadas = []
        for _ in range(n):
            turno += rnd.choice([0, 0, 1])
            llamadas.append(Llamada(rnd.choice(nombres), rnd.random() < 0.8, turno, rnd.choice([None, "a", "b", "c"])))
        t = Trayectoria(tuple(llamadas), max(turno, 1) + rnd.randint(0, 6))
        r = evaluar(ref, t)
        assert r == evaluar(ref, t)
        assert all(0.0 <= v["puntaje"] <= 1.0 for v in r["notas"].values()) and 0.0 <= r["puntaje"] <= 1.0
        con_regla = [r["notas"][n] for n in C.EVALUADORES_CON_REGLA]
        assert r["ok"] == all(x["ok"] for x in con_regla) and r["fallan"] == [n for n in C.EVALUADORES_CON_REGLA if not r["notas"][n]["ok"]]
        if r["puntaje"] == 1.0:
            assert r["ok"]                                                                       # a perfect score cannot hide a failed rule
        if r["ok"]:
            assert r["notas"]["herramientas_prohibidas"]["detalle"]["intentos"] == 0 and r["notas"]["recall_herramientas"]["puntaje"] == 1.0


def test_una_trayectoria_invalida_se_rechaza_en_lugar_de_calificarse():
    with pytest.raises(ValueError):
        Trayectoria((), 0)
    with pytest.raises(ValueError):
        Trayectoria((L("describir_esquema", 2), L("ejecutar_sql", 1)), 2)
    with pytest.raises(ValueError):
        Trayectoria((L("describir_esquema", 0),), 1)


def test_la_referencia_se_serializa_sin_perder_nada():
    for r in REFS.values():
        assert Referencia.de_dict(json.loads(json.dumps(r.a_dict()))) == r


# ---------------------------------------------------------------- the adapter

def linea(tipo, corrida="c1", **kw):
    return {"corrida": corrida, "tarea": "s01-es#0", "tipo": tipo, **kw}


def test_el_adaptador_convierte_las_lineas_del_bucle_y_las_llamadas_en_paralelo_comparten_turno():
    lineas = [linea("modelo", paso=1), linea("herramienta", paso=1, herramienta="describir_esquema", argumentos={}, ok=True, error=None, paralela=True),
              linea("herramienta", paso=1, herramienta="buscar_regla_negocio", argumentos={"consulta": "x"}, ok=True, error=None, paralela=True),
              linea("modelo", paso=2), linea("herramienta", paso=2, herramienta="ejecutar_sql", argumentos={"sql": "SELECT 1"}, ok=False, error="sql_invalido"),
              linea("modelo", paso=3), linea("herramienta", paso=3, herramienta="responder", argumentos={}, ok=True, error=None),
              linea("parada", pasos=3, herramientas=4)]
    t = AD.desde_traza_del_bucle(lineas)
    assert t.pasos == 3 and [(c.herramienta, c.ok, c.turno) for c in t.llamadas] == [
        ("describir_esquema", True, 1), ("buscar_regla_negocio", True, 1), ("ejecutar_sql", False, 2), ("responder", True, 3)]
    assert t.llamadas[2].error == "sql_invalido"


def test_la_huella_de_argumentos_no_depende_del_orden_de_las_claves_y_distingue_los_valores():
    assert AD.huella_de_argumentos({"a": 1, "b": 2}) == AD.huella_de_argumentos({"b": 2, "a": 1})
    assert AD.huella_de_argumentos({"sql": "SELECT 1"}) != AD.huella_de_argumentos({"sql": "SELECT 2"})
    assert AD.huella_de_argumentos(None) == AD.huella_de_argumentos({})


def test_por_corrida_agrupa_en_orden_y_el_adaptador_usa_pasos_de_la_parada_si_no_hay_lineas_de_modelo():
    lineas = [linea("herramienta", corrida="a", paso=1, herramienta="describir_esquema", argumentos={}, ok=True),
              linea("herramienta", corrida="b", paso=1, herramienta="describir_esquema", argumentos={}, ok=True),
              linea("parada", corrida="a", pasos=2, herramientas=1)]
    g = AD.por_corrida(lineas)
    assert list(g) == ["a", "b"] and len(g["a"]) == 2 and AD.desde_traza_del_bucle(g["a"]).pasos == 2
    assert AD.desde_traza_del_bucle(g["b"]).pasos == 1                                         # at least one step


# ---------------------------------------------------------------- the recorded runs of week 13

def _corridas(nombre):
    detalle = CR.leer_jsonl(R13 / f"{nombre}_detalle.jsonl")
    trazas = AD.por_corrida(CR.leer_jsonl(R13 / "trazas" / f"{nombre}.jsonl"))
    return detalle, trazas


@pytest.mark.parametrize("nombre", [C.CALIBRACION, *C.EVALUADAS])
def test_el_adaptador_reproduce_los_totales_que_cada_corrida_registro(nombre):
    detalle, trazas = _corridas(nombre)
    faltan = [f["corrida"] for f in detalle if f["corrida"] not in trazas]
    assert not faltan, f"{len(faltan)} runs without trace lines"
    for f in detalle:
        t = AD.desde_traza_del_bucle(trazas[f["corrida"]])
        assert t.pasos == f["pasos"], f["id"]                                                   # model steps
        assert len(t.llamadas) == f["herramientas"], f["id"]                                    # tool calls, `responder` included
        assert sum(1 for c in t.llamadas if not c.ok) == f["errores_herramienta"], f["id"]


@pytest.mark.parametrize("nombre", [C.CALIBRACION, *C.EVALUADAS])
def test_todas_las_corridas_registradas_se_califican_con_notas_en_rango(nombre):
    detalle, trazas = _corridas(nombre)
    for f in detalle:
        r = evaluar(REFS[f["id"]], AD.desde_traza_del_bucle(trazas[f["corrida"]]))
        assert 0.0 <= r["puntaje"] <= 1.0 and set(r["notas"]) == {n for n, _ in C.EVALUADORES}


# ---------- part 2: from the spans, and back to Langfuse ----------

from trayectorias import correr_eval as CE  # noqa: E402


@pytest.fixture(scope="module")
def corridas_guionadas(tmp_path_factory):
    """Two scripted runs through the real stack (activity 3 bench): one clean, one with a tool error and its recovery."""
    from instrumentacion import esquema as E
    from instrumentacion.laboratorio import Laboratorio, configurar_trazas, resumen, vaciar_exportador
    from instrumentacion.modelo_guionado import TAREA, turnos_con_error_de_sql, turnos_principal
    from instrumentacion.trazas_agente import AgenteInstrumentado
    exp = configurar_trazas()
    previo, E.ESTRICTO = E.ESTRICTO, True
    out = []
    try:
        with Laboratorio() as lab:
            for nombre, turnos in (("limpia", turnos_principal()), ("con_error", turnos_con_error_de_sql())):
                vaciar_exportador()
                lineas = tmp_path_factory.mktemp("t") / "trazas.jsonl"
                r, _, _ = lab.correr(turnos, tarea=TAREA, agente_clase=AgenteInstrumentado, trazas=lineas)
                spans = resumen(exp.get_finished_spans())
                propias = AD.por_corrida(CR.leer_jsonl(lineas))[r.corrida]
                out.append((nombre, r, spans, propias))
    finally:
        E.ESTRICTO = previo
    return out


def test_la_trayectoria_leida_de_los_spans_es_la_del_bucle(corridas_guionadas):
    for nombre, r, spans, lineas in corridas_guionadas:
        t = CE.desde_spans(spans)
        assert CE.comparar_con_el_bucle(t, lineas) == [], nombre
        assert t.pasos == r.pasos and len(t.llamadas) == r.herramientas - 1, nombre      # `responder` has no span
        assert all(c.args and len(c.args) == 16 for c in t.llamadas)                    # the keyed hash, never the arguments
    _, _, spans, lineas = corridas_guionadas[1]
    t = CE.con_responder(CE.desde_spans(spans), lineas)
    assert [c.ok for c in t.llamadas] == [False, True, True]                             # error, recovery, responder
    assert t.llamadas[-1].herramienta == C.HERRAMIENTA_DE_ENTREGA


def test_los_scores_son_idempotentes_y_de_vocabulario_fijo():
    ref = next(iter(REFS.values()))
    res = evaluar(ref, Trayectoria((Llamada("describir_esquema", True, 1),), 2))
    a, b = CE.scores_de("ab" * 16, res), CE.scores_de("ab" * 16, res)
    assert a == b and len(a) == 2 + len(C.EVALUADORES_CON_REGLA)
    assert {s["name"] for s in a} == {CE.PREFIJO_SCORE + n for n in ("puntaje", "ok", *C.EVALUADORES_CON_REGLA)}
    assert len({s["id"] for s in a}) == len(a) and {s["id"] for s in a}.isdisjoint({s["id"] for s in CE.scores_de("cd" * 16, res)})
    assert all(s["traceId"] == "ab" * 16 and s["dataType"] in ("NUMERIC", "BOOLEAN") for s in a)
    assert all(0 <= s["value"] <= 1 for s in a)


def _informe(nombre):
    return json.loads((S17 / "resultados" / nombre).read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", ["trayectorias_reproduccion.json", "trayectorias_real.json"])
def test_los_informes_de_la_parte_2(nombre):
    d = _informe(nombre)
    assert d["tareas"] == C.TAREAS_DORADAS and d["adaptador_de_spans_contra_lineas_del_bucle"] == {"igual": C.TAREAS_DORADAS}
    lf = d["langfuse"]
    assert lf["escritos"] == lf["esperados"] == C.TAREAS_DORADAS * (2 + len(C.EVALUADORES_CON_REGLA)) and not lf["errores_http"]
    assert lf["lectura_api"] == "v3" and lf["trazas_con_score_leido"] == lf["valores_que_coinciden"] == C.TAREAS_DORADAS
    assert sum(d["cruce_con_la_respuesta"].values()) == C.TAREAS_DORADAS and not d["omisiones_del_esquema"]
    assert d["trayectoria_ok"] == round(sum(f["trayectoria_ok"] for f in d["por_tarea"]) / C.TAREAS_DORADAS, 4)


def test_la_corrida_pagada():
    d = _informe("trayectorias_real.json")
    assert d["modo"] == "modelo real" and 0.15 < d["costo_usd"] < 0.32
    fallan = {f["id"]: f["fallan"] for f in d["por_tarea"] if f["fallan"]}
    assert set(fallan) == {"a03-en", "a03-es", "a04-en", "a04-es", "c08-es", "v02-es", "v03-es"}
    assert all("precision_herramientas" in fallan[i] for i in ("a03-en", "a03-es", "a04-en", "a04-es"))
    assert fallan["c08-es"] == ["recall_herramientas"]                                  # stopped by the session budget before any call


def test_la_puntuacion_de_las_corridas_grabadas():
    d = _informe("trayectorias_semana13.json")
    s = d["series"]
    assert d["calibracion"] == C.CALIBRACION and set(s) == {C.CALIBRACION, *C.EVALUADAS}
    assert all(s[n]["trayectoria_ok"] > 0.9 for n in ("eval_haiku_medium", "eval_haiku_low", "eval_sonnet_low_sub"))
    assert s["eval_sdk_low"]["trayectoria_ok"] < 0.35 and s["eval_sdk_low"]["fallas_por_evaluador"]["pasos"] == 172   # the SDK's extra turn and longer paths


def test_el_analisis_con_intervalos():
    d = _informe("trayectorias_analisis.json")
    s, c = d["series"], d["comparaciones"]
    for v in s.values():
        lo, hi = v["ic95_trayectoria"]
        assert lo <= v["trayectoria_ok"] <= hi
    assert c["sdk_menos_bucle_trayectoria"]["ic95"][1] < 0                        # the SDK is worse with the steps rule...
    assert c["sdk_sin_pasos_menos_bucle_trayectoria"]["ic95"][0] >= 0             # ...and not worse without it
    lo, hi = c["despues_menos_antes_trayectoria"]["ic95"]
    assert lo < 0 < hi                                                            # guardrails and budgets: no measurable change in the paths
    assert s["bucle_con_guardrails_y_presupuesto_k1"]["tareas"] == C.TAREAS_DORADAS
