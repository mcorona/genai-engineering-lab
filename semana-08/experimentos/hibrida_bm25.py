"""Activity 6: BM25, vector and hybrid (RRF) search over OpenSearch's semana8 index.

BM25 uses the standard analyzer of the content field (the OpenSearch default).
Hybrid: RRF fusion (k=60) of the BM25 top 20 and the vector top 20.
Metrics: recall@5, recall@10 and MRR per reference passage, in ES and EN.
Requires LM Studio with bge-m3 and OpenSearch running with the vectors loaded.
"""
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from cargar_vector_dbs import COLECCION, http  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

RAIZ = AQUI.parents[0]
OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
CANDIDATOS = 20
K_RRF = 60


def buscar_bm25(texto, k):
    r = http("POST", f"{OPENSEARCH}/{COLECCION}/_search",
             {"size": k, "query": {"match": {"content": texto}}})
    return [(h["_id"], h["_source"]["source"], h["_source"]["content"]) for h in r["hits"]["hits"]]


def buscar_vectorial(vec, k):
    r = http("POST", f"{OPENSEARCH}/{COLECCION}/_search",
             {"size": k, "query": {"knn": {"embedding": {"vector": vec, "k": k}}}})
    return [(h["_id"], h["_source"]["source"], h["_source"]["content"]) for h in r["hits"]["hits"]]


def fusionar_rrf(listas, k_rrf=K_RRF):
    puntaje, datos = {}, {}
    for lista in listas:
        for pos, (cid, src, cont) in enumerate(lista, start=1):
            puntaje[cid] = puntaje.get(cid, 0.0) + 1.0 / (k_rrf + pos)
            datos[cid] = (cid, src, cont)
    orden = sorted(puntaje, key=lambda c: -puntaje[c])
    return [datos[c] for c in orden]


def metricas(consulta, ranking):
    """recall@5, recall@10 and MRR for a query with its reference passages."""
    r5 = r10 = 0.0
    rr = []
    for g in consulta["gold"]:
        pos = next((i for i, (_, s, c) in enumerate(ranking, start=1)
                    if s == g["source"] and g["passage"] in c), None)
        if pos is not None and pos <= 5:
            r5 += 1
        if pos is not None and pos <= 10:
            r10 += 1
        rr.append(1.0 / pos if pos is not None and pos <= 10 else 0.0)
    n = len(consulta["gold"])
    return r5 / n, r10 / n, sum(rr) / n


def main():
    for idioma in ("es", "en"):
        consultas = [json.loads(l) for l in
                     (RAIZ / "datasets" / f"recuperacion_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        vq, _ = emb_bge([q["question"] for q in consultas], "query")
        metodos = {"bm25": [], "vectorial": [], "hibrido_rrf": []}
        for q, v in zip(consultas, vq):
            bm = buscar_bm25(q["question"], CANDIDATOS)
            vec = buscar_vectorial(v, CANDIDATOS)
            metodos["bm25"].append(metricas(q, bm[:10]))
            metodos["vectorial"].append(metricas(q, vec[:10]))
            metodos["hibrido_rrf"].append(metricas(q, fusionar_rrf([bm, vec])[:10]))
        for nombre, filas in metodos.items():
            n = len(filas)
            r5 = sum(f[0] for f in filas) / n
            r10 = sum(f[1] for f in filas) / n
            mrr = sum(f[2] for f in filas) / n
            print(f"{idioma} {nombre:<13} recall@5={r5:.3f} recall@10={r10:.3f} MRR={mrr:.3f}")


if __name__ == "__main__":
    main()
