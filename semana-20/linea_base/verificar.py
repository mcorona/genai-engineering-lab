"""Week 20, activity 1: the $0 checks of the baseline and of the regression gate.

    uv run --group semana20 python semana-20/linea_base/verificar.py

It reads only files of the repository, makes no AWS call, and writes `resultados/linea_base_verificacion.json`.
It exits with 1 if a required check fails:
- the plan's baseline table (`Fas5Sema20.md`, "What is measured as the baseline"), recomputed from
  `semana-19/resultados/eval_aws_detalle.jsonl`. Every figure must match;
- the week 19 hand-off (the same list as `preparar/verificar_entorno.py`);
- the prices file (`resultados/precios.json`, from `precios.py --si`): Haiku 4.5's on-demand, cache and batch rows.

Not required checks, reported:
- the same figures over the 20 main tasks only, without the 2 warm-up rows the plan's table includes;
- the regression gate: whether a corrected week 19 run exists. Today it does not, so the gate is open;
- the size of the cacheable prefix (system prompt plus tool definitions) against Haiku 4.5's minimum per cache point.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S20 = AQUI.parent
RAIZ = S20.parent
S19 = RAIZ / "semana-19"
LINEA_BASE = S19 / "resultados" / "eval_aws_detalle.jsonl"
EVAL_MD = S19 / "resultados" / "eval_aws.md"
PRECIOS = S20 / "resultados" / "precios.json"
SALIDA = S20 / "resultados" / "linea_base_verificacion.json"
CORRIDA = S20 / "resultados" / "corrida_corregida" / "crudo_eval.json"
# Manuel's decision of 2026-11-23 on the corrected run (16/20, still a regression under week 10's rule): it becomes
# week 20's baseline, stated as not passing; the remaining failures are model quality and go to activity 4.
DECISION_COMPUERTA = {"estado": "aceptada_sin_pasar", "fecha": "2026-11-23", "por": "Manuel",
                      "motivo": "c02 (both languages) and r05 (both languages) fail on model quality, not on the "
                                "budget; activity 4 escalates them to a stronger model, measured against this run"}

# The plan's table, as written in Fas5Sema20.md. A change here is a change of the plan, with its Log entry.
PLAN = {"con_costo": 19, "costo_mediana": 0.03708, "costo_max": 0.06301, "entrada_mediana": 26266,
        "salida_mediana": 1348, "cache_lectura": 0, "cache_escritura": 0, "pasos_mediana": 6, "pasos_max": 8,
        "latencia_mediana": 23.6, "latencia_max": 49.95, "exitos": 9, "tareas": 20}
# Docs (prompt-caching.html, read 2026-11-23): Haiku 4.5 caches from 4,096 tokens per cache point, at most 4 points.
MIN_TOKENS_PUNTO_CACHE_HAIKU45 = 4096
# The loop's measured characters per token on the first call (semana-17/presupuestos/estimacion.py).
CHARS_POR_TOKEN_PRIMERA = 2.7


def filas(ruta: Path = LINEA_BASE) -> list[dict]:
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def cifras(fs: list[dict]) -> dict:
    """The plan's figures over `fs`. Cost, tokens, steps and latency come from the rows with a cost (the rows that ran)."""
    c = [f for f in fs if f.get("costo_usd")]
    principal = [f for f in fs if f.get("fase") == "principal"]
    return {"filas": len(fs), "con_costo": len(c),
            "costo_mediana": round(statistics.median(f["costo_usd"] for f in c), 5),
            "costo_max": round(max(f["costo_usd"] for f in c), 5),
            "entrada_mediana": statistics.median(f["tokens_entrada"] for f in c),
            "salida_mediana": statistics.median(f["tokens_salida"] for f in c),
            "cache_lectura": sum(f.get("tokens_cache_lectura") or 0 for f in fs),
            "cache_escritura": sum(f.get("tokens_cache_escritura") or 0 for f in fs),
            "pasos_mediana": statistics.median(f["pasos"] for f in c), "pasos_max": max(f["pasos"] for f in c),
            "latencia_mediana": round(statistics.median(f["latencia_s"] for f in c), 2),
            "latencia_max": round(max(f["latencia_s"] for f in c), 2),
            "exitos": sum(1 for f in principal if f.get("exito")), "tareas": len(principal)}


def comparar(calculadas: dict, plan: dict = PLAN) -> dict:
    distintas = {k: {"plan": v, "calculada": calculadas.get(k)} for k, v in plan.items() if calculadas.get(k) != v}
    return {"ok": not distintas, "distintas": distintas}


def fallas(fs: list[dict]) -> dict:
    """Each failed main task with its state and reason group, for the regression diagnosis."""
    grupos: dict[str, list[str]] = {}
    for f in fs:
        if f.get("fase") != "principal" or f.get("exito"):
            continue
        g = {"limite_alcanzado": "presupuesto_tarea", "no_corrida": "tope_del_script"}.get(f["estado"], f["estado"])
        if f["estado"] == "respondida":
            g = "respuesta_incorrecta"
        grupos.setdefault(g, []).append(f["id"])
    return grupos


def compuerta(ruta_md: Path = EVAL_MD, ruta_corrida: Path = CORRIDA) -> dict:
    """The regression gate: week 19's verdict, then the corrected run's (corrida.py), then Manuel's decision on it."""
    regresion19 = "**Regression: yes.**" in ruta_md.read_text(encoding="utf-8")
    salida = {"regresion_semana19": regresion19, "corrida_corregida": ruta_corrida.exists()}
    if not ruta_corrida.exists():
        return {**salida, "estado": "abierta" if regresion19 else "cerrada",
                "nota": "week 20 fixes the cause and re-runs the 20 tasks, estimated and capped, with Manuel's OK"}
    d = json.loads(ruta_corrida.read_text(encoding="utf-8"))
    comparacion, exito = d["resumen"]["comparacion"], d["resumen"]["exito"]["total"]
    salida.update({"exitos": exito["exito"], "tareas": exito["n"], "regresion": comparacion["regresion"],
                   "cortes_por_presupuesto": sum(1 for f in d["filas"] if f.get("motivo") == "presupuesto_tarea")})
    if not comparacion["regresion"]:
        return {**salida, "estado": "cerrada"}
    return {**salida, "estado": DECISION_COMPUERTA["estado"], "decision": DECISION_COMPUERTA}


def precios(ruta: Path = PRECIOS) -> dict:
    """Haiku 4.5's rows in the prices file, and the ratios week 20 relies on (cache read 0.1x, write 1.25x, batch 0.5x)."""
    if not ruta.exists():
        return {"ok": False, "motivo": "falta resultados/precios.json: correr precios.py --si"}
    d = json.loads(ruta.read_text(encoding="utf-8"))
    h = {f["uso"].split(":", 1)[-1]: f["precios"][0]["usd"] for f in d["precios"]
         if f.get("modelo") == "Claude Haiku 4.5" and f["precios"]}
    claves = {"entrada": "USE1_InputTokenCount-Units", "salida": "USE1_OutputTokenCount-Units",
              "cache_lectura": "USE1_CacheReadInputTokenCount-Units",
              "cache_escritura_5m": "USE1_CacheWriteInputTokenCount-Units",
              "cache_escritura_1h": "USE1_CacheWrite1hInputTokenCount-Units",
              "lote_entrada": "USE1_InputTokenCount_Batch-Units", "lote_salida": "USE1_OutputTokenCount_Batch-Units"}
    v = {k: h.get(u) for k, u in claves.items()}
    if None in v.values():
        return {"ok": False, "faltan": [k for k, x in v.items() if x is None]}
    razones = {"cache_lectura/entrada": round(v["cache_lectura"] / v["entrada"], 4),
               "cache_escritura_5m/entrada": round(v["cache_escritura_5m"] / v["entrada"], 4),
               "cache_escritura_1h/entrada": round(v["cache_escritura_1h"] / v["entrada"], 4),
               "lote_entrada/entrada": round(v["lote_entrada"] / v["entrada"], 4),
               "lote_salida/salida": round(v["lote_salida"] / v["salida"], 4)}
    return {"ok": True, "fecha": d["fecha"], "usd_por_millon_regional": v, "razones": razones}


def prefijo_cacheable() -> dict:
    """System prompt plus tool definitions of the week 13 loop the agent runs, against the minimum per cache point."""
    sys.path.insert(0, str(RAIZ / "semana-13"))
    try:
        from agente import loop  # noqa: PLC0415  (semana-13 on sys.path)
    except Exception as e:  # noqa: BLE001
        return {"alcanza": None, "motivo": f"could not import the week 13 loop: {type(e).__name__}"}
    finally:
        sys.path.remove(str(RAIZ / "semana-13"))
    herramientas = loop.definiciones() + [loop.herramienta_responder()]
    caracteres = len(loop.SISTEMA) + len(json.dumps(herramientas, ensure_ascii=False))
    tokens = round(caracteres / CHARS_POR_TOKEN_PRIMERA)
    return {"caracteres": caracteres, "herramientas": len(herramientas), "tokens_aprox": tokens,
            "minimo_haiku45": MIN_TOKENS_PUNTO_CACHE_HAIKU45, "alcanza": tokens >= MIN_TOKENS_PUNTO_CACHE_HAIKU45}


def main() -> int:
    fs = filas()
    todas, principal = cifras(fs), cifras([f for f in fs if f.get("fase") == "principal"])
    informe = {"fecha": date.today().isoformat(), "fuente": "semana-19/resultados/eval_aws_detalle.jsonl",
               "plan": PLAN, "todas_las_filas": todas, "contra_el_plan": comparar(todas),
               "solo_principales": principal, "fallas": fallas(fs), "compuerta": compuerta(),
               "precios": precios(), "prefijo_cacheable": prefijo_cacheable()}
    spec = importlib.util.spec_from_file_location("verificar_entorno20", S20 / "preparar" / "verificar_entorno.py")
    entorno = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entorno)
    informe["traspaso"] = entorno.traspaso()
    informe["ok"] = (informe["contra_el_plan"]["ok"] and informe["precios"]["ok"]
                     and all(informe["traspaso"].values()))
    SALIDA.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("ok", "contra_el_plan", "fallas", "compuerta", "prefijo_cacheable")},
                     ensure_ascii=False, indent=1))
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
