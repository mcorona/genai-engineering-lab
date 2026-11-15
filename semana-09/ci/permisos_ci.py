"""Activity 9: retrieval and permissions eval in CI (PRs that touch semana-09/**).

CI model: text-embedding-3-small (OpenAI), because bge-m3 runs in LM Studio, which is not available in GitHub Actions.
Database: a pgvector service, with the chunks of the alfa (semana-08/corpus) and beta (semana-09/corpus_beta) tenants,
`tenant_id` and `roles` (datasets/permisos.json). The filter goes inside the query.

The check fails if:
1. recall@5 of the base questions (an alfa user with every role) falls below UMBRAL in either language;
2. there is a leak by role: any unauthorized chunk in the top 10 (50 questions x 6 roles) or any forbidden passage
   returned in the permission cases;
3. there is a leak across tenants: any chunk of the other tenant (50 questions x 2 tenants) or the other tenant's figure
   in the near-identical cases (datasets/multitenant_*.jsonl).
Leaks have no threshold: they must be 0.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from chunking_pasajes import ESTRATEGIAS  # noqa: E402

UMBRAL = 0.90
MODELO = "text-embedding-3-small"
K = 10
ROLES_DOC = json.loads((RAIZ / "datasets" / "permisos.json").read_text(encoding="utf-8"))["roles_por_documento"]
ROLES = sorted({r for rs in ROLES_DOC.values() for r in rs})
TENANTS = ("alfa", "beta")


def embed(textos):
    out = []
    for i in range(0, len(textos), 100):
        req = Request("https://api.openai.com/v1/embeddings",
                      data=json.dumps({"model": MODELO, "input": textos[i:i + 100]}).encode("utf-8"),
                      headers={"Content-Type": "application/json",
                               "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        # Retries only for the provider's transient errors (429 and 5xx); everything else fails immediately.
        for intento in range(4):
            try:
                with urlopen(req, timeout=120) as r:
                    datos = json.loads(r.read())["data"]
                break
            except HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or intento == 3:
                    raise
                espera = 2 ** (intento + 1)
                print(f"embeddings: HTTP {e.code}, reintento {intento + 1}/3 en {espera} s", file=sys.stderr)
                time.sleep(espera)
        out += [d["embedding"] for d in sorted(datos, key=lambda d: d["index"])]
    return out


def vsql(v):
    return "[" + ",".join(map(str, v)) + "]"


def chunks():
    trocear = ESTRATEGIAS["fijo_400_solape_80"]
    out = []
    for tenant, carpeta in (("alfa", RAIZ.parent / "semana-08" / "corpus"), ("beta", RAIZ / "corpus_beta")):
        for p in sorted(carpeta.glob("*.md")):
            out += [(tenant, p.name, c) for c in trocear(p.read_text(encoding="utf-8"), p.name)]
    return out


def leer(nombre, idioma):
    return [json.loads(l) for l in (RAIZ / "datasets" / f"{nombre}_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]


def main():
    filas = chunks()
    faltan = {s for _, s, _ in filas} - set(ROLES_DOC)
    if faltan:
        sys.exit(f"Documents without roles in permisos.json: {sorted(faltan)}")
    vecs = embed([c for _, _, c in filas])
    errores = []
    with psycopg.connect(os.environ["PG_DSN"], autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        conn.execute("DROP TABLE IF EXISTS ci9_chunks")
        conn.execute(f"CREATE TABLE ci9_chunks (id int PRIMARY KEY, tenant_id text NOT NULL, source text NOT NULL, "
                     f"content text NOT NULL, roles text[] NOT NULL, embedding vector({len(vecs[0])}) NOT NULL)")
        conn.execute("CREATE INDEX ON ci9_chunks USING hnsw (embedding vector_cosine_ops)")
        for i, ((t, s, c), v) in enumerate(zip(filas, vecs)):
            conn.execute("INSERT INTO ci9_chunks VALUES (%s,%s,%s,%s,%s,%s::vector)", (i, t, s, c, ROLES_DOC[s], vsql(v)))
        conn.execute("SET hnsw.ef_search = 100")
        try:
            conn.execute("SET hnsw.iterative_scan = strict_order")
            modo = "iterative_scan strict_order"
        except psycopg.Error:
            modo = "ef_search 100 (sin iterative_scan)"
        print(f"pgvector {version}, {modo}; chunks: " +
              ", ".join(f"{t} {sum(1 for f in filas if f[0] == t)}" for t in TENANTS))

        def buscar(v, tenant, roles):
            return conn.execute("SELECT tenant_id, source, content FROM ci9_chunks WHERE tenant_id = %s "
                                "AND roles && %s::text[] ORDER BY embedding <=> %s::vector LIMIT %s",
                                (tenant, roles, vsql(v), K)).fetchall()

        def no_aut(fila, tenant, roles):
            t, s, _ = fila
            return t != tenant or not (set(ROLES_DOC[s]) & set(roles))

        for idioma in ("es", "en"):
            av = leer("avanzado", idioma)
            base = [x for x in av if x["tipo"] == "base"]
            perm = [x for x in av if x["tipo"] == "permiso"]
            solap = leer("multitenant", idioma)
            vb = embed([x["question"] for x in base])
            vp = embed([x["question"] for x in perm])
            vs = embed([x["question"] for x in solap])

            rec = []
            for x, v in zip(base, vb):
                top = buscar(v, "alfa", ROLES)[:5]
                rec.append(sum(1 for g in x["gold"] if any(s == g["source"] and g["passage"] in c for _, s, c in top))
                           / len(x["gold"]))
            r5 = sum(rec) / len(rec)

            fuga_rol = sum(no_aut(f, "alfa", [r]) for v in vb for r in ROLES for f in buscar(v, "alfa", [r]))
            prohibidos = 0
            for x, v in zip(perm, vp):
                u = x["usuario"]
                res = buscar(v, u["tenant"], u["roles"])
                fuga_rol += sum(no_aut(f, u["tenant"], u["roles"]) for f in res)
                if not x["permitido"]:
                    g = x["gold"][0]
                    prohibidos += any(s == g["source"] and g["passage"] in c for _, s, c in res)

            fuga_tenant = sum(no_aut(f, t, ROLES) for v in vb for t in TENANTS for f in buscar(v, t, ROLES))
            otra_cifra = propia = 0
            for x, v in zip(solap, vs):
                for t in TENANTS:
                    otro = "beta" if t == "alfa" else "alfa"
                    res = buscar(v, t, [ROLES_DOC[x["source"]][0]])
                    fuga_tenant += sum(no_aut(f, t, [ROLES_DOC[x["source"]][0]]) for f in res)
                    otra_cifra += any(x["gold"][otro] in c for _, _, c in res)
                    propia += any(tt == t and x["gold"][t] in c for tt, _, c in res[:5])

            print(f"{idioma}: recall@5={r5:.3f} (threshold {UMBRAL}) | leak by role={fuga_rol} | "
                  f"forbidden returned={prohibidos}/{sum(not x['permitido'] for x in perm)} | "
                  f"leak across tenants={fuga_tenant} | other tenant's figure={otra_cifra}/{2 * len(solap)} | "
                  f"own figure in top 5={propia}/{2 * len(solap)}")
            if r5 < UMBRAL:
                errores.append(f"{idioma}: recall@5 {r5:.3f} bajo el umbral {UMBRAL}")
            if fuga_rol or prohibidos:
                errores.append(f"{idioma}: fuga por rol ({fuga_rol} chunks, {prohibidos} pasajes prohibidos)")
            if fuga_tenant or otra_cifra:
                errores.append(f"{idioma}: fuga entre tenants ({fuga_tenant} chunks, {otra_cifra} cifras del otro tenant)")
    if errores:
        sys.exit("FALLA: " + "; ".join(errores))
    print("OK: recall within the threshold and 0 leaks (by role and across tenants) in ES and EN")


if __name__ == "__main__":
    main()
