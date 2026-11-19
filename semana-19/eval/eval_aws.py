"""Week 19, activity 8: the mini eval against the deployed endpoint.

The 10 + 10 CI golden tasks (week 13's TAREAS_CI, Spanish and English), one at a time, through the public API
(POST /consultas, then GET /consultas/{id}, ADR 0007), with real Cognito tokens of the `analista` user. The password is
read from the local file of ADR 0013 and never printed or stored. Each task is sent and measured by activity 7's
`agentes/comparar.medir_api`: week 13's task message, polling, late spans retried, discarded runs kept.

Per task:
- success: week 13's execution-based verifier (agente/verificar.py). The agent's reported SQL is re-run through the
  tools function as copilot_ro. The expected rows are recomputed on this database first, as week 13's CI does on its
  own (loader mode `esperados`).
- the trajectory: week 17's deterministic graders (trayectorias/evaluadores.py) on the task's spans, against the frozen
  references (trayectorias/referencias.jsonl);
- cold or warm: the REPORT lines of the agent and questions functions inside the task's window. `Init Duration` is
  printed "for the first request served" by an execution environment (Lambda developer guide, Python logging);
- latency end to end, steps, tool calls, input, output and cache tokens, cost from the spans, and blocks by the
  deterministic layer, the Guardrail and the Policy.

Cold starts are measured in a separate warm-up run. It runs right after computo is deployed, so its code is new and no
environment exists yet. FRIO tasks are sent together, one per environment: the agent's reserved concurrency is 2
(ADR 0012). The 20 tasks then run one at a time. Each task is classified from its own REPORT lines, not assumed.

Simulation by default: prints the plan and the caps and calls nothing. `--si` acts; `--informe` aggregates offline.
Run with the admin profile, by Manuel (Cognito admin auth, the loader and the tools function need it):

    S19_PERFIL=manuel-admin .venv/bin/python semana-19/eval/eval_aws.py --si

Hard caps in the code (TOPE_USD, TOPE_TOKENS) over the warm-up and the 20 tasks. Before each task the run checks that
what was spent plus week 17's per-task limit still fits; otherwise the task is not sent and is reported as aborted
(`no_corrida`, `tope_del_script`).
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
for ruta in (S19, RAIZ / "semana-17"):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from agentes import comparar as C  # noqa: E402
from comun.redaccion import redactar  # noqa: E402
from trayectorias import construir_referencias as CR  # noqa: E402
from trayectorias.evaluadores import Llamada, Trayectoria, evaluar  # noqa: E402

TOPE_USD = 1.20
TOPE_TOKENS = 800_000
FRIO = ("s01-es", "s02-es")          # the warm-up: two tasks outside the CI subset, one per environment
SALIDA = S19 / "resultados" / "eval_aws"
CRUDO = "crudo_eval.json"
LARGO_RESPUESTA = 4000               # the judge reads the whole answer
FILAS_DE_CONTEXTO = 20


# ---------------------------------------------------------------- what is reused from earlier weeks, not copied

def _constante(archivo: Path, nombre: str):
    for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise LookupError(f"{nombre} no está en {archivo}")


def _funcion(archivo: Path, nombre: str, globales: dict) -> Callable:
    """One function from a CI script whose module imports things this eval does not need (psycopg, the week 10
    assistant). Only that definition is compiled, from the file as it is."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    (definicion,) = [n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre]
    espacio = dict(globales)
    exec(compile(ast.Module(body=[definicion], type_ignores=[]), str(archivo), "exec"), espacio)  # noqa: S102
    return espacio[nombre]


TAREAS_CI = _constante(RAIZ / "semana-13" / "ci" / "eval_ci.py", "TAREAS_CI")
umbral_de = _funcion(RAIZ / "semana-10" / "ci" / "eval_ci.py", "umbral_de", {"math": __import__("math")})


def _modulo(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


wilson = _modulo(RAIZ / "semana-03" / "estadistica.py", "estadistica_semana03").wilson


# ---------------------------------------------------------------- the tasks and their expected rows

def tareas_ci(raiz: Path = RAIZ) -> list[dict]:
    """The CI subset of week 13 in both languages, in file order, each with its language."""
    tareas = []
    for idioma in ("es", "en"):
        for linea in (raiz / "semana-13" / "golden" / f"tareas_{idioma}.jsonl").read_text(encoding="utf-8").splitlines():
            if linea.strip():
                t = json.loads(linea)
                if t["id"].rsplit("-", 1)[0] in TAREAS_CI:
                    tareas.append({**t, "idioma": idioma})
    if len(tareas) != 2 * len(TAREAS_CI):
        raise RuntimeError(f"se esperaban {2 * len(TAREAS_CI)} tareas de CI y hay {len(tareas)}")
    return tareas


def tareas_de_calentamiento(raiz: Path = RAIZ) -> list[dict]:
    por_id = {}
    for linea in (raiz / "semana-13" / "golden" / "tareas_es.jsonl").read_text(encoding="utf-8").splitlines():
        if linea.strip():
            t = json.loads(linea)
            por_id[t["id"]] = {**t, "idioma": "es"}
    return [por_id[i] for i in FRIO]


def consultas_esperadas(tareas: list[dict]) -> dict[str, str]:
    """{"<task>/<key>": sql_ref}: what the loader recomputes, as week 13's CI does on its database."""
    return {f"{t['id']}/{clave}": s["sql_ref"] for t in tareas for clave, s in (t.get("salida") or {}).items()}


def con_esperados(tareas: list[dict], esperados: dict[str, list]) -> list[dict]:
    salida = []
    for t in tareas:
        t = json.loads(json.dumps(t))
        for clave, s in (t.get("salida") or {}).items():
            s["esperado"] = esperados[f"{t['id']}/{clave}"]
        salida.append(t)
    return salida


# ---------------------------------------------------------------- cold or warm, from the REPORT lines

INIT = re.compile(r"Init Duration: ([0-9.]+) ms")


def arranque(lineas_report: dict[str, list[str]]) -> dict:
    """lineas_report = {"agente": [...], "consultas": [...]}: the REPORT lines of each function inside the task's window.
    A task is cold when the agent's environment ran its INIT for it. The questions function's INIT is reported too,
    since it is part of the latency end to end. No REPORT line of the agent: unknown (never assumed warm)."""
    def de(lineas):
        if not lineas:
            return None
        inits = [float(m.group(1)) for l in lineas for m in [INIT.search(l)] if m]
        return {"frio": bool(inits), "init_ms": max(inits) if inits else None, "reportes": len(lineas)}
    agente, consultas = de(lineas_report.get("agente")), de(lineas_report.get("consultas"))
    clase = "desconocido" if agente is None else ("frio" if agente["frio"] else "caliente")
    return {"clase": clase, "agente": agente, "consultas": consultas}


# ---------------------------------------------------------------- week 17's trajectory graders on the spans

def trayectoria_de_spans(spans_herramientas: list[dict], pasos: int | None) -> Trayectoria:
    """The task's execute_tool spans (activity 6's shape) as week 17's abstract trajectory. In week 19 `lab.step` is the
    call's position in the task, not the model turn, so `orden` compares positions; `pasos` is the agent span's
    `lab.run.steps`. Blocked calls and week 13's `responder` have no span, as in week 17 (correr_eval.desde_spans)."""
    ordenadas = sorted(spans_herramientas, key=lambda h: int(h.get("lab.step") or 0))
    llamadas = tuple(Llamada(str(h.get("gen_ai.tool.name") or "_unknown"), h.get("lab.tool.status") == "ok",
                             max(1, int(h.get("lab.step") or 1)), h.get("lab.tool.args.hmac"), h.get("error.type"))
                     for h in ordenadas)
    return Trayectoria(llamadas, max(1, int(pasos or 1), max((c.turno for c in llamadas), default=1)))


def calificar_trayectoria(tarea_id: str, fila: dict, referencias: dict | None = None) -> dict | None:
    referencias = referencias if referencias is not None else CR.cargar()
    ref = referencias.get(tarea_id)
    if ref is None or fila.get("estado") in ("no_corrida", "error_api"):
        return None
    r = evaluar(ref, trayectoria_de_spans(fila.get("spans_herramientas") or [], fila.get("pasos")))
    return {"ok": r["ok"], "puntaje": r["puntaje"], "fallan": r["fallan"],
            "notas": {n: {"puntaje": x["puntaje"], "ok": x["ok"]} for n, x in r["notas"].items()}}


# ---------------------------------------------------------------- the context the judge reads

def registrar_contexto(ejecutar_sql: Callable[[str], dict], destino: list) -> Callable[[str], dict]:
    """The verifier's own re-execution, recorded: the rows behind each reported SQL are the answer's context."""
    def envuelta(sql: str) -> dict:
        r = ejecutar_sql(sql)
        if not sql.lstrip().upper().startswith("SET "):
            destino.append({"sql": sql, "filas": (r.get("filas") or [])[:FILAS_DE_CONTEXTO], "error": r.get("error")})
        return r
    return envuelta


# ---------------------------------------------------------------- one run

def correr(tareas: list[dict], *, medir: Callable[[dict], dict], ejecutar_sql: Callable, reportes: Callable,
           tope: C.Tope, verificador=None, referencias=None, en_paralelo: bool = False) -> list[dict]:
    """medir(tarea) -> comparar.medir_api's row; reportes(inicio, fin) -> {"agente": [...], "consultas": [...]}."""
    def una(t):
        if not tope.cabe_otra():
            return {"id_tarea": t["id"], "idioma": t["idioma"], "estado": "no_corrida", "motivo": "tope_del_script"}
        f = medir(t)
        tope.sumar(f.get("costo_usd") or 0.0, (f.get("tokens_entrada") or 0) + (f.get("tokens_salida") or 0))
        return f

    if en_paralelo:
        with ThreadPoolExecutor(len(tareas)) as ex:
            medidas = list(ex.map(una, tareas))
    else:
        medidas = [una(t) for t in tareas]
    filas = []
    for t, f in zip(tareas, medidas):
        f = {**f, "idioma": t["idioma"], "tipo": t.get("tipo"), "estado_esperado": t["estado_esperado"]}
        if f["estado"] != "no_corrida":
            contexto: list = []
            f["verificacion"] = C.verificar(t, f["estado"], f.get("resultados") or [],
                                            registrar_contexto(ejecutar_sql, contexto), verificador)
            f["contexto"] = contexto
            f["arranque"] = arranque(reportes(f["inicio"], f["fin"])) if f.get("inicio") is not None else None
            f["trayectoria"] = calificar_trayectoria(t["id"], f, referencias)
        filas.append(f)
    return filas


def gasto(filas: list[dict]) -> dict:
    hechas = [f for f in filas if f.get("estado") != "no_corrida"]
    return {"usd": round(sum(f.get("costo_usd") or 0 for f in hechas), 6),
            "tokens": sum((f.get("tokens_entrada") or 0) + (f.get("tokens_salida") or 0) for f in hechas)}


# ---------------------------------------------------------------- aggregation

def _exito(f):
    return bool((f.get("verificacion") or {}).get("exito"))


def resumen_exito(filas: list[dict]) -> dict:
    """Success with Wilson's 95% interval (week 3), per language and in total. Aborted tasks count as run-and-failed:
    a cap that stops the eval does not improve its score."""
    def bloque(fs):
        n, k = len(fs), sum(_exito(f) for f in fs)
        bajo, alto = wilson(k, n) if n else (None, None)
        return {"n": n, "exito": k, "tasa": round(k / n, 3) if n else None,
                "ic95": [round(bajo, 3), round(alto, 3)] if n else None,
                "abortadas": sum(f.get("estado") == "no_corrida" for f in fs)}
    return {"es": bloque([f for f in filas if f["idioma"] == "es"]), "en": bloque([f for f in filas if f["idioma"] == "en"]),
            "total": bloque(filas)}


def resumen_latencia(filas: list[dict]) -> dict:
    """p50 and p95 by nearest rank (comparar.percentil), cold and warm apart; unknown is counted, not mixed in."""
    salida = {}
    for clase in ("frio", "caliente"):
        v = [f["latencia_s"] for f in filas if (f.get("arranque") or {}).get("clase") == clase and f.get("latencia_s") is not None]
        salida[clase] = {"n": len(v), "p50_s": C.percentil(v, 50), "p95_s": C.percentil(v, 95)}
    salida["desconocido"] = {"n": sum(1 for f in filas if (f.get("arranque") or {}).get("clase") == "desconocido")}
    return salida


def resumen_trayectoria(filas: list[dict]) -> dict:
    cal = [f["trayectoria"] for f in filas if f.get("trayectoria")]
    fallan: dict[str, int] = {}
    for c in cal:
        for n in c["fallan"]:
            fallan[n] = fallan.get(n, 0) + 1
    return {"calificadas": len(cal), "ok": sum(c["ok"] for c in cal),
            "puntaje_medio": round(sum(c["puntaje"] for c in cal) / len(cal), 3) if cal else None, "fallan": fallan}


def resumen_costo(filas: list[dict]) -> dict:
    hechas = [f for f in filas if f.get("estado") not in ("no_corrida", "error_api")]
    n = len(hechas)
    suma = lambda k: sum(f.get(k) or 0 for f in hechas)  # noqa: E731
    return {"tareas": n, "tokens_entrada": suma("tokens_entrada"), "tokens_salida": suma("tokens_salida"),
            "tokens_cache_lectura": suma("tokens_cache_lectura"), "tokens_cache_escritura": suma("tokens_cache_escritura"),
            "costo_usd": round(suma("costo_usd"), 6), "costo_por_tarea_usd": round(suma("costo_usd") / n, 6) if n else None,
            "tokens_por_tarea": round((suma("tokens_entrada") + suma("tokens_salida")) / n, 1) if n else None}


# ---------------------------------------------------------------- the regression rule of week 10

LINEA_BASE = RAIZ / "semana-17" / "resultados" / "eval_ci_local.json"
SEMANA13 = RAIZ / "semana-13" / "resultados" / "eval_sdk_low_detalle.jsonl"
ACTIVIDAD7 = S19 / "resultados" / "agentes" / "crudo_directo.json"


def linea_base_semana17(archivo: Path = LINEA_BASE) -> dict[str, bool]:
    """The baseline: week 17's local mini eval on the same 20 tasks, with the same loop and controls (budgets and the
    deterministic layer) that week 19 ported. Only the model's host differs (Anthropic's API, Haiku 5.5 `low`)."""
    return {f["id"]: bool(f["exito"]) for f in json.loads(archivo.read_text(encoding="utf-8"))["subconjunto"]["filas"]}


def semana13_por_tarea(archivo: Path = SEMANA13) -> dict[str, float]:
    """Week 13's success rate per task over its repetitions (in-house loop, Haiku 5.5 `low`, 3 runs per task)."""
    por: dict[str, list] = {}
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            f = json.loads(linea)
            por.setdefault(f["id"], []).append(bool(f["exito"]))
    return {i: sum(v) / len(v) for i, v in por.items()}


def actividad7_por_tarea(archivo: Path = ACTIVIDAD7) -> dict[str, bool]:
    if not archivo.exists():
        return {}
    return {f["id_tarea"]: bool((f.get("verificacion") or {}).get("exito"))
            for f in json.loads(archivo.read_text(encoding="utf-8"))["filas"] if f.get("estado") != "no_corrida"}


def regla_semana10(valor: float, base: float, n: int) -> dict:
    """Week 10's rule (semana-10/ci/eval_ci.umbral_de): threshold = the multiple of 0.05 just below
    (baseline − max(0.03, 1/n)). A regression is a value under the threshold."""
    u = round(umbral_de(base, n), 2)
    return {"base": round(base, 3), "valor": round(valor, 3), "n": n, "umbral": u, "regresion": valor < u}


def comparar_con_lineas_base(filas: list[dict], s17: dict | None = None, s13: dict | None = None,
                             a7: dict | None = None) -> dict:
    s17 = linea_base_semana17() if s17 is None else s17
    s13 = semana13_por_tarea() if s13 is None else s13
    a7 = actividad7_por_tarea() if a7 is None else a7
    por_id = {f["id_tarea"]: _exito(f) for f in filas}
    salida = {"linea_base": "semana 17 local (eval_ci_local.json)", "regla": {}, "semana13": {}, "actividad7": {}}
    for grupo in ("es", "en", "total"):
        ids = [i for i in por_id if grupo == "total" or i.endswith(f"-{grupo}")]
        valor = sum(por_id[i] for i in ids) / len(ids)
        salida["regla"][grupo] = regla_semana10(valor, sum(s17[i] for i in ids) / len(ids), len(ids))
        con13 = [i for i in ids if i in s13]
        salida["semana13"][grupo] = {"n": len(con13), "tasa": round(sum(s13[i] for i in con13) / len(con13), 3) if con13 else None}
    comunes = sorted(set(por_id) & set(a7))
    salida["actividad7"] = {"tareas_comunes": comunes, "aws": sum(por_id[i] for i in comunes), "actividad7": sum(a7[i] for i in comunes)}
    salida["regresion"] = any(r["regresion"] for r in salida["regla"].values())
    return salida


# ---------------------------------------------------------------- access checks (no model call)

def controles_de_acceso(http: Callable, token_analista: str) -> list[dict]:
    """Before the tasks: a request without a token gets 401 from the JWT authorizer, and the analyst's token gets 403 on
    the approval route (no `legacybridge/aprobaciones` scope, ADR 0009). Neither reaches a function."""
    casos = [("POST", "/consultas", None, {"pregunta": "x"}, 401),
             ("POST", "/aprobaciones/no-existe", token_analista, {"decision": "aprobar"}, 403)]
    filas = []
    for metodo, ruta, token, cuerpo, esperado in casos:
        st, _ = http(metodo, ruta, token, cuerpo)
        filas.append({"metodo": metodo, "ruta": ruta, "con_token": token is not None, "esperado": esperado,
                      "obtenido": st, "ok": st == esperado})
    return filas


# ---------------------------------------------------------------- the detail line (week 20's baseline)

CAMPOS_DETALLE = ("id", "idioma", "fase", "exito", "estado", "estado_esperado", "arranque", "latencia_s", "pasos",
                  "herramientas", "tokens_entrada", "tokens_salida", "tokens_cache_lectura", "tokens_cache_escritura",
                  "costo_usd", "trayectoria_ok", "bloqueos_capa", "bloqueos_guardrail", "bloqueos_politica",
                  "veredicto_juez")


def linea_detalle(f: dict, fase: str, veredicto_juez: dict | None = None) -> dict:
    return {"id": f["id_tarea"], "idioma": f["idioma"], "fase": fase, "exito": _exito(f), "estado": f["estado"],
            "estado_esperado": f.get("estado_esperado"), "arranque": (f.get("arranque") or {}).get("clase"),
            "latencia_s": f.get("latencia_s"), "pasos": f.get("pasos"), "herramientas": f.get("herramientas"),
            "tokens_entrada": f.get("tokens_entrada"), "tokens_salida": f.get("tokens_salida"),
            "tokens_cache_lectura": f.get("tokens_cache_lectura"), "tokens_cache_escritura": f.get("tokens_cache_escritura"),
            "costo_usd": f.get("costo_usd"), "trayectoria_ok": (f.get("trayectoria") or {}).get("ok"),
            "bloqueos_capa": f.get("bloqueos_capa"), "bloqueos_guardrail": f.get("bloqueos_guardrail"),
            "bloqueos_politica": f.get("bloqueos_politica"), "veredicto_juez": veredicto_juez}


# The schema of resultados/eval_aws_detalle.jsonl, documented in resultados/eval_aws.md and checked by the tests:
# field -> (accepted JSON types, meaning). One line per task; week 20 reads it as its baseline.
_N = type(None)
ESQUEMA_DETALLE = {
    "id": ((str,), "task id, week 13's id plus the language (s03-es)"),
    "idioma": ((str,), "es or en"),
    "fase": ((str,), "principal (the 20 CI tasks) or calentamiento (the cold warm-up, reported apart)"),
    "exito": ((bool,), "week 13's execution verifier against the rows recomputed on RDS; an aborted task is false"),
    "estado": ((str,), "the API's final state, or no_corrida when the script's cap stopped it"),
    "estado_esperado": ((str, _N), "week 13's expected state"),
    "arranque": ((str, _N), "frio, caliente or desconocido, from the REPORT lines of the task's window"),
    "latencia_s": ((int, float, _N), "POST /consultas to the final GET, seconds"),
    "pasos": ((int, _N), "model turns (lab.run.steps of the agent span)"),
    "herramientas": ((int, _N), "tool calls (execute_tool spans)"),
    "tokens_entrada": ((int, _N), "input tokens of the run"),
    "tokens_salida": ((int, _N), "output tokens of the run"),
    "tokens_cache_lectura": ((int, _N), "prompt-cache read tokens"),
    "tokens_cache_escritura": ((int, _N), "prompt-cache write tokens"),
    "costo_usd": ((int, float, _N), "model cost of the run from the agent span (lab.run.cost_usd)"),
    "trayectoria_ok": ((bool, _N), "week 17's trajectory graders against the frozen reference"),
    "bloqueos_capa": ((int, _N), "decisions of the policy layer that were not allow"),
    "bloqueos_guardrail": ((int, _N), "1 when the run ended on a guardrail intervention"),
    "bloqueos_politica": ((int, _N), "tool calls refused by the gateway's Cedar policies (path b only)"),
    "veredicto_juez": ((dict, _N), "the Bedrock judge's verdict (comparar_jueces.veredicto plus the scores); null "
                                    "for the warm-up and for tasks not judged"),
}
assert tuple(ESQUEMA_DETALLE) == CAMPOS_DETALLE


def validar_detalle(linea: dict) -> list[str]:
    """The problems of one detail line (empty: valid)."""
    if tuple(linea) != CAMPOS_DETALLE:
        return [f"campos {list(linea)}"]
    errores = [f"{k}: {type(linea[k]).__name__}" for k, (tipos, _) in ESQUEMA_DETALLE.items()
               if not isinstance(linea[k], tipos) or (isinstance(linea[k], bool) and bool not in tipos)]
    if linea["fase"] not in ("principal", "calentamiento"):
        errores.append(f"fase {linea['fase']}")
    if linea["arranque"] not in (None, "frio", "caliente", "desconocido"):
        errores.append(f"arranque {linea['arranque']}")
    return errores


def detalle(crudo: dict, juez: dict | None = None) -> list[dict]:
    """The detail lines from the raw run and, when it exists, the judge's output (juez_bedrock.json). The verdict
    uses comparar_jueces' thresholds, fixed before the run."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("comparar_jueces_para_detalle", Path(__file__).with_name("comparar_jueces.py"))
    cj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cj)
    por_tarea = (juez or {}).get("por_tarea") or {}

    def veredicto(id_):
        if id_ not in por_tarea:
            return None
        v = cj.veredicto(por_tarea[id_]["puntajes"])
        return {**v, "puntajes": por_tarea[id_]["puntajes"]}

    return ([linea_detalle(f, "calentamiento") for f in crudo.get("calentamiento", [])]
            + [linea_detalle(f, "principal", veredicto(f["id_tarea"])) for f in crudo["filas"]])


def escribir_detalle(lineas: list[dict], archivo: Path) -> Path:
    errores = {l["id"]: validar_detalle(l) for l in lineas if validar_detalle(l)}
    if errores:
        raise ValueError(f"líneas fuera del esquema: {errores}")
    archivo.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lineas), encoding="utf-8")
    return archivo


# ---------------------------------------------------------------- files

def escribir(nombre: str, datos: Any, cuentas=(), carpeta: Path = SALIDA) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / nombre
    archivo.write_text(json.dumps(redactar(datos, cuentas), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    return archivo


def descartar_previa(carpeta: Path = SALIDA) -> Path | None:
    """comparar.descartar_previa's rule for this run's file: a rerun keeps the previous one, and its spend counts."""
    actual = carpeta / CRUDO
    if not actual.exists():
        return None
    n = 1 + len(list(carpeta.glob("crudo_eval_descartada_*.json")))
    destino = carpeta / f"crudo_eval_descartada_{n}.json"
    actual.rename(destino)
    return destino


def tope_con_lo_previo(carpeta: Path = SALIDA) -> C.Tope:
    tope = C.Tope(usd=TOPE_USD, tokens=TOPE_TOKENS)
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        g = json.loads(archivo.read_text(encoding="utf-8"))["gasto"]
        tope.sumar(g["usd"], g["tokens"])
    return tope


def plan(tareas: list[dict], calentamiento: list[dict]) -> dict:
    lim = C.limite_de_tarea()
    previo = tope_con_lo_previo()
    n = len(tareas) + len(calentamiento)
    return {"simulacion": True, "tareas": [t["id"] for t in tareas], "calentamiento_en_frio": [t["id"] for t in calentamiento],
            "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
            "gastado_en_corridas_previas": {"usd": round(previo.gastado_usd, 6), "tokens": previo.gastado_tokens},
            "limite_por_tarea": {"usd": lim.usd, "tokens": lim.tokens},
            "peor_caso": {"usd": round(lim.usd * n, 4), "tokens": lim.tokens * n},
            "llamadas": ["lambda:Invoke del cargador (esperados, solo lectura)", "cognito-idp:AdminInitiateAuth (analista)",
                         "POST /consultas sin token y POST /aprobaciones con el analista (401 y 403)",
                         f"POST/GET /consultas × {n}", "logs:FilterLogEvents (spans y líneas REPORT)",
                         "lambda:Invoke de la función de herramientas (verificador, copilot_ro)"]}


# ---------------------------------------------------------------- real clients (only with --si)

class AwsEval(C.Aws):  # pragma: no cover - live only
    def __init__(self, perfil: str):
        super().__init__(perfil)
        cfn = self.s.client("cloudformation")
        self.datos = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName="semana19-datos")["Stacks"][0]["Outputs"]}
        self.cargador = self.datos["NombreCargador"]
        self.grupos = {
            "agente": self.lam.get_function_configuration(FunctionName=self.computo["ArnAgente"])["LoggingConfig"]["LogGroup"],
            "consultas": self._grupo_de_consultas(cfn)}

    def _grupo_de_consultas(self, cfn) -> str:
        """CDK adds a hash to the logical id (FuncionConsultas<hash>), so the function is found by its prefix."""
        (nombre,) = [r["PhysicalResourceId"] for r in cfn.describe_stack_resources(StackName="semana19-computo")["StackResources"]
                     if r["ResourceType"] == "AWS::Lambda::Function" and r["LogicalResourceId"].startswith("FuncionConsultas")]
        return self.lam.get_function_configuration(FunctionName=nombre)["LoggingConfig"]["LogGroup"]

    def http(self, metodo, ruta, token, cuerpo):
        if token is not None:
            return super().http(metodo, ruta, token, cuerpo)
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.computo["UrlApi"].rstrip("/") + ruta, method=metodo,
                                     data=json.dumps(cuerpo).encode(), headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, {}
        except urllib.error.HTTPError as e:
            return e.code, {}

    def cargador_invoca(self, evento: dict) -> dict:
        evento = {"secret_arn": self.datos["ArnSecretoBd"], "db_host": self.datos["HostBd"], **evento}
        r = self.lam.invoke(FunctionName=self.cargador, Payload=json.dumps(evento).encode())
        cuerpo = json.loads(r["Payload"].read())
        if r.get("FunctionError"):
            raise RuntimeError(f"el cargador falló: {cuerpo.get('errorType')}")
        return cuerpo

    def reportes(self, desde_s: float, hasta_s: float) -> dict[str, list[str]]:
        logs = self.s.client("logs")
        salida = {}
        for clave, grupo in self.grupos.items():
            lineas, siguiente = [], None
            while True:
                kw = {"logGroupName": grupo, "startTime": int(desde_s * 1000), "endTime": int((hasta_s + 5) * 1000),
                      "filterPattern": '"REPORT RequestId"'}
                if siguiente:
                    kw["nextToken"] = siguiente
                r = logs.filter_log_events(**kw)
                lineas += [e["message"] for e in r.get("events", [])]
                siguiente = r.get("nextToken")
                if not siguiente:
                    break
            salida[clave] = lineas
        return salida


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", action="store_true", help="actuar (por omisión solo simula)")
    ap.add_argument("--informe", action="store_true", help="agrega el archivo crudo, sin AWS")
    a = ap.parse_args(argv)
    tareas, calentamiento = tareas_ci(), tareas_de_calentamiento()
    if a.informe:
        datos = json.loads((SALIDA / CRUDO).read_text(encoding="utf-8"))
        juez = SALIDA / "juez_bedrock.json"
        juez = json.loads(juez.read_text(encoding="utf-8")) if juez.exists() else None
        print(escribir_detalle(detalle(datos, juez), S19 / "resultados" / "eval_aws_detalle.jsonl"))
        print(json.dumps({k: datos[k] for k in ("resumen", "gasto", "acceso")}, ensure_ascii=False, indent=2))
        return 0
    if not a.si:
        print(json.dumps(plan(tareas, calentamiento), ensure_ascii=False, indent=2))
        print("Simulación: no se llamó a AWS. Agrega --si para actuar.")
        return 0
    aws = AwsEval(os.environ.get("S19_PERFIL", "manuel-admin"))
    if aws.camino_desplegado != "directo":
        raise SystemExit(f"el agente desplegado usa {aws.camino_desplegado}; la eval corre en el camino directo")
    todas = tareas + calentamiento
    esperados = aws.cargador_invoca({"modo": "esperados", "consultas": consultas_esperadas(todas)})["esperados"]
    tareas, calentamiento = con_esperados(tareas, esperados), con_esperados(calentamiento, esperados)
    token = aws.token("analista")
    acceso = controles_de_acceso(aws.http, token)
    if not all(c["ok"] for c in acceso):
        print(json.dumps(acceso, ensure_ascii=False, indent=2))
        raise SystemExit("los controles de acceso no dieron 401 y 403: no se manda ninguna tarea")
    previa = descartar_previa()
    if previa:
        print(f"corrida previa conservada como {previa.name}; su gasto sigue en el tope")
    tope = tope_con_lo_previo()
    referencias = CR.cargar()
    medir = lambda t: C.medir_api(t, "directo", token=token, http=aws.http, spans_entre=aws.spans_entre,  # noqa: E731
                                  largo_respuesta=LARGO_RESPUESTA)
    comun = dict(medir=medir, ejecutar_sql=aws.ejecutar_sql, reportes=aws.reportes, tope=tope, referencias=referencias)
    frio = correr(calentamiento, en_paralelo=True, **comun)
    principal = correr(tareas, **comun)
    filas = principal
    datos = {"fecha": time.strftime("%Y-%m-%d"), "acceso": acceso, "calentamiento": frio, "filas": principal,
             "esperados": esperados,   # the rows recomputed on RDS: the judge's reference (juez_bedrock.py)
             "gasto": gasto(frio + principal), "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
             "resumen": {"exito": resumen_exito(filas), "latencia": resumen_latencia(frio + principal),
                         "trayectoria": resumen_trayectoria(filas), "costo": resumen_costo(frio + principal),
                         "comparacion": comparar_con_lineas_base(filas)}}
    print(escribir(CRUDO, datos, [aws.cuenta]))
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
