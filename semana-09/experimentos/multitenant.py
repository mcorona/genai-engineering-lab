"""Activity 6: multi-tenant isolation in pgvector, Qdrant and OpenSearch.

Loads two tenants into new indexes (semana9.chunks_mt, semana9_mt, semana9_mt):
- alfa: the 57 week 8 chunks;
- beta: corpus_beta/ (10 documents almost identical to alfa's, with a different figure in the reference passage).
bge-m3 vectors and fixed 400/80 chunking in both. The filter goes inside the query, as in activity 5.

Measures, per database and language:
- Sweep: 50 base questions x 2 tenants, a user with every role (only the tenant filter acts).
  The leak across tenants with the filter (must be 0) and, without the filter, how many chunks of the other
  tenant an alfa user and a beta user would see (separately: added together they are always 10 per question).
- Overlapping cases (datasets/multitenant_*.jsonl): 10 questions x 2 tenants, with a role that sees the document.
  The tenant's own figure in the top 5 with the filter; the other tenant's figure returned (without / with the
  filter; with it, it must be 0); how often, without the filter, the other tenant's passage ranks above the own one.
- Short results: filtered searches with fewer than k chunks although k are visible.

Exits with code 1 on any leak with the filter.
Requires PG_ADMIN_DSN, LM Studio with bge-m3, Qdrant and OpenSearch.
"""
import json
import os
import sys
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from cargar_vector_dbs import DIM, filas, http  # noqa: E402
from chunking_pasajes import ESTRATEGIAS  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402
from permisos import K, OPENSEARCH, QDRANT, ROLES, ROLES_DOC, vec_sql  # noqa: E402

NOMBRE = "semana9_mt"
TABLA = "semana9.chunks_mt"
TENANTS = ("alfa", "beta")


def todas_filas():
    alfa = [dict(f, tenant_id="alfa") for f in filas()]
    trocear = ESTRATEGIAS["fijo_400_solape_80"]
    beta, i = [], 1000
    for p in sorted((RAIZ / "corpus_beta").glob("*.md")):
        for n, c in enumerate(trocear(p.read_text(encoding="utf-8"), p.name)):
            beta.append({"id": i, "source": p.name, "chunk_index": n, "content": c, "tenant_id": "beta"})
            i += 1
    return alfa + beta


def cargar_pgvector(conn, fs, vecs):
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE SCHEMA IF NOT EXISTS semana9")
    conn.execute(f"DROP TABLE IF EXISTS {TABLA}")
    conn.execute(f"CREATE TABLE {TABLA} (id int PRIMARY KEY, source text NOT NULL, chunk_index int NOT NULL, "
                 f"content text NOT NULL, tenant_id text NOT NULL, roles text[] NOT NULL, embedding vector({DIM}) NOT NULL)")
    conn.execute(f"CREATE INDEX ON {TABLA} USING hnsw (embedding vector_cosine_ops)")
    conn.execute(f"CREATE INDEX ON {TABLA} (tenant_id)")
    conn.execute(f"CREATE INDEX ON {TABLA} USING gin (roles)")
    with conn.cursor() as cur:
        for f, v in zip(fs, vecs):
            cur.execute(f"INSERT INTO {TABLA} VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (f["id"], f["source"], f["chunk_index"], f["content"], f["tenant_id"], ROLES_DOC[f["source"]], vec_sql(v)))
    return conn.execute(f"SELECT tenant_id, count(*) FROM {TABLA} GROUP BY 1 ORDER BY 1").fetchall()


def cargar_qdrant(fs, vecs):
    http("DELETE", f"{QDRANT}/collections/{NOMBRE}", ignorar=(404,))
    http("PUT", f"{QDRANT}/collections/{NOMBRE}", {"vectors": {"size": DIM, "distance": "Cosine"}})
    for campo in ("tenant_id", "roles"):
        http("PUT", f"{QDRANT}/collections/{NOMBRE}/index?wait=true", {"field_name": campo, "field_schema": "keyword"})
    puntos = [{"id": f["id"], "vector": v,
               "payload": {"source": f["source"], "chunk_index": f["chunk_index"], "content": f["content"],
                           "tenant_id": f["tenant_id"], "roles": ROLES_DOC[f["source"]]}}
              for f, v in zip(fs, vecs)]
    http("PUT", f"{QDRANT}/collections/{NOMBRE}/points?wait=true", {"points": puntos})
    return http("GET", f"{QDRANT}/collections/{NOMBRE}")["result"]["points_count"]


def cargar_opensearch(fs, vecs):
    http("DELETE", f"{OPENSEARCH}/{NOMBRE}", ignorar=(404,))
    http("PUT", f"{OPENSEARCH}/{NOMBRE}", {
        "settings": {"index": {"knn": True}},
        "mappings": {"properties": {
            "source": {"type": "keyword"}, "chunk_index": {"type": "integer"}, "content": {"type": "text"},
            "tenant_id": {"type": "keyword"}, "roles": {"type": "keyword"},
            "embedding": {"type": "knn_vector", "dimension": DIM,
                          "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"}},
        }}})
    lineas = []
    for f, v in zip(fs, vecs):
        lineas.append(json.dumps({"index": {"_index": NOMBRE, "_id": str(f["id"])}}))
        lineas.append(json.dumps({"source": f["source"], "chunk_index": f["chunk_index"], "content": f["content"],
                                  "tenant_id": f["tenant_id"], "roles": ROLES_DOC[f["source"]], "embedding": v}))
    http("POST", f"{OPENSEARCH}/_bulk", "\n".join(lineas) + "\n", ctype="application/x-ndjson")
    http("POST", f"{OPENSEARCH}/{NOMBRE}/_refresh")
    return http("GET", f"{OPENSEARCH}/{NOMBRE}/_count")["count"]


def buscar_pgvector(conn, v, u):
    if u:
        q = (f"SELECT source, content, tenant_id FROM {TABLA} WHERE tenant_id = %s AND roles && %s::text[] "
             "ORDER BY embedding <=> %s::vector LIMIT %s")
        args = (u["tenant"], u["roles"], vec_sql(v), K)
    else:
        q = f"SELECT source, content, tenant_id FROM {TABLA} ORDER BY embedding <=> %s::vector LIMIT %s"
        args = (vec_sql(v), K)
    return [tuple(r) for r in conn.execute(q, args).fetchall()]


def buscar_qdrant(v, u):
    cuerpo = {"query": v, "limit": K, "with_payload": True}
    if u:
        cuerpo["filter"] = {"must": [{"key": "tenant_id", "match": {"value": u["tenant"]}},
                                     {"key": "roles", "match": {"any": u["roles"]}}]}
    r = http("POST", f"{QDRANT}/collections/{NOMBRE}/points/query", cuerpo)
    return [(p["payload"]["source"], p["payload"]["content"], p["payload"]["tenant_id"]) for p in r["result"]["points"]]


def buscar_opensearch(v, u):
    knn = {"embedding": {"vector": v, "k": K}}
    if u:
        knn["embedding"]["filter"] = {"bool": {"filter": [{"term": {"tenant_id": u["tenant"]}},
                                                          {"terms": {"roles": u["roles"]}}]}}
    r = http("POST", f"{OPENSEARCH}/{NOMBRE}/_search", {"size": K, "query": {"knn": knn}})
    return [(h["_source"]["source"], h["_source"]["content"], h["_source"]["tenant_id"]) for h in r["hits"]["hits"]]


def no_autorizado(fila, u):
    source, _, tenant = fila
    return tenant != u["tenant"] or not (set(ROLES_DOC[source]) & set(u["roles"]))


def posicion(res, pasaje, tenant):
    return next((i for i, (s, c, t) in enumerate(res) if t == tenant and pasaje in c), None)


def medir(nombre, buscar, fs, idioma, base, vb, solap, vs):
    fuga = cortos = barrido = 0
    otro_sin = {t: 0 for t in TENANTS}
    for x, v in zip(base, vb):
        res_n = buscar(v, None)
        for t in TENANTS:
            u = {"tenant": t, "roles": ROLES}
            res_f = buscar(v, u)
            barrido += 1
            fuga += sum(no_autorizado(r, u) for r in res_f)
            otro_sin[t] += sum(r[2] != t for r in res_n)
            if len(res_f) < min(K, sum(f["tenant_id"] == t for f in fs)):
                cortos += 1
    propia = otra_sin = otra_con = antes = casos = 0
    for x, v in zip(solap, vs):
        res_n = buscar(v, None)
        for t in TENANTS:
            otro = "beta" if t == "alfa" else "alfa"
            u = {"tenant": t, "roles": [ROLES_DOC[x["source"]][0]]}
            res_f = buscar(v, u)
            casos += 1
            fuga += sum(no_autorizado(r, u) for r in res_f)
            p_propia = posicion(res_f, x["gold"][t], t)
            propia += p_propia is not None and p_propia < 5
            otra_con += any(x["gold"][otro] in c for _, c, _ in res_f)
            otra_sin += posicion(res_n, x["gold"][otro], otro) is not None
            pp, po = posicion(res_n, x["gold"][t], t), posicion(res_n, x["gold"][otro], otro)
            antes += po is not None and (pp is None or po < pp)
            if len(res_f) < min(K, sum(f["tenant_id"] == t and bool(set(ROLES_DOC[f["source"]]) & set(u["roles"])) for f in fs)):
                cortos += 1
    print(f"| {nombre} | {idioma} | {barrido} | {fuga} | {otro_sin['alfa']} / {otro_sin['beta']} | {casos} | {propia}/{casos} | "
          f"{otra_sin}/{casos} / {otra_con}/{casos} | {antes}/{casos} | {cortos} |")
    return fuga + otra_con


def main():
    fs = todas_filas()
    vecs, _ = emb_bge([f["content"] for f in fs], "doc")
    conn = psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True)
    conn.execute("SET hnsw.ef_search = 100")
    try:
        conn.execute("SET hnsw.iterative_scan = strict_order")
    except psycopg.Error:
        print("pgvector: sin hnsw.iterative_scan; se usa ef_search = 100", file=sys.stderr)
    print(f"load: pgvector {cargar_pgvector(conn, fs, vecs)}, qdrant {cargar_qdrant(fs, vecs)}, "
          f"opensearch {cargar_opensearch(fs, vecs)} chunks\n")

    bases = [("pgvector", lambda v, u: buscar_pgvector(conn, v, u)), ("Qdrant", buscar_qdrant), ("OpenSearch", buscar_opensearch)]
    print("| Database | Language | Sweep (question x tenant) | Leak with filter | Other tenant's chunks without filter (in alfa's / beta's top 10) | "
          "Overlapping cases | Own figure in top 5 (with filter) | Other tenant's figure returned (without / with filter) | "
          "Other tenant ranked above own (without filter) | Short results |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    total = 0
    for idioma in ("es", "en"):
        base = [json.loads(l) for l in (RAIZ / "datasets" / f"avanzado_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        base = [x for x in base if x["tipo"] == "base"]
        solap = [json.loads(l) for l in (RAIZ / "datasets" / f"multitenant_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        vb, _ = emb_bge([x["question"] for x in base], "query")
        vs, _ = emb_bge([x["question"] for x in solap], "query")
        for nombre, buscar in bases:
            total += medir(nombre, buscar, fs, idioma, base, vb, solap, vs)
    conn.close()
    print(f"\ntotal leak with the filter (including the other tenant's figure): {total}")
    if total:
        sys.exit(1)


if __name__ == "__main__":
    main()
