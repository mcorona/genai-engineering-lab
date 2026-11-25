"""Week 19, activity 9, step 2: read-only checks of the deployed stack.

    uv run --group semana19 python semana-19/seguridad/verificar_desplegado.py [--perfil semana19-lectura] \
        [--desde 2026-11-22T10:00:00Z] [--salida semana-19/resultados/seguridad/verificacion.json]

It changes nothing. Every AWS call goes through `SoloLectura`, which refuses any operation that is not Describe*,
Get*, List* or LookupEvents. It runs with the read-only role semana19-lectura (ReadOnlyAccess). A call the role cannot
make is recorded under `sin_permiso` with its operation, and the check that needed it reports `sin_permiso`. A missing
call is never treated as passing.

Where the resources come from:
- the CloudFormation stacks `semana19-*`, every resource with its physical id;
- the log groups Lambda creates outside CloudFormation (`/aws/lambda/semana19-*`, activity 8).

The six checks each report `ok`, `conocido` (only known, documented exceptions), `hallazgo` or `sin_permiso`.
  1. cifrado: every bucket, log group, RDS instance, state machine, DynamoDB table, guardrail, Knowledge Base (its
     vector bucket and its data source), secret, prompt, gateway, queue or topic uses the project's customer managed
     key (alias/semana19). So does every Lambda with environment variables. Anything on another key is listed with
     its key. A known exception (CONOCIDOS and GRUPOS_CONOCIDOS, finding H10 of seguridad/threat_model.md) is
     `conocido`; any other is `hallazgo`.
  2. publico: nothing is public except the HTTP API.
     - Buckets: Block Public Access is all on, the policy is not public, and no Allow has Principal "*" without a
       condition.
     - RDS has PubliclyAccessible=false. Lambdas have no function URL and no open resource policy.
     - The key policy and the secret's resource policy are not open.
     - Every HTTP API route has an authorizer. The AgentCore gateway has an inbound authorizer.
  3. rds_sin_ip_publica: PubliclyAccessible=false, and the RDS network interfaces carry no public IP.
  4. red: the subnets of the VPC Lambdas and of RDS have no 0.0.0.0/0 or ::/0 route. The VPC has no internet gateway
     and no NAT gateway. No security group of the VPC admits 0.0.0.0/0 or ::/0.
  5. endpoints: every VPC endpoint has a policy, and each Allow is limited to this account (`aws:PrincipalAccount`).
     Whether it also limits `aws:ResourceAccount` is reported (finding H12).
  6. cloudtrail: LookupEvents (Event history: 90 days of management events, free) for bedrock.amazonaws.com since
     `--desde`. Every runtime call must come from an expected role.
     - Management events, so visible here: Converse, ConverseStream, InvokeModel, InvokeModelWithResponseStream.
     - Data events, which need a trail (finding H11): ApplyGuardrail, Retrieve, RetrieveAndGenerate, InvokeAgent and
       AgentCore InvokeGateway. They are listed as not visible; no trail is created.

The output is redacted with the common function (`comun/redaccion.py`): the account in ARNs and the account ID become
<account>.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.exceptions import ClientError

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))
from comun.redaccion import redactar  # noqa: E402

SALIDA = S19 / "resultados" / "seguridad" / "verificacion.json"
REGION = "us-east-1"
PREFIJO = "semana19"
ALIAS = "alias/semana19"
FUENTE_BEDROCK = "bedrock.amazonaws.com"

# Known resources on another key: finding H10 of seguridad/threat_model.md, open. They are listed, never hidden.
CONOCIDOS = {
    "AWS::StepFunctions::StateMachine": "H10: no EncryptionConfiguration, so Step Functions uses an AWS owned key. "
                                        "Its log group is on the CMK.",
    "AWS::S3Vectors::VectorBucket": "H10: no encryption configuration, so S3 Vectors uses SSE-S3. It cannot be "
                                    "changed after the bucket is created.",
    "AWS::Bedrock::KnowledgeBase": "H10: the Knowledge Base stores its vectors in the vector bucket above (SSE-S3).",
    "AWS::Bedrock::DataSource": "H10: no ServerSideEncryptionConfiguration, so the transient ingestion data uses an "
                                "AWS owned key.",
    "AWS::Lambda::Function": "H10: environment variables (resource names and ids, no secrets) under the AWS managed "
                             "key aws/lambda.",
}
# Log groups the Lambda runtime creates for the two functions without a log group in CloudFormation (H10). Any other
# log group without the key is a finding.
GRUPOS_CONOCIDOS = {
    r"^/aws/lambda/semana19-datos-Cargador": "H10: the loader has no log group in CloudFormation; the Lambda runtime "
                                             "created this one without a key.",
    r"^/aws/lambda/semana19-base-CustomVpcRestrictDefault": "H10: the CDK custom resource that restricts the default "
                                                            "security group has no log group in CloudFormation; the "
                                                            "Lambda runtime created this one without a key.",
}
# Roles that may call the Bedrock runtime (logical id prefix in the stacks, and why).
ROLES_ESPERADOS = {
    "FuncionAgenteServiceRole": "the agent (Converse, Haiku 4.5 profile)",
    "RolKb": "the Knowledge Base ingestion (InvokeModel, Titan Text Embeddings V2)",
    "RolJuez": "the activity 8 judge (InvokeModel)",
}
RUNTIME = {"Converse", "ConverseStream", "InvokeModel", "InvokeModelWithResponseStream"}
EVENTOS_DE_DATOS = {
    "ApplyGuardrail": "AWS::Bedrock::Guardrail",
    "Retrieve": "AWS::Bedrock::KnowledgeBase",
    "RetrieveAndGenerate": "AWS::Bedrock::KnowledgeBase",
    "InvokeAgent": "AWS::Bedrock::AgentAlias",
    "InvokeGateway": "AWS::BedrockAgentCore::Gateway",
}
DENEGADO = {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "UnauthorizedException",
            "AuthorizationError", "AuthorizationErrorException"}
ABIERTAS = ("0.0.0.0/0", "::/0")
ORDEN = ["ok", "conocido", "sin_eventos", "sin_permiso", "hallazgo"]


# ---------- read-only access ----------

PERMITIDAS = re.compile(r"^(describe|get|list|lookup)_")


class SoloLectura:
    """A boto3 client that only lets read operations through."""

    def __init__(self, cliente):
        self._c = cliente

    def __getattr__(self, nombre):
        if nombre in ("meta", "exceptions", "can_paginate") or PERMITIDAS.match(nombre):
            return getattr(self._c, nombre)
        raise PermissionError(f"verificar_desplegado is read-only: {nombre} refused")

    def get_paginator(self, operacion):
        if not PERMITIDAS.match(operacion):
            raise PermissionError(f"verificar_desplegado is read-only: {operacion} refused")
        return self._c.get_paginator(operacion)


AUSENTE = object()   # the resource has no such configuration (no bucket policy, no Lambda policy, ...)


class Llamadas:
    """Read calls with one error policy: an expected 'not found' is AUSENTE, a denied call is recorded and is None."""

    def __init__(self, sesion=None, clientes: dict | None = None):
        self._sesion, self._clientes = sesion, dict(clientes or {})
        self.sin_permiso: list[str] = []

    def cliente(self, servicio: str) -> SoloLectura:
        if servicio not in self._clientes:
            self._clientes[servicio] = self._sesion.client(servicio, region_name=REGION)
        c = self._clientes[servicio]
        return c if isinstance(c, SoloLectura) else SoloLectura(c)

    def _denegada(self, servicio: str, operacion: str) -> None:
        c = self.cliente(servicio)
        nombre = c.meta.method_to_api_mapping.get(operacion, operacion)
        accion = f"{c.meta.service_model.signing_name}:{nombre}"
        if accion not in self.sin_permiso:
            self.sin_permiso.append(accion)

    def __call__(self, servicio: str, operacion: str, ausente=(), **kw):
        try:
            return getattr(self.cliente(servicio), operacion)(**kw)
        except ClientError as e:
            codigo = e.response.get("Error", {}).get("Code", "")
            if codigo in ausente:
                return AUSENTE
            if codigo in DENEGADO:
                self._denegada(servicio, operacion)
                return None
            raise

    def paginar(self, servicio: str, operacion: str, clave: str, **kw) -> list | None:
        try:
            return [x for p in self.cliente(servicio).get_paginator(operacion).paginate(**kw) for x in p.get(clave, [])]
        except ClientError as e:
            if e.response.get("Error", {}).get("Code", "") in DENEGADO:
                self._denegada(servicio, operacion)
                return None
            raise


# ---------- policy helpers ----------

def _doc(x):
    if x is None or x is AUSENTE:
        return None
    return json.loads(x) if isinstance(x, str) else x


def _declaraciones(doc) -> list[dict]:
    doc = _doc(doc)
    if not doc:
        return []
    s = doc.get("Statement", [])
    return s if isinstance(s, list) else [s]


def _principal_abierto(p) -> bool:
    if p == "*":
        return True
    if isinstance(p, dict):
        v = p.get("AWS")
        return "*" in (v if isinstance(v, list) else [v])
    return False


def abiertas(doc) -> list[dict]:
    """Allow statements with Principal "*" and no condition."""
    return [s for s in _declaraciones(doc)
            if s.get("Effect") == "Allow" and _principal_abierto(s.get("Principal")) and not s.get("Condition")]


def _valores(condicion: dict, clave: str) -> list[str]:
    for op, pares in (condicion or {}).items():
        if op in ("StringEquals", "ForAllValues:StringEquals"):
            for k, v in pares.items():
                if k.lower() == clave.lower():
                    return v if isinstance(v, list) else [v]
    return []


# ---------- collection ----------

def recursos_de_stacks(ll: Llamadas) -> list[dict] | None:
    pilas = ll.paginar("cloudformation", "list_stacks", "StackSummaries")
    if pilas is None:
        return None
    out = []
    for s in pilas:
        if not s["StackName"].startswith(PREFIJO) or s["StackStatus"] == "DELETE_COMPLETE":
            continue
        for r in ll.paginar("cloudformation", "list_stack_resources", "StackResourceSummaries",
                            StackName=s["StackName"]) or []:
            if r.get("PhysicalResourceId"):
                out.append({"stack": s["StackName"], "logico": r["LogicalResourceId"], "tipo": r["ResourceType"],
                            "fisico": r["PhysicalResourceId"]})
    return out


def _de_tipo(recursos, *tipos):
    return [r for r in recursos if r["tipo"] in tipos]


def _llave(tipo, ident, valor, etiqueta_sin_llave):
    return {"tipo": tipo, "id": ident, "llave": valor or etiqueta_sin_llave}


def cifrado_de_bucket(ll, nombre):
    r = ll("s3", "get_bucket_encryption", ausente=("ServerSideEncryptionConfigurationNotFoundError",), Bucket=nombre)
    if r is None:
        return None
    if r is AUSENTE:
        return _llave("AWS::S3::Bucket", nombre, None, "none")
    regla = r["ServerSideEncryptionConfiguration"]["Rules"][0]["ApplyServerSideEncryptionByDefault"]
    if regla.get("SSEAlgorithm") == "AES256":
        return _llave("AWS::S3::Bucket", nombre, None, "SSE-S3")
    return _llave("AWS::S3::Bucket", nombre, regla.get("KMSMasterKeyID"), "aws/s3 (AWS managed)")


def publico_de_bucket(ll, nombre):
    bpa = ll("s3", "get_public_access_block", ausente=("NoSuchPublicAccessBlockConfiguration",), Bucket=nombre)
    pol = ll("s3", "get_bucket_policy", ausente=("NoSuchBucketPolicy",), Bucket=nombre)
    est = ll("s3", "get_bucket_policy_status", ausente=("NoSuchBucketPolicy",), Bucket=nombre)
    return {"id": nombre,
            "bloqueo_publico": None if bpa is None else ({} if bpa is AUSENTE else bpa["PublicAccessBlockConfiguration"]),
            "politica": None if pol is None or pol is AUSENTE else pol["Policy"],
            "es_publico": None if est is None else (False if est is AUSENTE else est["PolicyStatus"]["IsPublic"]),
            "leido": None not in (bpa, pol, est)}


def recolectar(ll: Llamadas, cuenta: str, desde: datetime) -> dict:
    e = {"cuenta": cuenta, "cifrado": [], "buckets": [], "rds": [], "lambdas": [], "politicas": [], "rutas_api": [],
         "gateways": [], "subredes": {}, "vpcs": [], "igw": [], "nat": [], "grupos": [], "endpoints": [],
         "interfaces_rds": [], "cloudtrail": None, "roles_esperados": {}}
    recursos = recursos_de_stacks(ll)
    if recursos is None:
        e["recursos"] = None
        return e
    e["recursos"] = Counter(r["tipo"] for r in recursos)

    k = ll("kms", "describe_key", KeyId=ALIAS)
    e["llave"] = None if k is None else {"arn": k["KeyMetadata"]["Arn"], "id": k["KeyMetadata"]["KeyId"]}
    if k is not None:
        pol = ll("kms", "get_key_policy", KeyId=k["KeyMetadata"]["KeyId"], PolicyName="default")
        if pol is not None:
            e["politicas"].append({"recurso": ALIAS, "politica": pol["Policy"]})

    for r in _de_tipo(recursos, "AWS::S3::Bucket"):
        c = cifrado_de_bucket(ll, r["fisico"])
        if c:
            e["cifrado"].append(c)
        e["buckets"].append(publico_de_bucket(ll, r["fisico"]))

    grupos_logs = {r["fisico"] for r in _de_tipo(recursos, "AWS::Logs::LogGroup")}
    implicitos = ll.paginar("logs", "describe_log_groups", "logGroups", logGroupNamePrefix=f"/aws/lambda/{PREFIJO}-")
    vistos = {g["logGroupName"]: g for g in implicitos or []}
    for nombre in sorted(grupos_logs - set(vistos)):
        for g in ll.paginar("logs", "describe_log_groups", "logGroups", logGroupNamePrefix=nombre) or []:
            if g["logGroupName"] == nombre:
                vistos[nombre] = g
    for nombre, g in sorted(vistos.items()):
        e["cifrado"].append(_llave("AWS::Logs::LogGroup", nombre, g.get("kmsKeyId"), "CloudWatch Logs default"))

    for r in _de_tipo(recursos, "AWS::RDS::DBInstance"):
        d = ll("rds", "describe_db_instances", DBInstanceIdentifier=r["fisico"])
        if d is None:
            continue
        i = d["DBInstances"][0]
        e["cifrado"].append(_llave("AWS::RDS::DBInstance", r["fisico"], i.get("KmsKeyId") if i.get("StorageEncrypted")
                                   else None, "not encrypted"))
        e["rds"].append({"id": r["fisico"], "publica": i.get("PubliclyAccessible"), "vpc": i["DBSubnetGroup"]["VpcId"],
                         "subredes": [s["SubnetIdentifier"] for s in i["DBSubnetGroup"]["Subnets"]]})

    for r in _de_tipo(recursos, "AWS::StepFunctions::StateMachine"):
        d = ll("stepfunctions", "describe_state_machine", stateMachineArn=r["fisico"])
        if d is not None:
            ec = d.get("encryptionConfiguration") or {}
            valor = ec.get("kmsKeyId") if ec.get("type") == "CUSTOMER_MANAGED_KMS_KEY" else None
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], valor, "AWS owned key"))

    for r in _de_tipo(recursos, "AWS::DynamoDB::Table"):
        d = ll("dynamodb", "describe_table", TableName=r["fisico"])
        if d is not None:
            sse = d["Table"].get("SSEDescription") or {}
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], sse.get("KMSMasterKeyArn"),
                                       "AWS owned key" if not sse else "aws/dynamodb (AWS managed)"))

    for r in [r for r in recursos if r["logico"] == "Guardrail" and r["tipo"].startswith(("Custom::", "AWS::CloudFormation"))]:
        d = ll("bedrock", "get_guardrail", guardrailIdentifier=r["fisico"])
        if d is not None:
            e["cifrado"].append(_llave("Guardrail", r["fisico"], d.get("kmsKeyArn"), "AWS owned key"))

    buckets_vectores = {r["fisico"] for r in _de_tipo(recursos, "AWS::S3Vectors::VectorBucket")}
    for r in _de_tipo(recursos, "AWS::Bedrock::KnowledgeBase"):
        d = ll("bedrock-agent", "get_knowledge_base", knowledgeBaseId=r["fisico"].split("|")[0])
        if d is None:
            continue
        vb = ((d["knowledgeBase"].get("storageConfiguration") or {}).get("s3VectorsConfiguration") or {})
        arn_vb = vb.get("vectorBucketArn")
        if arn_vb:
            buckets_vectores = {b for b in buckets_vectores if b not in arn_vb} | {arn_vb}
        e["cifrado"].append({"tipo": r["tipo"], "id": r["fisico"].split("|")[0], "llave": f"vector bucket {arn_vb}",
                             "via": arn_vb})
        for ds in ll.paginar("bedrock-agent", "list_data_sources", "dataSourceSummaries",
                             knowledgeBaseId=r["fisico"].split("|")[0]) or []:
            dd = ll("bedrock-agent", "get_data_source", knowledgeBaseId=r["fisico"].split("|")[0],
                    dataSourceId=ds["dataSourceId"])
            if dd is not None:
                sse = dd["dataSource"].get("serverSideEncryptionConfiguration") or {}
                e["cifrado"].append(_llave("AWS::Bedrock::DataSource", ds["dataSourceId"], sse.get("kmsKeyArn"),
                                           "AWS owned key"))
    for b in sorted(buckets_vectores):
        d = ll("s3vectors", "get_vector_bucket", **({"vectorBucketArn": b} if b.startswith("arn:") else {"vectorBucketName": b}))
        if d is not None:
            ec = d["vectorBucket"].get("encryptionConfiguration") or {}
            e["cifrado"].append(_llave("AWS::S3Vectors::VectorBucket", b, ec.get("kmsKeyArn") if ec.get("sseType") == "aws:kms"
                                       else None, "SSE-S3"))
    for c in e["cifrado"]:   # the KB is on the key of its vector bucket
        if c["tipo"] == "AWS::Bedrock::KnowledgeBase":
            vb = next((x for x in e["cifrado"] if x["tipo"] == "AWS::S3Vectors::VectorBucket" and x["id"] == c.get("via")), None)
            c["llave"] = vb["llave"] if vb else "vector bucket not read"

    for r in _de_tipo(recursos, "AWS::SecretsManager::Secret"):
        d = ll("secretsmanager", "describe_secret", SecretId=r["fisico"])
        if d is not None:
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], d.get("KmsKeyId"), "aws/secretsmanager (AWS managed)"))
        p = ll("secretsmanager", "get_resource_policy", SecretId=r["fisico"])
        if p is not None and p.get("ResourcePolicy"):
            e["politicas"].append({"recurso": r["fisico"], "politica": p["ResourcePolicy"]})

    for r in _de_tipo(recursos, "AWS::Bedrock::Prompt"):
        d = ll("bedrock-agent", "get_prompt", promptIdentifier=r["fisico"])
        if d is not None:
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], d.get("customerEncryptionKeyArn"), "AWS owned key"))

    for r in _de_tipo(recursos, "AWS::BedrockAgentCore::Gateway"):
        d = ll("bedrock-agentcore-control", "get_gateway", gatewayIdentifier=r["fisico"].split("/")[-1])
        if d is not None:
            e["cifrado"].append(_llave(r["tipo"], d["gatewayId"], d.get("kmsKeyArn"), "AWS owned key"))
            e["gateways"].append({"id": d["gatewayId"], "autorizador": d.get("authorizerType")})

    for r in _de_tipo(recursos, "AWS::SQS::Queue"):
        d = ll("sqs", "get_queue_attributes", QueueUrl=r["fisico"], AttributeNames=["KmsMasterKeyId", "Policy"])
        if d is not None:
            a = d.get("Attributes", {})
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], a.get("KmsMasterKeyId"), "SQS managed (SSE-SQS)"))
            if a.get("Policy"):
                e["politicas"].append({"recurso": r["fisico"], "politica": a["Policy"]})
    for r in _de_tipo(recursos, "AWS::SNS::Topic"):
        d = ll("sns", "get_topic_attributes", TopicArn=r["fisico"])
        if d is not None:
            a = d.get("Attributes", {})
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], a.get("KmsMasterKeyId"), "none"))
            if a.get("Policy"):
                e["politicas"].append({"recurso": r["fisico"], "politica": a["Policy"]})

    for r in _de_tipo(recursos, "AWS::Lambda::Function"):
        d = ll("lambda", "get_function_configuration", FunctionName=r["fisico"])
        if d is None:
            continue
        if d.get("Environment", {}).get("Variables"):
            e["cifrado"].append(_llave(r["tipo"], r["fisico"], d.get("KMSKeyArn"), "aws/lambda (AWS managed)"))
        urls = ll.paginar("lambda", "list_function_url_configs", "FunctionUrlConfigs", FunctionName=r["fisico"])
        pol = ll("lambda", "get_policy", ausente=("ResourceNotFoundException",), FunctionName=r["fisico"])
        vpc = d.get("VpcConfig") or {}
        e["lambdas"].append({"nombre": r["fisico"], "url": None if urls is None else len(urls) > 0,
                             "politica": None if pol is None or pol is AUSENTE else pol["Policy"],
                             "vpc": vpc.get("VpcId") or None, "subredes": vpc.get("SubnetIds", [])})

    for r in _de_tipo(recursos, "AWS::ApiGatewayV2::Api"):
        for ruta in ll.paginar("apigatewayv2", "get_routes", "Items", ApiId=r["fisico"]) or []:
            e["rutas_api"].append({"api": r["fisico"], "ruta": ruta["RouteKey"],
                                   "autorizacion": ruta.get("AuthorizationType", "NONE")})

    _red(ll, e, recursos)
    _cloudtrail(ll, e, recursos, desde)
    return e


def _red(ll, e, recursos):
    vpcs = {r["fisico"] for r in _de_tipo(recursos, "AWS::EC2::VPC")}
    vpcs |= {x["vpc"] for x in e["lambdas"] + e["rds"] if x.get("vpc")}
    e["vpcs"] = sorted(vpcs)
    subredes = sorted({s for x in e["lambdas"] + e["rds"] for s in x.get("subredes", [])})
    for vpc in e["vpcs"]:
        principal = ll.paginar("ec2", "describe_route_tables", "RouteTables",
                               Filters=[{"Name": "vpc-id", "Values": [vpc]}, {"Name": "association.main", "Values": ["true"]}])
        asociadas = ll.paginar("ec2", "describe_route_tables", "RouteTables", Filters=[{"Name": "vpc-id", "Values": [vpc]}])
        if principal is None or asociadas is None:
            e["subredes"] = None
            break
        por_subred = {a["SubnetId"]: t for t in asociadas for a in t.get("Associations", []) if a.get("SubnetId")}
        for s in subredes:
            if s in por_subred or principal:
                tabla = por_subred.get(s) or principal[0]
                e["subredes"][s] = {"tabla": tabla["RouteTableId"], "rutas": [
                    {"destino": r.get("DestinationCidrBlock") or r.get("DestinationIpv6CidrBlock") or r.get("DestinationPrefixListId"),
                     "objetivo": next((r[k] for k in ("GatewayId", "NatGatewayId", "EgressOnlyInternetGatewayId",
                                                       "TransitGatewayId", "VpcPeeringConnectionId", "NetworkInterfaceId",
                                                       "InstanceId") if r.get(k)), None)}
                    for r in tabla.get("Routes", [])]}
        igw = ll("ec2", "describe_internet_gateways", Filters=[{"Name": "attachment.vpc-id", "Values": [vpc]}])
        e["igw"] += [] if igw is None else [g["InternetGatewayId"] for g in igw["InternetGateways"]]
        nat = ll.paginar("ec2", "describe_nat_gateways", "NatGateways", Filter=[{"Name": "vpc-id", "Values": [vpc]}])
        e["nat"] += [] if nat is None else [n["NatGatewayId"] for n in nat if n.get("State") not in ("deleted", "failed")]
        for g in ll.paginar("ec2", "describe_security_groups", "SecurityGroups",
                            Filters=[{"Name": "vpc-id", "Values": [vpc]}]) or []:
            origenes = [x["CidrIp"] for p in g.get("IpPermissions", []) for x in p.get("IpRanges", [])] + \
                       [x["CidrIpv6"] for p in g.get("IpPermissions", []) for x in p.get("Ipv6Ranges", [])]
            e["grupos"].append({"id": g["GroupId"], "nombre": g.get("GroupName"), "entrada": origenes})
        for ep in ll.paginar("ec2", "describe_vpc_endpoints", "VpcEndpoints",
                             Filters=[{"Name": "vpc-id", "Values": [vpc]}]) or []:
            e["endpoints"].append({"id": ep["VpcEndpointId"], "servicio": ep["ServiceName"],
                                   "tipo": ep.get("VpcEndpointType"), "politica": ep.get("PolicyDocument")})
        for ni in ll.paginar("ec2", "describe_network_interfaces", "NetworkInterfaces",
                             Filters=[{"Name": "vpc-id", "Values": [vpc]},
                                      {"Name": "description", "Values": ["RDSNetworkInterface"]}]) or []:
            e["interfaces_rds"].append({"id": ni["NetworkInterfaceId"],
                                        "ip_publica": (ni.get("Association") or {}).get("PublicIp")})


def _cloudtrail(ll, e, recursos, desde):
    for r in _de_tipo(recursos, "AWS::IAM::Role"):
        for prefijo, motivo in ROLES_ESPERADOS.items():
            if r["logico"].startswith(prefijo):
                e["roles_esperados"][r["fisico"]] = motivo
    eventos = ll.paginar("cloudtrail", "lookup_events", "Events",
                         LookupAttributes=[{"AttributeKey": "EventSource", "AttributeValue": FUENTE_BEDROCK}],
                         StartTime=desde)
    if eventos is None:
        return
    e["cloudtrail"] = []
    for ev in eventos:
        detalle = json.loads(ev.get("CloudTrailEvent") or "{}")
        ui = detalle.get("userIdentity", {})
        rol = ((ui.get("sessionContext") or {}).get("sessionIssuer") or {}).get("userName") or ui.get("invokedBy") \
            or ui.get("type")
        e["cloudtrail"].append({"evento": ev["EventName"], "rol": rol, "error": detalle.get("errorCode"),
                                "hora": detalle.get("eventTime")})


# ---------- checks (pure: they read only the collected state) ----------

def es_la_llave(valor, llave) -> bool:
    """The value names the project key: its ARN, its id, its alias, or the alias ARN."""
    if not valor or not llave:
        return False
    alias_arn = llave["arn"].rsplit(":", 1)[0] + ":" + ALIAS
    return valor in (llave["arn"], llave["id"], ALIAS, alias_arn) or valor.endswith(f":key/{llave['id']}")


def razon_conocida(c: dict) -> str | None:
    if c["tipo"] == "AWS::Logs::LogGroup":
        return next((r for patron, r in GRUPOS_CONOCIDOS.items() if re.match(patron, c["id"])), None)
    return CONOCIDOS.get(c["tipo"])


def check_cifrado(e) -> dict:
    if e.get("llave") is None:
        return {"veredicto": "sin_permiso", "detalle": "the project key alias/semana19 could not be read"}
    filas = []
    for c in e["cifrado"]:
        cmk = es_la_llave(c["llave"], e["llave"])
        filas.append({**{k: v for k, v in c.items() if k != "via"}, "cmk": cmk,
                      "razon": None if cmk else razon_conocida(c)})
    otras = [f for f in filas if not f["cmk"]]
    v = "ok" if not otras else ("conocido" if all(f["razon"] for f in otras) else "hallazgo")
    return {"veredicto": v, "recursos": len(filas), "con_la_llave": len(filas) - len(otras),
            "por_tipo": dict(Counter(f["tipo"] for f in filas)), "otra_llave": otras}


def check_publico(e) -> dict:
    malos = []
    for b in e["buckets"]:
        bpa = b["bloqueo_publico"]
        if bpa is not None and not all(bpa.get(k) for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy",
                                                              "RestrictPublicBuckets")):
            malos.append({"recurso": b["id"], "motivo": "Block Public Access is not fully on", "valor": bpa})
        if b["es_publico"]:
            malos.append({"recurso": b["id"], "motivo": "S3 reports the bucket policy as public"})
        if abiertas(b["politica"]):
            malos.append({"recurso": b["id"], "motivo": "bucket policy: Allow with Principal * and no condition"})
    for r in e["rds"]:
        if r["publica"] is not False:
            malos.append({"recurso": r["id"], "motivo": "RDS PubliclyAccessible is not false"})
    for f in e["lambdas"]:
        if f["url"]:
            malos.append({"recurso": f["nombre"], "motivo": "Lambda function URL"})
        if abiertas(f["politica"]):
            malos.append({"recurso": f["nombre"], "motivo": "Lambda policy: Allow with Principal * and no condition"})
    for p in e["politicas"]:
        if abiertas(p["politica"]):
            malos.append({"recurso": p["recurso"], "motivo": "resource policy: Allow with Principal * and no condition"})
    for r in e["rutas_api"]:
        if r["autorizacion"] in (None, "NONE"):
            malos.append({"recurso": f"{r['api']} {r['ruta']}", "motivo": "HTTP API route without an authorizer"})
    for g in e["gateways"]:
        if g["autorizador"] in (None, "NONE"):
            malos.append({"recurso": g["id"], "motivo": "AgentCore gateway without an inbound authorizer"})
    no_leidos = [b["id"] for b in e["buckets"] if not b["leido"]] + [f["nombre"] for f in e["lambdas"] if f["url"] is None]
    v = "hallazgo" if malos else ("sin_permiso" if no_leidos else "ok")
    return {"veredicto": v, "publicos": malos, "no_leidos": no_leidos,
            "excepcion": "the HTTP API endpoint is public by design; every route has the JWT authorizer",
            "rutas_api": [f"{r['ruta']}: {r['autorizacion']}" for r in e["rutas_api"]],
            "gateways": [f"{g['id']}: {g['autorizador']}" for g in e["gateways"]]}


def _rutas_abiertas(e, subredes) -> list[dict]:
    return [{"subred": s, "tabla": e["subredes"][s]["tabla"], **r} for s in subredes if s in (e["subredes"] or {})
            for r in e["subredes"][s]["rutas"] if r["destino"] in ABIERTAS]


def check_rds_sin_ip_publica(e) -> dict:
    if not e["rds"]:
        return {"veredicto": "hallazgo", "detalle": "no RDS instance found in the stacks"}
    malos = [{"recurso": r["id"], "motivo": "PubliclyAccessible is not false"} for r in e["rds"] if r["publica"] is not False]
    malos += [{"recurso": i["id"], "motivo": "RDS network interface with a public IP"} for i in e["interfaces_rds"]
              if i["ip_publica"]]
    malos += [{"recurso": x["subred"], "motivo": f"route {x['destino']} to {x['objetivo']}"}
              for x in _rutas_abiertas(e, sorted({s for r in e["rds"] for s in r["subredes"]}))]
    return {"veredicto": "hallazgo" if malos else "ok", "instancias": [r["id"] for r in e["rds"]],
            "interfaces": len(e["interfaces_rds"]), "malos": malos}


def check_red(e) -> dict:
    if e["subredes"] is None:
        return {"veredicto": "sin_permiso", "detalle": "route tables could not be read"}
    en_vpc = [f for f in e["lambdas"] if f["vpc"]]
    subredes = sorted({s for f in en_vpc for s in f["subredes"]} | {s for r in e["rds"] for s in r["subredes"]})
    faltan = [s for s in subredes if s not in e["subredes"]]
    malos = [{"recurso": x["subred"], "motivo": f"route {x['destino']} to {x['objetivo']}"} for x in _rutas_abiertas(e, subredes)]
    malos += [{"recurso": g, "motivo": "internet gateway attached to the VPC"} for g in e["igw"]]
    malos += [{"recurso": n, "motivo": "NAT gateway in the VPC"} for n in e["nat"]]
    malos += [{"recurso": g["id"], "motivo": f"security group admits {o}"} for g in e["grupos"] for o in g["entrada"]
              if o in ABIERTAS]
    malos += [{"recurso": s, "motivo": "subnet without a route table read"} for s in faltan]
    return {"veredicto": "hallazgo" if malos else "ok", "lambdas_en_vpc": [f["nombre"] for f in en_vpc],
            "subredes": {s: e["subredes"][s]["rutas"] for s in subredes if s in e["subredes"]},
            "grupos": len(e["grupos"]), "malos": malos}


def check_endpoints(e) -> dict:
    filas, malos = [], []
    cuenta = e["cuenta"]
    for ep in e["endpoints"]:
        decl = [s for s in _declaraciones(ep["politica"]) if s.get("Effect") == "Allow"]
        limitada = bool(decl) and all(
            _valores(s.get("Condition"), "aws:PrincipalAccount") == [cuenta] or
            (not _principal_abierto(s.get("Principal")) and s.get("Principal") is not None) for s in decl)
        recursos = bool(decl) and all(_valores(s.get("Condition"), "aws:ResourceAccount") for s in decl)
        filas.append({"id": ep["id"], "servicio": ep["servicio"], "tipo": ep["tipo"], "limitada_a_la_cuenta": limitada,
                      "limita_aws_ResourceAccount": recursos})
        if not ep["politica"]:
            malos.append({"recurso": ep["id"], "motivo": "no endpoint policy (full access)"})
        elif not limitada:
            malos.append({"recurso": ep["id"], "motivo": "an Allow statement is not limited to this account"})
    if not e["endpoints"]:
        malos.append({"recurso": ",".join(e["vpcs"]) or "-", "motivo": "no VPC endpoint found"})
    return {"veredicto": "hallazgo" if malos else "ok", "endpoints": filas, "malos": malos,
            "nota": "limita_aws_ResourceAccount false: the policy limits who calls, not whose resources (H12)"}


def check_cloudtrail(e) -> dict:
    no_visibles = {k: f"data event ({v}): needs a trail with advanced event selectors, not created (H11)"
                   for k, v in EVENTOS_DE_DATOS.items()}
    if e["cloudtrail"] is None:
        return {"veredicto": "sin_permiso", "no_visibles": no_visibles}
    runtime = [x for x in e["cloudtrail"] if x["evento"] in RUNTIME]
    por_rol = Counter((x["evento"], x["rol"]) for x in runtime)
    inesperados = sorted({x["rol"] for x in runtime} - set(e["roles_esperados"]))
    control = Counter((x["evento"], x["rol"]) for x in e["cloudtrail"] if x["evento"] not in RUNTIME)
    v = "sin_eventos" if not runtime else ("hallazgo" if inesperados else "ok")
    return {"veredicto": v, "eventos": len(e["cloudtrail"]), "runtime": len(runtime),
            "runtime_por_evento_y_rol": [{"evento": a, "rol": b, "n": n} for (a, b), n in sorted(por_rol.items())],
            "errores": dict(Counter(x["error"] for x in runtime if x["error"])),
            "roles_esperados": e["roles_esperados"], "roles_inesperados": inesperados,
            "plano_de_control": [{"evento": a, "rol": b, "n": n} for (a, b), n in sorted(control.items())],
            "no_visibles": no_visibles}


CHECKS = {"cifrado": check_cifrado, "publico": check_publico, "rds_sin_ip_publica": check_rds_sin_ip_publica,
          "red": check_red, "endpoints": check_endpoints, "cloudtrail": check_cloudtrail}


def informe(e: dict, ll: Llamadas, *, identidad: str, desde: datetime) -> dict:
    if e.get("recursos") is None:
        checks = {n: {"veredicto": "sin_permiso"} for n in CHECKS}
    else:
        checks = {n: f(e) for n, f in CHECKS.items()}
    peor = max((c["veredicto"] for c in checks.values()), key=ORDEN.index)
    if ll.sin_permiso and ORDEN.index(peor) < ORDEN.index("sin_permiso"):
        peor = "sin_permiso"   # a denied call means a resource may be missing from a check that says ok
    r = {"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "identidad": identidad,
         "region": REGION, "desde": desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "recursos_por_tipo": dict(sorted((e.get("recursos") or {}).items())),
         "veredictos": {n: c["veredicto"] for n, c in checks.items()}, "veredicto": peor,
         "sin_permiso": ll.sin_permiso, "checks": checks}
    return redactar(r, cuentas=[e["cuenta"]])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--perfil", "--profile", default="semana19-lectura", help="read-only AWS profile", metavar="PROFILE")
    ap.add_argument("--desde", "--since", help="CloudTrail start, ISO 8601 UTC (default: 24 hours ago)", metavar="SINCE")
    ap.add_argument("--salida", "--output", type=Path, default=SALIDA, metavar="OUTPUT")
    a = ap.parse_args(argv)
    desde = (datetime.fromisoformat(a.desde.replace("Z", "+00:00")) if a.desde
             else datetime.now(timezone.utc) - timedelta(hours=24))
    import boto3
    sesion = boto3.Session(profile_name=a.perfil, region_name=REGION)
    ll = Llamadas(sesion)
    yo = ll("sts", "get_caller_identity")
    rol = yo["Arn"].split(":assumed-role/")[-1].split("/")[0] if ":assumed-role/" in yo["Arn"] else yo["Arn"]
    e = recolectar(ll, yo["Account"], desde)
    r = informe(e, ll, identidad=rol, desde=desde)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("veredictos", "veredicto", "sin_permiso")}, ensure_ascii=False))
    return 0 if r["veredicto"] in ("ok", "conocido") else 1


if __name__ == "__main__":
    sys.exit(main())
