"""Week 19, activity 1: baseline of the account, Bedrock, the prices and the tools. Read-only; no model is invoked.

Each probe runs in its own subprocess and prints one JSON line. Results go to
resultados/linea_base_<where>.json with no secret: account IDs become <account>, ARNs are cut, and home paths become ~.

Marks: M = measured by this run (date recorded), D = documented (official doc link), N = not verified.

    uv run --group semana19 python semana-19/linea_base/verificar.py --perfil <operador> --donde mac
    uv run --group semana19 python semana-19/linea_base/verificar.py --perfil <operador> --donde mac --gasto-mes   # Cost Explorer: $0.01 per call, needs OK

Costs: Price List, Service Quotas, Bedrock list/get, STS, Free Tier API, IAM list and Tagging API are free.
Cost Explorer is off by default; --gasto-mes makes at most 1 call per run (the activity allows 5 in total).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ19 = AQUI.parent
FECHA = date.today().isoformat()
REGION = "us-east-1"

# One row per item of activity 1. "patron" is a regex over usagetype + description (Price List, us-east-1).
# Items with no patron are not in the Price List: they are D (documented, official link) and never M.
ARTICULOS = [
    ("lambda_arm_solicitudes", "AWSLambda", None, "https://aws.amazon.com/lambda/pricing/",
     "la solicitud ARM estándar no aparece en el catálogo de Price List; la consulta exacta queda en la doc oficial"),
    ("lambda_arm_gb_s", "AWSLambda", r"Lambda-GB-Second-ARM", None, ""),
    ("step_functions_standard_transiciones", None, None, "https://aws.amazon.com/step-functions/pricing/",
     "Step Functions no tiene código de servicio en la Price List"),
    ("api_gateway_http_solicitudes", "AmazonApiGateway", r"ApiGatewayHttpRequest", None, ""),
    ("cognito_mau_essentials", "AmazonCognito", r"CognitoEssentialsMAU", None, "tier Essentials; el free tier es documental"),
    ("rds_postgres_t4g_micro_single_az", "AmazonRDS", r"InstanceUsage:db\.t4g\.micro.*Single-AZ.*PostgreSQL", None, ""),
    ("rds_gp3_almacenamiento_postgres", "AmazonRDS", r"RDS:GP3-Storage\b", None, ""),
    ("aurora_serverless_v2_acu_hora_postgres", "AmazonRDS", r"Aurora:ServerlessV2Usage", None, ""),
    ("aurora_escala_a_0_acu", None, None, "https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html",
     "el escalado a 0 ACU es un atributo de configuración, no un precio; se confirma en la doc"),
    ("endpoint_vpc_interface_por_az_hora", None, None, "https://aws.amazon.com/privatelink/pricing/",
     "la tarifa por hora de endpoint de interfaz no aparece en AmazonVPC de la Price List"),
    ("endpoint_vpc_interface_por_gb", None, None, "https://aws.amazon.com/privatelink/pricing/",
     "la tarifa por GB de endpoint de interfaz no aparece en AmazonVPC de la Price List"),
    ("ipv4_publica_en_uso_hora", "AmazonVPC", r"PublicIPv4:InUseAddress", None, ""),
    ("kms_llave_administrada_mes", "awskms", r"KMS-Keys\b", None, ""),
    ("kms_llave_pendiente_de_borrado", None, None, "https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html",
     "cobro de la llave pendiente de borrado: se confirma en la doc; no es un artículo del catálogo"),
    ("cloudwatch_logs_ingesta", "AmazonCloudWatch", r"DataProcessing-Bytes", None, "clase Standard"),
    ("cloudwatch_logs_almacenamiento", "AmazonCloudWatch", r"TimedStorage-ByteHrs", None, ""),
    ("s3_vectors_almacenamiento", "AmazonS3", r"Vectors-TimedStorage-ByteHrs", None, ""),
    ("modelo_claude_elegido", None, None, "https://aws.amazon.com/bedrock/pricing/",
     "Claude Haiku 5.5 y Haiku 4.5 no aparecen en la Price List de AmazonBedrock; la tarifa vigente se confirma en la página de precios"),
    ("titan_text_embeddings_v2_tokens", "AmazonBedrock", r"TitanEmbeddingV2-Text-input-tokens\b(?!-batch)", None, "por 1K tokens"),
    ("agentcore_gateway_invocaciones", "AmazonBedrockAgentCore", r"Gateway:Consumption-based:API-Invocations", None, ""),
    ("agentcore_runtime_instancia", "AmazonBedrockAgentCore", r"Runtime:Instance-based:c5\.large:Management-Hours", None, "unidad por instancia y hora"),
    ("agentcore_policy", "AmazonBedrockAgentCore", r"Policy", None, "sin coincidencia en la búsqueda del 2026-11-12; se revisa"),
]

HERRAMIENTAS = {"aws": ["aws", "--version"], "node": ["node", "--version"], "npm": ["npm", "--version"],
                "uv": ["uv", "--version"], "cdk": ["cdk", "--version"], "terraform": ["terraform", "version"],
                "checkov": ["checkov", "--version"]}


def sesion_boto(perfil: str):
    import boto3
    return boto3.Session(profile_name=perfil, region_name=REGION)


# ---------- probes: each returns a dict; a failure is {"estado": "N", "error": ...}, never a fake zero ----------

def sonda_cuenta(perfil: str) -> dict:
    s = sesion_boto(perfil)
    out = {"fecha": FECHA, "fuentes": {}}
    try:
        fr = s.client("freetier", region_name=REGION)
        plan = fr.get_account_plan_state()
        out["plan"] = {"marca": "M", "plan": plan.get("accountPlanType"), "estado": plan.get("accountPlanStatus"),
                       "fuente": "Free Tier API get_account_plan_state", "fecha": FECHA}
    except Exception as exc:  # noqa: BLE001
        out["plan"] = {"marca": "N", "error": type(exc).__name__}
    out["creditos"] = {"marca": "D", "nota": "la API no da saldo ni vencimiento; se confirma con la pantalla de Billing",
                       "pendiente": "captura o dato de Manuel"}
    out["servicios_del_plan"] = {"marca": "N", "nota": "pendiente de medir con el plan y la lista de la documentación de Free Tier"}
    return out


def sonda_gasto_mes(perfil: str) -> dict:
    s = sesion_boto(perfil)
    ce = s.client("ce", region_name=REGION)
    inicio = date.today().replace(day=1).isoformat()
    fin = date.today().isoformat()
    if inicio == fin:
        return {"marca": "N", "nota": "primer día del mes: no hay gasto que medir"}
    r = ce.get_cost_and_usage(TimePeriod={"Start": inicio, "End": fin}, Granularity="MONTHLY", Metrics=["UnblendedCost"])
    monto = r["ResultsByTime"][0]["Total"]["UnblendedCost"]
    return {"marca": "M", "periodo": [inicio, fin], "monto_usd": monto.get("Amount"), "moneda": monto.get("Unit"),
            "fuente": "Cost Explorer get_cost_and_usage (1 llamada, $0.01)", "fecha": FECHA}


def sonda_bedrock(perfil: str) -> dict:
    s = sesion_boto(perfil)
    b = s.client("bedrock", region_name=REGION)
    out = {"fecha": FECHA}
    try:
        modelos = b.list_foundation_models()["modelSummaries"]
        out["modelos"] = sorted({m["modelId"] for m in modelos
                                 if "anthropic" in m.get("providerName", "").lower() or "embed" in m["modelId"]})
        out["modelos_marca"] = "M"
    except Exception as exc:  # noqa: BLE001
        out["modelos"] = {"marca": "N", "error": type(exc).__name__}
    perfiles = []
    try:
        for p in b.list_inference_profiles(typeEquals="SYSTEM_DEFINED")["inferenceProfileSummaries"]:
            if "anthropic" in p["inferenceProfileId"] or "titan" in p["inferenceProfileId"]:
                perfiles.append(p["inferenceProfileId"])
        out["inference_profiles"] = {"marca": "M", "ids": sorted(perfiles)}
    except Exception as exc:  # noqa: BLE001
        out["inference_profiles"] = {"marca": "N", "error": type(exc).__name__}
    # Service availability: a list call that answers 200 means the capability is available in the region.
    disp = {}
    for nombre, llamada in {
        "guardrails": lambda: b.list_guardrails(),
        "evaluation_jobs": lambda: b.list_evaluation_jobs(),
        "prompt_management": lambda: s.client("bedrock-agent", region_name=REGION).list_prompts(),
        "knowledge_bases": lambda: s.client("bedrock-agent", region_name=REGION).list_knowledge_bases(),
        "bedrock_agents": lambda: s.client("bedrock-agent", region_name=REGION).list_agents(),
        "agentcore_gateway": lambda: s.client("bedrock-agentcore-control", region_name=REGION).list_gateways(),
        "agentcore_runtime": lambda: s.client("bedrock-agentcore-control", region_name=REGION).list_agent_runtimes(),
    }.items():
        try:
            llamada()
            disp[nombre] = {"marca": "M", "respuesta": 200}
        except Exception as exc:  # noqa: BLE001
            disp[nombre] = {"marca": "N", "error": type(exc).__name__}
    out["disponibilidad_list"] = disp
    try:
        out["agentcore_policy"] = {"marca": "N", "nota": "se mide con list_policy_engines si la versión de boto3 lo trae"}
        s.client("bedrock-agentcore-control", region_name=REGION).list_policy_engines()
        out["agentcore_policy"] = {"marca": "M", "respuesta": 200}
    except Exception as exc:  # noqa: BLE001
        out["agentcore_policy"] = {"marca": "N", "error": type(exc).__name__}
    return out


def sonda_cuotas(perfil: str) -> dict:
    s = sesion_boto(perfil)
    sq = s.client("service-quotas", region_name=REGION)
    filas = []
    try:
        for p in sq.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock"):
            for q in p["Quotas"]:
                n = q["QuotaName"]
                if "Claude" in n or "Titan" in n or "Embed" in n:
                    filas.append({"nombre": n, "valor": q.get("Value"), "unidad": q.get("Unit"),
                                  "ajustable": q.get("Adjustable")})
        return {"marca": "M", "filas": filas, "fecha": FECHA, "fuente": "Service Quotas list_service_quotas bedrock"}
    except Exception as exc:  # noqa: BLE001
        return {"marca": "N", "error": type(exc).__name__}


def filas_servicio(codigo: str, cliente) -> list[dict]:
    """All on-demand rows of one Price List service in us-east-1 (paginated, read-only)."""
    filas = []
    for p in cliente.get_paginator("get_products").paginate(
            ServiceCode=codigo, Filters=[{"Type": "TERM_MATCH", "Field": "regionCode", "Value": REGION}]):
        for item in p["PriceList"]:
            prod = json.loads(item) if isinstance(item, str) else item
            at = prod["product"].get("attributes", {})
            for term in prod.get("terms", {}).get("OnDemand", {}).values():
                for dim in term["priceDimensions"].values():
                    filas.append({"servicio": codigo, "usagetype": at.get("usagetype", ""),
                                  "sku": prod["product"].get("sku", ""), "descripcion": dim.get("description", ""),
                                  "unidad": dim.get("unit", ""), "usd": dim["pricePerUnit"].get("USD", "")})
    return filas


def sonda_precios(perfil: str) -> dict:
    """One mark per item: M with the catalog id and price, D with the official link, or N with the reason."""
    cliente = sesion_boto(perfil).client("pricing", region_name=REGION)  # Price List lives in us-east-1
    cache: dict[str, list[dict]] = {}
    articulos, errores = {}, {}
    for nombre, servicio, patron, enlace, nota in ARTICULOS:
        if patron is None:
            articulos[nombre] = {"marca": "D", "enlace": enlace, "nota": nota, "fecha": FECHA}
            continue
        try:
            if servicio not in cache:
                cache[servicio] = filas_servicio(servicio, cliente)
        except Exception as exc:  # noqa: BLE001
            errores[servicio] = type(exc).__name__
            articulos[nombre] = {"marca": "N", "error": type(exc).__name__, "fecha": FECHA}
            continue
        coinc = [f for f in cache[servicio] if re.search(patron, f["usagetype"] + " | " + f["descripcion"])]
        if not coinc:
            articulos[nombre] = {"marca": "N", "nota": nota or "sin coincidencia en la Price List", "fecha": FECHA}
            continue
        f = sorted(coinc, key=lambda x: float(x["usd"] or 0))[0]
        articulos[nombre] = {"marca": "M", "precio_usd": f["usd"], "unidad": f["unidad"], "usagetype": f["usagetype"],
                             "sku": f["sku"], "descripcion": f["descripcion"][:160], "nota": nota,
                             "fuente": f"AWS Price List API, servicio {servicio}, us-east-1", "fecha": FECHA}
    marcas = [a["marca"] for a in articulos.values()]
    return {"fecha": FECHA, "articulos": articulos, "errores": errores,
            "conteo": {m: marcas.count(m) for m in ("M", "D", "N")}}


def version_herramienta(nombre: str) -> dict:
    ruta = shutil.which(HERRAMIENTAS[nombre][0])
    if not ruta:
        return {"instalada": None, "marca": "M", "nota": "no instalada"}
    r = subprocess.run(HERRAMIENTAS[nombre], capture_output=True, text=True, timeout=60)
    salida = (r.stdout + r.stderr).strip()
    m = re.search(r"(\d+\.\d+(\.\d+)?)", salida)
    return {"instalada": m.group(1) if m else salida[:60], "marca": "M", "fecha": FECHA}


def sonda_herramientas() -> dict:
    out = {nombre: version_herramienta(nombre) for nombre in HERRAMIENTAS}
    npm = {}
    if shutil.which("npm"):
        for paquete in ("aws-cdk", "aws-cdk-lib", "constructs", "cdk-nag"):
            r = subprocess.run(["npm", "view", paquete, "version"], capture_output=True, text=True, timeout=60)
            npm[paquete] = {"ultima_publicada": r.stdout.strip() or None, "marca": "M" if r.returncode == 0 else "N", "fecha": FECHA}
    out["npm"] = npm
    return out


def sonda_repo() -> dict:
    flujo = (RAIZ19.parent / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    return {"semana-19 en regresion": '"semana-19/**"' in flujo, "marca": "M"}


SONDAS = {"cuenta": lambda p: sonda_cuenta(p), "gasto_mes": lambda p: sonda_gasto_mes(p),
          "bedrock": lambda p: sonda_bedrock(p), "cuotas": lambda p: sonda_cuotas(p),
          "precios": lambda p: sonda_precios(p), "herramientas": lambda _p: sonda_herramientas(),
          "repo": lambda _p: sonda_repo()}


# ---------- sanitizer: nothing that identifies the account or the home folder reaches a result ----------

def sanear(texto: str) -> str:
    texto = re.sub(r"\b\d{12}\b", "<account>", texto)
    texto = re.sub(r"arn:aws[\w-]*:[^\s\"']+", "<arn>", texto)
    texto = re.sub(r"/(?:Users|home)/[^/\s\"']+", "~", texto)
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<correo>", texto)
    return texto


def correr_sonda(nombre: str, perfil: str | None) -> dict:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--sonda", nombre]
    if perfil:
        cmd += ["--perfil", perfil]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode:
        return {"error": sanear(r.stderr.strip()[-300:])}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", help="perfil de solo lectura (operador)")
    ap.add_argument("--donde", choices=["mac", "ci"], default="mac")
    ap.add_argument("--gasto-mes", action="store_true", help="incluye Cost Explorer (1 llamada de $0.01)")
    ap.add_argument("--sonda", choices=list(SONDAS), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.sonda:
        resultado = SONDAS[a.sonda](a.perfil)
        print(sanear(json.dumps(resultado, ensure_ascii=False)))
        return 0
    if not a.perfil:
        print("Falta --perfil (operador, solo lectura).", file=sys.stderr)
        return 2
    informe = {"fecha": FECHA, "donde": a.donde, "region": REGION}
    for nombre in SONDAS:
        if nombre == "gasto_mes" and not a.gasto_mes:
            continue
        informe[nombre] = correr_sonda(nombre, a.perfil if nombre not in ("herramientas", "repo") else None)
    salida = AQUI.parent / "resultados" / f"linea_base_{a.donde}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    texto = sanear(json.dumps(informe, indent=2, ensure_ascii=False))
    salida.write_text(texto, encoding="utf-8")
    print(f"escrito: {salida.relative_to(RAIZ19.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
