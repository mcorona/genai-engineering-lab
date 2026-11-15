"""Activity 3: HyDE with claude-haiku-5-5.

Haiku writes a hypothetical passage that would answer the question. That passage is embedded and used
for the search, instead of the question. It is compared against the original question with the week 8
vector search (bge-m3 in OpenSearch, semana8 index).

- base: a self-contained question (no previous question).
- follow-up: the hypothetical passage is generated with the previous question as context.
- Permission cases are outside this metric: they are evaluated in activity 5.

Outputs: a table on stdout, and resultados/hyde_detalle.csv (one row per query, with the block types
the API returns, to confirm whether there are invisible reasoning tokens).

Requires LM Studio with bge-m3, OpenSearch with the semana8 index, and ANTHROPIC_API_KEY.
"""
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
DATOS = RAIZ / "datasets"
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ.parent / "semana-08" / "experimentos"))
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import MODELO, PRECIO, buscar_vectorial, http, metricas  # noqa: E402

SISTEMA = ("Escribes un pasaje breve (2 o 3 oraciones) que respondería la pregunta como si fuera un "
           "fragmento de un documento interno de una empresa de inventarios. Usa el mismo idioma de la pregunta. "
           "Si hay pregunta previa, úsala como contexto. Responde SOLO con el pasaje, sin títulos ni texto adicional.")


# high max_tokens: Haiku consumes reasoning tokens (a thinking block) before the text.
# With 250 there were 5 answers without text, which fell back to the original question.
def pasaje_hipotetico(previa, pregunta):
    contenido = (f"Pregunta previa: {previa}\nPregunta: {pregunta}" if previa else f"Pregunta: {pregunta}")
    r = http("POST", "https://api.anthropic.com/v1/messages", {
        "model": MODELO, "max_tokens": 1500, "system": SISTEMA,
        "messages": [{"role": "user", "content": contenido}]},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    texto = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text").strip()
    tipos = "|".join(b.get("type", "?") for b in r["content"])
    return (texto or pregunta), r["usage"]["input_tokens"], r["usage"]["output_tokens"], tipos


def promedio(filas):
    n = len(filas)
    return [sum(f[i] for f in filas) / n for i in range(3)]


def costo_llamada(tin, tout):
    return (tin * PRECIO["in"] + tout * PRECIO["out"]) / 1e6


def main():
    print(f"price used (prices.json, Haiku): {PRECIO}", file=sys.stderr)
    detalle = []
    print("| Type | Language | Variant | recall@5 | nDCG@10 | MRR | cost per query | HyDE latency p50 / p95 (ms) |")
    print("|---|---|---|---|---|---|---|---|")
    for idioma in ("es", "en"):
        items = [json.loads(l) for l in (DATOS / f"avanzado_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()]
        for tipo in ("base", "seguimiento"):
            sel = [x for x in items if x["tipo"] == tipo]
            previas = [x.get("pregunta_previa") if tipo == "seguimiento" else None for x in sel]
            pasajes, tin, tout, latencias, llamadas = [], 0, 0, [], []
            for x, p in zip(sel, previas):
                t0 = time.perf_counter()
                t, a, b, tipos = pasaje_hipotetico(p, x["question"])
                lat = (time.perf_counter() - t0) * 1000
                latencias.append(lat)
                pasajes.append(t)
                tin += a
                tout += b
                llamadas.append({"id": x["id"], "tipo": tipo, "idioma": idioma, "pregunta": x["question"],
                                 "pasaje_hyde": t, "tokens_in": a, "tokens_out": b, "tipos_bloque": tipos,
                                 "costo_usd": f"{costo_llamada(a, b):.7f}", "latencia_ms": f"{lat:.0f}"})
            vo = emb_bge([x["question"] for x in sel], "query")[0]
            vh = emb_bge(pasajes, "query")[0]
            filas_o = [metricas(x, buscar_vectorial(v, 10)) for x, v in zip(sel, vo)]
            filas_h = [metricas(x, buscar_vectorial(v, 10)) for x, v in zip(sel, vh)]
            for fila, fo, fh in zip(llamadas, filas_o, filas_h):
                fila["acierto_original_r5"] = int(fo[0] > 0)
                fila["acierto_hyde_r5"] = int(fh[0] > 0)
                detalle.append(fila)
            costo = costo_llamada(tin, tout) / len(sel)
            lat_txt = f"{statistics.median(latencias):.0f} / {statistics.quantiles(latencias, n=20)[18]:.0f}"
            for nombre, filas in (("original", filas_o), ("HyDE", filas_h)):
                r5, nd, mr = promedio(filas)
                c = f"${costo:.6f}" if nombre == "HyDE" else "-"
                lt = lat_txt if nombre == "HyDE" else "-"
                print(f"| {tipo} | {idioma} | {nombre} | {r5:.3f} | {nd:.3f} | {mr:.3f} | {c} | {lt} |")

    salida = RAIZ / "resultados" / "hyde_detalle.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)
    print(f"detail per query: {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
