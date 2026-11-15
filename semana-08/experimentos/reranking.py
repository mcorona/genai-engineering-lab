"""Activity 7: reranking with claude-haiku-5-5 over the vector top 20 (OpenSearch, bge-m3).

Metrics per language, with and without the reranker: recall@5, nDCG@10 (binary relevance: the chunk contains
a reference passage) and MRR. Also: cost per query with week 7's prices.json, and latency.
Requires LM Studio with bge-m3, OpenSearch with the semana8 index, and ANTHROPIC_API_KEY.
"""
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
sys.path.insert(0, str(AQUI))
from embeddings_comparacion import emb_bge  # noqa: E402

OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
COLECCION = "semana8"
CANDIDATOS = 20
MODELO = "claude-haiku-5-5"
PRECIO = json.loads((RAIZ.parent / "semana-07" / "prices.json").read_text(encoding="utf-8"))[f"anthropic:{MODELO}"]
SISTEMA = ("Eres un evaluador de relevancia. Recibes una consulta y pasajes numerados. "
           "Responde SOLO con JSON: {\"orden\": [índices de los 10 pasajes más relevantes, del más relevante al menos]}. "
           "Sin texto adicional.")


def http(metodo, url, cuerpo=None, cabeceras=None):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo,
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def buscar_vectorial(vec, k):
    r = http("POST", f"{OPENSEARCH}/{COLECCION}/_search",
             {"size": k, "query": {"knn": {"embedding": {"vector": vec, "k": k}}}})
    return [(h["_source"]["source"], h["_source"]["content"]) for h in r["hits"]["hits"]]


def llamar_haiku(consulta, candidatos):
    bloque = "\n\n".join(f"[{i}] {c[:800]}" for i, (_, c) in enumerate(candidatos))
    cuerpo = {"model": MODELO, "max_tokens": 4096, "system": SISTEMA,
              "messages": [{"role": "user", "content": f"Consulta: {consulta}\n\nPasajes:\n{bloque}"}]}
    r = http("POST", "https://api.anthropic.com/v1/messages", cuerpo, {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
    m = re.search(r"\{.*\}", texto, re.S)
    orden = None
    if m:
        try:
            orden = [i for i in json.loads(m.group(0))["orden"] if isinstance(i, int) and 0 <= i < len(candidatos)]
        except (json.JSONDecodeError, KeyError, TypeError):
            orden = None
    return orden, r["usage"]["input_tokens"], r["usage"]["output_tokens"]


def relevante(c, gold):
    src, cont = c
    return any(src == g["source"] and g["passage"] in cont for g in gold)


def metricas(consulta, ranking):
    gold = consulta["gold"]
    # Each reference passage counts only once: with overlapping chunks, the same passage
    # can be in two chunks, and without this check nDCG could exceed 1.
    rel, usados = [], set()
    for c in ranking[:10]:
        idx = next((i for i, g in enumerate(gold)
                    if i not in usados and c[0] == g["source"] and g["passage"] in c[1]), None)
        if idx is not None:
            usados.add(idx)
            rel.append(1)
        else:
            rel.append(0)
    rec = {}
    for corte in (5, 10):
        hits = sum(1 for g in gold
                   if any(c[0] == g["source"] and g["passage"] in c[1] for c in ranking[:corte]))
        rec[corte] = hits / len(gold)
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 10)))
    ndcg = dcg / ideal if ideal else 0.0
    pos = next((i for i, c in enumerate(ranking[:10], start=1) if relevante(c, gold)), None)
    mrr = 1 / pos if pos else 0.0
    return rec[5], ndcg, mrr


def main():
    for idioma in ("es", "en"):
        consultas = [json.loads(l) for l in
                     (RAIZ / "datasets" / f"recuperacion_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        vq, _ = emb_bge([q["question"] for q in consultas], "query")
        base, rer = [], []
        fallos, tin, tout, latencias = 0, 0, 0, []
        for q, v in zip(consultas, vq):
            cands = buscar_vectorial(v, CANDIDATOS)
            base.append(metricas(q, cands[:10]))
            t0 = time.perf_counter()
            orden, a, b = llamar_haiku(q["question"], cands)
            latencias.append((time.perf_counter() - t0) * 1000)
            tin += a
            tout += b
            if orden is None:
                fallos += 1
                ranking = cands[:10]
            else:
                ordenados = list(dict.fromkeys(orden))
                resto = [i for i in range(len(cands)) if i not in ordenados]
                ranking = [cands[i] for i in (ordenados + resto)[:10]]
            rer.append(metricas(q, ranking))
        n = len(consultas)
        costo = (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6
        for nombre, filas in (("vectorial", base), ("vectorial + haiku", rer)):
            print(f"{idioma} {nombre:<18} recall@5={sum(f[0] for f in filas)/n:.3f} "
                  f"nDCG@10={sum(f[1] for f in filas)/n:.3f} MRR={sum(f[2] for f in filas)/n:.3f}")
        print(f"{idioma} haiku: format_failures={fallos}/{n} total_cost=${costo:.5f} "
              f"per_query=${costo/n:.6f} p50={statistics.median(latencias):.0f} ms\n")


if __name__ == "__main__":
    main()
