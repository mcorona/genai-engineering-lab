"""Semana 15, actividad 8: infraestructura de AgentCore para el agente Strands. Simulación por defecto.

    python agentcore/infra.py inventario                     # qué existe con el prefijo semana15 ($0)
    python agentcore/infra.py crear                          # muestra el plan sin tocar nada
    python agentcore/infra.py crear --confirmar              # presupuesto, bucket, proveedor de llave, rol y runtime
    python agentcore/infra.py probar-jwt --confirmar         # ¿acepta AgentCore el Keycloak local como autorizador?
    python agentcore/infra.py borrar --confirmar             # borra todo menos el presupuesto
    python agentcore/infra.py borrar --confirmar --presupuesto   # también el presupuesto (después de revisar la factura)

Por qué boto3 y no la CLI de AgentCore: la CLI despliega con CDK y deja el bootstrap de CDK en la cuenta (stack,
bucket, repositorio ECR y roles). Aquí cada recurso se crea y se borra explícitamente, con el prefijo `semana15`, y
`inventario` comprueba que no queda ninguno.

La llave de Anthropic se lee de la variable ANTHROPIC_API_KEY de quien corre `crear` y se entrega solo a AgentCore
Identity (proveedor de llave de API, guardado en su bóveda de tokens). No se imprime ni se escribe en disco.
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
RUNTIME = "semana15_legacybridge"          # nombres de runtime: letras, números y guion bajo
ROL = "semana15-agentcore-runtime"
PROVEEDOR = "semana15-anthropic"
PRESUPUESTO = "semana15-agentcore"
PRESUPUESTO_USD = "2"
CLAVE_ZIP = "agente/agente.zip"
ESTADO = AQUI / "estado.json"              # ids de lo creado; no se versiona (lleva el id de la cuenta)
ETIQUETAS = {"proyecto": PREFIJO, "actividad": "agentcore"}
CICLO = {"idleRuntimeSessionTimeout": 60, "maxLifetime": 900}   # sesión ociosa 60 s y vida máxima 15 min: tope de cobro
KEYCLOAK_LOCAL = "http://127.0.0.1:8180/realms/legacybridge/.well-known/openid-configuration"


def bucket(cuenta: str) -> str:
    return f"{PREFIJO}-agentcore-{cuenta}"


def confianza(cuenta: str, region: str = REGION) -> dict:
    """Solo AgentCore de esta cuenta y región puede asumir el rol (aws:SourceAccount y aws:SourceArn)."""
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": cuenta},
                      "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{cuenta}:*"}}}]}


def politica(cuenta: str, secreto_arn: str, region: str = REGION) -> dict:
    """Permisos mínimos del rol de ejecución: sus registros, sus trazas, su token de carga de trabajo, SU proveedor de
    llave y SU secreto. Sin Bedrock (el modelo es la API de Anthropic) y sin ECR (paquete CodeZip)."""
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
    """Sustituto de boto3 en modo simulación: imprime cada llamada que haría y no toca AWS."""

    def __init__(self, cuenta="000000000000"):
        self.cuenta, self.llamadas = cuenta, []

    def client(self, servicio, **_):
        sim = self

        class C:
            def __getattr__(self, op):
                def f(**kw):
                    sim.llamadas.append((servicio, op, kw))
                    print(f"[simulación] {servicio}.{op}({', '.join(k for k in kw)})")
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
        print("Falta ANTHROPIC_API_KEY en esta terminal (se entrega solo a AgentCore Identity).")
        return 1
    if confirmar and not zip_ruta.exists():
        print(f"Falta el paquete {zip_ruta}: corre antes python agentcore/empaquetar.py")
        return 1
    correo = os.environ.get("ALERTA_CORREO") or subprocess.run(["git", "config", "user.email"], capture_output=True,
                                                               text=True).stdout.strip()
    if not correo:
        print("Define ALERTA_CORREO=<correo> para las alertas del presupuesto")
        return 1
    s, cuenta = sesion(confirmar)
    t0 = time.time()
    # 1. Presupuesto con alertas (AWS avisa; no corta el gasto)
    bud = s.client("budgets", region_name="us-east-1")
    avisos = [("ACTUAL", 50), ("ACTUAL", 100), ("FORECASTED", 100)]
    try:
        bud.create_budget(AccountId=cuenta, Budget={"BudgetName": PRESUPUESTO, "BudgetLimit": {"Amount": PRESUPUESTO_USD,
                          "Unit": "USD"}, "TimeUnit": "MONTHLY", "BudgetType": "COST"},
                          NotificationsWithSubscribers=[{"Notification": {"NotificationType": t, "ComparisonOperator":
                                                         "GREATER_THAN", "Threshold": u, "ThresholdType": "PERCENTAGE"},
                                                         "Subscribers": [{"SubscriptionType": "EMAIL", "Address": correo}]}
                                                        for t, u in avisos])
        print(f"presupuesto {PRESUPUESTO}: ${PRESUPUESTO_USD}/mes, alertas 50 % y 100 % real y 100 % pronosticado")
    except Exception as e:  # noqa: BLE001
        if "DuplicateRecord" not in str(e):
            raise
        print(f"presupuesto {PRESUPUESTO}: ya existe")
    # 2. Bucket privado con el paquete
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
    print(f"bucket {b}: privado, paquete en s3://{b}/{CLAVE_ZIP}")
    # 3. La llave de Anthropic, solo en AgentCore Identity
    ctl = s.client("bedrock-agentcore-control")
    try:
        prov = ctl.create_api_key_credential_provider(name=PROVEEDOR, apiKey=os.environ.get("ANTHROPIC_API_KEY", "sim"),
                                                      tags=dict(ETIQUETAS))
    except Exception as e:  # noqa: BLE001
        if "already exists" not in str(e) and "Conflict" not in str(e):
            raise
        prov = ctl.get_api_key_credential_provider(name=PROVEEDOR)
    secreto = prov["apiKeySecretArn"]["secretArn"]
    print(f"AgentCore Identity: proveedor de llave {PROVEEDOR} (secreto administrado por el servicio)")
    # 4. Rol de ejecución con permisos mínimos
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
    print(f"rol {ROL}: confianza solo de AgentCore de la cuenta; permisos mínimos")
    # 5. Runtime (el rol tarda unos segundos en propagarse en IAM)
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
    print(f"runtime {RUNTIME}: {estado} ({round(time.time() - t0)} s desde el inicio)")
    if confirmar:
        _escribir_estado(cuenta=cuenta, region=REGION, runtime_id=rid, runtime_arn=r["agentRuntimeArn"], rol_arn=rol_arn,
                         bucket=b, proveedor=PROVEEDOR, creado=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         despliegue_s=round(time.time() - t0))
    return 0 if estado == "READY" else 1


def probar_jwt(confirmar: bool) -> int:
    """¿Puede el Runtime validar tokens de nuestro Keycloak? Se crea un runtime de prueba con un autorizador JWT que
    apunta al descubrimiento OIDC local. Si AWS lo acepta, se borra de inmediato."""
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
    """Todo lo que existe con el prefijo de la semana. Solo lectura."""
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
                     for x in pag.get("SecretList", []) if PREFIJO in x["Name"]],   # el de Identity no empieza con el prefijo
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
        except Exception:  # noqa: BLE001  sin presupuestos la API responde NotFound
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
        print(f"runtime {r['agentRuntimeName']}: borrado solicitado")
    if confirmar:
        for _ in range(60):
            if not [x for x in ctl.list_agent_runtimes().get("agentRuntimes", []) if x["agentRuntimeName"].startswith(PREFIJO)]:
                break
            time.sleep(5)
        for w in ctl.list_workload_identities().get("workloadIdentities", []):
            if w["name"].startswith(PREFIJO):
                try:
                    ctl.delete_workload_identity(name=w["name"])
                    print(f"identidad de carga {w['name']}: borrada")
                except Exception as e:  # noqa: BLE001
                    print(f"identidad de carga {w['name']}: {type(e).__name__} (la administra el runtime)")
    # El borrado es idempotente en AWS (responde bien aunque el proveedor no exista): se consulta antes para reportar
    # la verdad. Primera corrida con --presupuesto: decía "borrado" de un proveedor que ya no existía.
    existe = not confirmar or PROVEEDOR in [x["name"] for x in ctl.list_api_key_credential_providers()
                                            .get("credentialProviders", [])]
    if existe:
        ctl.delete_api_key_credential_provider(name=PROVEEDOR)
        print(f"proveedor de llave {PROVEEDOR}: borrado (y su secreto)")
    else:
        print(f"proveedor de llave {PROVEEDOR}: no existía")
    iam = s.client("iam")
    try:
        iam.delete_role_policy(RoleName=ROL, PolicyName=f"{ROL}-permisos")
        iam.delete_role(RoleName=ROL)
        print(f"rol {ROL}: borrado")
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
        print(f"bucket {b}: vaciado y borrado")
    except Exception as e:  # noqa: BLE001
        if "NoSuchBucket" not in str(e):
            raise
    logs = s.client("logs")
    grupos = [g["logGroupName"] for g in logs.describe_log_groups(logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/")
              .get("logGroups", []) if PREFIJO in g["logGroupName"]] if confirmar else [f"/aws/bedrock-agentcore/runtimes/{RUNTIME}-sim-DEFAULT"]
    for g in grupos:
        logs.delete_log_group(logGroupName=g)
        print(f"registros {g}: borrados")
    if presupuesto:
        try:
            s.client("budgets", region_name="us-east-1").delete_budget(AccountId=cuenta, BudgetName=PRESUPUESTO)
            print(f"presupuesto {PRESUPUESTO}: borrado")
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
    ap.add_argument("--confirmar", action="store_true", help="sin esto solo se muestra lo que se haría")
    ap.add_argument("--presupuesto", action="store_true", help="borrar también el presupuesto")
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
