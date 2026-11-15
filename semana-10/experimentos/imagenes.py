"""Activity 5: images with information that is not in the text.

1. Generates two images with Pillow from the sources frozen in activity 1:
   - imagenes/grafica_nivel_servicio.png: bars of the service level per distribution center, with the value labeled
     above each bar and the center's name below it.
   - imagenes/plano_cedis_occidente.png: a floor plan with receiving docks (1 to 4) and shipping docks (5 to 8), the
     critical-SKU zone drawn next to dock 2 and the quarantine zone inside aisle 12.
2. Uses the image in four ways:
   - no image: only the text corpus (the baseline);
   - Tesseract (spa) on the image;
   - Claude describes the image and extracts its data (text that is indexed with the pipeline);
   - Claude answers the question by looking at the image directly (no RAG).
3. Metrics, fixed before the run:
   - Facts extracted (7): each value or zone with its label on the SAME line of the extracted text (association, not just reading).
   - recall@5 of answers: the gold set's image questions (5 per language); a hit if a chunk in the top 5 comes from the
     image and contains the answer (case- and accent-insensitive). Index: the text corpus + the extracted text.
   - Accuracy of the direct answer: the model's answer contains the correct figure.
Requires Pillow, reportlab (only to locate the TTF font), Tesseract with 'spa', LM Studio with bge-m3, and ANTHROPIC_API_KEY.
"""
import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
EXT_DIR = RES / "imagenes_extracciones"
IMG_DIR = RAIZ / "imagenes"
CORPUS = REPO / "semana-08" / "corpus"
sys.path.insert(0, str(AQUI))
import pdf_tablas as pt  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402

GRAFICA = json.loads((RAIZ / "fuentes" / "grafica_nivel_servicio.json").read_text(encoding="utf-8"))
PLANO = json.loads((RAIZ / "fuentes" / "plano_cedis_occidente.json").read_text(encoding="utf-8"))
HECHOS = [  # (image, description, pattern on the same line)
    ("grafica_nivel_servicio", "CEDIS Centro 97.8%", r"centro.*97[.,]8|97[.,]8.*centro"),
    ("grafica_nivel_servicio", "CEDIS Occidente 95.1%", r"occidente.*95[.,]1|95[.,]1.*occidente"),
    ("grafica_nivel_servicio", "CEDIS Norte 98.6%", r"norte.*98[.,]6|98[.,]6.*norte"),
    ("plano_cedis_occidente", "Recepción: andenes 1 a 4", r"recepcion.*\b1\b.*\b4\b|\b1\b.*\b4\b.*recepcion"),
    ("plano_cedis_occidente", "Embarque: andenes 5 a 8", r"embarque.*\b5\b.*\b8\b|\b5\b.*\b8\b.*embarque"),
    ("plano_cedis_occidente", "SKUs críticos junto al andén 2", r"critic.*anden 2|anden 2.*critic"),
    ("plano_cedis_occidente", "Cuarentena en el pasillo 12", r"cuarentena.*pasillo 12|pasillo 12.*cuarentena"),
]
PROMPT_DESC = ("Describe esta imagen y extrae todos sus datos como texto: el título y, en una línea por dato, cada valor con "
               "su etiqueta o cada zona con su ubicación. Usa el texto tal como aparece en la imagen, sin traducirlo.")
PROMPT_QA = ("Responde la pregunta usando solo la imagen. Responde en una línea, con el dato exacto tal como aparece en la "
             "imagen, sin traducirlo.\n\nPregunta: {pregunta}")


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


# ---------- image generation ----------

def fuente(tam):
    from PIL import ImageFont
    return ImageFont.truetype(str(pt.fuente_unicode()[1]), tam)


def dibujar_grafica(destino):
    from PIL import Image, ImageDraw
    W, H = 1200, 820
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 30), GRAFICA["titulo"], fill="black", font=fuente(34))
    x0, y0, x1, y1 = 140, 120, 1120, 660          # axis area
    vmin, vmax = 90.0, 100.0
    d.line((x0, y0, x0, y1), fill="black", width=2)
    d.line((x0, y1, x1, y1), fill="black", width=2)
    for v in range(90, 101, 2):
        y = y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
        d.line((x0 - 8, y, x0, y), fill="black", width=2)
        d.text((x0 - 70, y - 12), f"{v}%", fill="#444444", font=fuente(20))
    barras = list(GRAFICA["barras"].items())
    ancho = (x1 - x0) / len(barras)
    colores = ["#4C72B0", "#DD8452", "#55A868"]
    for i, (cedis, valor) in enumerate(barras):
        v = float(valor.rstrip("%"))
        bx0 = x0 + i * ancho + ancho * 0.25
        bx1 = bx0 + ancho * 0.5
        by = y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
        d.rectangle((bx0, by, bx1, y1), fill=colores[i % 3])
        d.text((bx0 + 20, by - 40), valor, fill="black", font=fuente(28))
        d.text((bx0 - 10, y1 + 20), cedis, fill="black", font=fuente(26))
    d.text((60, H - 50), GRAFICA["nota"], fill="#666666", font=fuente(16))
    img.save(destino)


def dibujar_plano(destino):
    from PIL import Image, ImageDraw
    W, H = 1400, 960
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 30), PLANO["titulo"], fill="black", font=fuente(34))
    mx0, my0, mx1, my1 = 80, 180, 1320, 860          # building wall
    d.rectangle((mx0, my0, mx1, my1), outline="black", width=4)
    anden_w = (mx1 - mx0) / 8
    for n in range(1, 9):
        ax0 = mx0 + (n - 1) * anden_w
        d.rectangle((ax0 + 8, my0 - 60, ax0 + anden_w - 8, my0), outline="black", width=2,
                    fill="#DCE6F2" if n <= 4 else "#F2E6DC")
        d.text((ax0 + 30, my0 - 45), f"Andén {n}", fill="black", font=fuente(22))
    d.text((mx0 + 1.5 * anden_w, my0 - 110), "Recepción", fill="#1F4E79", font=fuente(26))
    d.text((mx0 + 5.5 * anden_w, my0 - 110), "Embarque", fill="#7F3F00", font=fuente(26))
    # critical-SKU zone, right below dock 2
    # as wide as dock 2, so that it is not ambiguous with dock 3
    zx0, zx1 = mx0 + anden_w + 8, mx0 + 2 * anden_w - 8
    d.rectangle((zx0, my0 + 20, zx1, my0 + 150), outline="#C00000", width=3, fill="#FDECEC")
    f19 = fuente(19)
    for k, linea in enumerate(("Zona de SKUs", "críticos")):
        d.text(((zx0 + zx1) / 2 - d.textlength(linea, font=f19) / 2, my0 + 55 + k * 26), linea, fill="#C00000", font=f19)
    # aisles 10 to 14 as vertical strips; the quarantine inside aisle 12
    for k, p in enumerate(range(10, 15)):
        px = mx0 + 240 + k * 200
        d.rectangle((px, my0 + 220, px + 70, my1 - 40), outline="#888888", width=2)
        d.text((px - 15, my1 - 35), f"Pasillo {p}", fill="#333333", font=fuente(20))
        if p == 12:
            d.rectangle((px + 4, my0 + 380, px + 66, my0 + 560), outline="#7030A0", width=3, fill="#EFE3F7")
            # label centered over aisle 12 (without spilling into aisles 11 and 13) and a line to the zone
            rotulo, f22 = "Zona de cuarentena", fuente(22)
            ancho_rot = d.textlength(rotulo, font=f22)
            d.text((px + 35 - ancho_rot / 2, my0 + 172), rotulo, fill="#7030A0", font=f22)
            d.line((px + 35, my0 + 200, px + 35, my0 + 380), fill="#7030A0", width=2)
    d.text((60, H - 40), PLANO["nota"], fill="#666666", font=fuente(16))
    img.save(destino)


# ---------- extractors ----------

def tesseract(img):
    return subprocess.run(["tesseract", str(img), "stdout", "-l", "spa"], capture_output=True, text=True, check=True).stdout


def llamar_claude(modelo, esfuerzo, img, texto):
    cuerpo = {"model": modelo, "max_tokens": 3000, "output_config": {"effort": esfuerzo},
              "messages": [{"role": "user", "content": [
                  {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                               "data": base64.b64encode(img.read_bytes()).decode()}},
                  {"type": "text", "text": texto}]}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"API HTTP {e.code} ({img.name}): {e.read().decode()[:300]}")
    if d.get("stop_reason") == "max_tokens":
        raise SystemExit(f"Output truncated by max_tokens ({img.name}); it is not used.")
    u, precio = d["usage"], pt.PRECIOS[f"anthropic:{modelo}"]
    return {"texto": "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text"),
            "tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"], "latencia_s": round(time.perf_counter() - t0, 2),
            "costo_usd": round((u["input_tokens"] * precio["in"] + u["output_tokens"] * precio["out"]) / 1e6, 6)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--regenerar-claude", action="store_true")
    args = ap.parse_args()
    if "spa" not in subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split():
        raise SystemExit("Tesseract does not have the 'spa' language.")

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    imgs = {"grafica_nivel_servicio": IMG_DIR / "grafica_nivel_servicio.png", "plano_cedis_occidente": IMG_DIR / "plano_cedis_occidente.png"}
    dibujar_grafica(imgs["grafica_nivel_servicio"])
    dibujar_plano(imgs["plano_cedis_occidente"])
    print(f"images: {len(imgs)} in {IMG_DIR.relative_to(REPO)}", file=sys.stderr)

    EXT_DIR.mkdir(parents=True, exist_ok=True)
    ruta_cache = EXT_DIR / f"claude_{args.modelo}_{args.esfuerzo}.json"
    cache = json.loads(ruta_cache.read_text(encoding="utf-8")) if ruta_cache.exists() and not args.regenerar_claude else {}

    def cacheado(clave, img, texto):
        if clave not in cache:
            cache[clave] = llamar_claude(args.modelo, args.esfuerzo, img, texto)
            ruta_cache.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return cache[clave]

    nombre_claude = f"Claude {args.modelo} ({args.esfuerzo}), descripción"
    textos = {"sin imagen": {}, "Tesseract (spa)": {s: tesseract(p) for s, p in imgs.items()},
              nombre_claude: {s: cacheado(f"desc::{s}", p, PROMPT_DESC)["texto"] for s, p in imgs.items()}}
    for nombre, t in textos.items():
        clave = re.sub(r"[^a-z0-9]+", "_", nombre.lower()).strip("_")
        for s, texto in t.items():
            (EXT_DIR / f"{clave}__{s}.txt").write_text(texto, encoding="utf-8")

    detalle = []
    print("| Use of the image | Facts extracted (label and value on the same line) |")
    print("|---|---|")
    for nombre, t in textos.items():
        ok = 0
        for img, desc, patron in HECHOS:
            lineas = [sin_acentos(l) for l in t.get(img, "").splitlines()]
            hallado = any(re.search(patron, l) for l in lineas)
            ok += hallado
            detalle.append({"uso": nombre, "medida": "hecho", "item": desc, "acierto": int(hallado)})
        print(f"| {nombre} | {ok}/{len(HECHOS)} |")

    preguntas = {lang: [d for d in map(json.loads, (RAIZ / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines())
                        if d.get("formato") == "imagen"] for lang in ("es", "en")}
    corpus = {p.stem: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
    vq = {l: emb_bge([q["question"] for q in qs], "query")[0] for l, qs in preguntas.items()}
    print("\n| Use of the image | Language | recall@5 of answers |")
    print("|---|---|---|")
    for nombre, t in textos.items():
        chunks = [(s, c) for s, x in {**corpus, **t}.items() for c in pt.trocear(x, s)]
        vc, _ = emb_bge([c for _, c in chunks], "doc")
        for lang, qs in preguntas.items():
            ok = 0
            for q, v in zip(qs, vq[lang]):
                top = sorted(range(len(chunks)), key=lambda i: -pt.coseno(v, vc[i]))[:5]
                fuente_q = Path(q["fuente"]).stem
                hit = any(chunks[i][0] == fuente_q and sin_acentos(q["respuesta"]) in sin_acentos(chunks[i][1]) for i in top)
                ok += hit
                detalle.append({"uso": nombre, "medida": "recall5", "idioma": lang, "item": q["id"], "acierto": int(hit)})
            print(f"| {nombre} | {lang} | {ok}/{len(qs)} |")

    print(f"\n| Direct answer with the image ({args.modelo}, {args.esfuerzo}) | Language | Accuracy |")
    print("|---|---|---|")
    for lang, qs in preguntas.items():
        ok = 0
        for q in qs:
            r = cacheado(f"qa::{q['id']}::{lang}", imgs[Path(q["fuente"]).stem], PROMPT_QA.format(pregunta=q["question"]))
            hit = sin_acentos(q["respuesta"]) in sin_acentos(r["texto"])
            ok += hit
            detalle.append({"uso": "respuesta directa", "medida": "exactitud", "idioma": lang, "item": q["id"],
                            "acierto": int(hit), "respuesta_modelo": r["texto"].strip()[:200]})
        print(f"| direct answer | {lang} | {ok}/{len(qs)} |")

    v = list(cache.values())
    print(f"\nClaude {args.modelo} ({args.esfuerzo}): {len(v)} calls, input tokens {sum(x['tokens_in'] for x in v)}, "
          f"output {sum(x['tokens_out'] for x in v)}, cost ${sum(x['costo_usd'] for x in v):.5f}, "
          f"mean latency {sum(x['latencia_s'] for x in v) / len(v):.1f} s")
    campos = sorted({k for x in detalle for k in x})
    with (RES / "imagenes_detalle.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(detalle)
    print(f"detail: {RES / 'imagenes_detalle.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
