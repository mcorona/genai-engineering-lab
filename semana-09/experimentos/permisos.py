"""Activity 5: metadata filters and ACLs in pgvector, Qdrant and OpenSearch.

Loads the 57 week 8 chunks (fixed 400/80, bge-m3) with `tenant_id` and `roles` into new indexes
(semana9.chunks, semana9_acl, semana9_acl) and applies the filter INSIDE the search query.

Measures, per database and language:
- Permission leak: chunks returned (top 10) to a user without permission. It is judged against
  datasets/permisos.json, not against what the database stores, to also detect loading errors.
  Sweep: 50 base questions x 6 roles, with and without the filter (contrast).
- recall@5 with vs. without the filter, on the question-role pairs where the role can see the document.
- Permission cases from the gold set: allowed (recall@5) and forbidden (passage returned: must be 0).
- Short results: filtered searches with fewer than k chunks although k are visible.

Exits with code 1 on any leak with the filter.
Requires PG_ADMIN_DSN, LM Studio with bge-m3, Qdrant and OpenSearch (semana-08/infra/docker-compose.yml).
"""
import json
import os
import sys
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from cargar_vector_dbs import DIM, filas, http  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import metricas  # noqa: E402

PERMISOS = json.loads((RAIZ / "datasets" / "permisos.json").read_text(encoding="utf-8"))
ROLES_DOC = PERMISOS["roles_por_documento"]
ROLES = sorted({r for rs in ROLES_DOC.values() for r in rs})
TENANT = "alfa"
NOMBRE = "semana9_acl"
K = 10
QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")
OPENSEARCH = os.getenv("OPENSEARCH_URL", "http://localhost:9200")


def vec_sql(v):
    return "[" + ",".join(map(str, v)) + "]"


# ---------- load ----------

def cargar_pgvector(conn, fs, vecs):
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("DROP SCHEMA IF EXISTS semana9 CASCADE")
    conn.execute("CREATE SCHEMA semana9")
    conn.execute(f"CREATE TABLE semana9.chunks (id int PRIMARY KEY, source text NOT NULL, chunk_index int NOT NULL, "
                 f"content text NOT NULL, tenant_id text NOT NULL, roles text[] NOT NULL, embedding vector({DIM}) NOT NULL)")
    conn.execute("CREATE INDEX ON semana9.chunks USING hnsw (embedding vector_cosine_ops)")
    conn.execute("CREATE INDEX ON semana9.chunks (tenant_id)")
    conn.execute("CREATE INDEX ON semana9.chunks USING gin (roles)")
    with conn.cursor() as cur:
        for f, v in zip(fs, vecs):
            cur.execute("INSERT INTO semana9.chunks VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (f["id"], f["source"], f["chunk_index"], f["content"], TENANT, ROLES_DOC[f["source"]], vec_sql(v)))
    return conn.execute("SELECT count(*) FROM semana9.chunks").fetchone()[0]


def cargar_qdrant(fs, vecs):
    http("DELETE", f"{QDRANT}/collections/{NOMBRE}", ignorar=(404,))
    http("PUT", f"{QDRANT}/collections/{NOMBRE}", {"vectors": {"size": DIM, "distance": "Cosine"}})
    for campo in ("tenant_id", "roles"):
        http("PUT", f"{QDRANT}/collections/{NOMBRE}/index?wait=true", {"field_name": campo, "field_schema": "keyword"})
    puntos = [{"id": f["id"], "vector": v,
               "payload": {"source": f["source"], "chunk_index": f["chunk_index"], "content": f["content"],
                           "tenant_id": TENANT, "roles": ROLES_DOC[f["source"]]}}
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
                                  "tenant_id": TENANT, "roles": ROLES_DOC[f["source"]], "embedding": v}))
    http("POST", f"{OPENSEARCH}/_bulk", "\n".join(lineas) + "\n", ctype="application/x-ndjson")
    http("POST", f"{OPENSEARCH}/{NOMBRE}/_refresh")
    return http("GET", f"{OPENSEARCH}/{NOMBRE}/_count")["count"]


# ---------- search (usuario=None: no filter) ----------

def buscar_pgvector(conn, v, usuario):
    if usuario:
        q = ("SELECT source, content, tenant_id FROM semana9.chunks "
             "WHERE tenant_id = %s AND roles && %s::text[] ORDER BY embedding <=> %s::vector LIMIT %s")
        args = (usuario["tenant"], usuario["roles"], vec_sql(v), K)
    else:
        q = "SELECT source, content, tenant_id FROM semana9.chunks ORDER BY embedding <=> %s::vector LIMIT %s"
        args = (vec_sql(v), K)
    return [tuple(r) for r in conn.execute(q, args).fetchall()]


def buscar_qdrant(v, usuario):
    cuerpo = {"query": v, "limit": K, "with_payload": True}
    if usuario:
        cuerpo["filter"] = {"must": [{"key": "tenant_id", "match": {"value": usuario["tenant"]}},
                                     {"key": "roles", "match": {"any": usuario["roles"]}}]}
    r = http("POST", f"{QDRANT}/collections/{NOMBRE}/points/query", cuerpo)
    return [(p["payload"]["source"], p["payload"]["content"], p["payload"]["tenant_id"]) for p in r["result"]["points"]]


def buscar_opensearch(v, usuario):
    knn = {"embedding": {"vector": v, "k": K}}
    if usuario:
        # The filter goes inside the knn clause (filtering during the search), not afterwards.
        knn["embedding"]["filter"] = {"bool": {"filter": [{"term": {"tenant_id": usuario["tenant"]}},
                                                          {"terms": {"roles": usuario["roles"]}}]}}
    r = http("POST", f"{OPENSEARCH}/{NOMBRE}/_search", {"size": K, "query": {"knn": knn}})
    return [(h["_source"]["source"], h["_source"]["content"], h["_source"]["tenant_id"]) for h in r["hits"]["hits"]]


# ---------- measurement ----------

def autorizado(fila, usuario):
    source, _, tenant = fila
    return tenant == usuario["tenant"] and bool(set(ROLES_DOC[source]) & set(usuario["roles"]))


def visibles(fs, usuario):
    return sum(1 for f in fs if set(ROLES_DOC[f["source"]]) & set(usuario["roles"]))


def medir(nombre, buscar, fs, idioma, items, vq):
    base = [(x, v) for x, v in zip(items, vq) if x["tipo"] == "base"]
    perm = [(x, v) for x, v in zip(items, vq) if x["tipo"] == "permiso"]
    fuga_f = fuga_n = consultas = cortos = 0
    r5_f, r5_n, pares = 0.0, 0.0, 0
    fugas = []
    for x, v in base:
        doc = x["gold"][0]["source"]
        res_n = buscar(v, None)
        for rol in ROLES:
            u = {"tenant": TENANT, "roles": [rol]}
            res_f = buscar(v, u)
            consultas += 1
            malos = [r for r in res_f if not autorizado(r, u)]
            fuga_f += len(malos)
            fugas += [(x["id"], rol, r[0]) for r in malos]
            fuga_n += sum(1 for r in res_n if not autorizado(r, u))
            if len(res_f) < min(K, visibles(fs, u)):
                cortos += 1
            if rol in ROLES_DOC[doc]:
                pares += 1
                r5_f += metricas(x, [(s, c) for s, c, _ in res_f])[0]
                r5_n += metricas(x, [(s, c) for s, c, _ in res_n])[0]
    perm_ok_f = perm_ok_n = n_ok = prohib_f = prohib_n = n_prohib = 0
    for x, v in perm:
        u = x["usuario"]
        res_f, res_n = buscar(v, u), buscar(v, None)
        fuga_f += sum(1 for r in res_f if not autorizado(r, u))
        rf = [(s, c) for s, c, _ in res_f]
        rn = [(s, c) for s, c, _ in res_n]
        if x["permitido"]:
            n_ok += 1
            perm_ok_f += metricas(x, rf)[0]
            perm_ok_n += metricas(x, rn)[0]
        else:
            n_prohib += 1
            g = x["gold"][0]
            prohib_f += any(s == g["source"] and g["passage"] in c for s, c in rf)
            prohib_n += any(s == g["source"] and g["passage"] in c for s, c in rn)
    print(f"| {nombre} | {idioma} | {consultas} | {fuga_f} | {fuga_n} | {r5_n / pares:.3f} | {r5_f / pares:.3f} | "
          f"{perm_ok_n / n_ok:.3f} / {perm_ok_f / n_ok:.3f} | {prohib_n}/{n_prohib} / {prohib_f}/{n_prohib} | {cortos} |")
    for f in fugas[:10]:
        print(f"    FUGA {nombre} {idioma}: {f}", file=sys.stderr)
    return fuga_f


def main():
    fs = filas()
    faltan = {f["source"] for f in fs} - set(ROLES_DOC)
    if faltan:
        raise SystemExit(f"Documents without roles in permisos.json: {sorted(faltan)}")
    vecs, _ = emb_bge([f["content"] for f in fs], "doc")

    conn = psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True)
    version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    print(f"pgvector {version[0] if version else 'no instalado'}", file=sys.stderr)
    conn.execute("SET hnsw.ef_search = 100")
    try:
        conn.execute("SET hnsw.iterative_scan = strict_order")
        print("pgvector: hnsw.iterative_scan = strict_order", file=sys.stderr)
    except psycopg.Error:
        print("pgvector: no hnsw.iterative_scan (version < 0.8); using ef_search = 100", file=sys.stderr)

    print(f"carga: pgvector {cargar_pgvector(conn, fs, vecs)}, qdrant {cargar_qdrant(fs, vecs)}, "
          f"opensearch {cargar_opensearch(fs, vecs)} chunks; tenant '{TENANT}'; roles {ROLES}\n")

    bases = [("pgvector", lambda v, u: buscar_pgvector(conn, v, u)),
             ("Qdrant", buscar_qdrant),
             ("OpenSearch", buscar_opensearch)]
    print("| Database | Language | Queries (question x role) | Leak with filter | Unauthorized chunks without filter | "
          "recall@5 without filter | recall@5 with filter | Allowed recall@5 (without / with) | "
          "Forbidden returned (without / with) | Short results |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    total = 0
    for idioma in ("es", "en"):
        items = [json.loads(l) for l in (RAIZ / "datasets" / f"avanzado_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        items = [x for x in items if x["tipo"] in ("base", "permiso")]
        vq, _ = emb_bge([x["question"] for x in items], "query")
        for nombre, buscar in bases:
            total += medir(nombre, buscar, fs, idioma, items, vq)
    conn.close()
    print(f"\ntotal leak with the filter: {total}")
    if total:
        sys.exit(1)


if __name__ == "__main__":
    main()
