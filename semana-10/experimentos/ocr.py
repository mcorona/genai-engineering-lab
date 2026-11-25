"""Activity 4: OCR of scanned documents.

1. Scans 5 documents: the 2 OCR sources frozen in activity 1 (fuentes/acta_inventario_norte.md,
   fuentes/remision_r4471.md) and 3 dense-text documents from the week 8 corpus (devoluciones, inventario_ciclico,
   recepcion_almacen). Markdown -> PDF (the same generator as activity 3) -> an image at 200 dpi in grayscale, a slight
   rotation (±1.5°), blur and noise, with a fixed seed -> JPEG in escaneos/.
2. Extracts the text with Tesseract (Spanish) and with Claude (the image as input). Upper reference: the original text.
3. Metrics, fixed before the run:
   - CER: the edit distance (Levenshtein) between the visible text of the page and the extracted one, over the length of
     the original. Both are normalized the same way: no Markdown marks or bullets, collapsed spaces, keeping case and accents.
   - recall@5 of passages: week 9 base questions whose passage is in a scanned document (rec-01 to 06 and 18 to 20,
     9 per language). A hit: some chunk in the top 5 comes from that document and contains the literal passage (no bold,
     collapsed spaces, case-insensitive). An OCR error inside the passage counts as a miss.
   - recall@5 of answers: the gold set's OCR questions (datasets/integrado_*.jsonl, ocr format, 5 per language).
   What is extracted from the 5 scans is indexed together with the rest of the text corpus (fixed 400/80 chunking, bge-m3).
Requires PyMuPDF, Pillow, reportlab, Tesseract with 'spa', LM Studio with bge-m3 and, unless --sin-claude, ANTHROPIC_API_KEY.
"""
import argparse
import base64
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
EXT_DIR = RES / "ocr_extracciones"
ESC_DIR = RAIZ / "escaneos"
CORPUS = REPO / "semana-08" / "corpus"
sys.path.insert(0, str(AQUI))
import pdf_tablas as pt  # noqa: E402  (PDF generator, blocks, cosine; it also adds semana-08 to the path)
from embeddings_comparacion import emb_bge  # noqa: E402

trocear = pt.trocear
DOCS = [RAIZ / "fuentes" / "acta_inventario_norte.md", RAIZ / "fuentes" / "remision_r4471.md",
        CORPUS / "devoluciones.md", CORPUS / "inventario_ciclico.md", CORPUS / "recepcion_almacen.md"]
PASAJES_IDS = ["rec-01", "rec-02", "rec-03", "rec-04", "rec-05", "rec-06", "rec-18", "rec-19", "rec-20"]
SEMILLA = 20261026
PROMPT = ("Transcribe el texto de este documento escaneado, completo y literal, en Markdown. Conserva las tablas como "
          "tablas Markdown. No corrijas, no resumas, no traduzcas y no agregues texto.")


# ---------- visible text and normalization ----------

def texto_visible(md):
    partes = []
    for tipo, cont in pt.bloques(md):
        if tipo == "tabla":
            partes += [" ".join(fila) for fila in cont]
        else:
            partes.append(re.sub(r"^- ", "", cont.replace("**", "")))
    return "\n".join(partes)


def limpiar(t):
    t = t.replace("**", "").replace("•", " ").replace("|", " ")
    t = re.sub(r"(?m)^\s*#+\s*", "", t)
    t = re.sub(r"(?m)^\s*>\s*", "", t)
    t = re.sub(r"(?m)^\s*[-*]\s+", "", t)
    t = re.sub(r"(?m)^\s*:?-{3,}:?(\s+:?-{3,}:?)*\s*$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(referencia, hipotesis):
    r, h = limpiar(referencia), limpiar(hipotesis)
    return levenshtein(r, h) / max(1, len(r))


# ---------- scanning ----------

def escanear():
    import fitz
    from PIL import Image, ImageFilter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    fuente, ruta = pt.fuente_unicode()
    pdfmetrics.registerFont(fuente)
    estilos = {"h": ParagraphStyle("h", fontName="Uni", fontSize=15, leading=19, spaceAfter=8),
               "nota": ParagraphStyle("nota", fontName="Uni", fontSize=8, leading=10, spaceAfter=8, textColor="#555555"),
               "p": ParagraphStyle("p", fontName="Uni", fontSize=10, leading=13, spaceAfter=6),
               "item": ParagraphStyle("item", fontName="Uni", fontSize=10, leading=13, leftIndent=10, spaceAfter=3),
               "celda": ParagraphStyle("celda", fontName="Uni", fontSize=9, leading=11)}
    ESC_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEMILLA)
    paginas = {}
    for md in DOCS:
        pdf = ESC_DIR / f"{md.stem}.pdf"
        pt.generar_pdf(md, pdf, estilos)
        doc = fitz.open(str(pdf))
        paginas[md.stem] = []
        for n, pagina in enumerate(doc):
            pix = pagina.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, fillcolor=255)
            img = img.filter(ImageFilter.GaussianBlur(0.6))
            img = Image.blend(img, Image.effect_noise(img.size, 40), 0.12)
            px, (w, h) = img.load(), img.size
            for _ in range(int(w * h * 0.001)):
                px[rng.randrange(w), rng.randrange(h)] = 0 if rng.random() < 0.5 else 255
            destino = ESC_DIR / f"{md.stem}_p{n + 1}.jpg"
            img.save(destino, quality=85)
            paginas[md.stem].append(destino)
        doc.close()
        pdf.unlink()
    print(f"scans: {sum(len(p) for p in paginas.values())} pages of {len(DOCS)} documents in "
          f"{ESC_DIR.relative_to(REPO)} (font {ruta.name}, seed {SEMILLA})", file=sys.stderr)
    return paginas


# ---------- extractors ----------

def tesseract(imagenes):
    salida = []
    for img in imagenes:
        r = subprocess.run(["tesseract", str(img), "stdout", "-l", "spa"], capture_output=True, text=True, check=True)
        salida.append(r.stdout)
    return "\n".join(salida)


def claude(modelo, esfuerzo, regenerar):
    ruta = EXT_DIR / f"claude_{modelo}_{esfuerzo}.json"
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() and not regenerar else {}
    precio = pt.PRECIOS[f"anthropic:{modelo}"]

    def f(stem, imagenes):
        if stem not in cache:
            contenido = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                      "data": base64.b64encode(i.read_bytes()).decode()}} for i in imagenes]
            contenido.append({"type": "text", "text": PROMPT})
            cuerpo = {"model": modelo, "max_tokens": 6000, "output_config": {"effort": esfuerzo},
                      "messages": [{"role": "user", "content": contenido}]}
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                         headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                                  "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    d = json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise SystemExit(f"API HTTP {e.code} en {stem} ({modelo}): {e.read().decode()[:300]}")
            if d.get("stop_reason") == "max_tokens":
                raise SystemExit(f"Output truncated by max_tokens in {stem} ({modelo}); it is not used.")
            u = d["usage"]
            cache[stem] = {"texto": "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text"),
                           "tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"],
                           "latencia_s": round(time.perf_counter() - t0, 2),
                           "costo_usd": round((u["input_tokens"] * precio["in"] + u["output_tokens"] * precio["out"]) / 1e6, 6)}
            EXT_DIR.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return cache[stem]["texto"]
    return f, cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", "--models", default="claude-haiku-5-5,claude-sonnet-5-5", metavar="MODELS")
    ap.add_argument("--esfuerzo", "--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--sin-claude", "--no-claude", action="store_true")
    ap.add_argument("--regenerar-claude", "--regenerate-claude", action="store_true")
    args = ap.parse_args()

    idiomas = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()
    if "spa" not in idiomas:
        raise SystemExit("Tesseract does not have the 'spa' language (install it with brew install tesseract-lang).")
    paginas = escanear()

    extractores = {"original (sin escanear)": lambda stem, imgs: texto_visible(next(d for d in DOCS if d.stem == stem).read_text(encoding="utf-8")),
                   "Tesseract (spa)": lambda stem, imgs: tesseract(imgs)}
    caches = {}
    if not args.sin_claude:
        for modelo in args.modelos.split(","):
            f, caches[modelo] = claude(modelo, args.esfuerzo, args.regenerar_claude)
            extractores[f"Claude {modelo} ({args.esfuerzo})"] = f

    EXT_DIR.mkdir(parents=True, exist_ok=True)
    textos, detalle = {}, []
    for nombre, fx in extractores.items():
        textos[nombre] = {stem: fx(stem, imgs) for stem, imgs in paginas.items()}
        clave = re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")
        for stem, t in textos[nombre].items():
            (EXT_DIR / f"{clave}__{stem}.txt").write_text(t, encoding="utf-8")

    print("| Extractor | " + " | ".join(f"CER {d.stem}" for d in DOCS) + " | Mean CER |")
    print("|---|" + "---|" * (len(DOCS) + 1))
    for nombre in extractores:
        cers = []
        for md in DOCS:
            c = cer(texto_visible(md.read_text(encoding="utf-8")), textos[nombre][md.stem])
            cers.append(c)
            detalle.append({"extractor": nombre, "documento": md.stem, "cer": round(c, 4)})
        print(f"| {nombre} | " + " | ".join(f"{c:.3f}" for c in cers) + f" | {sum(cers) / len(cers):.3f} |")

    escaneados = {d.name for d in DOCS}
    otros = {p.stem: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md") if p.name not in escaneados}
    pasajes = {lang: [d for d in map(json.loads, (REPO / "semana-09" / "datasets" / f"avanzado_{lang}.jsonl").read_text(encoding="utf-8").splitlines())
                      if d["tipo"] == "base" and d["id"] in PASAJES_IDS] for lang in ("es", "en")}
    respuestas = {lang: [d for d in map(json.loads, (RAIZ / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines())
                         if d.get("formato") == "ocr"] for lang in ("es", "en")}
    norm = lambda s: pt.norm_ws(s).lower()  # noqa: E731
    vp = {l: emb_bge([q["question"] for q in qs], "query")[0] for l, qs in pasajes.items()}
    vr = {l: emb_bge([q["question"] for q in qs], "query")[0] for l, qs in respuestas.items()}
    print("\n| Extractor | Language | recall@5 of passages | recall@5 of answers |")
    print("|---|---|---|---|")
    for nombre in extractores:
        chunks = [(s, c) for s, t in {**otros, **textos[nombre]}.items() for c in trocear(t, s)]
        vc, _ = emb_bge([c for _, c in chunks], "doc")
        for lang in ("es", "en"):
            def top5(v):
                return sorted(range(len(chunks)), key=lambda i: -pt.coseno(v, vc[i]))[:5]
            ok_p = ok_r = 0
            for q, v in zip(pasajes[lang], vp[lang]):
                g = q["gold"][0]
                ok = any(chunks[i][0] == Path(g["source"]).stem and norm(g["passage"]) in norm(chunks[i][1]) for i in top5(v))
                ok_p += ok
                detalle.append({"extractor": nombre, "idioma": lang, "pregunta": q["id"], "tipo": "pasaje", "acierto_r5": int(ok)})
            for q, v in zip(respuestas[lang], vr[lang]):
                ok = any(chunks[i][0] == Path(q["fuente"]).stem and norm(q["respuesta"]) in norm(chunks[i][1]) for i in top5(v))
                ok_r += ok
                detalle.append({"extractor": nombre, "idioma": lang, "pregunta": q["id"], "tipo": "respuesta", "acierto_r5": int(ok)})
            print(f"| {nombre} | {lang} | {ok_p}/{len(pasajes[lang])} | {ok_r}/{len(respuestas[lang])} |")

    for modelo, c in caches.items():
        v = list(c.values())
        print(f"\nClaude {modelo}: {len(v)} documents, input tokens {sum(x['tokens_in'] for x in v)}, output "
              f"{sum(x['tokens_out'] for x in v)}, cost ${sum(x['costo_usd'] for x in v):.5f}, "
              f"mean latency {sum(x['latencia_s'] for x in v) / len(v):.1f} s per document")
    campos = sorted({k for d in detalle for k in d})
    with (RES / "ocr_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(detalle)
    print(f"detail: {RES / 'ocr_detalle.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
