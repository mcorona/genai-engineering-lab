"""Week 15, activity 8: AgentCore infrastructure for the Strands agent. A dry run by default.

    python agentcore/infra.py inventario                     # what exists with the semana15 prefix ($0)
    python agentcore/infra.py crear                          # shows the plan without touching anything
    python agentcore/infra.py crear --confirmar              # budget, bucket, key provider, role and runtime
    python agentcore/infra.py probar-jwt --confirmar         # does AgentCore accept the local Keycloak as an authorizer?
    python agentcore/infra.py borrar --confirmar             # deletes everything except the budget
    python agentcore/infra.py borrar --confirmar --presupuesto   # the budget too (after reviewing the invoice)

Why boto3 and not the AgentCore CLI: the CLI deploys with CDK and leaves the CDK bootstrap in the account (a stack,
a bucket, an ECR repository and roles). Here each resource is created and deleted explicitly, with the `semana15` prefix, and
`inventario` checks that none is left.

The Anthropic key is read from the ANTHROPIC_API_KEY variable of whoever runs `crear` and handed only to AgentCore
Identity (an API key provider, stored in its token vault). It is not printed or written to disk.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REGION = os.environ.get("AWS_REGION", "us-east-1")
PREFIJO = "semana15"
RUNTIME = "semana15_legacybridge"          # runtime names: letters, digits and underscores
ROL = "semana15-agentcore-runtime"
PROVEEDOR = "semana15-anthropic"
PRESUPUESTO = "semana15-agentcore"
PRESUPUESTO_USD = "2"
CLAVE_ZIP = "agente/agente.zip"
ESTADO = AQUI / "estado.json"              # ids of what was created; not versioned (it carries the account id)
ETIQUETAS = {"proyecto": PREFIJO, "actividad": "agentcore"}
CICLO = {"idleRuntimeSessionTimeout": 60, "maxLifetime": 900}   # idle session 60 s and maximum lifetime 15 min: a billing cap
KEYCLOAK_LOCAL = "http://127.0.0.1:8180/realms/legacybridge/.well-known/openid-configuration"


def bucket(cuenta: str) -> str:
    return f"{PREFIJO}-agentcore-{cuenta}"


def confianza(cuenta: str, region: str = REGION) -> dict:
    """Only AgentCore in this account and region can assume the role (aws:SourceAccount and aws:SourceArn)."""
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": cuenta},
                      "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{cuenta}:*"}}}]}


def politica(cuenta: str, secreto_arn: str, region: str = REGION) -> dict:
    """The execution role's least privilege: its logs, its traces, its workload token, ITS key
    provider and ITS secret. No Bedrock (the model is the Anthropic API) and no ECR (a CodeZip package)."""
    ac = f"arn:aws:bedrock-agentcore:{region}:{cuenta}"
    directorio = [f"{ac}:workload-identity-directory/default",
                  f"{ac}:workload-identity-directory/default/workload-identity/{RUNTIME}-*"]
    grupo = f"arn:aws:logs:{region}:{cuenta}:log-group:/aws/bedrock-agentcore/runtimes/{RUNTIME}-*"
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "Registros", "Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:DescribeLogStreams",
                                                           "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": [grupo, f"{grupo}:log-stream:*"]},
        {"Sid": "RegistrosListar", "Effect": "Allow", "Action": ["logs:DescribeLogGroups"],
         "Resource": f"arn:aws:logs:{region}:{cuenta}:log-group:*"},
        {"Sid": "Trazas", "Effect": "Allow", "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords",
                                                        "xray:GetSamplingRules", "xray:GetSamplingTargets"],
         "Resource": "*"},
        {"Sid": "Metricas", "Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*",
         "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}}},
        {"Sid": "TokenDeCarga", "Effect": "Allow", "Action": ["bedrock-agentcore:GetWorkloadAccessToken",
                                                              "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                                                              "bedrock-agentcore:GetWorkloadAccessTokenForUserId"],
         "Resource": directorio},
        {"Sid": "LlaveDeAnthropic", "Effect": "Allow", "Action": ["bedrock-agentcore:GetResourceApiKey"],
         "Resource": directorio + [f"{ac}:token-vault/default", f"{ac}:token-vault/default/apikeycredentialprovider/{PROVEEDOR}",
                                   f"{ac}:token-vault/default/api-key/{PROVEEDOR}"]},
        {"Sid": "SecretoDeLaLlave", "Effect": "Allow", "Action": ["secretsmanager:GetSecretValue"], "Resource": secreto_arn},
        {"Sid": "Codigo", "Effect": "Allow", "Action": ["s3:GetObject"],
         "Resource": f"arn:aws:s3:::{bucket(cuenta)}/{CLAVE_ZIP}"},
    ]}


def definicion_runtime(cuenta: str, rol_arn: str, autorizador: dict | None = None, nombre: str = RUNTIME) -> dict:
    d = {"agentRuntimeName": nombre, "description": "Semana 15: agente LegacyBridge en Strands (actividad 8)",
         "agentRuntimeArtifact": {"codeConfiguration": {"code": {"s3": {"bucket": bucket(cuenta), "prefix": CLAVE_ZIP}},
                                                        "runtime": "PYTHON_3_13", "entryPoint": ["main.py"]}},
         "roleArn": rol_arn, "networkConfiguration": {"networkMode": "PUBLIC"},
         "protocolConfiguration": {"serverProtocol": "HTTP"}, "lifecycleConfiguration": dict(CICLO),
         "environmentVariables": {"PROVEEDOR_LLAVE": PROVEEDOR}, "tags": dict(ETIQUETAS)}
    if autorizador:
        d["authorizerConfiguration"] = autorizador
    return d


class Simulador:
    """A boto3 substitute in dry-run mode: prints each call it would make and does not touch AWS."""

    def __init__(self, cuenta="000000000000"):
        self.cuenta, self.llamadas = cuenta, []

    def client(self, servicio, **_):
        sim = self

        class C:
            def __getattr__(self, op):
                def f(**kw):
                    sim.llamadas.append((servicio, op, kw))
                    print(f"[dry run] {servicio}.{op}({', '.join(k for k in kw)})")
                    return {"agentRuntimeArn": f"arn:aws:bedrock-agentcore:{REGION}:{sim.cuenta}:runtime/{RUNTIME}-sim",
                            "agentRuntimeId": f"{RUNTIME}-sim", "status": "READY", "Role": {"Arn": "arn:sim:rol"},
                            "apiKeySecretArn": {"secretArn": "arn:sim:secreto"}, "credentialProviderArn": "arn:sim:prov"}
                return f
        return C()


def sesion(confirmar: bool):
    if not confirmar:
        return Simulador(), "000000000000"
    import boto3
    s = boto3.Session(region_name=REGION)
    return s, s.client("sts").get_caller_identity()["Account"]


def _escribir_estado(**kw):
    e = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    e.update(kw)
    ESTADO.write_text(json.dumps(e, indent=1, default=str) + "\n")
    return e


def crear(confirmar: bool, zip_ruta: Path) -> int:
    if confirmar and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is missing in this terminal (it is handed only to AgentCore Identity).")
        return 1
    if confirmar and not zip_ruta.exists():
        print(f"The package {zip_ruta} is missing: run python agentcore/empaquetar.py first")
        return 1
    correo = os.environ.get("ALERTA_CORREO") or subprocess.run(["git", "config", "user.email"], capture_output=True,
                                                               text=True).stdout.strip()
    if not correo:
        print("Set ALERTA_CORREO=<email> for the budget alerts")
        return 1
    s, cuenta = sesion(confirmar)
    t0 = time.time()
    # 1. A budget with alerts (AWS notifies; it does not stop the spending)
    bud = s.client("budgets", region_name="us-east-1")
    avisos = [("ACTUAL", 50), ("ACTUAL", 100), ("FORECASTED", 100)]
    try:
        bud.create_budget(AccountId=cuenta, Budget={"BudgetName": PRESUPUESTO, "BudgetLimit": {"Amount": PRESUPUESTO_USD,
                          "Unit": "USD"}, "TimeUnit": "MONTHLY", "BudgetType": "COST"},
                          NotificationsWithSubscribers=[{"Notification": {"NotificationType": t, "ComparisonOperator":
                                                         "GREATER_THAN", "Threshold": u, "ThresholdType": "PERCENTAGE"},
                                                         "Subscribers": [{"SubscriptionType": "EMAIL", "Address": correo}]}
                                                        for t, u in avisos])
        print(f"budget {PRESUPUESTO}: ${PRESUPUESTO_USD}/month, alerts at 50 % and 100 % actual and 100 % forecasted")
    except Exception as e:  # noqa: BLE001
        if "DuplicateRecord" not in str(e):
            raise
        print(f"budget {PRESUPUESTO}: already exists")
    # 2. A private bucket with the package
    s3, b = s.client("s3"), bucket(cuenta)
    try:
        s3.create_bucket(Bucket=b)
    except Exception as e:  # noqa: BLE001
        if "BucketAlreadyOwnedByYou" not in str(e):
            raise
    s3.put_public_access_block(Bucket=b, PublicAccessBlockConfiguration={k: True for k in (
        "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")})
    s3.put_bucket_tagging(Bucket=b, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in ETIQUETAS.items()]})
    if confirmar:
        s3.upload_file(str(zip_ruta), b, CLAVE_ZIP)
    else:
        s3.upload_file(Filename=str(zip_ruta), Bucket=b, Key=CLAVE_ZIP)
    print(f"bucket {b}: private, package at s3://{b}/{CLAVE_ZIP}")
    # 3. The Anthropic key, only in AgentCore Identity
    ctl = s.client("bedrock-agentcore-control")
    try:
        prov = ctl.create_api_key_credential_provider(name=PROVEEDOR, apiKey=os.environ.get("ANTHROPIC_API_KEY", "sim"),
                                                      tags=dict(ETIQUETAS))
    except Exception as e:  # noqa: BLE001
        if "already exists" not in str(e) and "Conflict" not in str(e):
            raise
        prov = ctl.get_api_key_credential_provider(name=PROVEEDOR)
    secreto = prov["apiKeySecretArn"]["secretArn"]
    print(f"AgentCore Identity: key provider {PROVEEDOR} (a secret managed by the service)")
    # 4. An execution role with least privilege
    iam = s.client("iam")
    try:
        rol_arn = iam.create_role(RoleName=ROL, AssumeRolePolicyDocument=json.dumps(confianza(cuenta)),
                                  Description="Semana 15: ejecución del agente en AgentCore Runtime",
                                  Tags=[{"Key": k, "Value": v} for k, v in ETIQUETAS.items()])["Role"]["Arn"]
    except Exception as e:  # noqa: BLE001
        if "EntityAlreadyExists" not in str(e):
            raise
        rol_arn = iam.get_role(RoleName=ROL)["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROL, PolicyName=f"{ROL}-permisos", PolicyDocument=json.dumps(politica(cuenta, secreto)))
    print(f"role {ROL}: trusted only by the account's AgentCore; least privilege")
    # 5. Runtime (the role takes a few seconds to propagate in IAM)
    for intento in range(12):
        try:
            r = ctl.create_agent_runtime(**definicion_runtime(cuenta, rol_arn))
            break
        except Exception as e:  # noqa: BLE001
            if "ConflictException" in type(e).__name__ or "already exists" in str(e):
                r = next(x for x in ctl.list_agent_runtimes()["agentRuntimes"] if x["agentRuntimeName"] == RUNTIME)
                break
            if intento == 11 or "role" not in str(e).lower():
                raise
            time.sleep(10)
    rid = r["agentRuntimeId"]
    estado = "?"
    for _ in range(60 if confirmar else 1):
        estado = ctl.get_agent_runtime(agentRuntimeId=rid)["status"]
        if estado in ("READY", "CREATE_FAILED", "UPDATE_FAILED"):
            break
        time.sleep(10)
    print(f"runtime {RUNTIME}: {estado} ({round(time.time() - t0)} s since the start)")
    if confirmar:
        _escribir_estado(cuenta=cuenta, region=REGION, runtime_id=rid, runtime_arn=r["agentRuntimeArn"], rol_arn=rol_arn,
                         bucket=b, proveedor=PROVEEDOR, creado=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         despliegue_s=round(time.time() - t0))
    return 0 if estado == "READY" else 1


def probar_jwt(confirmar: bool) -> int:
    """Can the Runtime validate tokens from our Keycloak? A test runtime is created with a JWT authorizer that
    points to the local OIDC discovery. If AWS accepts it, it is deleted immediately."""
    s, cuenta = sesion(confirmar)
    ctl = s.client("bedrock-agentcore-control")
    rol_arn = s.client("iam").get_role(RoleName=ROL)["Role"]["Arn"]
    aut = {"customJWTAuthorizer": {"discoveryUrl": KEYCLOAK_LOCAL, "allowedAudience": ["http://127.0.0.1:8014/mcp"]}}
    nombre = f"{RUNTIME}_jwt"
    try:
        r = ctl.create_agent_runtime(**definicion_runtime(cuenta, rol_arn, aut, nombre))
    except Exception as e:  # noqa: BLE001
        res = {"aceptado": False, "error": f"{type(e).__name__}: {e}"[:500]}
    else:
        res = {"aceptado": True, "nota": "AWS aceptó la URL al crear; se borra de inmediato"}
        for _ in range(30 if confirmar else 1):
            st = ctl.get_agent_runtime(agentRuntimeId=r["agentRuntimeId"])["status"]
            res["estado"] = st
            if st not in ("CREATING", "UPDATING"):
                break
            time.sleep(5)
        ctl.delete_agent_runtime(agentRuntimeId=r["agentRuntimeId"])
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if confirmar:
        _escribir_estado(prueba_jwt=res)
    return 0


def inventario(confirmar: bool = True, con_presupuesto: bool = True) -> dict:
    """Everything that exists with the week's prefix. Read-only."""
    import boto3
    s = boto3.Session(region_name=REGION)
    cuenta = s.client("sts").get_caller_identity()["Account"]
    ctl = s.client("bedrock-agentcore-control")
    inv = {
        "runtimes": [x["agentRuntimeName"] for x in ctl.list_agent_runtimes().get("agentRuntimes", [])
                     if x["agentRuntimeName"].startswith(PREFIJO)],
        "identidades_de_carga": [x["name"] for x in ctl.list_workload_identities().get("workloadIdentities", [])
                                 if x["name"].startswith(PREFIJO)],
        "proveedores_de_llave": [x["name"] for x in ctl.list_api_key_credential_providers().get("credentialProviders", [])
                                 if x["name"].startswith(PREFIJO)],
        "secretos": [x["Name"] for pag in s.client("secretsmanager").get_paginator("list_secrets").paginate()
                     for x in pag.get("SecretList", []) if PREFIJO in x["Name"]],   # Identity's one does not start with the prefix
        "roles": [x["RoleName"] for x in s.client("iam").list_roles(MaxItems=1000)["Roles"]
                  if x["RoleName"].startswith(PREFIJO)],
        "buckets": [x["Name"] for x in s.client("s3").list_buckets()["Buckets"] if x["Name"].startswith(PREFIJO)],
        "grupos_de_registros": [x["logGroupName"] for x in s.client("logs").describe_log_groups(
            logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/").get("logGroups", []) if PREFIJO in x["logGroupName"]],
        "stacks": [x["StackName"] for x in s.client("cloudformation").list_stacks(StackStatusFilter=[
            "CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE", "CREATE_IN_PROGRESS", "DELETE_FAILED"])
            ["StackSummaries"] if PREFIJO in x["StackName"].lower()],
        "repositorios_ecr": [x["repositoryName"] for x in s.client("ecr").describe_repositories().get("repositories", [])
                             if PREFIJO in x["repositoryName"] or "agentcore" in x["repositoryName"]],
    }
    if con_presupuesto:
        try:
            inv["presupuestos"] = [x["BudgetName"] for x in s.client("budgets", region_name="us-east-1").describe_budgets(
                AccountId=cuenta).get("Budgets", []) if x["BudgetName"].startswith(PREFIJO)]
        except Exception:  # noqa: BLE001  without budgets the API answers NotFound
            inv["presupuestos"] = []
    return inv


def borrar(confirmar: bool, presupuesto: bool) -> int:
    s, cuenta = sesion(confirmar)
    ctl = s.client("bedrock-agentcore-control")
    if confirmar:
        runtimes = [x for x in ctl.list_agent_runtimes().get("agentRuntimes", []) if x["agentRuntimeName"].startswith(PREFIJO)]
    else:
        runtimes = [{"agentRuntimeId": f"{RUNTIME}-sim", "agentRuntimeName": RUNTIME}]
    for r in runtimes:
        ctl.delete_agent_runtime(agentRuntimeId=r["agentRuntimeId"])
        print(f"runtime {r['agentRuntimeName']}: deletion requested")
    if confirmar:
        for _ in range(60):
            if not [x for x in ctl.list_agent_runtimes().get("agentRuntimes", []) if x["agentRuntimeName"].startswith(PREFIJO)]:
                break
            time.sleep(5)
        for w in ctl.list_workload_identities().get("workloadIdentities", []):
            if w["name"].startswith(PREFIJO):
                try:
                    ctl.delete_workload_identity(name=w["name"])
                    print(f"workload identity {w['name']}: deleted")
                except Exception as e:  # noqa: BLE001
                    print(f"workload identity {w['name']}: {type(e).__name__} (managed by the runtime)")
    # Deletion is idempotent in AWS (it answers fine even if the provider does not exist): it is queried first to report
    # the truth. The first run with --presupuesto said "deleted" for a provider that no longer existed.
    existe = not confirmar or PROVEEDOR in [x["name"] for x in ctl.list_api_key_credential_providers()
                                            .get("credentialProviders", [])]
    if existe:
        ctl.delete_api_key_credential_provider(name=PROVEEDOR)
        print(f"key provider {PROVEEDOR}: deleted (with its secret)")
    else:
        print(f"key provider {PROVEEDOR}: did not exist")
    iam = s.client("iam")
    try:
        iam.delete_role_policy(RoleName=ROL, PolicyName=f"{ROL}-permisos")
        iam.delete_role(RoleName=ROL)
        print(f"role {ROL}: deleted")
    except Exception as e:  # noqa: BLE001
        if "NoSuchEntity" not in str(e):
            raise
    s3, b = s.client("s3"), bucket(cuenta)
    try:
        if confirmar:
            for pag in s3.get_paginator("list_object_versions").paginate(Bucket=b):
                objs = [{"Key": o["Key"], "VersionId": o["VersionId"]} for o in pag.get("Versions", []) + pag.get("DeleteMarkers", [])]
                if objs:
                    s3.delete_objects(Bucket=b, Delete={"Objects": objs})
        else:
            s3.delete_objects(Bucket=b, Delete={"Objects": [{"Key": CLAVE_ZIP}]})
        s3.delete_bucket(Bucket=b)
        print(f"bucket {b}: emptied and deleted")
    except Exception as e:  # noqa: BLE001
        if "NoSuchBucket" not in str(e):
            raise
    logs = s.client("logs")
    grupos = [g["logGroupName"] for g in logs.describe_log_groups(logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/")
              .get("logGroups", []) if PREFIJO in g["logGroupName"]] if confirmar else [f"/aws/bedrock-agentcore/runtimes/{RUNTIME}-sim-DEFAULT"]
    for g in grupos:
        logs.delete_log_group(logGroupName=g)
        print(f"logs {g}: deleted")
    if presupuesto:
        try:
            s.client("budgets", region_name="us-east-1").delete_budget(AccountId=cuenta, BudgetName=PRESUPUESTO)
            print(f"budget {PRESUPUESTO}: deleted")
        except Exception as e:  # noqa: BLE001
            if "NotFound" not in str(e):
                raise
    if not confirmar:
        return 0
    inv = inventario(con_presupuesto=presupuesto)
    quedan = {k: v for k, v in inv.items() if v}
    print(json.dumps({"quedan": quedan or "nada"}, ensure_ascii=False, indent=1))
    _escribir_estado(borrado=time.strftime("%Y-%m-%dT%H:%M:%S%z"), inventario_final=inv)
    return 1 if quedan else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["crear", "borrar", "inventario", "probar-jwt"])
    ap.add_argument("--confirmar", action="store_true", help="without this, it only shows what it would do")
    ap.add_argument("--presupuesto", action="store_true", help="also delete the budget")
    ap.add_argument("--zip", type=Path, default=AQUI / "build" / "agente.zip")
    a = ap.parse_args(argv)
    if a.accion == "inventario":
        inv = inventario()
        print(json.dumps(inv, ensure_ascii=False, indent=1))
        return 0
    if a.accion == "crear":
        return crear(a.confirmar, a.zip)
    if a.accion == "probar-jwt":
        return probar_jwt(a.confirmar)
    return borrar(a.confirmar, a.presupuesto)


if __name__ == "__main__":
    sys.exit(main())
