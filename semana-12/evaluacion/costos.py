"""Week 12, activity 7 (cost): the ingestion cost, the fixed monthly cost and the cost per query of each option, and the
break-even point in queries per month. Prices from resultados/precios_catalogo_2026-10-28.csv (official catalogs, activity 1)
and, to host the in-house pipeline, the smallest RDS instance with pgvector, looked up in the AWS Price List API.
Costs per query measured in activities 3 to 5 (the *_resumen.json summaries) and in latencia_resumen.json.

Assumptions (written here and in resultados/latencia_costo.md):
- The in-house pipeline in the cloud = PostgreSQL with pgvector on RDS db.t4g.micro Single-AZ with 20 GB gp3 (the minimum
  that sustains this corpus), query embeddings with Cohere multilingual on Bedrock (bge-m3 runs locally, at no API
  cost) and reranking with Haiku 5.5. Application compute and network are not counted; they are the same for every option.
- Every option answers with the common generator (Haiku 5.5, Anthropic API), except RetrieveAndGenerate.
- Vertex: the first 10,000 queries per month are free (Enterprise and Standard); after that, the Enterprise list price.
"""
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RES = RAIZ / "resultados"
PAQ = RAIZ / "ingesta" / "paquete"
HORAS_MES = 730


def precio(id_, modelo=None):
    for f in csv.DictReader(open(RES / "precios_catalogo_2026-10-28.csv", encoding="utf-8")):
        if f["id"] == id_ and (modelo is None or f["modelo"] == modelo):
            return float(f["usd"])
    raise SystemExit(f"price not found: {id_}")


def rds():
    """db.t4g.micro PostgreSQL Single-AZ (USD/hora) y almacenamiento gp3 (USD/GB-mes), us-east-1, Price List API."""
    def get(filtros):
        args = ["aws", "pricing", "get-products", "--region", "us-east-1", "--service-code", "AmazonRDS", "--output", "json",
                "--filters"] + [f"Type=TERM_MATCH,Field={k},Value={v}" for k, v in filtros.items()]
        d = json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout)
        for item in d["PriceList"]:
            p = json.loads(item)
            for t in p["terms"]["OnDemand"].values():
                for dim in t["priceDimensions"].values():
                    return float(dim["pricePerUnit"]["USD"]), dim["description"]
    hora = get({"regionCode": "us-east-1", "instanceType": "db.t4g.micro", "databaseEngine": "PostgreSQL",
                "deploymentOption": "Single-AZ"})
    gp3 = get({"regionCode": "us-east-1", "volumeType": "General Purpose-GP3", "databaseEngine": "PostgreSQL",
               "deploymentOption": "Single-AZ"})
    return hora, gp3


def resumen(nombre):
    return json.loads((RES / f"{nombre}_resumen.json").read_text(encoding="utf-8"))


def main():
    man = json.loads((PAQ / "manifiesto.json").read_text(encoding="utf-8"))
    docs = man["documentos"]
    chars_textos = sum(d["chars_texto"] for d in docs)
    chars_chunks = sum(len((PAQ / "controlado" / "chunks" / d["tenant_id"] / f"{d['source']}__{i:03d}.txt").read_text(encoding="utf-8"))
                       for d in docs for i in range(d["chunks"]))
    pdf_pag = 0
    try:
        from pypdf import PdfReader
        pdf_pag = sum(len(PdfReader(PAQ / "administrado" / "alfa" / f"{s}.pdf").pages) for s in ("tarifas_flete", "matriz_proveedores"))
    except Exception:  # noqa: BLE001
        pdf_pag = 2
    imagenes = sum(1 for d in docs if d["tipo"] in ("jpg", "png"))
    html_pag = sum(math.ceil(d["chars_texto"] / 3000) for d in docs if d["tipo"] == "texto")

    p = {"cohere_tok": precio("USE1-MP:USE1_InputTokenCount-Units", "Embed Multilingual") / 1e6,
         "s3v_put_gb": precio("Vectors-Put-Bytes"), "s3v_gb_mes": precio("Vectors-TimedStorage-ByteHrs"),
         "s3_gb_mes": 0.023, "bda_pag": 0.01, "bda_img": 0.003,
         "layout_pag": precio("5F3F-A230-7FDA"), "ocr_pag": precio("8E95-B0FA-9047"),
         "vx_consulta": 4.0 / 1000, "vx_gratis": 10000, "ranking": precio("EE89-3EE8-2541"), "gcs_gb_mes": 0.026}
    (hora, desc_h), (gp3, desc_s) = rds()
    rds_mes = hora * HORAS_MES + gp3 * 20

    # ---------- ingestion (one time) ----------
    vect_bytes = 1024 * 4 + 1024  # float32 vector + metadata (≤ 1 KB)
    ing = {
        "propio": {"usd": 0.003, "detalle": "bge-m3 local; extracción de imágenes con Haiku (semana 10, $0.003)"},
        "bedrock_ctl-chunks": {"usd": chars_chunks / 4 * p["cohere_tok"] + 101 * vect_bytes / 1e9 * p["s3v_put_gb"],
                               "detalle": f"embeddings Cohere de {chars_chunks:,} caracteres y carga en S3 Vectors"},
        "bedrock_adm-fijo-bda": {"usd": chars_textos / 4 * p["cohere_tok"] + pdf_pag * p["bda_pag"] + imagenes * p["bda_img"],
                                 "detalle": f"embeddings de {chars_textos:,} caracteres; BDA {pdf_pag} páginas PDF y {imagenes} imágenes "
                                            "(si BDA cobrara también los 34 Markdown, +$0.34 como máximo)"},
        "vertex_vx-ctl": {"usd": 0.0, "detalle": "parser digital sin costo; embeddings incluidos"},
        "vertex_vx-adm": {"usd": (html_pag + pdf_pag + imagenes) * p["layout_pag"],
                          "detalle": f"layout parser: {html_pag} páginas HTML (3,000 caracteres por página), {pdf_pag} PDF, {imagenes} imágenes en PDF"},
    }
    # ---------- fixed monthly ----------
    gb_vect = 101 * vect_bytes / 1e9
    gb_docs = sum(f.stat().st_size for f in PAQ.rglob("*") if f.is_file()) / 1e9
    fijo = {"propio": rds_mes, "bedrock_ctl-chunks": gb_vect * p["s3v_gb_mes"] + gb_docs * p["s3_gb_mes"],
            "bedrock_adm-fijo-bda": gb_vect * 2 * p["s3v_gb_mes"] + gb_docs * p["s3_gb_mes"],
            "vertex_vx-ctl": gb_docs * p["gcs_gb_mes"], "vertex_vx-adm": gb_docs * p["gcs_gb_mes"]}
    # ---------- per query (full answer) ----------
    lat = json.loads((RES / "latencia_resumen.json").read_text(encoding="utf-8")) if (RES / "latencia_resumen.json").exists() else {}
    gen = resumen("propio")["costo_usd_por_consulta"]["generacion"]
    emb_q = 20 * p["cohere_tok"]
    porq = {"propio": {"var": resumen("propio")["costo_usd_por_consulta"]["recuperacion"] + emb_q + gen, "vx": 0},
            "bedrock_ctl-chunks": {"var": resumen("bedrock_ctl-chunks")["costo_usd_por_consulta"]["recuperacion"] + gen, "vx": 0},
            "bedrock_adm-fijo-bda": {"var": resumen("bedrock_adm-fijo-bda_rag")["costo_usd_por_consulta"]["generacion"], "vx": 0},
            "vertex_vx-ctl": {"var": p["ranking"] + resumen("vertex_vx-ctl_semantico")["costo_usd_por_consulta"]["generacion"], "vx": 1},
            "vertex_vx-adm": {"var": p["ranking"] + resumen("vertex_vx-adm_semantico")["costo_usd_por_consulta"]["generacion"], "vx": 1}}

    def mensual(op, n):
        c = fijo[op] + n * porq[op]["var"]
        if porq[op]["vx"]:
            c += max(0, n - p["vx_gratis"]) * p["vx_consulta"]
        return c
    volumenes = [1_000, 10_000, 50_000, 100_000, 1_000_000]
    tabla = {op: {n: round(mensual(op, n), 2) for n in volumenes} for op in fijo}
    equilibrio = {}
    for op in fijo:
        if op == "propio":
            continue
        cruce = next((n for n in range(0, 5_000_001, 1000) if mensual(op, n) > mensual("propio", n)), None)
        equilibrio[op] = cruce
    out = {"precios": p, "rds": {"usd_hora": hora, "descripcion": desc_h, "gp3_gb_mes": gp3, "descripcion_gp3": desc_s, "usd_mes": round(rds_mes, 2)},
           "paquete": {"chars_textos": chars_textos, "chars_chunks": chars_chunks, "pdf_paginas": pdf_pag, "imagenes": imagenes,
                       "html_paginas": html_pag, "gb_documentos": round(gb_docs, 4)},
           "ingesta_usd": {k: {"usd": round(v["usd"], 4), "detalle": v["detalle"]} for k, v in ing.items()},
           "fijo_mensual_usd": {k: round(v, 4) for k, v in fijo.items()},
           "variable_por_consulta_usd": {k: round(v["var"], 6) for k, v in porq.items()},
           "vertex": "primeras 10,000 consultas al mes sin cargo; después $0.004 por consulta (Enterprise)",
           "costo_mensual_usd": tabla, "equilibrio_contra_propio_consultas_mes": equilibrio, "latencia": lat}
    (RES / "costos_resumen.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("rds", "paquete", "ingesta_usd", "fijo_mensual_usd", "variable_por_consulta_usd",
                                          "costo_mensual_usd", "equilibrio_contra_propio_consultas_mes")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
