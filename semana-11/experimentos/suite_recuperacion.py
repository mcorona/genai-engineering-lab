"""Week 11, activity 2: the retrieval suite (does not call the answer model).

Gold set: datasets/eval_rag_{es,en}.jsonl, only the answerable questions (65 per language: 50 base and 15 non-text).
Index: activity 7's semana10.chunks (30 documents, 68 chunks, bge-m3), a user of the alfa tenant with every role;
the tenant and role filter goes inside the query, as in the assistant.

Configurations:
- base: vector + filter, in similarity order (top 20 candidates).
- adoptado: vector + filter + reranking with Haiku 5.5 (the one from week 8 and the assistant) over the 20 candidates.

In-house metrics (exact relevance: a chunk of the reference document that contains the passage; for non-text questions,
the exact answer; the same definition as weeks 8 to 10):
- recall@k (k = 1, 3, 5, 10): the fraction of reference passages that appear in the top k.
- MRR: the inverse of the position of the first relevant chunk in the top 10.
- nDCG@10: binary gain; each passage counts only once (the chunks overlap).
- precision@5: the fraction of the first 5 chunks that are relevant (the in-house counterpart of context precision).
RAGAS 0.4.3 metrics over the top 5, with the reference answer and judge Haiku 5.5 low:
- context precision (with reference): the position-weighted precision of the chunks useful for the reference.
- context recall: the fraction of the reference's claims that can be attributed to the top 5.
In-house vs. RAGAS comparison on the same queries: correlation, an agreement table (recall@5 = 1 vs. context
recall >= 0.5) and the disagreements with their text. Difference between configurations: the paired mean per query with
a 95 % bootstrap interval (2,000 resamples, seed 11).
Cost: reranking and the RAGAS judge separately (the judge uses a disk cache, so chunks repeated across
configurations are not billed again). Cache of rankings and scores in resultados/suite_recuperacion_cache.json.
Requires NLQ_DSN, LM Studio with bge-m3, and ANTHROPIC_API_KEY.
"""
import asyncio
import csv
import json
import math
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO = RAIZ.parent
sys.path.insert(0, str(REPO / "semana-10" / "experimentos"))
import asistente as a  # noqa: E402

RES = RAIZ / "resultados"
CACHE = RES / "suite_recuperacion_cache.json"
USUARIO = {"tenant": "alfa", "roles": a.USUARIO["roles"]}
CANDIDATOS, K_RAGAS = 20, 5
CONFIGS = ("base", "adoptado")
CONCURRENCIA = 8
PRECIO = a.PRECIOS[f"anthropic:{a.HAIKU}"]


def norm(s):
    return " ".join(s.replace("**", "").lower().split())


def pasajes_en(chunk, gold):
    s, c = chunk
    return {i for i, g in enumerate(gold) if Path(g["source"]).stem == s and norm(g["passage"]) in norm(c)}


def metricas(ranking, gold):
    m = {}
    for k in (1, 3, 5, 10):
        hallados = set().union(*(pasajes_en(c, gold) for c in ranking[:k])) if ranking[:k] else set()
        m[f"recall@{k}"] = len(hallados) / len(gold)
    rel, usados = [], set()
    for c in ranking[:10]:
        nuevos = pasajes_en(c, gold) - usados
        rel.append(1 if nuevos else 0)
        usados |= set(list(nuevos)[:1])
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
    m["ndcg@10"] = sum(r / math.log2(i + 2) for i, r in enumerate(rel)) / ideal
    pos = next((i for i, c in enumerate(ranking[:10], 1) if pasajes_en(c, gold)), None)
    m["mrr"] = 1 / pos if pos else 0.0
    m["precision@5"] = sum(1 for c in ranking[:5] if pasajes_en(c, gold)) / 5
    # AP@5: the same formula as RAGAS context precision (the mean of precision@i at the relevant positions),
    # but with exact relevance instead of the judge. Added after the first run to compare one to one.
    r = [bool(pasajes_en(c, gold)) for c in ranking[:5]]
    m["ap@5"] = (sum(sum(r[:i]) / i for i in range(1, 6) if r[i - 1]) / sum(r)) if any(r) else 0.0
    return m


def recuperar(items, cache):
    faltan = [x for x in items if f"base::{x['id']}::{x['lang']}" not in cache]
    if faltan:
        import psycopg
        conn = psycopg.connect(os.environ["NLQ_DSN"], autocommit=True)
        conn.execute("SET hnsw.ef_search = 100")
        conn.execute("SET hnsw.iterative_scan = strict_order")
        t0 = time.perf_counter()
        vecs, _ = a.emb_bge([x["question"] for x in faltan], "query")
        lat_emb = (time.perf_counter() - t0) / len(faltan)
        for x, v in zip(faltan, vecs):
            t0 = time.perf_counter()
            filas = conn.execute(
                "SELECT source, content FROM semana10.chunks WHERE tenant_id = %s AND roles && %s::text[] "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (USUARIO["tenant"], USUARIO["roles"], "[" + ",".join(map(str, v)) + "]", CANDIDATOS)).fetchall()
            cache[f"base::{x['id']}::{x['lang']}"] = {"ranking": [list(f) for f in filas],
                                                      "latencia_s": round(lat_emb + time.perf_counter() - t0, 4), "costo": 0.0}

    def rerank(x):
        k = f"adoptado::{x['id']}::{x['lang']}"
        if k in cache:
            return
        cands = [tuple(c) for c in cache[f"base::{x['id']}::{x['lang']}"]["ranking"]]
        t0 = time.perf_counter()
        orden, tin, tout = a.llamar_haiku(x["question"], cands)
        ordenados = list(dict.fromkeys(orden or [])) + [i for i in range(len(cands)) if i not in (orden or [])]
        cache[k] = {"ranking": [list(cands[i]) for i in ordenados], "rerank_fallo": orden is None,
                    "latencia_s": round(cache[f"base::{x['id']}::{x['lang']}"]["latencia_s"] + time.perf_counter() - t0, 4),
                    "costo": (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6}
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(rerank, items))


async def puntuar_ragas(items, cache, guardar):
    from anthropic import AsyncAnthropic
    from ragas.cache import DiskCacheBackend
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, ContextRecall

    uso = {"in": 0, "out": 0, "llamadas": 0}
    cliente = AsyncAnthropic()
    crear = cliente.messages.create

    async def crear_contando(*args, **kw):
        r = await crear(*args, **kw)
        uso["in"] += r.usage.input_tokens
        uso["out"] += r.usage.output_tokens
        uso["llamadas"] += 1
        return r
    cliente.messages.create = crear_contando
    juez = llm_factory(a.HAIKU, provider="anthropic", client=cliente, max_tokens=4000,
                       extra_body={"output_config": {"effort": "low"}},
                       cache=DiskCacheBackend(str(Path.home() / ".cache" / "ragas_semana11")))
    juez.model_args.pop("temperature", None)
    juez.model_args.pop("top_p", None)
    prec, rec = ContextPrecision(llm=juez), ContextRecall(llm=juez)
    sem = asyncio.Semaphore(CONCURRENCIA)

    async def uno(config, x):
        k = f"ragas::{config}::{x['id']}::{x['lang']}"
        if k in cache:
            return
        ctx = [c for _, c in cache[f"{config}::{x['id']}::{x['lang']}"]["ranking"][:K_RAGAS]]
        async with sem:
            res = {}
            for nombre, metrica, kw in (("context_precision", prec, dict(user_input=x["question"], reference=x["referencia"], retrieved_contexts=ctx)),
                                        ("context_recall", rec, dict(user_input=x["question"], retrieved_contexts=ctx, reference=x["referencia"]))):
                try:
                    res[nombre] = (await metrica.ascore(**kw)).value
                except Exception as e:  # noqa: BLE001
                    res[nombre] = None
                    res[f"{nombre}_error"] = type(e).__name__
        cache[k] = res
        guardar()
    await asyncio.gather(*(uno(c, x) for c in CONFIGS for x in items))
    return uso


def bootstrap(dif, n=2000, semilla=11):
    rnd = random.Random(semilla)
    medias = sorted(statistics.mean(rnd.choice(dif) for _ in dif) for _ in range(n))
    return statistics.mean(dif), medias[int(0.025 * n)], medias[int(0.975 * n) - 1]


def pearson(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sx, sy = math.sqrt(sum((v - mx) ** 2 for v in x)), math.sqrt(sum((v - my) ** 2 for v in y))
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / (sx * sy) if sx and sy else float("nan")


def main():
    items = [x for lang in ("es", "en") for l in (RAIZ / "datasets" / f"eval_rag_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
             if (x := json.loads(l))["respondible"]]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    def guardar():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False) + "\n", encoding="utf-8")

    recuperar(items, cache)
    guardar()
    uso = asyncio.run(puntuar_ragas(items, cache, guardar))
    guardar()

    detalle = []
    for config in CONFIGS:
        for x in items:
            r = cache[f"{config}::{x['id']}::{x['lang']}"]
            g = cache[f"ragas::{config}::{x['id']}::{x['lang']}"]
            detalle.append({"config": config, "id": x["id"], "lang": x["lang"],
                            "tipo": "no_textual" if x["tipo"].startswith("no_textual") else "base",
                            **metricas([tuple(c) for c in r["ranking"]], x["gold"]),
                            "context_precision": g.get("context_precision"), "context_recall": g.get("context_recall"),
                            "ragas_error": g.get("context_precision_error", "") or g.get("context_recall_error", ""),
                            "latencia_s": r["latencia_s"], "costo_rerank": r["costo"]})
    campos = ["recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@10", "precision@5", "ap@5", "context_precision", "context_recall"]

    def media(f, c):
        v = [d[c] for d in f if d[c] is not None]
        return statistics.mean(v) if v else float("nan")

    print("## Metrics per configuration\n")
    print("| Configuration | Language | Type | n | " + " | ".join(campos) + " | p50 latency (s) |")
    print("|" + "---|" * (len(campos) + 5))
    for config in CONFIGS:
        for lang in ("es", "en"):
            for tipo in ("base", "no_textual", "todas"):
                f = [d for d in detalle if d["config"] == config and d["lang"] == lang and (tipo == "todas" or d["tipo"] == tipo)]
                print(f"| {config} | {lang} | {tipo} | {len(f)} | " + " | ".join(f"{media(f, c):.3f}" for c in campos)
                      + f" | {statistics.median(d['latencia_s'] for d in f):.2f} |")

    print("\n## Difference adoptado − base (paired mean per query, 95 % bootstrap CI)\n")
    print("| Language | Metric | Difference | 95 % CI | Queries that rise / fall |")
    print("|---|---|---|---|---|")
    for lang in ("es", "en"):
        for c in campos:
            par = [(b[c], d[c]) for b in detalle if b["config"] == "base" and b["lang"] == lang
                   for d in detalle if d["config"] == "adoptado" and d["id"] == b["id"] and d["lang"] == lang
                   and b[c] is not None and d[c] is not None]
            dif = [d - b for b, d in par]
            m, lo, hi = bootstrap(dif)
            print(f"| {lang} | {c} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {sum(v > 0 for v in dif)} / {sum(v < 0 for v in dif)} |")

    print("\n## In-house vs. RAGAS (same queries, top 5)\n")
    print("| Configuration | Pair | Pearson | Agreement |")
    print("|---|---|---|---|")
    desacuerdos = []
    for config in CONFIGS:
        f = [d for d in detalle if d["config"] == config and d["context_recall"] is not None and d["context_precision"] is not None]
        acuerdo = sum((d["recall@5"] == 1) == (d["context_recall"] >= 0.5) for d in f)
        print(f"| {config} | recall@5 / context_recall | {pearson([d['recall@5'] for d in f], [d['context_recall'] for d in f]):.3f} | "
              f"{acuerdo}/{len(f)} (recall@5 = 1 contra context_recall >= 0.5) |")
        print(f"| {config} | precision@5 / context_precision | {pearson([d['precision@5'] for d in f], [d['context_precision'] for d in f]):.3f} | - |")
        print(f"| {config} | mrr / context_precision | {pearson([d['mrr'] for d in f], [d['context_precision'] for d in f]):.3f} | - |")
        print(f"| {config} | ap@5 / context_precision | {pearson([d['ap@5'] for d in f], [d['context_precision'] for d in f]):.3f} | "
              f"{sum(abs(d['ap@5'] - d['context_precision']) <= 0.1 for d in f)}/{len(f)} with a difference <= 0.1; RAGAS higher in "
              f"{sum(d['context_precision'] > d['ap@5'] + 0.1 for d in f)}, lower in {sum(d['context_precision'] < d['ap@5'] - 0.1 for d in f)} |")
        desacuerdos += [(config, d) for d in f if (d["recall@5"] == 1) != (d["context_recall"] >= 0.5)
                        or abs(d["ap@5"] - d["context_precision"]) > 0.3]
    preguntas = {(x["id"], x["lang"]): x["question"] for x in items}
    print("\nDesacuerdos (recall@5 contra context_recall, o |ap@5 - context_precision| > 0.3):")
    for config, d in desacuerdos:
        print(f"- {config} {d['id']} {d['lang']}: recall@5={d['recall@5']:.2f}, context_recall={d['context_recall']:.2f}, "
              f"ap@5={d['ap@5']:.2f}, context_precision={d['context_precision']:.2f} | {preguntas[(d['id'], d['lang'])][:80]}")
    errores = sum(1 for d in detalle if d["ragas_error"])
    costo_rerank = sum(d["costo_rerank"] for d in detalle)
    print(f"\nRAGAS without a score (judge error): {errores} of {len(detalle)}")
    print(f"Cost: reranking ${costo_rerank:.4f} (${costo_rerank / len(items):.5f} per query); RAGAS judge in this run "
          f"${(uso['in'] * PRECIO['in'] + uso['out'] * PRECIO['out']) / 1e6:.4f} ({uso['llamadas']} calls, "
          f"{uso['in']} input tokens and {uso['out']} output tokens; cached answers are not billed)")
    with (RES / "suite_recuperacion_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)


if __name__ == "__main__":
    main()
