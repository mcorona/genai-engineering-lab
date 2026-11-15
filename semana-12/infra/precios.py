"""Week 12, activity 1: official prices from each cloud's price catalogs (not from third-party pages).

- AWS: the Price List API (`aws pricing get-products`, us-east-1 endpoint) for the Bedrock services and for S3 (S3 Vectors
  and S3 Standard), region us-east-1.
- Google Cloud: the Cloud Billing Catalog API (`cloudbilling.googleapis.com/v1/services/.../skus`), with the ADC token, for
  Vertex AI Search (Discovery Engine / Agent Search) and Cloud Storage.
It filters by keywords of what week 12 uses and writes resultados/precios_catalogo_<date>.csv with source, service,
SKU or usage type, description, unit and price in USD. Read-only, at no cost.
Requires the AWS CLI with a signed-in session and gcloud with ADC (gcloud auth application-default login).
"""
import csv
import datetime as dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REGION = "us-east-1"
CLAVES_AWS = ("haiku", "titan", "embed", "embed-multilingual", "embed multilingual",
              "rerank", "knowledge", "vector", "dataautomation", "data automation")
CLAVES_S3 = ("vector", "timedstorage-bytehrs", "requests-tier1", "requests-tier2")
CLAVES_GCP = {"Vertex AI Search": ("search", "query", "storage", "index", "layout", "ocr", "pars", "rank", "chunk"),
              "Cloud Storage": ("standard storage us multi-region", "standard storage northern virginia",
                                "standard storage us east", "class a", "class b")}


def aws(*args):
    r = subprocess.run(["aws", *args, "--region", "us-east-1", "--output", "json"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"aws {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def filas_aws(codigo, claves):
    datos = aws("pricing", "get-products", "--service-code", codigo,
                "--filters", f"Type=TERM_MATCH,Field=regionCode,Value={REGION}")
    filas = []
    for item in datos.get("PriceList", []):
        p = json.loads(item)
        at = p["product"].get("attributes", {})
        texto_prod = " ".join(str(v) for v in at.values()).lower()
        for term in p.get("terms", {}).get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                texto = (texto_prod + " " + dim.get("description", "")).lower()
                if any(c in texto for c in claves):
                    filas.append({"fuente": "AWS Price List API", "servicio": codigo,
                                  "id": at.get("usagetype", ""), "modelo": at.get("model", at.get("titanModel", "")),
                                  "descripcion": dim.get("description", ""), "unidad": dim.get("unit", ""),
                                  "usd": dim["pricePerUnit"].get("USD", "")})
    return filas


def gcp_get(url, token, proyecto):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "x-goog-user-project": proyecto})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def filas_gcp():
    token = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"], capture_output=True, text=True).stdout.strip()
    proyecto = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True).stdout.strip()
    if not token:
        raise SystemExit("Sin token ADC: gcloud auth application-default login")
    servicios, page = [], ""
    while True:
        d = gcp_get(f"https://cloudbilling.googleapis.com/v1/services?pageSize=5000&pageToken={page}", token, proyecto)
        servicios += d.get("services", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    filas = []
    for nombre, claves in CLAVES_GCP.items():
        objetivo = [s for s in servicios if s["displayName"] == nombre
                    or (nombre == "Vertex AI Search" and s["displayName"] in ("Discovery Engine", "Agent Search", "Vertex AI Agent Builder"))]
        if not objetivo:
            print(f"warning: service '{nombre}' not found in the catalog", file=sys.stderr)
        for s in objetivo:
            page = ""
            while True:
                d = gcp_get(f"https://cloudbilling.googleapis.com/v1/{s['name']}/skus?pageSize=5000&currencyCode=USD&pageToken={page}", token, proyecto)
                for sku in d.get("skus", []):
                    desc = sku["description"]
                    if not any(c in desc.lower() for c in claves):
                        continue
                    for pi in sku.get("pricingInfo", [])[:1]:
                        e = pi["pricingExpression"]
                        for t in e.get("tieredRates", []):
                            u = t["unitPrice"]
                            precio = int(u.get("units", 0) or 0) + u.get("nanos", 0) / 1e9
                            filas.append({"fuente": "Cloud Billing Catalog API", "servicio": s["displayName"],
                                          "id": sku["skuId"], "modelo": ",".join(sku.get("serviceRegions", [])[:3]),
                                          "descripcion": f"{desc} (desde {t.get('startUsageAmount', 0)} {e.get('usageUnit', '')})",
                                          "unidad": e.get("usageUnitDescription", ""), "usd": f"{precio:.10g}"})
                page = d.get("nextPageToken", "")
                if not page:
                    break
    return filas


def main():
    hoy = dt.date.today().isoformat()
    codigos = [s["ServiceCode"] for s in aws("pricing", "describe-services")["Services"] if "bedrock" in s["ServiceCode"].lower()]
    print("servicios de Bedrock en la Price List API:", codigos, file=sys.stderr)
    filas = []
    for c in codigos:
        filas += filas_aws(c, CLAVES_AWS)
    filas += filas_aws("AmazonS3", CLAVES_S3)
    filas += filas_gcp()
    vistos, unicas = set(), []
    for f in filas:
        k = tuple(f.values())
        if k not in vistos:
            vistos.add(k)
            unicas.append(f)
    salida = RAIZ / "resultados" / f"precios_catalogo_{hoy}.csv"
    with salida.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(unicas[0].keys()))
        w.writeheader()
        w.writerows(sorted(unicas, key=lambda f: (f["fuente"], f["servicio"], f["descripcion"])))
    print(f"{len(unicas)} rows in {salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
