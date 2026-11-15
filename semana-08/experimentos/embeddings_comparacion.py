"""Activity 3: a comparison of embedding models with fixed 400/80 chunking.

Models: local bge-m3 (LM Studio), OpenAI text-embedding-3-small and -large, Google gemini-embedding-2.
Metrics: recall@5 and recall@10 in ES and EN, dimension, tokens (when the API reports them) and cost.
The keys are read from semana-05/.env, as in week 5.
"""
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
sys.path.insert(0, str(AQUI))
from chunking_pasajes import ESTRATEGIAS, CORPUS  # noqa: E402

PRECIOS = json.loads((RAIZ / "precios_embeddings.json").read_text(encoding="utf-8"))
ENV = AQUI.parents[1] / "semana-05" / ".env"
KS = (5, 10)
DATOS = RAIZ / "datasets"


def cargar_env():
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def post(url, cuerpo, cabeceras=None):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def emb_bge(textos, tipo):
    base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    modelo = os.getenv("LMSTUDIO_EMBED_MODEL", "text-embedding-bge-m3")
    r = post(f"{base}/embeddings", {"model": modelo, "input": textos})
    return [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])], None


def emb_openai(modelo):
    def f(textos, tipo):
        r = post("https://api.openai.com/v1/embeddings", {"model": modelo, "input": textos},
                 {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        vecs = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
        return vecs, r["usage"]["total_tokens"]
    return f


def emb_gemini(textos, tipo):
    clave = os.environ["GEMINI_API_KEY"]
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-embedding-2:batchEmbedContents?key={clave}")
    tarea = "RETRIEVAL_DOCUMENT" if tipo == "doc" else "RETRIEVAL_QUERY"
    vecs = []
    for i in range(0, len(textos), 50):
        peticiones = [{"model": "models/gemini-embedding-2", "taskType": tarea,
                       "content": {"parts": [{"text": t}]}} for t in textos[i:i + 50]]
        r = post(url, {"requests": peticiones})
        vecs += [e["values"] for e in r["embeddings"]]
    return vecs, None


MODELOS = {
    "bge-m3 (local)": (emb_bge, "bge-m3 (local)"),
    "text-embedding-3-small": (emb_openai("text-embedding-3-small"), "openai:text-embedding-3-small"),
    "text-embedding-3-large": (emb_openai("text-embedding-3-large"), "openai:text-embedding-3-large"),
    "gemini-embedding-2": (emb_gemini, "gemini:gemini-embedding-2"),
}


def coseno(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def main():
    cargar_env()
    docs = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
    trocear = ESTRATEGIAS["fijo_400_solape_80"]
    chunks = [(src, c) for src, texto in docs.items() for c in trocear(texto, src)]
    consultas = {
        idioma: [json.loads(l) for l in (DATOS / f"recuperacion_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        for idioma in ("es", "en")
    }
    print(f"fixed 400/80 chunks: {len(chunks)}")
    for nombre, (funcion, clave_precio) in MODELOS.items():
        try:
            t0 = time.time()
            vecs, tok_chunks = funcion([c for _, c in chunks], "doc")
            dim = len(vecs[0])
            for idioma, cons in consultas.items():
                qvecs, tok_q = funcion([q["question"] for q in cons], "query")
                recall = {k: [] for k in KS}
                for q, qv in zip(cons, qvecs):
                    orden = sorted(range(len(chunks)), key=lambda i: -coseno(qv, vecs[i]))
                    for k in KS:
                        top = [chunks[i] for i in orden[:k]]
                        hits = sum(1 for g in q["gold"]
                                   if any(src == g["source"] and g["passage"] in c for src, c in top))
                        recall[k].append(hits / len(q["gold"]))
                medias = {k: sum(v) / len(v) for k, v in recall.items()}
                tokens = (tok_chunks or 0) + (tok_q or 0) if (tok_chunks is not None or tok_q is not None) else None
                precio = PRECIOS[clave_precio]["in"]
                costo = (tokens * precio / 1e6) if (tokens is not None and precio is not None) else None
                print(f"{idioma} {nombre:<24} dim={dim:<5} r@5={medias[5]:.3f} r@10={medias[10]:.3f} "
                      f"tokens={tokens} cost_usd={costo if costo is None else round(costo, 6)} "
                      f"sec={time.time() - t0:.1f}")
        except Exception as e:  # one API being down does not stop the others
            print(f"{nombre}: ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
