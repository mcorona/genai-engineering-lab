"""Week 20, activity 1: the prices and limits week 20 builds on, read from AWS at $0.

    .venv/bin/python semana-20/linea_base/precios.py            prints what it would read, no AWS call
    .venv/bin/python semana-20/linea_base/precios.py --si       reads (semana19-lectura) and writes resultados/precios.json

Only free, read-only calls:
- the Price List API (`pricing:GetProducts`, us-east-1): Haiku 4.5, the Nova models, Sonnet 4.5 and 4.6, CloudWatch and
  X-Ray, each row with its SKU and usage type (source M, as in week 19);
- Service Quotas (`servicequotas:ListServiceQuotas`, bedrock): the cross-region tokens and requests per minute of the
  routing candidates, and the batch inference limits;
- Bedrock (`bedrock:ListPromptRouters`): the prompt routers of the region and their models.
No Cost Explorer call: each one costs 0.01 USD and needs Manuel's OK.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
SALIDA = S20 / "resultados" / "precios.json"
REGION = "us-east-1"

# The models week 20 can route between or batch with, by their Price List and Service Quotas names.
MODELOS_FM = ("Claude Haiku 4.5", "Claude Sonnet 4.5", "Claude Sonnet 4.6")   # AmazonBedrockFoundationModels
MODELOS_NOVA = ("NovaMicro", "NovaLite", "Nova2.0Lite", "NovaPro")             # AmazonBedrock, by usage type
CUOTAS_CANDIDATOS = ("Anthropic Claude Haiku 4.5", "Anthropic Claude Sonnet 4.5 V1", "Anthropic Claude Sonnet 4.6",
                     "Amazon Nova Micro", "Amazon Nova Lite", "Amazon Nova 2 Lite", "Amazon Nova Pro")
LOTE_MODELOS = ("Claude Haiku 4.5", "Nova Micro V1", "Nova Lite V1", "Nova 2 Lite", "Nova Pro V1")
# CloudWatch and X-Ray usage types the dashboard, the alarms and the traces are billed under.
USOS_CW = ("CW:MetricMonitorUsage", "CW:AlarmMonitorUsage", "CW:HighResAlarmMonitorUsage", "USE1-DataProcessing-Bytes",
           "USE1-DataScanned-Bytes", "USE1-XRay-Spans-Indexed", "USE1-Application-Signals-Bytes")
USOS_XRAY = ("USE1-XRay-TracesStored", "USE1-XRay-TracesAccessed")
# Dashboards are priced globally (location "Any", no regionCode), so they are read by usage type, not by region.
USOS_CW_GLOBALES = ("Global-DashboardsUsageHour-Basic", "DashboardsUsageHour-Basic", "DashboardsUsageHour")


def _dimensiones(producto: dict) -> list[dict]:
    """The USD dimensions only: some rows also carry a CNY dimension (the dashboards' free tier)."""
    return [{"unidad": d["unit"], "usd": float(d["pricePerUnit"]["USD"]), "desde": d.get("beginRange"),
             "hasta": d.get("endRange"), "descripcion": d.get("description", "")}
            for t in producto["terms"].get("OnDemand", {}).values() for d in t["priceDimensions"].values()
            if "USD" in d["pricePerUnit"]]


def fila(producto: dict, servicio: str) -> dict:
    a = producto["product"]["attributes"]
    return {"servicio": servicio, "sku": producto["product"].get("sku"), "uso": a.get("usagetype"),
            "modelo": a.get("model"), "tipo": a.get("inferenceType"), "modalidad": a.get("feature"),
            "precios": _dimensiones(producto)}


def _productos(cliente, servicio: str, campo: str = "regionCode", valor: str = REGION) -> list[dict]:
    salida, token = [], None
    while True:
        kw = {"ServiceCode": servicio, "MaxResults": 100,
              "Filters": [{"Type": "TERM_MATCH", "Field": campo, "Value": valor}]}
        if token:
            kw["NextToken"] = token
        r = cliente.get_products(**kw)
        salida += [json.loads(x) for x in r["PriceList"]]
        token = r.get("NextToken")
        if not token:
            return salida


def elegir(productos_fm: list, productos_br: list, productos_cw: list, productos_xr: list) -> list[dict]:
    """The rows week 20 uses, out of the four catalogs. Custom-model rows are left out: week 20 runs base models."""
    filas = [fila(p, "AmazonBedrockFoundationModels") for p in productos_fm
             if p["product"]["attributes"].get("model") in MODELOS_FM]
    filas += [fila(p, "AmazonBedrock") for p in productos_br
              if re.match(rf"USE1-({'|'.join(map(re.escape, MODELOS_NOVA))})-", p["product"]["attributes"].get("usagetype", ""))
              and "custom-model" not in p["product"]["attributes"].get("usagetype", "")]
    filas += [fila(p, "AmazonCloudWatch") for p in productos_cw
              if p["product"]["attributes"].get("usagetype") in USOS_CW + USOS_CW_GLOBALES]
    filas += [fila(p, "AWSXRay") for p in productos_xr if p["product"]["attributes"].get("usagetype") in USOS_XRAY]
    vistos, unicas = set(), []
    for f in sorted(filas, key=lambda f: (f["servicio"], f["modelo"] or "", f["uso"] or "")):
        if f["sku"] not in vistos:
            vistos.add(f["sku"])
            unicas.append(f)
    return unicas


def cuotas(cliente) -> dict:
    todas, token = [], None
    while True:
        kw = {"ServiceCode": "bedrock", "MaxResults": 100}
        if token:
            kw["NextToken"] = token
        r = cliente.list_service_quotas(**kw)
        todas += r["Quotas"]
        token = r.get("NextToken")
        if not token:
            break
    return elegir_cuotas(todas)


def elegir_cuotas(todas: list[dict]) -> dict:
    por_nombre = {q["QuotaName"]: q for q in todas}
    candidatos = {}
    for m in CUOTAS_CANDIDATOS:
        tpm = por_nombre.get(f"Cross-region model inference tokens per minute for {m}")
        rpm = por_nombre.get(f"Cross-region model inference requests per minute for {m}")
        candidatos[m] = {"tpm": tpm and tpm["Value"], "rpm": rpm and rpm["Value"],
                         "codigos": [q["QuotaCode"] for q in (tpm, rpm) if q]}
    lote = {}
    for m in LOTE_MODELOS:
        lote[m] = {clave: por_nombre[n]["Value"] for clave, n in (
            ("min_registros", f"Minimum number of records per batch inference job for {m}"),
            ("max_registros", f"Records per batch inference job for {m}"),
            ("max_registros_archivo", f"Records per input file per batch inference job for {m}"),
            ("gb_trabajo", f"Batch inference job size (in GB) for {m}"),
            ("gb_archivo", f"Batch inference input file size (in GB) for {m}"),
            ("trabajos_en_curso", f"Sum of in-progress and submitted batch inference jobs using a base model for {m}"),
        ) if n in por_nombre}
    return {"candidatos": candidatos, "lote": lote}


def enrutadores(cliente) -> list[dict]:
    return [{"nombre": r["promptRouterName"], "tipo": r["type"],
             "modelos": [m["modelArn"].rsplit("/", 1)[-1] for m in r["models"]],
             "respaldo": r.get("fallbackModel", {}).get("modelArn", "").rsplit("/", 1)[-1]}
            for r in cliente.list_prompt_routers()["promptRouterSummaries"]]


def main(argv=None, sesion=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--si", "--yes", action="store_true", help="read from AWS (by default only prints what it would read)")
    a = ap.parse_args(argv)
    if not a.si:
        print(json.dumps({"pricing": ["AmazonBedrockFoundationModels", "AmazonBedrock", "AmazonCloudWatch", "AWSXRay"],
                          "service-quotas": "bedrock", "bedrock": "ListPromptRouters", "region": REGION}, indent=2))
        print("Simulation: no AWS calls were made.")
        return 0
    if sesion is None:
        import boto3
        sesion = boto3.Session(profile_name=os.environ.get("S20_PERFIL", "semana19-lectura"), region_name=REGION)
    p = sesion.client("pricing", region_name="us-east-1")
    datos = {"fecha": date.today().isoformat(), "region": REGION, "fuente": "M",
             "precios": elegir(_productos(p, "AmazonBedrockFoundationModels"), _productos(p, "AmazonBedrock"),
                               _productos(p, "AmazonCloudWatch")
                               + [x for u in USOS_CW_GLOBALES for x in _productos(p, "AmazonCloudWatch", "usagetype", u)],
                               _productos(p, "AWSXRay")),
             "cuotas": cuotas(sesion.client("service-quotas")),
             "enrutadores": enrutadores(sesion.client("bedrock"))}
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"precios": len(datos["precios"]), "candidatos": len(datos["cuotas"]["candidatos"]),
                      "enrutadores": len(datos["enrutadores"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
