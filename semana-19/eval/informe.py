"""Week 19, activity 8: the data sections of resultados/eval_aws.md, rendered from the run's files. No AWS.

Every number in the generated block comes from a file the live steps wrote (eval_aws.py, aprobacion_e2e.py,
juez_bedrock.py, comparar_jueces.py). A missing file is reported as "not run": no figure is typed by hand. The block
sits between two markers, so the analysis written by hand outside them survives a re-render.

    .venv/bin/python semana-19/eval/informe.py          # rewrites the block in resultados/eval_aws.md
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
CARPETA = S19 / "resultados" / "eval_aws"
DESTINO = S19 / "resultados" / "eval_aws.md"
INICIO = "<!-- generado por eval/informe.py: inicio (no editar a mano) -->"
FIN = "<!-- generado por eval/informe.py: fin -->"
NO_CORRIO = "_Not run: {archivo} does not exist._"


def _eval_aws():
    spec = importlib.util.spec_from_file_location("eval_aws_para_informe", S19 / "eval" / "eval_aws.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _n(v, d=3) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{d}f}".rstrip("0").rstrip(".") if d else str(round(v))
    return str(v)


def _tabla(encabezado: list[str], filas: list[list]) -> list[str]:
    return ["| " + " | ".join(encabezado) + " |", "|" + "---|" * len(encabezado),
            *("| " + " | ".join(_n(c) if not isinstance(c, str) else c for c in f) + " |" for f in filas)]


def seccion_corrida(c: dict) -> list[str]:
    g, t = c["gasto"], c["tope"]
    out = ["### The run", "", f"Date: {c['fecha']}. Spent by the script (agent spans): {_n(g['usd'], 6)} USD and "
           f"{g['tokens']:,} tokens, against the caps in the code ({_n(t['usd'])} USD, {t['tokens']:,} tokens).", ""]
    out += _tabla(["Access check", "Expected", "Got", "OK"],
                  [[f"{a['metodo']} {a['ruta']} {'with' if a['con_token'] else 'without'} token", a["esperado"],
                    a["obtenido"], a["ok"]] for a in c["acceso"]])
    abortadas = [f["id_tarea"] for f in c["filas"] if f.get("estado") == "no_corrida"]
    out += ["", f"Tasks aborted by the cap: {', '.join(abortadas) if abortadas else 'none'}."]
    return out


def seccion_exito(r: dict) -> list[str]:
    e = r["exito"]
    out = ["### Success (week 13's execution verifier)", ""]
    out += _tabla(["Group", "n", "Passed", "Rate", "Wilson 95%", "Aborted"],
                  [[g, e[g]["n"], e[g]["exito"], e[g]["tasa"],
                    f"[{_n(e[g]['ic95'][0])}, {_n(e[g]['ic95'][1])}]" if e[g]["ic95"] else "—", e[g]["abortadas"]]
                   for g in ("es", "en", "total")])
    return out


def seccion_regresion(r: dict) -> list[str]:
    c = r["comparacion"]
    out = ["### Regression against the baselines (week 10's rule)", "",
           f"Baseline: {c['linea_base']}, the same 20 tasks. Threshold = the multiple of 0.05 just below "
           "(baseline − max(0.03, 1/n)).", ""]
    out += _tabla(["Group", "n", "Baseline", "AWS", "Threshold", "Regression", "Week 13 (3 runs)"],
                  [[g, c["regla"][g]["n"], c["regla"][g]["base"], c["regla"][g]["valor"], c["regla"][g]["umbral"],
                    c["regla"][g]["regresion"], c["semana13"][g]["tasa"]] for g in ("es", "en", "total")])
    a7 = c["actividad7"]
    out += ["", f"Activity 7 (path a, same deployment): {len(a7['tareas_comunes'])} tasks in common "
            f"({', '.join(a7['tareas_comunes']) or 'none'}): {a7['aws']} passed here, {a7['actividad7']} there.",
            "", f"**Regression: {'yes' if c['regresion'] else 'no'}.**"]
    return out


def seccion_trayectoria(r: dict) -> list[str]:
    t = r["trayectoria"]
    fallan = ", ".join(f"{k} ({v})" for k, v in sorted(t["fallan"].items())) or "none"
    return ["### Trajectory (week 17's graders)", "",
            f"Graded: {t['calificadas']}; OK: {t['ok']}; mean score: {_n(t['puntaje_medio'])}. Failing graders: {fallan}."]


def seccion_latencia(r: dict) -> list[str]:
    lat = r["latencia"]
    out = ["### Latency, cold and warm apart", ""]
    out += _tabla(["Start", "n", "p50 (s)", "p95 (s)"],
                  [["cold", lat["frio"]["n"], lat["frio"]["p50_s"], lat["frio"]["p95_s"]],
                   ["warm", lat["caliente"]["n"], lat["caliente"]["p50_s"], lat["caliente"]["p95_s"]]])
    out += ["", f"Unknown (no REPORT line in the window): {lat['desconocido']['n']}."]
    return out


def seccion_costo(c: dict) -> list[str]:
    k = c["resumen"]["costo"]
    out = ["### Tokens and model cost per task (agent spans)", "",
           f"{k['tareas']} tasks: {k['tokens_entrada']:,} input, {k['tokens_salida']:,} output, "
           f"{k['tokens_cache_lectura']:,} cache read, {k['tokens_cache_escritura']:,} cache write; "
           f"{_n(k['costo_usd'], 6)} USD, {_n(k['costo_por_tarea_usd'], 6)} USD and {_n(k['tokens_por_tarea'], 1)} "
           "tokens per task. The AWS charge comes from Cost Explorer (costo_real.md).", ""]
    filas = c.get("calentamiento", []) + c["filas"]
    out += _tabla(["Task", "Phase", "State", "OK", "Start", "Latency (s)", "Steps", "Tools", "In", "Out", "USD"],
                  [[f["id_tarea"], "warm-up" if f in c.get("calentamiento", []) else "main", f["estado"],
                    bool((f.get("verificacion") or {}).get("exito")), (f.get("arranque") or {}).get("clase"),
                    f.get("latencia_s"), f.get("pasos"), f.get("herramientas"), f.get("tokens_entrada"),
                    f.get("tokens_salida"), _n(f.get("costo_usd"), 6)] for f in filas])
    return out


def seccion_descartadas(descartadas: list[tuple[str, dict]]) -> list[str]:
    """Runs a rerun replaced (eval_aws.py keeps them as crudo_eval_descartada_<n>.json): their spend still counts."""
    out = ["### Discarded runs (kept; their spend counts)", ""]
    if not descartadas:
        return out + ["None."]
    filas = []
    for nombre, c in descartadas:
        r = c["resumen"]
        uso = {}
        for f in c["filas"]:
            for sp in f.get("spans_herramientas") or []:
                uso[sp["gen_ai.tool.name"]] = uso.get(sp["gen_ai.tool.name"], 0) + 1
        filas.append([nombre, c["fecha"], f"{r['exito']['total']['exito']}/{r['exito']['total']['n']}",
                      r["comparacion"]["regresion"], _n(c["gasto"]["usd"], 6), f"{c['gasto']['tokens']:,}",
                      ", ".join(f"{k} {v}" for k, v in sorted(uso.items())) or "none"])
    return out + _tabla(["File", "Date", "Passed", "Regression", "USD", "Tokens", "Tool calls"], filas)


def seccion_aprobacion(a: dict | None) -> list[str]:
    out = ["### The approval workflow, step by step", ""]
    if a is None:
        return out + [NO_CORRIO.format(archivo="eval_aws/aprobacion_e2e.json")]
    out += _tabla(["Step", "Check", "OK", "Evidence"],
                  [[p["paso"], p["comprobacion"], p["ok"],
                    "; ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in p.items()
                              if k not in ("paso", "comprobacion", "ok") and not isinstance(v, (dict, list)))]
                   for p in a["pasos"]])
    completas = [p["paso"] for p in a["pasos"]] == [0, 1, 2, 3, 4, 5] and all(p["ok"] for p in a["pasos"])
    out += ["", f"Short test wait deployed: {a['espera_de_prueba_s']} s. All five checks passed: "
            f"{'yes' if completas else 'no'}. Spent: {_n(a['gasto']['usd'], 6)} USD, {a['gasto']['tokens']:,} tokens "
            f"(caps {_n(a['tope']['usd'])} USD, {a['tope']['tokens']:,})."]
    return out


def seccion_juez(j: dict | None, cj: dict | None) -> list[str]:
    out = ["### The Bedrock judge against the verifier", ""]
    if j is None:
        return out + [NO_CORRIO.format(archivo="eval_aws/juez_bedrock.json")]
    if j.get("estado") == "abortado":
        return out + [f"Aborted before creating the job: estimate {_n(j['estimacion']['usd'], 6)} USD over the cap "
                      f"{_n(j['estimacion']['tope_usd'])} USD."]
    out += [f"Job {j['trabajo']}: {j['estado']} in {j['duracion_s']} s; judge {j['juez']}; "
            f"{len(j['por_tarea'])} tasks judged. Estimate before the job: {_n(j['estimacion']['usd'], 6)} USD.", ""]
    if cj is None:
        return out + [NO_CORRIO.format(archivo="eval_aws/comparar_jueces.json")]
    m = cj["matriz"]
    out += [f"Thresholds fixed before the run: {', '.join(f'{k} ≥ {v}' for k, v in cj['criterio'].items())}.", ""]
    out += _tabla(["", "Judge passes", "Judge fails"],
                  [["Verifier passes", m["ambos_aprueban"], m["falso_reprobado"]],
                   ["Verifier fails", m["falso_aprobado"], m["ambos_reprueban"]]])
    out += ["", f"Agreement {_n(cj['acuerdo'], 4)}, Cohen's kappa {_n(cj['kappa'], 4)} (n = {cj['n']}; without a score: "
            f"{', '.join(cj['sin_puntaje']) or 'none'}). False passes: {', '.join(cj['falsos_aprobados']) or 'none'}. "
            f"False fails: {', '.join(cj['falsos_reprobados']) or 'none'}.", ""]
    out += _tabla(["Metric", "Mean"], [[k, _n(v, 4)] for k, v in cj["promedios"].items()])
    return out


def seccion_esquema() -> list[str]:
    e = _eval_aws()
    return ["### Schema of eval_aws_detalle.jsonl (week 20's baseline)", "",
            "One line per task, the fields in this order; checked by `eval_aws.validar_detalle` before writing.", "",
            *_tabla(["Field", "Type", "Meaning"],
                    [[k, " or ".join("null" if t is type(None) else {"str": "string", "bool": "boolean", "int": "integer",
                                                                      "float": "number", "dict": "object"}[t.__name__]
                                      for t in tipos), d] for k, (tipos, d) in e.ESQUEMA_DETALLE.items()])]


def render(crudo: dict | None, aprobacion: dict | None = None, juez: dict | None = None,
           comparacion: dict | None = None, descartadas: list[tuple[str, dict]] = ()) -> str:
    out = [INICIO, ""]
    if crudo is None:
        out += [NO_CORRIO.format(archivo="eval_aws/crudo_eval.json"), ""]
    else:
        r = crudo["resumen"]
        for s in (seccion_corrida(crudo), seccion_exito(r), seccion_regresion(r), seccion_trayectoria(r),
                  seccion_latencia(r), seccion_costo(crudo)):
            out += s + [""]
    out += seccion_descartadas(list(descartadas)) + [""]
    for s in (seccion_aprobacion(aprobacion), seccion_juez(juez, comparacion), seccion_esquema()):
        out += s + [""]
    return "\n".join(out + [FIN]) + "\n"


def con_bloque(texto: str, bloque: str) -> str:
    """Replaces the generated block, or appends it when the file has none. Text outside the markers is kept."""
    if INICIO in texto and FIN in texto:
        antes, resto = texto.split(INICIO, 1)
        return antes + bloque.rstrip("\n") + resto.split(FIN, 1)[1]
    return (texto.rstrip("\n") + "\n\n" if texto.strip() else "") + bloque


def _leer(nombre: str) -> dict | None:
    archivo = CARPETA / nombre
    return json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else None


def main() -> int:  # pragma: no cover - reads the run's files
    descartadas = [(p.name, json.loads(p.read_text(encoding="utf-8")))
                   for p in sorted(CARPETA.glob("crudo_eval_descartada_*.json"))]
    bloque = render(_leer("crudo_eval.json"), _leer("aprobacion_e2e.json"), _leer("juez_bedrock.json"),
                    _leer("comparar_jueces.json"), descartadas)
    previo = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else "# Week 19, activity 8: the eval against the deployed endpoint\n"
    DESTINO.write_text(con_bloque(previo, bloque), encoding="utf-8")
    print(DESTINO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
