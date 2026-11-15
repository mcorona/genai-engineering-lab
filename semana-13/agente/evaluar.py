"""Week 13, activity 5: the agent evaluation report (resultados/agente.md and agente_resumen.json).

Reads the details and traces of the given runs and computes, per configuration (model and effort):
- Task success: by execution (the gold set's keys) or by state (clarification and abstention). pass@1 = the mean
  success over all runs; pass^k = the fraction of tasks in which all k repetitions succeed. 95 % CI by bootstrap
  over tasks (2,000 resamples, fixed seed); the difference between configurations with a paired bootstrap.
- Trajectory (from the traces): valid calls (an existing tool and arguments that pass the schema), successful
  calls, steps vs. the minimum, redundant calls (the same tool with the same arguments in one run) and
  recovery after an error (runs with some tool error that end in success).
- Behavior: correct clarification and abstention, false clarifications or abstentions on tasks with an answer and, only
  where the answer is free text (the clarification question or the explanation of the abstention), a Haiku 5.5
  `low` judge that compares it with the gold set's reason. The judge is validated first on known good and bad cases.
- Cost and latency per task: p50 and p95 of steps, tokens, dollars and seconds.

    python agente/evaluar.py --corridas eval_haiku_low eval_haiku_medium
"""
import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from agente.loop import api_anthropic, costo  # noqa: E402

RES = AQUI / "resultados"
JUEZ = "claude-haiku-5-5"
CACHE_JUEZ = RES / "agente_juez_cache.json"
INVALIDAS = {"argumentos_invalidos", "herramienta_desconocida"}
TIPOS = ["simple", "regla", "compuesta", "valores", "ambigua", "sin_respuesta"]

PROMPT_JUEZ = """You grade one response of a data assistant. The user's request could not be answered directly.
Expected behavior: {esperado}.
Why (reference): {motivo}

Request: {tarea}
Assistant state: {estado}
Assistant answer: {respuesta}
Clarification question: {pregunta}

Grade "adecuada" = true only if:
- for a clarification: the question asks for the missing information named in the reference (or an equivalent \
missing piece), and does not invent an answer;
- for an abstention: the answer says the needed data does not exist in the database, consistent with the reference, \
and does not present an approximation as the answer.
Reply with JSON only: {{"adecuada": true|false, "razon": "<one sentence>"}}"""

CALIBRACION = [  # known cases to validate the judge before using it
    ({"tarea": "¿Cuántas unidades vendió el SKU?", "estado_esperado": "requiere_aclaracion", "motivo": "No dice qué SKU ni en qué periodo."},
     {"estado": "requiere_aclaracion", "respuesta": "Necesito más datos.", "pregunta_aclaracion": "¿De qué SKU y en qué periodo?"}, True),
    ({"tarea": "¿Cuántas unidades vendió el SKU?", "estado_esperado": "requiere_aclaracion", "motivo": "No dice qué SKU ni en qué periodo."},
     {"estado": "requiere_aclaracion", "respuesta": "Necesito más datos.", "pregunta_aclaracion": "¿Prefiere la respuesta en inglés?"}, False),
    ({"tarea": "¿Cuál es el margen de utilidad de cada SKU?", "estado_esperado": "abstenida", "motivo": "Solo hay costo unitario; no hay precio de venta."},
     {"estado": "abstenida", "respuesta": "La base solo registra el costo unitario; no hay precio de venta, así que no se puede calcular el margen.", "pregunta_aclaracion": None}, True),
    ({"tarea": "¿Cuál es el margen de utilidad de cada SKU?", "estado_esperado": "abstenida", "motivo": "Solo hay costo unitario; no hay precio de venta."},
     {"estado": "abstenida", "respuesta": "Estimé el margen como 30 % del costo unitario: SKU-0001 tiene 12.5 pesos de margen.", "pregunta_aclaracion": None}, False),
]


def p(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def boot(por_tarea: dict, f, n=2000, semilla=13):
    """95 % CI of f(list of values per task), resampling tasks."""
    ids = sorted(por_tarea)
    rnd = random.Random(semilla)
    vals = sorted(f([por_tarea[rnd.choice(ids)] for _ in ids]) for _ in range(n))
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def juez(tarea, final, cache, gasto):
    clave = json.dumps([tarea["tarea"], final.get("estado"), final.get("respuesta"), final.get("pregunta_aclaracion")], ensure_ascii=False)
    if clave not in cache:
        prompt = PROMPT_JUEZ.format(esperado="ask for clarification" if tarea["estado_esperado"] == "requiere_aclaracion" else "abstain",
                                    motivo=tarea["motivo"], tarea=tarea["tarea"], estado=final.get("estado"),
                                    respuesta=final.get("respuesta"), pregunta=final.get("pregunta_aclaracion"))
        for _ in range(3):
            d = api_anthropic({"model": JUEZ, "max_tokens": 2000, "output_config": {"effort": "low"},
                               "messages": [{"role": "user", "content": prompt}]})
            gasto[0] += costo(JUEZ, d["usage"]["input_tokens"], d["usage"]["output_tokens"])
            texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
            try:
                v = json.loads(texto[texto.index("{"): texto.rindex("}") + 1])
                if isinstance(v.get("adecuada"), bool):
                    cache[clave] = v
                    break
            except ValueError:
                continue
        else:
            return {"adecuada": None, "razon": "el juez no devolvió JSON válido en 3 intentos"}
    return cache[clave]


def trayectoria(eventos):
    llam = [e for e in eventos if e["tipo"] == "herramienta" and e["herramienta"] != "responder"]
    vistos, redundantes = set(), 0
    for e in llam:
        k = (e["herramienta"], json.dumps(e["argumentos"], sort_keys=True, ensure_ascii=False))
        redundantes += k in vistos
        vistos.add(k)
    return {"llamadas": len(llam), "validas": sum(e.get("error") not in INVALIDAS for e in llam),
            "exitosas": sum(bool(e["ok"]) for e in llam), "redundantes": redundantes,
            "uso": Counter(e["herramienta"] for e in llam)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridas", nargs="+", required=True)
    ap.add_argument("--sin-juez", action="store_true")
    a = ap.parse_args()

    tareas = {}
    for lang in ("es", "en"):
        for linea in open(AQUI / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
            t = json.loads(linea)
            tareas[t["id"]] = t
    cache = json.loads(CACHE_JUEZ.read_text(encoding="utf-8")) if CACHE_JUEZ.exists() else {}
    gasto = [0.0]

    calib = None
    if not a.sin_juez:
        aciertos = [juez(t, f, cache, gasto)["adecuada"] is esperado for t, f, esperado in CALIBRACION]
        calib = f"{sum(aciertos)}/{len(aciertos)}"
        if not all(aciertos):
            print(f"The judge failed the calibration ({calib}); reporting without the judge.")
            a.sin_juez = True

    resumen, secciones = {"calibracion_juez": calib}, []
    por_conf = {}
    for corrida in a.corridas:
        filas = [json.loads(x) for x in open(RES / f"{corrida}_detalle.jsonl", encoding="utf-8")]
        for f in filas:  # the pilots did not record the repetition or the configuration
            f.setdefault("rep", 0), f.setdefault("modelo", "claude-haiku-5-5"), f.setdefault("esfuerzo", "low"), f.setdefault("patron", "loop")
        eventos = defaultdict(list)
        for x in open(RES / "trazas" / f"{corrida}.jsonl", encoding="utf-8"):
            e = json.loads(x)
            eventos[e["corrida"]].append(e)
        conf = f"{filas[0]['modelo']} {filas[0]['esfuerzo']}" + (" · Agent SDK" if filas[0]["patron"] == "sdk" else "")
        k = max(f["rep"] for f in filas) + 1
        por_tarea = defaultdict(list)
        for f in filas:
            por_tarea[f["id"]].append(f)
        if len(por_tarea) < 84:
            conf += f" (subset: {len(por_tarea)} tasks)"
        exito = {i: [x["exito"] for x in v] for i, v in por_tarea.items()}
        pass1 = lambda vs: statistics.mean(statistics.mean(v) for v in vs)  # noqa: E731
        passk = lambda vs: statistics.mean(all(v) and len(v) == k for v in vs)  # noqa: E731
        r = {"corrida": corrida, "configuracion": conf, "k": k, "tareas": len(por_tarea), "corridas": len(filas),
             "pass@1": pass1(exito.values()), "pass@1_ic": boot(exito, pass1),
             f"pass^{k}": passk(exito.values()), f"pass^{k}_ic": boot(exito, passk)}
        r["por_tipo"] = {}
        for tipo in TIPOS:
            sub = {i: v for i, v in exito.items() if tareas[i]["tipo"] == tipo}
            r["por_tipo"][tipo] = {"tareas": len(sub), "pass@1": pass1(sub.values()) if sub else None,
                                   f"pass^{k}": passk(sub.values()) if sub else None}
        r["por_idioma"] = {lang: pass1([v for i, v in exito.items() if i.endswith("-" + lang)]) for lang in ("es", "en")
                           if any(i.endswith("-" + lang) for i in exito)}
        claves = [c for f in filas for c in f["claves"].values()]
        r["exactitud_claves"] = statistics.mean(c["exacta"] for c in claves) if claves else None
        r["coherencia_claves"] = statistics.mean(c["coherente"] for c in claves) if claves else None
        # behavior
        resp = [f for f in filas if f["esperado"] == "respondida"]
        r["estados"] = dict(Counter(f"{f['esperado']} -> {f['estado']}" for f in filas).most_common())
        media = lambda xs: statistics.mean(xs) if xs else None  # noqa: E731
        r["aclaracion_correcta"] = media([f["estado"] == "requiere_aclaracion" for f in filas if f["esperado"] == "requiere_aclaracion"])
        r["abstencion_correcta"] = media([f["estado"] == "abstenida" for f in filas if f["esperado"] == "abstenida"])
        r["falsa_aclaracion_o_abstencion"] = media([f["estado"] in ("requiere_aclaracion", "abstenida") for f in resp])
        r["limite_alcanzado"] = sum(f["estado"] in ("limite_alcanzado", "error") for f in filas)
        if not a.sin_juez:
            libres = [f for f in filas if f["esperado"] in ("requiere_aclaracion", "abstenida") and f["estado"] == f["esperado"]]
            veredictos = [juez(tareas[f["id"]], f["final"], cache, gasto) for f in libres]
            r["juez_texto_libre"] = {"evaluadas": sum(v["adecuada"] is not None for v in veredictos),
                                     "adecuadas": sum(v["adecuada"] is True for v in veredictos),
                                     "sin_veredicto": sum(v["adecuada"] is None for v in veredictos),
                                     "no_adecuadas": [{"id": f["id"], "rep": f["rep"], "razon": v["razon"]}
                                                      for f, v in zip(libres, veredictos) if v["adecuada"] is False]}
        # trajectory
        tr = [trayectoria(eventos[f["corrida"]]) for f in filas]
        tot = sum(x["llamadas"] for x in tr)
        r["trayectoria"] = {
            "llamadas": tot, "validas": sum(x["validas"] for x in tr) / tot, "exitosas": sum(x["exitosas"] for x in tr) / tot,
            "redundantes_por_corrida": statistics.mean(x["redundantes"] for x in tr),
            "corridas_con_redundancia": statistics.mean(x["redundantes"] > 0 for x in tr),
            "pasos_sobre_minimo": statistics.mean(f["pasos"] / f["pasos_min"] for f in filas),
            "corridas_con_error": sum(f["errores_herramienta"] > 0 for f in filas),
            "recuperacion_tras_error": (statistics.mean(f["exito"] for f in filas if f["errores_herramienta"] > 0)
                                        if any(f["errores_herramienta"] for f in filas) else None),
            "uso_herramientas": dict(sum((x["uso"] for x in tr), Counter())),
        }
        # cost and latency
        r["por_tarea"] = {m: {"p50": p([f[c] if isinstance(c, str) else c(f) for f in filas], .5),
                              "p95": p([f[c] if isinstance(c, str) else c(f) for f in filas], .95)}
                          for m, c in [("pasos", "pasos"), ("tokens", lambda f: f["tokens_in"] + f["tokens_out"]),
                                       ("usd", "costo_usd"), ("segundos", "segundos")]}
        r["costo_total_usd"] = sum(f["costo_usd"] for f in filas)
        r["fallas"] = [{"id": f["id"], "rep": f["rep"], "estado": f["estado"], "claves": {c: v["exacta"] for c, v in f["claves"].items()}}
                       for f in filas if not f["exito"]]
        resumen[corrida] = r
        por_conf[corrida] = exito

    # differences between configurations (paired by task)
    difs = []
    for i, c1 in enumerate(a.corridas):
        for c2 in a.corridas[i + 1:]:
            comunes = {t: (por_conf[c1][t], por_conf[c2][t]) for t in por_conf[c1] if t in por_conf[c2]}
            f = lambda vs: statistics.mean(statistics.mean(y) - statistics.mean(x) for x, y in vs)  # noqa: E731
            difs.append({"de": c1, "a": c2, "tareas": len(comunes), "dif_pass@1": f(comunes.values()), "ic": boot(comunes, f)})
    resumen["diferencias"] = difs
    resumen["costo_juez_usd"] = gasto[0]
    CACHE_JUEZ.write_text(json.dumps(cache, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    (RES / "agente_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    escribir_md(resumen, a.corridas)
    print((RES / "agente.md").read_text(encoding="utf-8")[:3000])


def f3(x):
    return "-" if x is None else f"{x:.3f}"


def ic(t):
    return f"[{t[0]:.3f}, {t[1]:.3f}]"


def escribir_md(R, corridas):
    k = R[corridas[0]]["k"]
    L = ["# Activity 5: agent evaluation", "",
         "Generated by [`agente/evaluar.py`](../agente/evaluar.py) from the run details and traces. Gold set: 42 tasks × "
         f"2 languages = 84 tasks, k = {k} runs each. 95 % confidence intervals by bootstrap over tasks.", "",
         "## Success and consistency", "",
         f"| Configuration | Runs | pass@1 | 95 % CI | pass^{k} | 95 % CI | Key accuracy | Key consistency | ES / EN pass@1 | Cost |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c in corridas:
        r = R[c]
        L.append(f"| {r['configuracion']} | {r['corridas']} | **{r['pass@1']:.3f}** | {ic(r['pass@1_ic'])} | **{r[f'pass^{k}']:.3f}** | "
                 f"{ic(r[f'pass^{k}_ic'])} | {f3(r['exactitud_claves'])} | {f3(r['coherencia_claves'])} | "
                 f"{f3(r['por_idioma'].get('es'))} / {f3(r['por_idioma'].get('en'))} | ${r['costo_total_usd']:.2f} |")
    for d in R["diferencias"]:
        L += ["", f"Difference in pass@1, {R[d['a']]['configuracion']} minus {R[d['de']]['configuracion']} (paired by task): "
              f"{d['dif_pass@1']:+.3f}, 95 % CI {ic(d['ic'])}."]
    L += ["", "## By task type (pass@1 / pass^k)", "", "| Type | Tasks | " + " | ".join(R[c]["configuracion"] for c in corridas) + " |",
          "|---|---|" + "---|" * len(corridas)]
    for tipo in TIPOS:
        L.append(f"| {tipo} | {max(R[c]['por_tipo'][tipo]['tareas'] for c in corridas)} | " + " | ".join(
            f"{f3(R[c]['por_tipo'][tipo]['pass@1'])} / {f3(R[c]['por_tipo'][tipo][f'pass^{k}'])}" for c in corridas) + " |")
    L += ["", "## Behavior", "", "| Configuration | Correct clarification | Correct abstention | False clarification or abstention on answerable tasks | "
          "Free text adequate (judge) | Stopped by a limit or error |", "|---|---|---|---|---|---|"]
    for c in corridas:
        r = R[c]
        j = r.get("juez_texto_libre")
        libre = f"{j['adecuadas']}/{j['evaluadas']}" if j else "-"
        L.append(f"| {r['configuracion']} | {f3(r['aclaracion_correcta'])} | {f3(r['abstencion_correcta'])} | "
                 f"{f3(r['falsa_aclaracion_o_abstencion'])} | {libre} | {r['limite_alcanzado']} |")
    if R.get("calibracion_juez"):
        L += ["", f"The judge (Haiku 5.5 `low`) only grades free text: the clarification question or the abstention explanation, "
              f"against the reason recorded in the gold set. It was validated first on known good and bad cases: {R['calibracion_juez']}. "
              f"Judge cost: ${R['costo_juez_usd']:.4f}."]
    L += ["", "## Trajectory", "", "| Configuration | Tool calls | Valid calls | Successful calls | Model calls / minimum | Redundant calls per run | "
          "Runs with a tool error | Recovery after error |", "|---|---|---|---|---|---|---|---|"]
    for c in corridas:
        t = R[c]["trayectoria"]
        L.append(f"| {R[c]['configuracion']} | {t['llamadas']} | {t['validas']:.3f} | {t['exitosas']:.3f} | {t['pasos_sobre_minimo']:.2f} | "
                 f"{t['redundantes_por_corrida']:.2f} ({t['corridas_con_redundancia']:.0%} of runs) | {t['corridas_con_error']} | "
                 f"{f3(t['recuperacion_tras_error'])} |")
    L += ["", "## Cost and latency per task (p50 / p95)", "", "| Configuration | Model calls | Tokens | USD | Seconds |", "|---|---|---|---|---|"]
    for c in corridas:
        q = R[c]["por_tarea"]
        L.append(f"| {R[c]['configuracion']} | {q['pasos']['p50']:.0f} / {q['pasos']['p95']:.0f} | {q['tokens']['p50']:,.0f} / {q['tokens']['p95']:,.0f} | "
                 f"{q['usd']['p50']:.4f} / {q['usd']['p95']:.4f} | {q['segundos']['p50']:.1f} / {q['segundos']['p95']:.1f} |")
    L += ["", "## Failed runs", ""]
    for c in corridas:
        fallas = Counter(f["id"] for f in R[c]["fallas"])
        L.append(f"- **{R[c]['configuracion']}:** " + (", ".join(f"{i} ({n}/{k})" for i, n in sorted(fallas.items())) or "none"))
    (RES / "agente.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
