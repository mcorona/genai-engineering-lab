"""Activity 9: retrieval eval in CI (PRs that touch semana-08/**).

CI model: text-embedding-3-small (OpenAI), because bge-m3 runs in LM Studio, which is not available in GitHub Actions.
Database: a pgvector service. Metric: recall@5 per language. Fails if either falls below UMBRAL.
"""
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "experimentos"))
import psycopg  # noqa: E402
from chunking_pasajes import ESTRATEGIAS, CORPUS  # noqa: E402

UMBRAL = 0.90
MODELO = "text-embedding-3-small"


def embed(textos):
    out = []
    for i in range(0, len(textos), 100):
        req = Request("https://api.openai.com/v1/embeddings",
                      data=json.dumps({"model": MODELO, "input": textos[i:i + 100]}).encode("utf-8"),
                      headers={"Content-Type": "application/json",
                               "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        with urlopen(req, timeout=120) as r:
            datos = json.loads(r.read())["data"]
        out += [d["embedding"] for d in sorted(datos, key=lambda d: d["index"])]
    return out


def main():
    trocear = ESTRATEGIAS["fijo_400_solape_80"]
    chunks = [(p.name, c) for p in sorted(CORPUS.glob("*.md"))
              for c in trocear(p.read_text(encoding="utf-8"), p.name)]
    vecs = embed([c for _, c in chunks])
    with psycopg.connect(os.environ["PG_DSN"], autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("DROP TABLE IF EXISTS ci_chunks")
        conn.execute(f"CREATE TABLE ci_chunks (id int PRIMARY KEY, source text, content text, "
                     f"embedding vector({len(vecs[0])}))")
        for i, ((src, cont), v) in enumerate(zip(chunks, vecs)):
            conn.execute("INSERT INTO ci_chunks VALUES (%s,%s,%s,%s::vector)",
                         (i, src, cont, "[" + ",".join(map(str, v)) + "]"))
        malos = []
        for idioma in ("es", "en"):
            consultas = [json.loads(l) for l in
                         (RAIZ / "datasets" / f"recuperacion_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
            qv = embed([q["question"] for q in consultas])
            rec = []
            for q, v in zip(consultas, qv):
                top = conn.execute("SELECT source, content FROM ci_chunks ORDER BY embedding <=> %s::vector "
                                   "LIMIT 5", ("[" + ",".join(map(str, v)) + "]",)).fetchall()
                hits = sum(1 for g in q["gold"]
                           if any(s == g["source"] and g["passage"] in c for s, c in top))
                rec.append(hits / len(q["gold"]))
            r5 = sum(rec) / len(rec)
            print(f"{idioma} recall@5={r5:.3f} (threshold {UMBRAL})")
            if r5 < UMBRAL:
                malos.append(idioma)
    if malos:
        sys.exit(f"Below the threshold in: {', '.join(malos)}")
    print("Recall within the threshold in ES and EN")


if __name__ == "__main__":
    main()
