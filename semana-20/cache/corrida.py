"""Week 20, activity 3, step 4: the 20 tasks with prompt caching on (CACHE_PROMPT=historial), against the corrected run.

    .venv/bin/python semana-20/cache/corrida.py                                    simulation: plan and caps, no AWS
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/cache/corrida.py --si       the run (Manuel runs it)
    .venv/bin/python semana-20/cache/corrida.py --informe                          detail and comparison, offline
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/cache/corrida.py --cost-explorer --si   next day, 0.01 USD

It is activity 1's corrected run (`linea_base/corrida.py`, reused through its `Corrida`, not copied): the warm-up and
the 10 + 10 CI golden tasks through the public API with real Cognito tokens, the week 13 verifier, the week 17
graders and the week 10 rule. What changes:
- the deployed agent must run CACHE_PROMPT=historial (and the 0.12 USD / 100,000-token ceiling); nothing is sent
  otherwise;
- its own caps, over its own files (`resultados/cache/`);
- the detail (`resultados/cache_detalle.jsonl`) has the corrected run's columns plus, per task, each model call's
  tokens (input, output, cache read and written), cost and duration, from the agent's chat spans;
- `--informe` also writes `resultados/cache_comparacion.json`: task by task against the corrected run and against
  the prediction committed before the run (`resultados/cache_prediccion.json`), which it reads and never changes.

The Region that served each call is not recorded: Converse's response has no Region field (API reference, read
2026-11-25). The hit rate is measured from the tokens instead: a call that could read (the call before it wrote)
and read nothing was served elsewhere.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
SALIDA = S20 / "resultados" / "cache"
DETALLE = S20 / "resultados" / "cache_detalle.jsonl"
DETALLE_CORREGIDA = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
PREDICCION = S20 / "resultados" / "cache_prediccion.json"
COMPARACION = S20 / "resultados" / "cache_comparacion.json"
# Caps over this run's files (any rerun included). The prediction's worst case (no call ever reads, every write at
# 1.25x) is 1.175 USD for the 22 tasks; the cap leaves room for that plus one task at the 0.12 ceiling.
TOPE_USD = 1.50
TOPE_TOKENS = 2_200_000     # 22 tasks at the 100,000-token ceiling, counting cache tokens as tokens (eval_aws.tokens_de)
COSTO_ESPERADO_TAREA = 0.0257   # prediction, optimistic scenario with the warm-up: 0.565418 USD / 22


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def linea_base():
    return _cargar("corrida_linea_base_cache", S20 / "linea_base" / "corrida.py")


# ---------------------------------------------------------------- pure parts (tested)

def pasos_de(fila: dict) -> list[dict]:
    """Each model call of a task: the chat spans in step order, with the durations from the agent line."""
    chat = sorted(fila.get("spans_modelo") or [], key=lambda a: int(a.get("lab.step") or 0))
    ms = list(fila.get("duracion_pasos_ms") or [])
    return [{"paso": a.get("lab.step"), "entrada": a.get("gen_ai.usage.input_tokens"),
             "salida": a.get("gen_ai.usage.output_tokens"),
             "lectura": a.get("gen_ai.usage.cache_read.input_tokens") or 0,
             "escritura": a.get("gen_ai.usage.cache_creation.input_tokens") or 0,
             "usd": a.get("lab.cost.usd"), "ms": ms[i] if i < len(ms) else None} for i, a in enumerate(chat)]


def aciertos(pasos: list[dict]) -> dict:
    """Calls that could read (the call before them wrote) and how many did read."""
    posibles = [p for previo, p in zip(pasos, pasos[1:]) if previo["escritura"] > 0]
    leyeron = [p for p in posibles if p["lectura"] > 0]
    return {"posibles": len(posibles), "leyeron": len(leyeron),
            "tasa": round(len(leyeron) / len(posibles), 4) if posibles else None}


def columnas(datos: dict, lineas: list[dict]) -> list[dict]:
    """The corrected run's detail lines plus the cache columns of each task."""
    filas = {f["id_tarea"]: f for f in datos.get("calentamiento", []) + datos.get("filas", [])}
    salida = []
    for l in lineas:
        pasos = pasos_de(filas.get(l["id"], {}))
        ms = [p["ms"] for p in pasos if p["ms"] is not None]
        salida.append({**l, "pasos_modelo": pasos, "aciertos_cache": aciertos(pasos),
                       "latencia_primer_paso_ms": ms[0] if ms else None,
                       "latencia_pasos_siguientes_ms_mediana": statistics.median(ms[1:]) if len(ms) > 1 else None,
                       "region": None})
    return salida


def _resumen(v: list[float], percentil) -> dict:
    return {"total": round(sum(v), 6), "mediana": round(statistics.median(v), 6), "p95": round(percentil(v, 0.95), 6)}


def comparar(cache: list[dict], corregida: list[dict], prediccion: dict, percentil) -> dict:
    """Task by task against the corrected run and the prediction (its optimistic scenario is quote v3's central)."""
    base = {l["id"]: l for l in corregida if l["fase"] == "principal"}
    pred = {t["id"]: t for t in prediccion["por_tarea"]}
    principales = [l for l in cache if l["fase"] == "principal"]
    tareas = []
    for l in principales:
        b, p = base.get(l["id"], {}), pred.get(l["id"], {})
        real, esperado = l.get("costo_usd"), p.get("optimista")
        tareas.append({"id": l["id"], "costo_usd": real, "corregida_usd": b.get("costo_usd"), "predicho_usd": esperado,
                       "error_prediccion_pct": None if not (real and esperado) else round(100 * (real - esperado) / esperado, 1),
                       "exito": l.get("exito"), "exito_corregida": b.get("exito"),
                       "lectura": l.get("tokens_cache_lectura"), "escritura": l.get("tokens_cache_escritura"),
                       "aciertos": l.get("aciertos_cache"), "pasos": l.get("pasos"), "pasos_corregida": b.get("pasos")})
    costos = [t["costo_usd"] for t in tareas if t["costo_usd"] is not None]
    posibles = sum((l.get("aciertos_cache") or {}).get("posibles", 0) for l in principales)
    leyeron = sum((l.get("aciertos_cache") or {}).get("leyeron", 0) for l in principales)

    def latencias(clase: str) -> dict:
        de = [l for l in cache if l.get("arranque") == clase]
        primero = [l["latencia_primer_paso_ms"] for l in de if l.get("latencia_primer_paso_ms") is not None]
        siguientes = [l["latencia_pasos_siguientes_ms_mediana"] for l in de
                      if l.get("latencia_pasos_siguientes_ms_mediana") is not None]
        return {"tareas": len(de), "primer_paso_ms_mediana": statistics.median(primero) if primero else None,
                "pasos_siguientes_ms_mediana": statistics.median(siguientes) if siguientes else None}

    total_real = sum(costos)
    total_pred = prediccion["escenarios"]["optimista"]["total"]
    return {
        "tareas": tareas,
        "costo": {"cache": _resumen(costos, percentil),
                  "corregida": _resumen([b["costo_usd"] for b in base.values()], percentil),
                  "predicho_optimista": {k: prediccion["escenarios"]["optimista"][k] for k in ("total", "mediana", "p95")},
                  "rango_predicho": {k: prediccion["escenarios"][k]["total"] for k in ("optimista", "pesimista", "peor")},
                  "error_total_pct": round(100 * (total_real - total_pred) / total_pred, 1) if costos else None},
        "aciertos": {"posibles": posibles, "leyeron": leyeron,
                     "tasa": round(leyeron / posibles, 4) if posibles else None,
                     "equilibrio_predicho": prediccion["equilibrio_p_acierto"]},
        "latencia": {"frio": latencias("frio"), "caliente": latencias("caliente")},
        "exito": {"cache": sum(1 for t in tareas if t["exito"]), "corregida": sum(1 for t in tareas if t["exito_corregida"]),
                  "tareas": len(tareas)},
        "cortes_por_presupuesto": {"cache": sum(1 for l in cache if l.get("estado") == "limite_alcanzado"),
                                   "corregida": sum(1 for l in corregida if l.get("estado") == "limite_alcanzado")},
    }


def corrida(LB):
    return LB.Corrida(salida=SALIDA, detalle=DETALLE, tope_usd=TOPE_USD, tope_tokens=TOPE_TOKENS,
                      costo_esperado_tarea=COSTO_ESPERADO_TAREA,
                      exigir={"PRESUPUESTO_TAREA": LB.PRESUPUESTO, "CACHE_PROMPT": "historial"},
                      columnas_detalle=columnas)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", "--yes", action="store_true", help="act (by default it only simulates)")
    ap.add_argument("--informe", "--report", action="store_true", help="the detail and the comparison, without AWS")
    ap.add_argument("--cost-explorer", action="store_true", help="GetCostAndUsage for the run's day (0.01 USD)")
    a = ap.parse_args(argv)
    LB = linea_base()
    c = corrida(LB)
    if a.cost_explorer:
        A = _cargar("atribucion_para_cache", S20 / "atribucion" / "corrida.py")
        E = LB._eval_aws()
        consulta = A.consulta_cost_explorer(json.loads((SALIDA / "crudo_eval.json").read_text())["fecha"])
        if not a.si:
            print(json.dumps(consulta, indent=2))
            print("Simulation: no AWS calls were made. Add --si (--yes) to act (0.01 USD).")
            return 0
        import boto3  # noqa: PLC0415
        ce = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "manuel-admin")).client("ce", region_name="us-east-1")
        r = ce.get_cost_and_usage(**consulta)
        grupos = [{"claves": g["Keys"], "usd": float(g["Metrics"]["UnblendedCost"]["Amount"])}
                  for d in r["ResultsByTime"] for g in d["Groups"]]
        print(E.escribir("cost_explorer.json", {"consulta": consulta, "grupos": grupos}, carpeta=SALIDA))
        return 0
    rc = LB.main(["--informe"] if a.informe else (["--si"] if a.si else []), corrida=c)
    if (a.informe or a.si) and DETALLE.exists():
        E = LB._eval_aws()
        cache = [json.loads(x) for x in DETALLE.read_text(encoding="utf-8").splitlines() if x.strip()]
        corregida = [json.loads(x) for x in DETALLE_CORREGIDA.read_text(encoding="utf-8").splitlines() if x.strip()]
        sys.path.insert(0, str(S20.parent / "semana-19"))
        from costos import modelo as M  # noqa: PLC0415
        comp = comparar(cache, corregida, json.loads(PREDICCION.read_text(encoding="utf-8")), M.percentil)
        datos = json.loads((SALIDA / "crudo_eval.json").read_text(encoding="utf-8"))
        comp["regla_semana_10"] = datos["resumen"]["comparacion"]
        print(E.escribir(COMPARACION.name, comp, carpeta=COMPARACION.parent))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
