"""Week 11, activity 5: end-to-end RAG and failure attribution.

Full RAG = retrieval (activity 2) + generation (activity 4) over what was retrieved, with the same metrics as the
generation suite (judge Haiku 5.5 low): faithfulness and answer relevancy (RAGAS), accuracy (in-house judge), citation
precision and coverage, and abstention. The full gold set: 75 questions per language.

Configurations:
- adoptado_top5: the assistant's pipeline (vector + filter + reranking with Haiku, top 5). The rankings of the
  answerable questions are those of activity 2 (resultados/suite_recuperacion_cache.json); those of the 10 unanswerable
  questions per language are computed here with the same code.
- estres_base_top3: vector + filter without reranking and only 3 chunks. It is not a candidate configuration: in activity 2
  it was the only one with recall < 1 in the top k (recall@3 0.962 ES, 0.908 EN), so it serves to check that the
  attribution separates retrieval failures from generation failures when there are some.

Failure: for an answerable question, accuracy 0 according to the in-house judge; for an unanswerable one, the generator
answering (not abstaining). Attribution, fixed before the run:
- retrieval: some reference passage did not reach the context (the configuration's top k);
- generation: every passage arrived and the answer failed; unanswerable questions that get an answer count here, because
  there is no passage to retrieve.
Caches per configuration in resultados/e2e_cache_<config>.json; contexts in resultados/e2e_contextos.json.
Requires NLQ_DSN (only the first time), LM Studio with bge-m3, and ANTHROPIC_API_KEY.
"""
import asyncio
import csv
import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_generacion as sg  # noqa: E402

sr, a = sg.sr, sg.a
RES = RAIZ / "resultados"
CONFIGS = {"adoptado_top5": ("adoptado", 5), "estres_base_top3": ("base", 3)}
CONTEXTOS = RES / "e2e_contextos.json"


def contextos(items):
    if CONTEXTOS.exists():
        return json.loads(CONTEXTOS.read_text(encoding="utf-8"))
    rec = json.loads((RES / "suite_recuperacion_cache.json").read_text(encoding="utf-8"))
    local = {k: v for k, v in rec.items() if k.startswith(("base::", "adoptado::"))}
    sr.recuperar(items, local)  # only computes what is missing (the unanswerable questions)
    ctx = {c: {f"{x['id']}::{x['lang']}": {"chunks": local[f"{orden}::{x['id']}::{x['lang']}"]["ranking"][:k]} for x in items}
           for c, (orden, k) in CONFIGS.items()}
    ctx["_costo_rerank_sin_respuesta"] = sum(local[f"adoptado::{x['id']}::{x['lang']}"].get("costo", 0)
                                             for x in items if not x["respondible"])
    CONTEXTOS.write_text(json.dumps(ctx, ensure_ascii=False) + "\n", encoding="utf-8")
    return ctx


def main():
    items = sg.items_todos()
    ctx_todos = contextos(items)
    resumen = {}
    for config in CONFIGS:
        ctx = ctx_todos[config]
        ruta = RES / f"e2e_cache_{config}.json"
        cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

        def guardar(cache=cache, ruta=ruta):
            ruta.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")
        sg.generar(items, ctx, cache, guardar)
        uso = asyncio.run(sg.evaluar(items, ctx, cache, guardar))
        guardar()
        filas = []
        for x in items:
            k = f"{x['id']}::{x['lang']}"
            chunks = ctx[k]["chunks"]
            f = {"config": config, "id": x["id"], "lang": x["lang"],
                 "tipo": "sin_respuesta" if not x["respondible"] else ("no_textual" if x["tipo"].startswith("no_textual") else "base"),
                 "clase": cache[f"clase::{k}"]["valor"], "costo_gen": cache[f"gen::{k}"]["costo"],
                 "latencia_gen_s": cache[f"gen::{k}"]["latencia_s"], "respuesta": cache[f"gen::{k}"]["respuesta"]}
            if x["respondible"]:
                llegaron = set().union(*(sr.pasajes_en(tuple(c), x["gold"]) for c in chunks))
                f["recall_contexto"] = len(llegaron) / len(x["gold"])
                f.update({m: cache[f"{m}::{k}"]["valor"] for m in ("faithfulness", "answer_relevancy", "exactitud")})
                f["citas"], f["citas_con_pasaje"] = sg.citas(f["respuesta"], chunks, x["gold"])
                f["falla"] = f["exactitud"] == 0
                f["atribucion"] = ("recuperación" if f["recall_contexto"] < 1 else "generación") if f["falla"] else ""
            else:
                f["falla"] = f["clase"] != "abstiene"
                f["atribucion"] = "generación" if f["falla"] else ""
            filas.append(f)
        resumen[config] = (filas, uso)

    todas = [f for filas, _ in resumen.values() for f in filas]
    with (RES / "e2e_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        campos = sorted({c for f in todas for c in f}, key=lambda c: (c == "respuesta", c))
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(todas)

    def media(f, c):
        v = [r[c] for r in f if r.get(c) is not None]
        return f"{statistics.mean(v):.3f}" if v else "-"

    print("## End-to-end metrics (answerable questions)\n")
    print("| Configuration | Language | n | context recall | accuracy | faithfulness | answer_relevancy | citation precision | citation coverage | false abstention |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for config, (filas, _) in resumen.items():
        for lang in ("es", "en"):
            f = [r for r in filas if r["lang"] == lang and r["tipo"] != "sin_respuesta"]
            nc = sum(r["citas"] for r in f)
            print(f"| {config} | {lang} | {len(f)} | {media(f, 'recall_contexto')} | {media(f, 'exactitud')} | {media(f, 'faithfulness')} | "
                  f"{media(f, 'answer_relevancy')} | {sum(r['citas_con_pasaje'] for r in f) / nc:.3f} ({nc}) | "
                  f"{sum(1 for r in f if r['citas_con_pasaje']) / len(f):.3f} | {sum(r['clase'] == 'abstiene' for r in f)}/{len(f)} |")
    print("\n## Unanswerable\n")
    print("| Configuration | Language | Correct abstention | Invented answer |")
    print("|---|---|---|---|")
    for config, (filas, _) in resumen.items():
        for lang in ("es", "en"):
            f = [r for r in filas if r["lang"] == lang and r["tipo"] == "sin_respuesta"]
            print(f"| {config} | {lang} | {sum(r['clase'] == 'abstiene' for r in f)}/{len(f)} | {sum(r['clase'] != 'abstiene' for r in f)}/{len(f)} |")
    print("\n## Failure attribution (language × type)\n")
    print("| Configuration | Language | Type | n | Failures | Retrieval | Generation |")
    print("|---|---|---|---|---|---|---|")
    for config, (filas, _) in resumen.items():
        for lang in ("es", "en"):
            for tipo in ("base", "no_textual", "sin_respuesta", "todas"):
                f = [r for r in filas if r["lang"] == lang and (tipo == "todas" or r["tipo"] == tipo)]
                fallas = [r for r in f if r["falla"]]
                print(f"| {config} | {lang} | {tipo} | {len(f)} | {len(fallas)} | {sum(r['atribucion'] == 'recuperación' for r in fallas)} | "
                      f"{sum(r['atribucion'] == 'generación' for r in fallas)} |")
    print("\n## Failures, one by one\n")
    for config, (filas, _) in resumen.items():
        for r in filas:
            if r["falla"]:
                rc = f"recall del contexto {r['recall_contexto']:.2f}" if "recall_contexto" in r else "sin respuesta"
                print(f"- {config} {r['id']} {r['lang']} [{r['atribucion']}; {rc}]: {r['respuesta'][:200].replace(chr(10), ' ')}")
    print("\n## Passage outside the context but a correct answer (attribution does not apply)\n")
    for config, (filas, _) in resumen.items():
        for r in filas:
            if r.get("recall_contexto", 1) < 1 and not r["falla"]:
                print(f"- {config} {r['id']} {r['lang']}: context recall {r['recall_contexto']:.2f}; {r['respuesta'][:160].replace(chr(10), ' ')}")
    print()
    for config, (filas, uso) in resumen.items():
        costo_gen = sum(r["costo_gen"] for r in filas)
        costo_ev = (uso["in"] * sg.PRECIO["in"] + uso["out"] * sg.PRECIO["out"]) / 1e6
        sin = sum(1 for r in filas for m in ("faithfulness", "answer_relevancy", "exactitud", "clase") if m in r and r[m] is None)
        print(f"Cost {config}: generation ${costo_gen:.4f}; evaluation in this run ${costo_ev:.4f} ({uso['llamadas']} calls); "
              f"without a score {sin}; generation p50 latency {statistics.median(r['latencia_gen_s'] for r in filas):.1f} s")
    print(f"Reranking of the unanswerable questions: ${ctx_todos['_costo_rerank_sin_respuesta']:.4f}")


if __name__ == "__main__":
    main()
