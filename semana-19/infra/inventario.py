"""Week 19, activity 1: inventory of everything the week 19 stack could leave behind. Read-only ($0, no model).

A resource counts when it has the tag proyecto=semana19 (Resource Groups Tagging API) OR its name starts with semana19
(or CDKToolkit for the bootstrap stack, with its qualifier). Each category is queried on its own; a category that
cannot be read is reported as NO MEDIDO, never as 0, and then "quedan" is "revisar", not "nada".

    uv run --group semana19 python semana-19/infra/inventario.py --perfil <operador> [--region us-east-1]

Output is JSON with counts per category and only names or IDs (never ARNs, account IDs or keys).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

PREFIJO = "semana19"
ETIQUETA = ("proyecto", "semana19")
BOOTSTRAP = "CDKToolkit"


def _nombre_de(tags_list, clave="Name"):
    for t in tags_list or []:
        if t.get("Key") == clave:
            return t.get("Value", "")
    return ""


def categorias(sesion, region: str) -> dict:
    """Returns {categoria: callable -> list of names}. Each callable may raise; the caller records it."""
    def cf():
        cli = sesion.client("cloudformation", region_name=region)
        nombres = []
        pag = cli.get_paginator("list_stacks")
        for pagina in pag.paginate(StackStatusFilter=[s for s in cli.meta.service_model.shape_for("StackStatus").enum
                                                    if not s.startswith("DELETE_")]):
            for s in pagina["StackSummaries"]:
                n = s["StackName"]
                if n.startswith(PREFIJO) or n.startswith(BOOTSTRAP):
                    nombres.append(n)
        return nombres

    def roles():
        cli = sesion.client("iam")
        pag = cli.get_paginator("list_roles")
        return [r["RoleName"] for p in pag.paginate() for r in p["Roles"] if r["RoleName"].startswith(PREFIJO)]

    def kms():
        cli = sesion.client("kms", region_name=region)
        out = []
        for p in cli.get_paginator("list_aliases").paginate():
            for a in p["Aliases"]:
                if a["AliasName"].startswith(f"alias/{PREFIJO}"):
                    out.append(a["AliasName"])
        return out

    def vpcs():
        cli = sesion.client("ec2", region_name=region)
        out = []
        for v in cli.describe_vpcs()["Vpcs"]:
            if _nombre_de(v.get("Tags")).startswith(PREFIJO) or any(
                    t["Key"] == ETIQUETA[0] and t["Value"] == ETIQUETA[1] for t in v.get("Tags", [])):
                out.append(v["VpcId"])
        return out

    def subredes():
        cli = sesion.client("ec2", region_name=region)
        out = []
        for p in cli.get_paginator("describe_subnets").paginate():
            for s in p["Subnets"]:
                if _nombre_de(s.get("Tags")).startswith(PREFIJO) or any(
                        t["Key"] == ETIQUETA[0] and t["Value"] == ETIQUETA[1] for t in s.get("Tags", [])):
                    out.append(s["SubnetId"])
        return out

    def security_groups():
        cli = sesion.client("ec2", region_name=region)
        out = []
        for p in cli.get_paginator("describe_security_groups").paginate():
            for g in p["SecurityGroups"]:
                if g["GroupName"].startswith(PREFIJO) or any(
                        t["Key"] == ETIQUETA[0] and t["Value"] == ETIQUETA[1] for t in g.get("Tags", [])):
                    out.append(g["GroupId"])
        return out

    def endpoints():
        cli = sesion.client("ec2", region_name=region)
        out = []
        for p in cli.get_paginator("describe_vpc_endpoints").paginate():
            for e in p["VpcEndpoints"]:
                if any(t["Key"] == ETIQUETA[0] and t["Value"] == ETIQUETA[1] for t in e.get("Tags", [])):
                    out.append(e["VpcEndpointId"])
        return out

    def lambdas():
        cli = sesion.client("lambda", region_name=region)
        return [f["FunctionName"] for p in cli.get_paginator("list_functions").paginate()
                for f in p["Functions"] if f["FunctionName"].startswith(PREFIJO)]

    def state_machines():
        cli = sesion.client("stepfunctions", region_name=region)
        return [m["name"] for p in cli.get_paginator("list_state_machines").paginate()
                for m in p["stateMachines"] if m["name"].startswith(PREFIJO)]

    def apis_http():
        cli = sesion.client("apigatewayv2", region_name=region)
        return [a["Name"] for a in cli.get_apis()["Items"] if a["Name"].startswith(PREFIJO)]

    def apis_rest():
        cli = sesion.client("apigateway", region_name=region)
        return [a["name"] for p in cli.get_paginator("get_rest_apis").paginate()
                for a in p["items"] if a["name"].startswith(PREFIJO)]

    def user_pools():
        cli = sesion.client("cognito-idp", region_name=region)
        out, token = [], None
        while True:
            kw = {"MaxResults": 60}
            if token:
                kw["NextToken"] = token
            r = cli.list_user_pools(**kw)
            out += [u["Name"] for u in r["UserPools"] if u["Name"].startswith(PREFIJO)]
            token = r.get("NextToken")
            if not token:
                return out

    def rds():
        cli = sesion.client("rds", region_name=region)
        inst = [d["DBInstanceIdentifier"] for p in cli.get_paginator("describe_db_instances").paginate()
                for d in p["DBInstances"] if d["DBInstanceIdentifier"].startswith(PREFIJO)]
        clus = [c["DBClusterIdentifier"] for p in cli.get_paginator("describe_db_clusters").paginate()
                for c in p["DBClusters"] if c["DBClusterIdentifier"].startswith(PREFIJO)]
        return {"instancias": inst, "clusters": clus}

    def buckets():
        cli = sesion.client("s3")
        return [b["Name"] for b in cli.list_buckets()["Buckets"] if b["Name"].startswith(PREFIJO)]

    def vector_buckets():
        cli = sesion.client("s3vectors", region_name=region)
        out, token = [], None
        while True:
            kw = {"prefix": PREFIJO}
            if token:
                kw["nextToken"] = token
            r = cli.list_vector_buckets(**kw)
            out += [b["vectorBucketName"] for b in r.get("vectorBuckets", [])]
            token = r.get("nextToken")
            if not token:
                return out

    def kbs():
        cli = sesion.client("bedrock-agent", region_name=region)
        return [k["name"] for p in cli.get_paginator("list_knowledge_bases").paginate()
                for k in p["knowledgeBaseSummaries"] if k["name"].startswith(PREFIJO)]

    def guardrails():
        cli = sesion.client("bedrock", region_name=region)
        return [g["name"] for p in cli.get_paginator("list_guardrails").paginate()
                for g in p["guardrails"] if g["name"].startswith(PREFIJO)]

    def prompts():
        cli = sesion.client("bedrock-agent", region_name=region)
        return [p_["name"] for p in cli.get_paginator("list_prompts").paginate()
                for p_ in p["promptSummaries"] if p_["name"].startswith(PREFIJO)]

    def gateways():
        cli = sesion.client("bedrock-agentcore-control", region_name=region)
        return [g["name"] for p in cli.get_paginator("list_gateways").paginate()
                for g in p["items"] if g["name"].startswith(PREFIJO)]

    def runtimes():
        cli = sesion.client("bedrock-agentcore-control", region_name=region)
        return [r["agentRuntimeName"] for p in cli.get_paginator("list_agent_runtimes").paginate()
                for r in p["agentRuntimes"] if r["agentRuntimeName"].startswith(PREFIJO)]

    def log_groups():
        cli = sesion.client("logs", region_name=region)
        out = []
        for p in cli.get_paginator("describe_log_groups").paginate():
            for g in p["logGroups"]:
                n = g["logGroupName"]
                if PREFIJO in n:
                    out.append(n)
        return out

    def etiquetados():
        cli = sesion.client("resourcegroupstaggingapi", region_name=region)
        out = []
        for p in cli.get_paginator("get_resources").paginate(
                TagFilters=[{"Key": ETIQUETA[0], "Values": [ETIQUETA[1]]}]):
            out += [r["ResourceARN"].split(":")[-1].split("/")[-1] for r in p["ResourceTagMappingList"]]
        return out

    def presupuestos():
        cli = sesion.client("budgets", region_name="us-east-1")
        cuenta = sesion.client("sts").get_caller_identity()["Account"]
        return [b["BudgetName"] for p in cli.get_paginator("describe_budgets").paginate(AccountId=cuenta)
                for b in p["Budgets"] if b["BudgetName"].startswith(PREFIJO)]

    def acciones_presupuesto():
        cli = sesion.client("budgets", region_name="us-east-1")
        cuenta = sesion.client("sts").get_caller_identity()["Account"]
        out = []
        for p in cli.get_paginator("describe_budget_actions_for_account").paginate(AccountId=cuenta):
            out += [a["BudgetName"] for a in p["Actions"] if a["BudgetName"].startswith(PREFIJO)]
        return out

    def politicas_iam():
        cli = sesion.client("iam")
        return [pol["PolicyName"] for p in cli.get_paginator("list_policies").paginate(Scope="Local")
                for pol in p["Policies"] if pol["PolicyName"].startswith(PREFIJO)]

    def flow_logs():
        cli = sesion.client("ec2", region_name=region)
        return [f["FlowLogId"] for p in cli.get_paginator("describe_flow_logs").paginate()
                for f in p["FlowLogs"] if (f.get("LogGroupName") or "").startswith(f"/{PREFIJO}/")]

    def endpoints_por_vpc():
        cli = sesion.client("ec2", region_name=region)
        vpcs_propias = set(vpcs())
        out = []
        for p in cli.get_paginator("describe_vpc_endpoints").paginate():
            for e in p["VpcEndpoints"]:
                if e["VpcId"] in vpcs_propias:
                    out.append(f"{e['VpcEndpointType']}:{e['ServiceName'].split('.')[-1]}")
        return out

    def llaves_pendientes_borrado():
        cli = sesion.client("kms", region_name=region)
        out = []
        for p in cli.get_paginator("list_aliases").paginate():
            for a in p["Aliases"]:
                if a["AliasName"].startswith((f"alias/{PREFIJO}", f"alias/cdk-s19")) and a.get("TargetKeyId"):
                    estado = cli.describe_key(KeyId=a["TargetKeyId"])["KeyMetadata"]
                    if estado["KeyState"] == "PendingDeletion":
                        out.append(f"{a['AliasName']} borrado {estado['DeletionDate'].date().isoformat()}")
        return out

    return {
        "stacks_cloudformation": cf, "roles_iam": roles, "llaves_kms_por_alias": kms,
        "vpcs": vpcs, "subredes": subredes, "security_groups": security_groups, "endpoints_vpc": endpoints,
        "lambdas": lambdas, "state_machines": state_machines, "apis_http": apis_http, "apis_rest": apis_rest,
        "user_pools": user_pools, "rds": rds, "buckets_s3": buckets, "vector_buckets_s3vectors": vector_buckets,
        "knowledge_bases": kbs, "guardrails": guardrails, "prompts": prompts, "gateways_agentcore": gateways,
        "runtimes_agentcore": runtimes, "log_groups": log_groups,
        "etiquetados_tagging_api": etiquetados,
        "presupuestos": presupuestos, "acciones_presupuesto": acciones_presupuesto,
        "politicas_iam_locales": politicas_iam, "flow_logs": flow_logs,
        "endpoints_por_vpc": endpoints_por_vpc, "llaves_pendientes_borrado": llaves_pendientes_borrado,
    }


def contar(valor) -> int:
    if isinstance(valor, dict):
        return sum(len(v) for v in valor.values())
    return len(valor)


# Leftovers that are allowed after a teardown, by category. The bootstrap and the control stack are allowed only
# when they are kept (--con-control). A pending-deletion key is allowed with its date (free while pending: D, see
# resultados/base.md). The read-only role of activity 1 is registered as an exception (linea_base.md section 9).
def permitidos(con_control: bool, con_base: bool = False) -> dict:
    base = {
        "roles_iam": {"semana19-lectura"},
        "llaves_pendientes_borrado": None,  # any name; the date is in the name
    }
    if con_control:
        base.update({
            "stacks_cloudformation": {"semana19-control"},
            "presupuestos": {"semana19"},
            "acciones_presupuesto": {"semana19"},
            "politicas_iam_locales": {"semana19-limite", "semana19-congelar", "semana19-cfn-exec"},
            "roles_iam": {"semana19-lectura", "semana19-despliegue", "semana19-accion-presupuesto", "semana19-flow-logs"},
            # With the control kept, the tag search also finds the control's own resources: reported, not judged.
            "etiquetados_tagging_api": None,
        })
    if con_base:
        # Before the teardown only: the base stack is up on purpose, so its resources are listed as expected.
        # After the teardown this flag is not passed, and any leftover is reported as unexpected.
        base.update({
            "stacks_cloudformation": {"semana19-control", "semana19-base", "semana19-cdktoolkit"},
            "roles_iam": None, "lambdas": None, "vpcs": None, "subredes": None, "security_groups": None,
            "endpoints_vpc": None, "endpoints_por_vpc": None, "log_groups": None, "flow_logs": None,
            "llaves_kms_por_alias": None,
        })
    return base


def inventario(sesion, region: str, con_control: bool = False, con_base: bool = False) -> dict:
    resultado, no_medido = {}, []
    for nombre, fn in categorias(sesion, region).items():
        try:
            valor = fn()
            resultado[nombre] = {"conteo": contar(valor), "nombres": valor}
        except Exception as exc:  # noqa: BLE001 - recorded, never counted as zero
            no_medido.append({"categoria": nombre, "error": type(exc).__name__, "detalle": str(exc)[:120]})
    reglas = permitidos(con_control, con_base)
    esperados, inesperados = {}, {}
    for cat, datos in resultado.items():
        if not datos["nombres"]:
            continue
        if cat in reglas and reglas[cat] is None:
            esperados[cat] = datos["nombres"]
            continue
        if cat in reglas:
            ok = [n for n in datos["nombres"] if (n if isinstance(n, str) else str(n)) in reglas[cat]]
            fuera = [n for n in datos["nombres"] if n not in ok]
            if ok:
                esperados[cat] = ok
            if fuera:
                inesperados[cat] = fuera
        else:
            inesperados[cat] = datos["nombres"]
    quedan = "nada" if not inesperados and not no_medido else "revisar"
    total = sum(v["conteo"] for v in resultado.values())
    return {"fecha": date.today().isoformat(), "region": region, "con_control": con_control,
            "por_categoria": {k: v["conteo"] for k, v in resultado.items()}, "total": total,
            "esperados": esperados, "inesperados": inesperados,
            "no_medido": no_medido, "quedan": quedan}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--perfil", required=True, help="perfil de solo lectura (operador)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--con-control", action="store_true", help="el stack de control se queda (no fue --todo)")
    ap.add_argument("--con-base", action="store_true", help="antes del teardown: el stack base está arriba a propósito")
    a = ap.parse_args()
    import boto3
    sesion = boto3.Session(profile_name=a.perfil, region_name=a.region)
    informe = inventario(sesion, a.region, con_control=a.con_control, con_base=a.con_base)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0 if informe["quedan"] == "nada" else 1


if __name__ == "__main__":
    sys.exit(main())
