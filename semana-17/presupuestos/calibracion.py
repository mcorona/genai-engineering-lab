"""Week 17, activity 4: where the budgets come from ($0, no model call).

    cd semana-17 && uv run --group semana17 python -m presupuestos.calibracion [--salida resultados/presupuestos_calibracion.json]

It reads the 252 runs (84 tasks x k = 3) of the week 13 evaluation (Haiku 5.5, effort `low`, the agent's own setting) and does
three things with them, so that no number of the budget is a guess:

1. the cost distribution of a task (USD, tokens, steps, output per step), overall and by task type: p50, p90, p95, p99, max;
2. a check of the upper estimate against what the API reported: the first call of every run (exact request, rebuilt from the
   golden set) and every step after it (the previous prompt plus the previous answer plus what the tools returned), for several
   characters-per-token divisors. The divisor in `estimacion.py` is the largest of those that never underestimates;
3. an offline replay of the policy over the recorded steps at budgets set at each percentile: how many runs would have been
   cut, how many of those had succeeded, what it saves, and that no run spends above its cap. The replay cannot know what a
   cut run would have done next, so a cut run is counted as lost, which is the pessimistic reading.

It writes the report, which also records the policy chosen (`politica_calibrada.json`, read by the agent and the evaluation).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))
from presupuestos import estimacion as EST  # noqa: E402
from presupuestos.politica import Gasto, Limite, Politica, decidir  # noqa: E402

S13 = EST.S13
if str(S13) not in sys.path:
    sys.path.insert(0, str(S13))

from agente.loop import SISTEMA, mensaje_tarea  # noqa: E402
from agente.respuesta import herramienta_responder  # noqa: E402
from herramientas import definiciones  # noqa: E402

CHARS_EN_USO, MARGEN_EN_USO = EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA      # what `estimacion.py` ships with
MODELO = "claude-haiku-5-5"
CORRIDA = "eval_haiku_low"
NIVELES = {"p50": 50, "p90": 90, "p95": 95, "p99": 99, "max": 100}
DIVISORES = (2.0, 1.5, 1.3)
MARGENES = (1.0, 1.10)
ESCAPE = 1.3        # JSON escaping of a tool result inside the next message (quotes become \"): measured on the shapes, rounded up
ENVOLTURA = 110     # characters of the `tool_result` block around each result (type, id, flag)


def percentil(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    a, b = int(math.floor(k)), int(math.ceil(k))
    return xs[a] + (xs[b] - xs[a]) * (k - a)


def resumen(xs: list[float], digitos: int = 6) -> dict:
    return {"n": len(xs), **{n: round(percentil(xs, p), digitos) for n, p in NIVELES.items()}, "media": round(sum(xs) / len(xs), digitos)}


def cargar() -> list[dict]:
    """One record per run: the detail row plus its steps (tokens per model call, size of what the tools returned)."""
    detalle = [json.loads(l) for l in open(S13 / "resultados" / f"{CORRIDA}_detalle.jsonl", encoding="utf-8")]
    ids = {r["corrida"] for r in detalle}
    pasos: dict[str, dict] = defaultdict(lambda: {"modelo": {}, "salidas": defaultdict(list)})
    for linea in open(S13 / "resultados" / "trazas" / f"{CORRIDA}.jsonl", encoding="utf-8"):
        e = json.loads(linea)
        if e["corrida"] not in ids:
            continue
        if e["tipo"] == "modelo":
            pasos[e["corrida"]]["modelo"][e["paso"]] = (e["tokens_in"], e["tokens_out"])
        elif e["tipo"] == "herramienta":
            pasos[e["corrida"]]["salidas"][e["paso"]].append(e["salida_chars"])
    tareas = {}
    for lang in ("es", "en"):
        for linea in open(S13 / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
            t = json.loads(linea)
            tareas[t["id"]] = t
    herramientas = definiciones() + [herramienta_responder()]
    runs = []
    for r in detalle:
        p = pasos[r["corrida"]]
        orden = sorted(p["modelo"])
        cuerpo = {"model": MODELO, "max_tokens": 4000, "system": SISTEMA, "tools": herramientas,
                  "messages": [{"role": "user", "content": mensaje_tarea(tareas[r["id"]])}], "output_config": {"effort": "low"}}
        runs.append({**{k: r[k] for k in ("id", "rep", "tipo", "exito", "estado", "costo_usd", "tokens_in", "tokens_out", "pasos")},
                     "pasos_modelo": [p["modelo"][i] for i in orden], "cuerpo": cuerpo,
                     "chars_nuevos": [math.ceil(ESCAPE * sum(p["salidas"][i]) + ENVOLTURA * len(p["salidas"][i])) for i in orden]})
    return runs


def distribucion(runs: list[dict]) -> dict:
    por_tipo = defaultdict(list)
    for r in runs:
        por_tipo[r["tipo"]].append(r)
    salida = [t for r in runs for (_, t) in r["pasos_modelo"]]
    entrada = [t for r in runs for (t, _) in r["pasos_modelo"]]
    return {
        "corridas": len(runs), "tareas": len({r["id"] for r in runs}), "repeticiones": len({r["rep"] for r in runs}),
        "exito": round(sum(r["exito"] for r in runs) / len(runs), 4),
        "usd_por_corrida": resumen([r["costo_usd"] for r in runs]),
        "tokens_por_corrida": resumen([r["tokens_in"] + r["tokens_out"] for r in runs], 0),
        "pasos_por_corrida": resumen([r["pasos"] for r in runs], 2),
        "salida_por_paso": resumen(salida, 0), "entrada_por_paso": resumen(entrada, 0),
        "por_tipo": {t: {"corridas": len(g), "exito": round(sum(x["exito"] for x in g) / len(g), 3),
                         "usd": resumen([x["costo_usd"] for x in g])} for t, g in sorted(por_tipo.items())}}


def validar_estimacion(runs: list[dict], divisor: float, margen: float) -> dict:
    """Estimate of each call against the tokens the API reported. The first call uses the exact request; the later ones use
    the recorded size of what the tools returned (escaped and wrapped, `ESCAPE` and `ENVOLTURA`)."""
    antes = EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA
    EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA = divisor, margen
    try:
        primera = [(EST.entrada_inicial(r["cuerpo"]), r["pasos_modelo"][0][0]) for r in runs]
        siguientes = []
        for r in runs:
            for k in range(1, len(r["pasos_modelo"])):
                (pin, pout), real = r["pasos_modelo"][k - 1], r["pasos_modelo"][k][0]
                siguientes.append((EST.entrada_siguiente_caracteres(pin, pout, r["chars_nuevos"][k - 1]), real))
    finally:
        EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA = antes

    def informe(pares):
        sobras = [e / a for e, a in pares]
        return {"llamadas": len(pares), "subestima": sum(1 for e, a in pares if e < a),
                "razon_minima": round(min(sobras), 3), "razon_media": round(sum(sobras) / len(sobras), 3)}
    return {"divisor": divisor, "margen": margen, "primera_llamada": informe(primera), "llamadas_siguientes": informe(siguientes)}


def repetir(runs: list[dict], pol: Politica) -> dict:
    """The policy over the recorded steps. A step is made if `decidir` allows it and the recorded output fits in the
    `max_tokens` it grants (otherwise the real call would have been cut off at that size)."""
    cortadas, perdidas_ok, gasto_total, gasto_original, pico = [], [], 0.0, 0.0, 0.0
    motivos: dict[str, int] = defaultdict(int)
    for r in runs:
        gasto, motivo = Gasto(), None
        est_in = EST.entrada_inicial(r["cuerpo"])
        for k, (tin, tout) in enumerate(r["pasos_modelo"]):
            if k:
                pin, pout = r["pasos_modelo"][k - 1]
                est_in = EST.entrada_siguiente_caracteres(pin, pout, r["chars_nuevos"][k - 1])
            d = decidir(pol, MODELO, est_in, {"task": Gasto(pol.tarea.usd - gasto.usd, pol.tarea.tokens - gasto.tokens)}, gasto)
            if d.accion == "stop":
                motivo = d.motivo
                break
            salida = min(tout, d.max_tokens)
            usd, tok = EST.costo_real(MODELO, {"input_tokens": tin, "output_tokens": salida})
            gasto = Gasto(gasto.usd + usd, gasto.tokens + tok)
            if tout > d.max_tokens:
                motivo = "salida_cortada"
                break
        gasto_total += gasto.usd
        gasto_original += r["costo_usd"]
        pico = max(pico, gasto.usd)
        if motivo:
            cortadas.append(r)
            motivos[motivo] += 1
            if r["exito"]:
                perdidas_ok.append(r)
    return {"cortadas": len(cortadas), "de_ellas_con_exito": len(perdidas_ok), "motivos": dict(motivos),
            "exito_perdido": round(len(perdidas_ok) / len(runs), 4), "usd_con_presupuesto": round(gasto_total, 4),
            "usd_original": round(gasto_original, 4), "gasto_maximo_de_una_corrida": round(pico, 6),
            "nunca_pasa_del_tope": pico <= pol.tarea.usd + 1e-12}


def techo(valor: float, paso: float) -> float:
    """Rounded UP to a clean step, so the budget is never below the percentile it came from."""
    return round(math.ceil(valor / paso - 1e-9) * paso, 10)


def suma_de_tareas(runs: list[dict], n: int, nivel: float, campo: str, remuestreos: int = 2000, semilla: int = 17) -> float:
    """Percentile `nivel` of the total of `n` tasks drawn from the recorded runs (bootstrap, fixed seed)."""
    import random
    azar = random.Random(semilla)
    valores = [r[campo] if campo == "costo_usd" else r["tokens_in"] + r["tokens_out"] for r in runs]
    return percentil([sum(azar.choice(valores) for _ in range(n)) for _ in range(remuestreos)], nivel)


TAREAS_POR_SESION = 10      # a conversation: ten tasks (an assumption of the lab, not a measurement)
TAREAS_POR_DIA = 100        # a tenant's day: one hundred tasks (the same)
NIVEL_DE_LA_TAREA = "p99"


def elegir(runs: list[dict], dist: dict) -> dict:
    """The policy written to `politica_calibrada.json`. The task budget is the p99 of one run (USD and tokens), rounded up;
    session and day are the p99 of the total of 10 and of 100 tasks (bootstrap). The cost per task comes from the data; how many
    tasks make a session or a day is the one assumption, and it is written next to the result."""
    usd, tok = dist["usd_por_corrida"], dist["tokens_por_corrida"]
    salida = dist["salida_por_paso"]
    return {
        "_doc": "Written by presupuestos/calibracion.py from the 252 runs of the week 13 Haiku `low` evaluation. Do not edit by hand.",
        "modelo": MODELO, "corrida_base": CORRIDA, "nivel_de_la_tarea": NIVEL_DE_LA_TAREA,
        "tarea": {"usd": techo(usd[NIVEL_DE_LA_TAREA], 0.0001), "tokens": int(techo(tok[NIVEL_DE_LA_TAREA], 1000))},
        "sesion": {"usd": techo(suma_de_tareas(runs, TAREAS_POR_SESION, 99, "costo_usd"), 0.001),
                   "tokens": int(techo(suma_de_tareas(runs, TAREAS_POR_SESION, 99, "tokens"), 10000)), "tareas": TAREAS_POR_SESION},
        "tenant_dia": {"usd": techo(suma_de_tareas(runs, TAREAS_POR_DIA, 99, "costo_usd"), 0.01),
                       "tokens": int(techo(suma_de_tareas(runs, TAREAS_POR_DIA, 99, "tokens"), 100000)), "tareas": TAREAS_POR_DIA},
        "min_salida": int(techo(salida["p95"], 100)), "max_salida": 4000,
        "chars_por_token": CHARS_EN_USO, "margen_entrada": MARGEN_EN_USO}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(S17 / "resultados" / "presupuestos_calibracion.json"))
    ap.add_argument("--politica", default=str(Path(__file__).with_name("politica_calibrada.json")))
    a = ap.parse_args(argv)
    runs = cargar()
    dist = distribucion(runs)
    validacion = [validar_estimacion(runs, d, m) for d in DIVISORES for m in MARGENES]
    en_uso = validar_estimacion(runs, CHARS_EN_USO, MARGEN_EN_USO)
    politica = elegir(runs, dist)
    reporte = {"corrida_base": CORRIDA, "modelo": MODELO, "distribucion": dist, "validacion_de_la_estimacion": validacion,
               "estimacion_en_uso": en_uso}
    usd, tok = dist["usd_por_corrida"], dist["tokens_por_corrida"]
    repeticion = {}
    for nivel in ("p90", "p95", "p99", "max"):
        pol = Politica(Limite(usd[nivel], int(tok[nivel])), min_salida=politica["min_salida"])
        repeticion[nivel] = {"tope_usd": usd[nivel], "tope_tokens": int(tok[nivel]), **repetir(runs, pol)}
    elegida = Politica.desde_archivo_dict(politica)
    repeticion["elegida"] = {"tope_usd": politica["tarea"]["usd"], "tope_tokens": politica["tarea"]["tokens"], **repetir(runs, elegida)}
    reporte["repeticion"] = repeticion
    reporte["politica_elegida"] = politica
    Path(a.salida).write_text(json.dumps(reporte, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(a.politica).write_text(json.dumps(politica, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(en_uso))
    for nombre, r in repeticion.items():
        print(nombre, {k: r[k] for k in ("tope_usd", "tope_tokens", "cortadas", "de_ellas_con_exito", "motivos", "usd_con_presupuesto",
                                          "usd_original", "gasto_maximo_de_una_corrida", "nunca_pasa_del_tope")})
    print(json.dumps(politica))
    return 0


if __name__ == "__main__":
    sys.exit(main())
