"""Week 11, activity 8: the RAG eval in CI, with two separate suites (one GitHub Actions job per suite).

--suite recuperacion (does not call the answer model):
  the semana10.chunks index (30 documents, fixed 400/80 chunking) rebuilt in the pgvector service, a user of the alfa
  tenant with every role and the filter inside the query; top 20 by similarity and reranking with Haiku 5.5 (the adopted
  pipeline). Exact metrics over the 65 answerable questions per language: recall@3, recall@5, MRR, nDCG@10 and AP@5
  (activity 2). No RAGAS in this suite: context precision is equivalent to AP@5 with a judge (Pearson 0.84, activity 2)
  and costs 4 times more (activity 7).
--suite generacion (does not depend on the retriever):
  the fixed contexts of resultados/contextos_generacion.json (activity 4), the Haiku 5.5 medium generator with the
  solo_documentos prompt (activity 6), the Haiku 5.5 low judge (activity 3). All 150 questions, no subset: the
  run costs ≈ $0.22 (activity 7). Metrics per language: faithfulness and answer relevancy (RAGAS 0.4.3), accuracy
  (in-house judge), citation precision, no false abstention on the 65 answerable questions, and correct abstention on
  the 10 unanswerable ones.

Embeddings in CI: text-embedding-3-small (OpenAI), as in weeks 8 to 10 (bge-m3 runs in LM Studio, not in Actions);
it affects the retrieval index and answer relevancy. That is why the thresholds are calibrated with the first CI run and
not with the local values.

Calibration rule (week 10, fixed before the first run): threshold = the multiple of 0.05 immediately below
(value of the first run - max(0.03, 1/n)), with n questions per language (65 answerable; 10 unanswerable). With
--calibrar, no thresholds are applied: the values and resulting thresholds are printed.
Judge metrics without a score (an API error after the retries): up to 1 % of the run's calls are tolerated and
excluded from the means; above that, the job fails.

--local: a smoke test on the Mac (bge-m3 from LM Studio and the semana10.chunks index already built). --limite N: N answerable
questions and 1 unanswerable per language.
Requires ANTHROPIC_API_KEY; retrieval: PG_ADMIN_DSN and NLQ_DSN (copilot_ro); without --local, OPENAI_API_KEY.
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "experimentos"))
import sensibilidad as sens  # noqa: E402  (imports the suites of activities 2 and 4 and the week 10 assistant)

sg, sr, a = sens.sg, sens.sr, sens.a
MODELO_EMB = "text-embedding-3-small"
MET_REC = ("recall@3", "recall@5", "mrr", "ndcg@10", "ap@5")
MET_GEN = ("faithfulness", "answer_relevancy", "exactitud", "precision_citas", "no_abstencion_falsa", "abstencion_correcta")
# Thresholds per suite, metric and language, calibrated with the first CI run (see resultados/ci_calibracion.md).
UMBRALES = {
    "recuperacion": {"recall@3": {"es": 0.95, "en": 0.95}, "recall@5": {"es": 0.95, "en": 0.95}, "mrr": {"es": 0.90, "en": 0.90},
                     "ndcg@10": {"es": 0.90, "en": 0.90}, "ap@5": {"es": 0.90, "en": 0.90}},
    "generacion": {"faithfulness": {"es": 0.80, "en": 0.75}, "answer_relevancy": {"es": 0.80, "en": 0.75},
                   "exactitud": {"es": 0.95, "en": 0.95}, "precision_citas": {"es": 0.65, "en": 0.70},
                   "no_abstencion_falsa": {"es": 0.95, "en": 0.95}, "abstencion_correcta": {"es": 0.90, "en": 0.90}},
}
MAX_SIN_PUNTAJE = 0.01
PRECIO = a.PRECIOS[f"anthropic:{a.HAIKU}"]


def embed_openai(textos, tipo=None):
    out = []
    for i in range(0, len(textos), 100):
        req = Request("https://api.openai.com/v1/embeddings",
                      data=json.dumps({"model": MODELO_EMB, "input": textos[i:i + 100]}).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        for intento in range(4):
            try:
                with urlopen(req, timeout=120) as r:
                    datos = json.loads(r.read())["data"]
                break
            except HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or intento == 3:
                    raise
                time.sleep(2 ** (intento + 1))
        out += [d["embedding"] for d in sorted(datos, key=lambda d: d["index"])]
    return out, None


def umbral_de(valor, n):
    return math.floor(round((valor - max(0.03, 1 / n)) / 0.05, 6)) * 0.05


def golden(limite):
    items = sg.items_todos()
    if not limite:
        return items
    sel = []
    for lang in ("es", "en"):
        sel += [x for x in items if x["lang"] == lang and x["respondible"]][:limite]
        sel += [x for x in items if x["lang"] == lang and not x["respondible"]][:1]
    return sel


def suite_recuperacion(items, local):
    if not local:
        a.emb_bge = embed_openai  # the assistant (index) and the retrieval suite use a.emb_bge
        a.indexar()
    resp = [x for x in items if x["respondible"]]
    cache = {}
    sr.recuperar(resp, cache)
    valores = {m: {"es": [], "en": []} for m in MET_REC}
    for x in resp:
        m = sr.metricas([tuple(c) for c in cache[f"adoptado::{x['id']}::{x['lang']}"]["ranking"]], x["gold"])
        for k in MET_REC:
            valores[k][x["lang"]].append(m[k])
    costo = sum(v["costo"] for k, v in cache.items() if k.startswith("adoptado::"))
    fallos = sum(1 for k, v in cache.items() if k.startswith("adoptado::") and v.get("rerank_fallo"))
    info = {"consultas": len(resp), "reranking_fallido": fallos}
    return {m: {l: (statistics.mean(v), len(v)) for l, v in por.items() if v} for m, por in valores.items()}, costo, info, []


def suite_generacion(items, local):
    if not local:  # RAGAS answer relevancy with OpenAI's embeddings
        os.environ["LMSTUDIO_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["LMSTUDIO_EMBED_MODEL"] = MODELO_EMB
        os.environ["EMB_API_KEY"] = os.environ["OPENAI_API_KEY"]
    ctx = json.loads(sg.CONTEXTOS.read_text(encoding="utf-8"))
    cache = {}

    def guardar():
        pass
    sg.generar(items, ctx, cache, guardar, sistema=sens.SIS_SOLO_DOCUMENTOS)
    uso = asyncio.run(sg.evaluar(items, ctx, cache, guardar))
    res = {m: {} for m in MET_GEN}
    for lang in ("es", "en"):
        r = [x for x in items if x["lang"] == lang and x["respondible"]]
        s = [x for x in items if x["lang"] == lang and not x["respondible"]]
        k = lambda x: f"{x['id']}::{x['lang']}"  # noqa: E731
        for m in ("faithfulness", "answer_relevancy", "exactitud"):
            v = [cache[f"{m}::{k(x)}"]["valor"] for x in r if cache[f"{m}::{k(x)}"]["valor"] is not None]
            if v:
                res[m][lang] = (statistics.mean(v), len(r))
        nc = nb = 0
        for x in r:
            c, b = sg.citas(cache[f"gen::{k(x)}"]["respuesta"], ctx[k(x)]["chunks"], x["gold"])
            nc, nb = nc + c, nb + b
        if r:
            res["precision_citas"][lang] = (nb / nc if nc else 0.0, len(r))
            res["no_abstencion_falsa"][lang] = (1 - sum(cache[f"clase::{k(x)}"]["valor"] == "abstiene" for x in r) / len(r), len(r))
        if s:
            res["abstencion_correcta"][lang] = (sum(cache[f"clase::{k(x)}"]["valor"] == "abstiene" for x in s) / len(s), len(s))
    metricas_juez = [v for kk, v in cache.items() if not kk.startswith("gen::")]
    sin = sum(1 for v in metricas_juez if v.get("valor") is None)
    costo_gen = sum(v["costo"] for kk, v in cache.items() if kk.startswith("gen::"))
    costo_ev = (uso["in"] * PRECIO["in"] + uso["out"] * PRECIO["out"]) / 1e6
    info = {"respuestas": len(items), "llamadas_juez": uso["llamadas"], "metricas_sin_puntaje": sin,
            "costo_generacion": round(costo_gen, 4), "costo_evaluacion": round(costo_ev, 4)}
    fallas = []
    if sin > MAX_SIN_PUNTAJE * len(metricas_juez):
        fallas.append(f"{sin}/{len(metricas_juez)} judge metrics without a score (maximum {MAX_SIN_PUNTAJE:.0%})")
    return res, costo_gen + costo_ev, info, fallas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=("recuperacion", "generacion"), required=True)
    ap.add_argument("--calibrar", "--calibrate", action="store_true", help="first run: prints the values and thresholds, without applying them")
    ap.add_argument("--local", action="store_true", help="smoke test with local bge-m3 and the existing index")
    ap.add_argument("--limite", "--limit", type=int, default=0, help="N answerable and 1 unanswerable question per language (smoke test)", metavar="LIMIT")
    args = ap.parse_args()
    aplicar = not (args.calibrar or args.local or args.limite)
    if aplicar and (UMBRALES is None or args.suite not in UMBRALES):
        raise SystemExit("No calibrated thresholds: run with --calibrar and set UMBRALES with the rule in the docstring.")
    t0 = time.time()
    items = golden(args.limite)
    correr = suite_recuperacion if args.suite == "recuperacion" else suite_generacion
    valores, costo, info, fallas = correr(items, args.local)

    lineas = [f"## {args.suite} suite", "", "| Metric | Language | Value | n | Threshold |", "|---|---|---|---|---|"]
    calibrados = {}
    for m, por_lang in valores.items():
        for lang in ("es", "en"):
            if lang not in por_lang:
                continue
            v, n = por_lang[lang]
            u = UMBRALES[args.suite][m][lang] if aplicar else umbral_de(v, n)
            calibrados.setdefault(m, {})[lang] = round(u, 2)
            nota = "" if aplicar else " (calibrated)"
            lineas.append(f"| {m} | {lang} | {v:.3f} | {n} | {u:.2f}{nota} |")
            if aplicar and v < u - 1e-9:
                fallas.append(f"{m}/{lang}: {v:.3f} < {u:.2f}")
    lineas += ["", "Details: " + json.dumps(info, ensure_ascii=False),
               f"Anthropic cost of the run: ${costo:.4f}; duration {time.time() - t0:.0f} s"]
    if not aplicar:
        lineas += ["", f'UMBRALES["{args.suite}"] = ' + json.dumps(calibrados)]
    texto = "\n".join(lineas)
    print(texto)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    if fallas:
        raise SystemExit("FAILURE:\n- " + "\n- ".join(fallas))
    print("All checks passed." if aplicar else "No thresholds applied (calibration or smoke test).")


if __name__ == "__main__":
    main()
