"""Week 20, activity 3, step 1: the cacheable prefix of each step, measured offline ($0) from the corrected run.

    .venv/bin/python semana-20/cache/medir.py          writes resultados/cache_medicion.json

What it measures, per task of the corrected run (resultados/corrida_corregida/crudo_eval.json, 2026-11-23):
- the fixed prefix: the tool definitions and the system prompt exactly as the deployed agent sends them to Converse
  (agente/converse_adaptador.py over the week 13 loop's SISTEMA and the week 19 catalog);
- the history at the start of each step, and the first step whose cacheable prefix reaches Haiku 4.5's minimum of
  4,096 tokens per cache point.

How tokens are counted. The repository has no tokenizer for Haiku 4.5 (week 20 activity 1 used characters / 2.7).
The saved spans hold, per task, the real input and output tokens (Converse's usage, summed), the number of model
calls, and per tool call its argument and result sizes in characters. They do not hold each call's tokens. So:
- each task gets its own characters-per-token ratio, fitted so that the input of its steps, rebuilt from the
  characters, sums to the real input tokens of the task;
- the history of step k = (fixed prefix + task message + tool results of the steps before k) / ratio + the output
  tokens of the steps before k (the task's output split evenly over its calls);
- the tool calls are spread in order over the calls that requested tools (the spans number tool calls, not model
  calls), and the last call is the one that answers.
It is an estimate. Its margin is the spread of the fitted ratios across tasks (reported as `razon_por_tarea`), and the
fixed prefix is also given at the lowest ratio (the most tokens), which is the bound the minimum test uses.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
S19 = RAIZ / "semana-19"
CRUDO = S20 / "resultados" / "corrida_corregida" / "crudo_eval.json"
SALIDA = S20 / "resultados" / "cache_medicion.json"
MINIMO_HAIKU45 = 4096      # tokens per cache point, cumulative over the prefix (prompt-caching docs, 2026-11-25)
CHARS_POR_TOKEN_ACTIVIDAD1 = 2.7


def _semana19():
    for ruta in (S19, RAIZ / "semana-17"):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    from agente import capa_determinista as C  # noqa: PLC0415
    from agente import construccion as K  # noqa: PLC0415
    from agente.converse_adaptador import peticion_a_converse  # noqa: PLC0415
    from ia import prompts_sistema  # noqa: PLC0415
    from ia.config import NOMBRE_EMPRESA  # noqa: PLC0415
    _, bucle = K.cargar_bucle_semana13()
    return C, bucle, peticion_a_converse, prompts_sistema, NOMBRE_EMPRESA


def prefijo_fijo() -> dict:
    """The tools and the system prompt of the deployed agent, in characters of their Converse JSON."""
    C, bucle, peticion, prompts, empresa = _semana19()
    herramientas = C.definiciones_semana19() + [bucle.herramienta_responder()]
    req = peticion({"system": bucle.SISTEMA, "tools": herramientas, "messages": [], "max_tokens": 1},
                   modelo_id="x")
    pm_en = prompts.PROMPTS["en"].replace("{{nombre_empresa}}", empresa["en"])
    return {"caracteres": len(json.dumps(req["toolConfig"], ensure_ascii=False))
                          + len(json.dumps(req["system"], ensure_ascii=False)),
            "caracteres_sistema": len(bucle.SISTEMA), "herramientas": [h["name"] for h in herramientas],
            "sistema_igual_a_prompt_management_en": pm_en == bucle.SISTEMA}


def tareas_golden() -> dict[str, dict]:
    tareas = {}
    for idioma in ("es", "en"):
        for linea in (RAIZ / "semana-13" / "golden" / f"tareas_{idioma}.jsonl").read_text(encoding="utf-8").splitlines():
            if linea.strip():
                t = json.loads(linea)
                tareas[t["id"]] = t
    return tareas


def resultados_por_paso(fila: dict) -> list[int]:
    """Result characters added to the history by each model call (the last call answers and adds none)."""
    n = fila["pasos"]
    llamadas = [s.get("lab.tool.result.chars", 0) for s in fila.get("spans_herramientas", [])]
    por_paso = [0] * n
    if n > 1:
        for i, chars in enumerate(llamadas):
            por_paso[min(i * (n - 1) // len(llamadas), n - 2)] += chars
    return por_paso


def historial(fila: dict, fijo: int, tarea_chars: int) -> dict:
    """The input tokens at each step, rebuilt from characters with the task's own fitted ratio."""
    n, entrada, salida = fila["pasos"], fila["tokens_entrada"], fila["tokens_salida"]
    res = resultados_por_paso(fila)
    salida_paso = salida / n
    chars = [fijo + tarea_chars + sum(res[:k]) for k in range(n)]
    tokens_de_salida = [salida_paso * k for k in range(n)]
    razon = sum(chars) / (entrada - sum(tokens_de_salida))
    pasos = [round(c / razon + o) for c, o in zip(chars, tokens_de_salida)]
    pasos[-1] += entrada - sum(pasos)       # rounding: the steps sum to the real input exactly
    return {"razon": razon, "entrada_por_paso": pasos, "salida_por_paso": [round(salida_paso)] * n}


def medir(crudo: Path = CRUDO) -> dict:
    datos = json.loads(crudo.read_text(encoding="utf-8"))
    fijo = prefijo_fijo()
    golden = tareas_golden()
    _, bucle, *_ = _semana19()
    filas = []
    orden = sorted(datos["calentamiento"] + datos["filas"], key=lambda f: f["inicio"])
    for previa, f in zip([None] + orden[:-1], orden):
        tarea_chars = len(bucle.mensaje_tarea(golden[f["id_tarea"]]))
        h = historial(f, fijo["caracteres"], tarea_chars)
        cruce = next((k + 1 for k, t in enumerate(h["entrada_por_paso"]) if t >= MINIMO_HAIKU45), None)
        filas.append({
            "id": f["id_tarea"], "fase": "calentamiento" if f in datos["calentamiento"] else "principal",
            "pasos": f["pasos"], "tokens_entrada": f["tokens_entrada"], "tokens_salida": f["tokens_salida"],
            "costo_usd": f["costo_usd"], "exito": f.get("verificacion", {}).get("exito"),
            "razon_chars_por_token": round(h["razon"], 3),
            "prefijo_fijo_tokens": round(fijo["caracteres"] / h["razon"]),
            "entrada_por_paso": h["entrada_por_paso"], "salida_por_paso": h["salida_por_paso"],
            "paso_que_alcanza_el_minimo": cruce,
            "segundos_por_paso": round(f["latencia_s"] / f["pasos"], 2),
            "segundos_desde_la_consulta_anterior": None if previa is None else round(f["inicio"] - previa["fin"], 2),
        })
    razones = [x["razon_chars_por_token"] for x in filas]
    principales = [x for x in filas if x["fase"] == "principal"]
    cruces = [x["paso_que_alcanza_el_minimo"] for x in principales]
    gaps = [x["segundos_desde_la_consulta_anterior"] for x in filas if x["segundos_desde_la_consulta_anterior"] is not None]
    return {
        "fuente": "semana-20/resultados/corrida_corregida/crudo_eval.json (2026-11-23)",
        "minimo_por_punto_haiku45": MINIMO_HAIKU45,
        "metodo": "characters per token fitted per task to its real input tokens (see the module docstring)",
        "prefijo_fijo": {**fijo,
                         "tokens_razon_mediana": round(fijo["caracteres"] / statistics.median(razones)),
                         "tokens_razon_minima": round(fijo["caracteres"] / min(razones)),
                         "tokens_a_2_7_actividad1": round(fijo["caracteres"] / CHARS_POR_TOKEN_ACTIVIDAD1),
                         "alcanza_el_minimo": fijo["caracteres"] / min(razones) >= MINIMO_HAIKU45},
        "razon_por_tarea": {"mediana": statistics.median(razones), "min": min(razones), "max": max(razones)},
        "paso_que_alcanza_el_minimo": {
            "por_paso": {str(k): cruces.count(k) for k in sorted({c for c in cruces if c is not None})},
            "nunca": cruces.count(None), "tareas": len(principales)},
        "tiempos": {"segundos_por_paso_max": max(x["segundos_por_paso"] for x in filas),
                    "segundos_por_paso_mediana": statistics.median(x["segundos_por_paso"] for x in filas),
                    "segundos_entre_consultas_mediana": statistics.median(gaps),
                    "segundos_entre_consultas_max": max(gaps)},
        "filas": filas,
    }


def main() -> int:  # pragma: no cover - the CLI around medir()
    m = medir()
    SALIDA.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: m[k] for k in m if k != "filas"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
