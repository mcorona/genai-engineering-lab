"""Activity 2: does the chunking keep each reference passage whole within a chunk?

It uses no embeddings and no APIs. It is the necessary condition for retrieval to be
able to find the passage, regardless of the model used afterwards.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CORPUS = RAIZ / "corpus"
GOLD = RAIZ / "datasets" / "recuperacion_es.jsonl"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunker_actual import chunk_markdown  # copia de inventory-copilot/src/rag/chunking.py


def fijo(texto, n=400, solape=80):
    """A fixed character window with overlap."""
    out, i = [], 0
    while i < len(texto):
        out.append(texto[i:i + n])
        if i + n >= len(texto):
            break
        i += n - solape
    return out


def recursivo(texto, n=300):
    """Packs paragraphs; if one does not fit, it splits it by sentences. No overlap."""
    piezas = []
    for par in texto.split("\n\n"):
        par = par.strip()
        if not par:
            continue
        if len(par) <= n:
            piezas.append(par)
        else:
            oraciones = par.replace("\n", " ").split(". ")
            actual = ""
            for o in oraciones:
                cand = (actual + ". " + o) if actual else o
                if len(cand) <= n:
                    actual = cand
                else:
                    if actual:
                        piezas.append(actual)
                    actual = o
            if actual:
                piezas.append(actual)
    # final packing of short contiguous pieces
    out, actual = [], ""
    for p in piezas:
        cand = (actual + "\n\n" + p) if actual else p
        if len(cand) <= n:
            actual = cand
        else:
            if actual:
                out.append(actual)
            actual = p
    if actual:
        out.append(actual)
    return out


def actual(texto, source):
    """inventory-copilot's chunker (by section headings)."""
    return [c.content for c in chunk_markdown(texto, source=source)]


ESTRATEGIAS = {
    "fijo_400_solape_80": lambda t, s: fijo(t, 400, 80),
    "recursivo_300": lambda t, s: recursivo(t, 300),
    "actual_por_seccion": actual,
}

docs = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
pasajes = {(g["source"], g["passage"]) for l in GOLD.read_text(encoding="utf-8").splitlines()
           for g in json.loads(l)["gold"]}
print(f"documents: {len(docs)} · unique reference passages: {len(pasajes)}")
print(f"{'estrategia':<22}{'chunks':>8}{'prom_chars':>12}{'íntegros':>12}{'partidos':>10}")
for nombre, f in ESTRATEGIAS.items():
    chunks = {src: f(texto, src) for src, texto in docs.items()}
    total = sum(len(v) for v in chunks.values())
    prom = sum(len(c) for v in chunks.values() for c in v) / total
    intactos, partidos = 0, []
    for src, pas in sorted(pasajes):
        if any(pas in c for c in chunks[src]):
            intactos += 1
        else:
            partidos.append((src, pas))
    print(f"{nombre:<22}{total:>8}{prom:>12.0f}{intactos:>7}/{len(pasajes):<4}{len(partidos):>10}")
    for src, pas in partidos[:6]:
        print(f"    split: {src} · {pas[:70]}")
