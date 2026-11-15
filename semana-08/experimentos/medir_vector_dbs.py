"""Activity 5: quality, latency, size and filters in pgvector, Qdrant and OpenSearch.

The same queries (ES and EN), the same k and the same recall as in activity 2.
Requires the same as cargar_vector_dbs.py: PG_ADMIN_DSN, LM Studio with bge-m3, and both databases running.
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from cargar_vector_dbs import COLECCION, http  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

RAIZ = AQUI.parents[0]
KMAX = 10
REPETICIONES = 3
QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")
OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")


def buscar_pgvector(conn, v, k, fuente=None):
    vec = "[" + ",".join(map(str, v)) + "]"
    if fuente:
        filas = conn.execute("SELECT source, content FROM semana8.chunks WHERE source = %s "
                             "ORDER BY embedding <=> %s::vector LIMIT %s", (fuente, vec, k)).fetchall()
    else:
        filas = conn.execute("SELECT source, content FROM semana8.chunks "
                             "ORDER BY embedding <=> %s::vector LIMIT %s", (vec, k)).fetchall()
    return [(s, c) for s, c in filas]


def buscar_qdrant(v, k, fuente=None):
    cuerpo = {"query": v, "limit": k, "with_payload": True}
    if fuente:
        cuerpo["filter"] = {"must": [{"key": "source", "match": {"value": fuente}}]}
    r = http("POST", f"{QDRANT}/collections/{COLECCION}/points/query", cuerpo)
    return [(p["payload"]["source"], p["payload"]["content"]) for p in r["result"]["points"]]


def buscar_opensearch(v, k, fuente=None):
    # The filter goes inside the knn clause (efficient filtering), not next to it (post-filtering).
    knn = {"embedding": {"vector": v, "k": k}}
    if fuente:
        knn["embedding"]["filter"] = {"term": {"source": fuente}}
    consulta = {"knn": knn}
    r = http("POST", f"{OPENSEARCH}/{COLECCION}/_search", {"size": k, "query": consulta})
    return [(h["_source"]["source"], h["_source"]["content"]) for h in r["hits"]["hits"]]


def main():
    from chunking_pasajes import ESTRATEGIAS  # noqa: F401  (the same chunking as the load)
    consultas = []
    for idioma in ("es", "en"):
        ruta = RAIZ / "datasets" / f"recuperacion_{idioma}.jsonl"
        consultas += [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()]
    vq, _ = emb_bge([q["question"] for q in consultas], "query")

    motores = {
        "pgvector": lambda v, k, f=None: buscar_pgvector(CONN, v, k, f),
        "qdrant": buscar_qdrant,
        "opensearch": buscar_opensearch,
    }
    with psycopg.connect(os.environ["PG_ADMIN_DSN"]) as conn:
        global CONN
        CONN = conn

        print(f"{'motor':<12}{'recall@5':>10}{'recall@10':>11}{'p50 ms':>9}{'p95 ms':>9}{'tamaño':>22}")
        for nombre, buscar in motores.items():
            r5, r10, tiempos = [], [], []
            for q, v in zip(consultas, vq):
                resultados = buscar(v, KMAX)
                for corte, lista in ((5, r5), (10, r10)):
                    top = resultados[:corte]
                    hits = sum(1 for g in q["gold"]
                               if any(s == g["source"] and g["passage"] in c for s, c in top))
                    lista.append(hits / len(q["gold"]))
                for _ in range(REPETICIONES):
                    t0 = time.perf_counter()
                    buscar(v, KMAX)
                    tiempos.append((time.perf_counter() - t0) * 1000)
            tiempos.sort()
            p50 = statistics.median(tiempos)
            p95 = tiempos[int(0.95 * (len(tiempos) - 1))]
            if nombre == "pgvector":
                tam = conn.execute("SELECT pg_size_pretty(pg_total_relation_size('semana8.chunks'))").fetchone()[0]
            elif nombre == "opensearch":
                tam = http("GET", f"{OPENSEARCH}/_cat/indices/{COLECCION}?format=json")[0]["store.size"]
            else:
                tam = "n/d"
            print(f"{nombre:<12}{statistics.mean(r5):>10.3f}{statistics.mean(r10):>11.3f}"
                  f"{p50:>9.1f}{p95:>9.1f}{tam:>22}")

        # Metadata filter: every result must come from the requested document
        objetivo = "politica_reorden.md"
        print(f"\nfilter by source='{objetivo}' (5 queries):")
        for nombre, buscar in motores.items():
            ok = 0
            for v in vq[:5]:
                res = buscar(v, 5, objetivo)
                ok += int(bool(res) and all(s == objetivo for s, _ in res))
            print(f"  {nombre:<12} {ok}/5 correct")


if __name__ == "__main__":
    main()
