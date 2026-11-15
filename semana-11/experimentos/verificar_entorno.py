"""Week 11, a prerequisite: checks LM Studio (bge-m3) and the semana10.chunks index in copilot-db.

- LM Studio: the embedding model responds and its dimension matches the index's.
- copilot-db: semana10.chunks exists, how many chunks there are per tenant and document, and whether it carries documents
  that are not part of the activity 7 index (week 9's beta or activity 8's injected ones, which seguridad.py adds).
If the index is not the activity 7 one (30 documents, 68 chunks, only the alfa tenant), reindex with
`python -c "import sys; sys.path.insert(0, 'semana-10/experimentos'); import asistente; asistente.indexar()"`.
Requires PG_ADMIN_DSN.
"""
import json
import os
import urllib.request

import psycopg

base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
modelo = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
req = urllib.request.Request(f"{base}/embeddings", data=json.dumps({"model": modelo, "input": ["prueba"]}).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    dim = len(json.loads(r.read())["data"][0]["embedding"])
print(f"LM Studio: {modelo} responds, dimension {dim}")

with psycopg.connect(os.environ["PG_ADMIN_DSN"]) as conn:
    if not conn.execute("SELECT to_regclass('semana10.chunks')").fetchone()[0]:
        raise SystemExit("semana10.chunks does not exist: reindex with asistente.indexar() (see the docstring)")
    dim_idx = conn.execute("SELECT vector_dims(embedding) FROM semana10.chunks LIMIT 1").fetchone()[0]
    por_tenant = conn.execute("SELECT tenant_id, count(DISTINCT source), count(*) FROM semana10.chunks GROUP BY 1 ORDER BY 1").fetchall()
    extra = [s for (s,) in conn.execute("SELECT DISTINCT source FROM semana10.chunks WHERE source LIKE '%inyeccion%' ORDER BY 1")]
print(f"semana10.chunks: dimension {dim_idx}; per tenant (documents, chunks): {por_tenant}")
print(f"documents with an injected instruction: {extra or 'none'}")
limpio = por_tenant == [("alfa", 30, 68)] and dim_idx == dim
print("INDEX OK (activity 7: 30 documents, 68 chunks, alfa only)" if limpio else
      "INDEX DOES NOT MATCH the activity 7 one: reindex (see the docstring)")
