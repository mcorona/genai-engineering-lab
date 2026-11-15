"""Activity 4: the same vectors (bge-m3, fixed 400/80 chunking) in pgvector, Qdrant and OpenSearch.

Requires: PG_ADMIN_DSN (inventory-copilot's Postgres with pgvector), LM Studio with bge-m3,
and Qdrant and OpenSearch running from semana-08/infra/docker-compose.yml.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from chunking_pasajes import ESTRATEGIAS, CORPUS  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

COLECCION = "semana8"
DIM = 1024


def http(metodo, url, cuerpo=None, ctype="application/json", ignorar=()):
    datos = None
    if cuerpo is not None:
        datos = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method=metodo, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code in ignorar:
            return {}
        raise RuntimeError(f"{metodo} {url}: {e.code} {e.read()[:300]!r}") from e


def filas():
    trocear = ESTRATEGIAS["fijo_400_solape_80"]
    out, i = [], 0
    for p in sorted(CORPUS.glob("*.md")):
        for n, c in enumerate(trocear(p.read_text(encoding="utf-8"), p.name)):
            out.append({"id": i, "source": p.name, "chunk_index": n, "content": c})
            i += 1
    return out


def cargar_pgvector(fs, vecs):
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("DROP SCHEMA IF EXISTS semana8 CASCADE")
        conn.execute("CREATE SCHEMA semana8")
        conn.execute(f"CREATE TABLE semana8.chunks (id int PRIMARY KEY, source text NOT NULL, "
                     f"chunk_index int NOT NULL, content text NOT NULL, embedding vector({DIM}) NOT NULL)")
        conn.execute("CREATE INDEX ON semana8.chunks USING hnsw (embedding vector_cosine_ops)")
        with conn.cursor() as cur:
            for f, v in zip(fs, vecs):
                cur.execute("INSERT INTO semana8.chunks VALUES (%s,%s,%s,%s,%s)",
                            (f["id"], f["source"], f["chunk_index"], f["content"],
                             "[" + ",".join(map(str, v)) + "]"))
        return conn.execute("SELECT count(*) FROM semana8.chunks").fetchone()[0]


def cargar_qdrant(fs, vecs):
    base = os.getenv("QDRANT_URL", "http://localhost:6333")
    http("DELETE", f"{base}/collections/{COLECCION}", ignorar=(404,))
    http("PUT", f"{base}/collections/{COLECCION}",
         {"vectors": {"size": DIM, "distance": "Cosine"}})
    puntos = [{"id": f["id"], "vector": v,
               "payload": {"source": f["source"], "chunk_index": f["chunk_index"], "content": f["content"]}}
              for f, v in zip(fs, vecs)]
    http("PUT", f"{base}/collections/{COLECCION}/points?wait=true", {"points": puntos})
    return http("GET", f"{base}/collections/{COLECCION}")["result"]["points_count"]


def cargar_opensearch(fs, vecs):
    base = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    http("DELETE", f"{base}/{COLECCION}", ignorar=(404,))
    http("PUT", f"{base}/{COLECCION}", {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            "source": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text"},
            "embedding": {"type": "knn_vector", "dimension": DIM,
                          "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"}},
        }}})
    lineas = []
    for f, v in zip(fs, vecs):
        lineas.append(json.dumps({"index": {"_index": COLECCION, "_id": str(f["id"])}}))
        lineas.append(json.dumps({"source": f["source"], "chunk_index": f["chunk_index"],
                                  "content": f["content"], "embedding": v}))
    http("POST", f"{base}/_bulk", "\n".join(lineas) + "\n", ctype="application/x-ndjson")
    http("POST", f"{base}/{COLECCION}/_refresh")
    return http("GET", f"{base}/{COLECCION}/_count")["count"]


def main():
    fs = filas()
    print(f"chunks: {len(fs)}")
    vecs, _ = emb_bge([f["content"] for f in fs], "doc")
    print(f"vectors: {len(vecs)} x {len(vecs[0])}")
    print(f"pgvector: {cargar_pgvector(fs, vecs)} rows")
    print(f"qdrant:   {cargar_qdrant(fs, vecs)} points")
    print(f"opensearch: {cargar_opensearch(fs, vecs)} documents")


if __name__ == "__main__":
    main()
