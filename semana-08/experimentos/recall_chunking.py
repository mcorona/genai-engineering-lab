"""Activity 2 (second part): recall@k per chunking strategy, with local bge-m3.

A reference passage counts as retrieved if any of the top-k chunks contains it whole.
Recall of a query = retrieved passages / reference passages of that query.
"""
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking_pasajes import ESTRATEGIAS, CORPUS  # noqa: E402

BASE = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
MODELO = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
KS = (5, 10)


def embed(textos):
    req = urllib.request.Request(
        f"{BASE}/embeddings",
        data=json.dumps({"model": MODELO, "input": textos}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        datos = json.loads(r.read())["data"]
    return [d["embedding"] for d in sorted(datos, key=lambda d: d["index"])]


def coseno(a, b):
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


docs = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
DATOS = Path(__file__).resolve().parents[1] / "datasets"
IDIOMAS = {"es": DATOS / "recuperacion_es.jsonl", "en": DATOS / "recuperacion_en.jsonl"}

for idioma, ruta in IDIOMAS.items():
    consultas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()]
    for nombre, trocear in ESTRATEGIAS.items():
        chunks = [(src, c) for src, texto in docs.items() for c in trocear(texto, src)]
        vecs = embed([c for _, c in chunks])
        qvecs = embed([q["question"] for q in consultas])
        recall = {k: [] for k in KS}
        for q, qv in zip(consultas, qvecs):
            orden = sorted(range(len(chunks)), key=lambda i: -coseno(qv, vecs[i]))
            for k in KS:
                top = [chunks[i] for i in orden[:k]]
                hits = sum(1 for g in q["gold"]
                           if any(src == g["source"] and g["passage"] in c for src, c in top))
                recall[k].append(hits / len(q["gold"]))
        medias = {k: sum(v) / len(v) for k, v in recall.items()}
        print(f"{idioma} {nombre:<22} chunks={len(chunks):<4} recall@5={medias[5]:.3f}  recall@10={medias[10]:.3f}")
