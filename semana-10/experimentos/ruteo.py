"""Activity 6: question routing (SQL, document or mixed).

The integrated gold set (datasets/integrado_{es,en}.jsonl, 51 per language). The correct label is derived from the frozen type:
sql -> sql; document and non_text (PDF, scan, image) -> document; mixed -> mixed.
Classifiers:
- majority: always 'documental' (the floor any classifier must beat).
- Claude (Haiku 5.5 by default, effort low): it receives the description of the two tools and returns JSON.
Metrics, fixed before the run: overall accuracy, by type and by language; confusion matrix; format failures;
cost and p50 latency per question. Response cache in resultados/ruteo_<model>_<effort>.json.
Requires ANTHROPIC_API_KEY.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
PRECIOS = json.loads((REPO / "semana-07" / "prices.json").read_text(encoding="utf-8"))
CLASES = ("sql", "documental", "mixta")
ETIQUETA = {"sql": "sql", "documental": "documental", "no_textual": "documental", "mixta": "mixta"}
SISTEMA = (
    "Eres el enrutador de un asistente de una distribuidora industrial. Decides qué herramienta responde cada pregunta.\n\n"
    "Herramienta 'sql': base de datos de inventario con productos o artículos (SKU, nombre, categoría, costo unitario, "
    "punto de reorden, si es crítico, proveedor), proveedores (nombre, país, tiempo de entrega), almacenes o CEDIS "
    "(nombre, ciudad), existencias por artículo y almacén, ventas diarias por artículo y órdenes de compra. Sirve para "
    "cifras calculadas sobre los datos actuales: conteos, sumas, promedios, existencias, ventas, rankings y listas.\n\n"
    "Herramienta 'documental': documentos internos indexados: políticas y procedimientos (devoluciones, reorden, "
    "órdenes de compra y sus niveles de aprobación, recepción, transferencias, SKUs críticos, evaluación de proveedores, "
    "contratos marco, descuentos, seguridad, mermas, capacitación, auditoría y otros), tablas en PDF, documentos "
    "escaneados (actas, remisiones) e imágenes (gráficas, planos). Sirve para reglas, plazos, umbrales, responsables y "
    "datos que solo están escritos en esos documentos.\n\n"
    "Responde SOLO con JSON: {\"ruta\": \"sql\"} si la respuesta sale solo de la base de datos, {\"ruta\": \"documental\"} "
    "si sale solo de los documentos, o {\"ruta\": \"mixta\"} si necesita ambas herramientas.")


def clasificar(modelo, esfuerzo, pregunta):
    cuerpo = {"model": modelo, "max_tokens": 1500, "system": SISTEMA, "output_config": {"effort": esfuerzo},
              "messages": [{"role": "user", "content": pregunta}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    for intento in range(4):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and intento < 3:
                time.sleep(2 ** (intento + 1))
                continue
            raise SystemExit(f"API HTTP {e.code}: {e.read().decode()[:300]}")
    texto = "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    m = re.search(r"\{.*?\}", texto, re.S)
    ruta = None
    if m:
        try:
            ruta = json.loads(m.group(0)).get("ruta")
        except json.JSONDecodeError:
            ruta = None
    u, p = d["usage"], PRECIOS[f"anthropic:{modelo}"]
    return {"ruta": ruta if ruta in CLASES else None, "texto": texto[:200], "stop": d.get("stop_reason"),
            "tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"], "latencia_s": round(time.perf_counter() - t0, 3),
            "costo_usd": round((u["input_tokens"] * p["in"] + u["output_tokens"] * p["out"]) / 1e6, 7)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="claude-haiku-5-5")
    ap.add_argument("--esfuerzo", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    args = ap.parse_args()
    items = [json.loads(l) for lang in ("es", "en")
             for l in (RAIZ / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines()]
    ruta_cache = RES / f"ruteo_{args.modelo}_{args.esfuerzo}.json"
    cache = json.loads(ruta_cache.read_text(encoding="utf-8")) if ruta_cache.exists() else {}
    RES.mkdir(parents=True, exist_ok=True)
    detalle = []
    for x in items:
        clave = f"{x['id']}::{x['lang']}"
        if clave not in cache:
            cache[clave] = clasificar(args.modelo, args.esfuerzo, x["question"])
            ruta_cache.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        c = cache[clave]
        esperado = ETIQUETA[x["tipo"]]
        sub = x["tipo"] + (f"/{x['formato']}" if "formato" in x else "")
        detalle.append({"id": x["id"], "lang": x["lang"], "tipo": sub, "esperado": esperado,
                        "mayoritaria": "documental", "claude": c["ruta"] or "formato_invalido",
                        "ok_mayoritaria": int(esperado == "documental"), "ok_claude": int(c["ruta"] == esperado),
                        "tokens_in": c["tokens_in"], "tokens_out": c["tokens_out"], "latencia_s": c["latencia_s"],
                        "costo_usd": c["costo_usd"], "pregunta": x["question"]})

    nombre = f"Claude {args.modelo} ({args.esfuerzo})"
    print(f"| Classifier | Language | Accuracy | sql | document (text) | document (non-text) | mixed |")
    print("|---|---|---|---|---|---|---|")
    for clf, col in (("mayoritaria (siempre documental)", "ok_mayoritaria"), (nombre, "ok_claude")):
        for lang in ("es", "en"):
            f = [d for d in detalle if d["lang"] == lang]
            def parte(pred):
                g = [d for d in f if pred(d["tipo"])]
                return f"{sum(d[col] for d in g)}/{len(g)}"
            print(f"| {clf} | {lang} | {sum(d[col] for d in f) / len(f):.3f} ({sum(d[col] for d in f)}/{len(f)}) | "
                  f"{parte(lambda t: t == 'sql')} | {parte(lambda t: t == 'documental')} | "
                  f"{parte(lambda t: t.startswith('no_textual'))} | {parte(lambda t: t == 'mixta')} |")

    print(f"\nConfusion matrix of {nombre} (rows: expected; columns: predicted), both languages")
    cols = list(CLASES) + ["formato_invalido"]
    conf = Counter((d["esperado"], d["claude"]) for d in detalle)
    print("| expected \\ predicted | " + " | ".join(cols) + " |")
    print("|---|" + "---|" * len(cols))
    for e in CLASES:
        print(f"| {e} | " + " | ".join(str(conf[(e, p)]) for p in cols) + " |")

    costo = sum(d["costo_usd"] for d in detalle)
    print(f"\n{nombre}: {len(detalle)} questions, total cost ${costo:.5f} (${costo / len(detalle):.6f} per question), "
          f"p50 latency {statistics.median(d['latencia_s'] for d in detalle):.2f} s, "
          f"mean output tokens {statistics.mean(d['tokens_out'] for d in detalle):.0f}, "
          f"truncated outputs {sum(1 for c in cache.values() if c['stop'] == 'max_tokens')}")
    for d in detalle:
        if not d["ok_claude"]:
            print(f"  error: {d['id']} {d['lang']} ({d['tipo']}) expected={d['esperado']} predicted={d['claude']} | {d['pregunta'][:90]}")
    with (RES / f"ruteo_detalle_{args.modelo}_{args.esfuerzo}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)


if __name__ == "__main__":
    main()
