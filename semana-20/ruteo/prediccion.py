"""Week 20, activity 4, step 4: the R1 prediction (quote v3 for routing), versioned before the live run ($0).

    uv run --group semana20 python semana-20/ruteo/prediccion.py     writes resultados/ruteo/r1_prediccion.json

Input:
- each main task's model calls measured in activity 3's cache run (resultados/cache_detalle.jsonl: per step, the
  input split as Converse reported it and the output), and its fixed prefix (resultados/cache_medicion.json);
- each candidate's prices, from the Price List by SKU (agente/construccion.py PRECIOS_POR_MODELO; a test checks the
  SKUs against resultados/precios.json).

What it assumes, said once:
- the same token counts on every model, step by step, as ADR 0015's hand-worked case (real tokenizers differ, and a
  cheaper model may take more steps or fewer: N);
- the live run's design: RUTEO=r1 with CACHE_PROMPT=historial, so each model's cache mode is CACHE_POR_MODELO;
- the cache hit rate: p = 1 (activity 3 measured 55 hits of 55 possible); p = 0 (no call ever reads) is the bound.

Which tasks escalate, and when, is the unknown: nothing has measured Nova Lite on these tasks. So the prediction gives
routes, each one the router can take (a test checks it), and the mix at which R1 costs what Haiku 4.5 alone does. It
does not predict success: that is what the run measures, under week 10's rule.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
sys.path.insert(0, str(RAIZ / "semana-19"))
from agente import construccion as K  # noqa: E402
from costos import modelo as M  # noqa: E402

DETALLE = S20 / "resultados" / "cache_detalle.jsonl"
MEDICION = S20 / "resultados" / "cache_medicion.json"
SALIDA = S20 / "resultados" / "ruteo" / "r1_prediccion.json"
NOVA, HAIKU, SONNET = K.RUTEO_CANDIDATOS
# Minimum tokens per cache point (prompt-caching docs and model cards, ADR 0015 section 3, read 2026-11-27).
MINIMO = {NOVA: 1000, HAIKU: M.MINIMO_CACHE_HAIKU45, SONNET: 1024}
MAXIMO_CACHEADO_NOVA = 20_000
REAL_ACTIVIDAD_3_USD = 0.505822     # the 20 main tasks of the cache run (resultados/cache.md)
TECHO_TAREA_USD = 0.12              # PRESUPUESTO_TAREA=techo_semana20, the deployed per-task ceiling


@dataclass(frozen=True)
class Llamada:
    """One paid model call: the loop step it serves, its whole input and its output, the model, and whether its answer
    was discarded (a response signal resent the same request to the next model)."""
    paso: int
    entrada: int
    salida: int
    modelo: str
    descartada: bool = False


def cargar_tareas(detalle: Path = DETALLE, medicion: Path = MEDICION) -> list[dict]:
    """The run's tasks in run order (warm-up first), each with its steps' whole input and output."""
    fijo = {f["id"]: f["prefijo_fijo_tokens"] for f in json.loads(medicion.read_text(encoding="utf-8"))["filas"]}
    tareas = []
    for linea in detalle.read_text(encoding="utf-8").splitlines():
        f = json.loads(linea)
        if not f.get("pasos_modelo"):
            continue
        tareas.append({"id": f["id"], "fase": f["fase"], "exito_actividad_3": f["exito"],
                       "prefijo_fijo": fijo[f["id"]],
                       "pasos": [{"total": x["entrada"] + x["lectura"] + x["escritura"], "salida": x["salida"]}
                                 for x in f["pasos_modelo"]]})
    return tareas


def dividir(llamadas: list[Llamada], *, modo_cache: str, prefijo_fijo: int, acierta: bool,
            calientes: set[str]) -> list[dict]:
    """Each call's input split into uncached, read and written, ADR 0015 section 3, with the model's own mode
    (CACHE_POR_MODELO) when caching is on. A history point goes on every call but the task's first; Nova and Sonnet
    also put a point after the system prompt, which covers the fixed prefix. A call reads the longest prefix its
    model holds: the previous call on that model, or the fixed prefix when `calientes` says it is warm (another task
    wrote it). With `acierta` False it reads nothing (another server each time). `calientes` is updated."""
    cacheado: dict[str, int] = {}
    pasos = []
    for c in llamadas:
        modo = "off" if modo_cache == "off" else K.CACHE_POR_MODELO[c.modelo]
        minimo = MINIMO[c.modelo]
        historial = modo in ("historial", "historial+sistema") and c.paso > 0
        sistema = modo == "historial+sistema" and prefijo_fijo >= minimo
        if modo == "off" or not (historial or sistema):
            pasos.append({"sin_cache": c.entrada, "lectura": 0, "escritura": 0})
            continue
        disponible = max(cacheado.get(c.modelo, 0), prefijo_fijo if sistema and c.modelo in calientes else 0)
        leido = disponible if acierta else 0
        if historial and c.entrada >= minimo:
            hasta = c.entrada
        elif sistema:
            hasta = prefijo_fijo
        else:
            hasta = 0
        escrito = max(hasta - leido, 0) if hasta else 0
        if c.modelo == NOVA and hasta > MAXIMO_CACHEADO_NOVA:
            raise ValueError(f"Nova caches at most {MAXIMO_CACHEADO_NOVA} tokens; this prefix has {hasta}")
        pasos.append({"sin_cache": c.entrada - leido - escrito, "lectura": leido, "escritura": escrito})
        cacheado[c.modelo] = hasta or cacheado.get(c.modelo, 0)
        if sistema:
            calientes.add(c.modelo)
    return pasos


def costo(llamadas: list[Llamada], pasos: list[dict]) -> float:
    """USD of the calls at each one's model prices (the discarded ones too: they are paid)."""
    total = 0.0
    for c, p in zip(llamadas, pasos):
        precio = K.PRECIOS_POR_MODELO[c.modelo]
        total += precio.usd(p["sin_cache"], c.salida) + precio.usd_cache(p["lectura"], p["escritura"])
    return total


def _todos(modelo: str):
    return lambda pasos: [Llamada(i, x["total"], x["salida"], modelo) for i, x in enumerate(pasos)]


def _desde(cambios: dict[int, str]):
    """Request signals: from step k on, the model cambios[k] (the latest k at or before the step)."""
    def ruta(pasos):
        llamadas, modelo = [], NOVA
        for i, x in enumerate(pasos):
            modelo = cambios.get(i, modelo)
            llamadas.append(Llamada(i, x["total"], x["salida"], modelo))
        return llamadas
    return ruta


def _abstencion_al_final(pasos):
    """Nova serves every step; its last answer abstains, so the same request goes again to Haiku 4.5."""
    *antes, ultimo = _todos(NOVA)(pasos)
    return [*antes, Llamada(ultimo.paso, ultimo.entrada, ultimo.salida, NOVA, descartada=True),
            Llamada(ultimo.paso, ultimo.entrada, ultimo.salida, HAIKU)]


def _peor(pasos):
    """The most the rules allow on these tokens: the first answer is resent twice, so Sonnet 4.6 serves every step and
    the first step is also paid on Nova Lite and Haiku 4.5."""
    x = pasos[0]
    return [Llamada(0, x["total"], x["salida"], NOVA, descartada=True),
            Llamada(0, x["total"], x["salida"], HAIKU, descartada=True),
            *_todos(SONNET)(pasos)]


ESCENARIOS = {
    "solo_nova": _todos(NOVA),
    "abstencion_al_final": _abstencion_al_final,
    "nova_y_haiku_desde_el_paso_2": _desde({1: HAIKU}),
    "nova_haiku_y_sonnet_desde_el_paso_3": _desde({1: HAIKU, 2: SONNET}),
    "peor": _peor,
}


def _correr(tareas: list[dict], ruta, acierta: bool) -> list[dict]:
    calientes: set[str] = set()
    filas = []
    for t in tareas:
        llamadas = ruta(t["pasos"])
        pasos = dividir(llamadas, modo_cache="historial", prefijo_fijo=t["prefijo_fijo"], acierta=acierta,
                        calientes=calientes)
        filas.append({"id": t["id"], "usd": costo(llamadas, pasos), "llamadas": [x.modelo for x in llamadas]})
    return filas


def _resumen(filas: list[dict]) -> dict:
    costos = [f["usd"] for f in filas]
    llamadas = [m for f in filas for m in f["llamadas"]]
    return {"total": round(sum(costos), 6), "mediana": round(statistics.median(costos), 6),
            "p95": round(M.percentil(costos, 0.95), 6), "maximo_tarea": round(max(costos), 6),
            "llamadas": len(llamadas),
            "llamadas_por_modelo": {m: llamadas.count(m) for m in K.RUTEO_CANDIDATOS}}


def predecir() -> dict:
    tareas = cargar_tareas()
    principales = [t for t in tareas if t["fase"] == "principal"]
    haiku = _resumen(_correr(principales, _todos(HAIKU), True))
    escenarios = {n: {**_resumen(_correr(principales, r, True)),
                      "sin_acierto_total": round(sum(f["usd"] for f in _correr(principales, r, False)), 6)}
                  for n, r in ESCENARIOS.items()}
    barato, caro = escenarios["solo_nova"]["total"], escenarios["peor"]["total"]
    # Per task, the dearest route with and without cache hits: the most the rules allow on these tokens. The budget
    # stops a task at its ceiling, so each task's bound is the smaller of the two.
    por_tarea = [max(f["usd"] for r in ESCENARIOS.values() for a in (True, False) for f in _correr([t], r, a))
                 for t in principales]
    con_techo = sum(min(x, TECHO_TAREA_USD) for x in por_tarea)
    return {
        "fecha": "2026-11-27",
        "fuente": "resultados/cache_detalle.jsonl (activity 3, per-step tokens); resultados/cache_medicion.json (fixed "
                  "prefix); agente/construccion.py PRECIOS_POR_MODELO (Price List, by SKU)",
        "diseno": {"RUTEO": "r1", "CACHE_PROMPT": "historial", "CACHE_TTL": "5m",
                   "cache_por_modelo": K.CACHE_POR_MODELO, "adr": "semana-19/arquitectura/adr/0015-ruteo-de-modelos.md"},
        "supuestos": ["the same tokens per step on every model (ADR 0015's hand-worked case)",
                      "p = 1 for the scenarios (activity 3: 55 of 55 possible reads hit); sin_acierto_total is p = 0",
                      "Nova Lite's cache write at 0 USD, its SKU's price: with no hit Nova writes for free, so "
                      "solo_nova's sin_acierto_total is below its total"],
        "referencia_haiku": {"modelo_usd": haiku["total"], "real_actividad_3_usd": REAL_ACTIVIDAD_3_USD,
                             "error_del_modelo_pct": round(100 * (haiku["total"] / REAL_ACTIVIDAD_3_USD - 1), 1)},
        "escenarios": escenarios,
        "ahorro_vs_haiku_pct": {n: round(100 * (1 - e["total"] / haiku["total"]), 1) for n, e in escenarios.items()},
        # The share of tasks that may take the worst route (the rest staying on Nova) before R1 costs what Haiku does.
        "equilibrio_fraccion_peor": round((haiku["total"] - barato) / (caro - barato), 3),
        "exito": "N: nothing has measured Nova Lite on these 20 tasks; the run measures it, under week 10's rule "
                 "(R0: Haiku 4.5 locally 16/20; activity 3 deployed 17/20)",
        "latencia": "N: the run measures it",
        "corrida": {"tareas": len(principales), "maximo_por_las_reglas_usd": round(sum(por_tarea), 6),
                    "techo_por_tarea_usd": TECHO_TAREA_USD,
                    "tareas_que_tocarian_el_techo": sum(x > TECHO_TAREA_USD for x in por_tarea),
                    "maximo_con_el_techo_usd": round(con_techo, 6),
                    "tope_usd": math.ceil(con_techo * 4) / 4},
    }


def main() -> int:  # pragma: no cover - the CLI around predecir()
    pr = predecir()
    SALIDA.write_text(json.dumps(pr, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(pr, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
