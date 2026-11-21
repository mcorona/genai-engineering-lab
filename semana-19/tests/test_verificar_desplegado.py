"""Week 19, activity 9, step 2: the read-only checks of the deployed stack, offline (Stubber and simulated state; no AWS).

Each check must pass on a good state and catch its simulated bad case: a bucket without the key, a security group open
to 0.0.0.0/0, a route to an internet gateway, an open endpoint policy, a Principal "*" without a condition.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verificar_desplegado", S19 / "seguridad" / "verificar_desplegado.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)

CUENTA = "123456789012"
LLAVE_ID = "1234abcd-12ab-34cd-56ef-1234567890ab"
LLAVE = f"arn:aws:kms:us-east-1:{CUENTA}:key/{LLAVE_ID}"
DESDE = datetime(2026, 11, 22, tzinfo=timezone.utc)


def _cliente(servicio):
    return boto3.client(servicio, region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")


def _stub(servicio):
    c = _cliente(servicio)
    s = Stubber(c)
    s.activate()
    return c, s


def _cuenta_abierta(principal="*", condicion=None):
    s = {"Effect": "Allow", "Principal": principal, "Action": "*", "Resource": "*"}
    if condicion:
        s["Condition"] = condicion
    return json.dumps({"Version": "2012-10-17", "Statement": [s]})


LIMITADA = _cuenta_abierta(condicion={"StringEquals": {"aws:PrincipalAccount": CUENTA}})


def estado_bueno() -> dict:
    return {
        "cuenta": CUENTA, "llave": {"arn": LLAVE, "id": LLAVE_ID}, "recursos": {"AWS::S3::Bucket": 1},
        "cifrado": [
            {"tipo": "AWS::S3::Bucket", "id": "semana19-datos-docs", "llave": LLAVE},
            {"tipo": "AWS::Logs::LogGroup", "id": "/semana19/agente", "llave": LLAVE},
            {"tipo": "AWS::RDS::DBInstance", "id": "semana19-bd", "llave": LLAVE},
            {"tipo": "AWS::DynamoDB::Table", "id": "semana19-tokens", "llave": LLAVE},
            {"tipo": "Guardrail", "id": "gr1", "llave": LLAVE},
            {"tipo": "AWS::SecretsManager::Secret", "id": "s", "llave": "alias/semana19"},
        ],
        "buckets": [{"id": "semana19-datos-docs", "leido": True, "es_publico": False, "politica": json.dumps({
            "Statement": [{"Effect": "Deny", "Principal": {"AWS": "*"}, "Action": "s3:*", "Resource": "*",
                           "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}),
            "bloqueo_publico": {"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True,
                                "RestrictPublicBuckets": True}}],
        "rds": [{"id": "semana19-bd", "publica": False, "vpc": "vpc-1", "subredes": ["subnet-a"]}],
        "lambdas": [{"nombre": "semana19-herramientas", "url": False, "vpc": "vpc-1", "subredes": ["subnet-a"],
                     "politica": json.dumps({"Statement": [{"Effect": "Allow",
                                                            "Principal": {"Service": "apigateway.amazonaws.com"},
                                                            "Action": "lambda:InvokeFunction", "Resource": "*",
                                                            "Condition": {"ArnLike": {"AWS:SourceArn": "arn:x"}}}]})},
                    {"nombre": "semana19-agente", "url": False, "vpc": None, "subredes": [], "politica": None}],
        "politicas": [{"recurso": "alias/semana19", "politica": json.dumps({"Statement": [
            {"Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{CUENTA}:root"}, "Action": "kms:*", "Resource": "*"}]})}],
        "rutas_api": [{"api": "a1", "ruta": "POST /consultas", "autorizacion": "JWT"}],
        "gateways": [{"id": "gw1", "autorizador": "CUSTOM_JWT"}],
        "vpcs": ["vpc-1"],
        "subredes": {"subnet-a": {"tabla": "rtb-1", "rutas": [{"destino": "10.0.0.0/16", "objetivo": "local"},
                                                              {"destino": "pl-63a5400a", "objetivo": "vpce-s3"}]}},
        "igw": [], "nat": [], "interfaces_rds": [{"id": "eni-1", "ip_publica": None}],
        "grupos": [{"id": "sg-1", "nombre": "semana19-rds", "entrada": []}],
        "endpoints": [{"id": "vpce-1", "servicio": "com.amazonaws.us-east-1.logs", "tipo": "Interface",
                       "politica": LIMITADA}],
        "cloudtrail": [{"evento": "Converse", "rol": "semana19-computo-FuncionAgenteServiceRole-X", "error": None,
                        "hora": "t"}],
        "roles_esperados": {"semana19-computo-FuncionAgenteServiceRole-X": "the agent"},
    }


def test_el_estado_bueno_pasa_los_seis_checks():
    e = estado_bueno()
    assert {n: f(e)["veredicto"] for n, f in V.CHECKS.items()} == {n: "ok" for n in V.CHECKS}


# ---------- each check catches its bad case ----------

def _bucket_sin_la_llave(e):
    e["cifrado"][0]["llave"] = "SSE-S3"


def _otra_llave_cmk(e):
    e["cifrado"][2]["llave"] = f"arn:aws:kms:us-east-1:{CUENTA}:key/ffffffff-0000-0000-0000-000000000000"


def _bucket_con_principal_estrella(e):
    e["buckets"][0]["politica"] = _cuenta_abierta({"AWS": "*"})


def _bucket_sin_bloqueo(e):
    e["buckets"][0]["bloqueo_publico"]["RestrictPublicBuckets"] = False


def _lambda_con_url(e):
    e["lambdas"][1]["url"] = True


def _lambda_con_principal_estrella(e):
    e["lambdas"][1]["politica"] = _cuenta_abierta()


def _llave_con_principal_estrella(e):
    e["politicas"][0]["politica"] = _cuenta_abierta()


def _ruta_sin_autorizador(e):
    e["rutas_api"].append({"api": "a1", "ruta": "GET /abierta", "autorizacion": "NONE"})


def _gateway_sin_autorizador(e):
    e["gateways"][0]["autorizador"] = None


def _rds_publica(e):
    e["rds"][0]["publica"] = True


def _rds_con_ip_publica(e):
    e["interfaces_rds"][0]["ip_publica"] = "203.0.113.10"


def _ruta_a_igw(e):
    e["subredes"]["subnet-a"]["rutas"].append({"destino": "0.0.0.0/0", "objetivo": "igw-1"})


def _ruta_ipv6_abierta(e):
    e["subredes"]["subnet-a"]["rutas"].append({"destino": "::/0", "objetivo": "eigw-1"})


def _igw_en_la_vpc(e):
    e["igw"] = ["igw-1"]


def _nat_en_la_vpc(e):
    e["nat"] = ["nat-1"]


def _sg_abierto(e):
    e["grupos"][0]["entrada"] = ["0.0.0.0/0"]


def _endpoint_abierto(e):
    e["endpoints"][0]["politica"] = _cuenta_abierta()


def _endpoint_sin_politica(e):
    e["endpoints"][0]["politica"] = None


def _endpoint_de_otra_cuenta(e):
    e["endpoints"][0]["politica"] = _cuenta_abierta(condicion={"StringEquals": {"aws:PrincipalAccount": "111111111111"}})


def _rol_inesperado_llama_a_bedrock(e):
    e["cloudtrail"].append({"evento": "InvokeModel", "rol": "semana19-otro", "error": None, "hora": "t"})


@pytest.mark.parametrize("check,dano", [
    ("cifrado", _bucket_sin_la_llave), ("cifrado", _otra_llave_cmk),
    ("publico", _bucket_con_principal_estrella), ("publico", _bucket_sin_bloqueo), ("publico", _lambda_con_url),
    ("publico", _lambda_con_principal_estrella), ("publico", _llave_con_principal_estrella),
    ("publico", _ruta_sin_autorizador), ("publico", _gateway_sin_autorizador), ("publico", _rds_publica),
    ("rds_sin_ip_publica", _rds_publica), ("rds_sin_ip_publica", _rds_con_ip_publica),
    ("rds_sin_ip_publica", _ruta_a_igw),
    ("red", _ruta_a_igw), ("red", _ruta_ipv6_abierta), ("red", _igw_en_la_vpc), ("red", _nat_en_la_vpc),
    ("red", _sg_abierto),
    ("endpoints", _endpoint_abierto), ("endpoints", _endpoint_sin_politica), ("endpoints", _endpoint_de_otra_cuenta),
    ("cloudtrail", _rol_inesperado_llama_a_bedrock),
], ids=lambda x: x if isinstance(x, str) else x.__name__.strip("_"))
def test_cada_check_detecta_su_caso_malo(check, dano):
    e = estado_bueno()
    dano(e)
    assert V.CHECKS[check](e)["veredicto"] == "hallazgo"


def test_otra_llave_conocida_se_lista_con_su_razon_y_no_es_hallazgo():
    e = estado_bueno()
    e["cifrado"].append({"tipo": "AWS::StepFunctions::StateMachine", "id": "sm", "llave": "AWS owned key"})
    r = V.check_cifrado(e)
    assert r["veredicto"] == "conocido"
    assert r["otra_llave"] == [{"tipo": "AWS::StepFunctions::StateMachine", "id": "sm", "llave": "AWS owned key",
                                "cmk": False, "razon": V.CONOCIDOS["AWS::StepFunctions::StateMachine"]}]


@pytest.mark.parametrize("grupo,conocido", [
    ("/aws/lambda/semana19-datos-Cargador29E38F40-AbCdEf", True),
    ("/aws/lambda/semana19-base-CustomVpcRestrictDefaultSGCustomR-XyZ", True),
    ("/aws/lambda/semana19-computo-FuncionAgente1EADB7D9-Q", False),
    ("/semana19/agente", False),
])
def test_solo_los_grupos_implicitos_documentados_son_conocidos(grupo, conocido):
    e = estado_bueno()
    e["cifrado"].append({"tipo": "AWS::Logs::LogGroup", "id": grupo, "llave": "CloudWatch Logs default"})
    assert V.check_cifrado(e)["veredicto"] == ("conocido" if conocido else "hallazgo")


def test_la_llave_se_reconoce_por_arn_id_alias_y_arn_del_alias():
    llave = {"arn": LLAVE, "id": LLAVE_ID}
    for valor in (LLAVE, LLAVE_ID, "alias/semana19", f"arn:aws:kms:us-east-1:{CUENTA}:alias/semana19"):
        assert V.es_la_llave(valor, llave), valor
    for valor in (None, "SSE-S3", "alias/aws/s3", f"arn:aws:kms:us-east-1:{CUENTA}:key/otra"):
        assert not V.es_la_llave(valor, llave), valor


def test_el_endpoint_que_no_limita_recursos_se_reporta_sin_fallar():
    r = V.check_endpoints(estado_bueno())
    assert r["veredicto"] == "ok" and r["endpoints"][0]["limita_aws_ResourceAccount"] is False


def test_sin_llamadas_de_runtime_no_es_ok_y_los_eventos_de_datos_se_dicen_no_visibles():
    e = estado_bueno()
    e["cloudtrail"] = [{"evento": "GetGuardrail", "rol": "semana19-lectura", "error": None, "hora": "t"}]
    r = V.check_cloudtrail(e)
    assert r["veredicto"] == "sin_eventos"
    assert set(r["no_visibles"]) == {"ApplyGuardrail", "Retrieve", "RetrieveAndGenerate", "InvokeAgent", "InvokeGateway"}


# ---------- read-only access ----------

def test_solo_lectura_rechaza_toda_operacion_que_no_lee():
    c = V.SoloLectura(_cliente("s3"))
    for op in ("put_bucket_policy", "delete_bucket", "create_bucket", "put_public_access_block"):
        with pytest.raises(PermissionError):
            getattr(c, op)
    with pytest.raises(PermissionError):
        c.get_paginator("delete_objects")
    assert callable(c.get_bucket_encryption) and callable(c.list_buckets)


def test_una_llamada_denegada_queda_como_sin_permiso_con_su_operacion():
    c, s = _stub("s3")
    s.add_client_error("get_bucket_encryption", service_error_code="AccessDenied", http_status_code=403)
    ll = V.Llamadas(clientes={"s3": c})
    assert V.cifrado_de_bucket(ll, "b") is None
    assert ll.sin_permiso == ["s3:GetBucketEncryption"]


def test_un_error_que_no_es_permiso_ni_ausencia_se_propaga():
    c, s = _stub("s3")
    s.add_client_error("get_bucket_encryption", service_error_code="InternalError", http_status_code=500)
    with pytest.raises(Exception):
        V.cifrado_de_bucket(V.Llamadas(clientes={"s3": c}), "b")


def test_el_informe_redacta_la_cuenta_y_baja_el_veredicto_si_hubo_llamadas_denegadas():
    ll = V.Llamadas(clientes={})
    ll.sin_permiso.append("bedrock:GetGuardrail")
    r = V.informe(estado_bueno(), ll, identidad="semana19-lectura", desde=DESDE)
    assert r["veredictos"] == {n: "ok" for n in V.CHECKS} and r["veredicto"] == "sin_permiso"
    assert CUENTA not in json.dumps(r)


# ---------- collectors with Stubber: the bad case is detected from AWS's own responses ----------

def test_bucket_sin_la_llave_desde_s3():
    c, s = _stub("s3")
    s.add_response("get_bucket_encryption", {"ServerSideEncryptionConfiguration": {"Rules": [
        {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}}, {"Bucket": "b"})
    s.add_response("get_bucket_encryption", {"ServerSideEncryptionConfiguration": {"Rules": [
        {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": LLAVE}}]}}, {"Bucket": "c"})
    ll = V.Llamadas(clientes={"s3": c})
    e = estado_bueno()
    e["cifrado"] = [V.cifrado_de_bucket(ll, "b"), V.cifrado_de_bucket(ll, "c")]
    r = V.check_cifrado(e)
    assert r["veredicto"] == "hallazgo" and [x["id"] for x in r["otra_llave"]] == ["b"]
    assert r["otra_llave"][0]["llave"] == "SSE-S3"


def test_bucket_con_principal_estrella_desde_s3():
    c, s = _stub("s3")
    s.add_response("get_public_access_block", {"PublicAccessBlockConfiguration": {
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}},
        {"Bucket": "b"})
    s.add_response("get_bucket_policy", {"Policy": _cuenta_abierta()}, {"Bucket": "b"})
    s.add_response("get_bucket_policy_status", {"PolicyStatus": {"IsPublic": True}}, {"Bucket": "b"})
    e = estado_bueno()
    e["buckets"] = [V.publico_de_bucket(V.Llamadas(clientes={"s3": c}), "b")]
    motivos = {m["motivo"] for m in V.check_publico(e)["publicos"]}
    assert motivos == {"S3 reports the bucket policy as public", "bucket policy: Allow with Principal * and no condition"}


def test_bucket_sin_politica_ni_bloqueo_desde_s3():
    c, s = _stub("s3")
    s.add_client_error("get_public_access_block", service_error_code="NoSuchPublicAccessBlockConfiguration",
                       http_status_code=404)
    s.add_client_error("get_bucket_policy", service_error_code="NoSuchBucketPolicy", http_status_code=404)
    s.add_client_error("get_bucket_policy_status", service_error_code="NoSuchBucketPolicy", http_status_code=404)
    b = V.publico_de_bucket(V.Llamadas(clientes={"s3": c}), "b")
    assert b == {"id": "b", "bloqueo_publico": {}, "politica": None, "es_publico": False, "leido": True}
    e = estado_bueno()
    e["buckets"] = [b]
    assert V.check_publico(e)["veredicto"] == "hallazgo"


def _red_desde_ec2(*, rutas, igw=(), sg_entrada=(), politica=LIMITADA, ip_publica=None):
    c, s = _stub("ec2")
    tabla = {"RouteTableId": "rtb-1", "VpcId": "vpc-1", "Routes": [{"DestinationCidrBlock": "10.0.0.0/16",
                                                                    "GatewayId": "local"}, *rutas],
             "Associations": [{"SubnetId": "subnet-a", "RouteTableId": "rtb-1"}]}
    principal = {"RouteTableId": "rtb-0", "VpcId": "vpc-1", "Routes": [], "Associations": [{"Main": True}]}
    s.add_response("describe_route_tables", {"RouteTables": [principal]})
    s.add_response("describe_route_tables", {"RouteTables": [principal, tabla]})
    s.add_response("describe_internet_gateways", {"InternetGateways": [{"InternetGatewayId": g} for g in igw]})
    s.add_response("describe_nat_gateways", {"NatGateways": []})
    s.add_response("describe_security_groups", {"SecurityGroups": [{
        "GroupId": "sg-1", "GroupName": "semana19-x", "IpPermissions": [
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": x} for x in sg_entrada]}]}]})
    s.add_response("describe_vpc_endpoints", {"VpcEndpoints": [{
        "VpcEndpointId": "vpce-1", "ServiceName": "com.amazonaws.us-east-1.logs", "VpcEndpointType": "Interface",
        **({"PolicyDocument": politica} if politica else {})}]})
    s.add_response("describe_network_interfaces", {"NetworkInterfaces": [{
        "NetworkInterfaceId": "eni-1", **({"Association": {"PublicIp": ip_publica}} if ip_publica else {})}]})
    e = estado_bueno()
    for k in ("subredes", "igw", "nat", "grupos", "endpoints", "interfaces_rds"):
        e[k] = {} if k == "subredes" else []
    V._red(V.Llamadas(clientes={"ec2": c}), e, [{"tipo": "AWS::EC2::VPC", "fisico": "vpc-1", "logico": "Vpc",
                                                  "stack": "semana19-base"}])
    s.assert_no_pending_responses()
    return e


def test_red_buena_desde_ec2():
    e = _red_desde_ec2(rutas=[{"DestinationPrefixListId": "pl-63a5400a", "GatewayId": "vpce-s3"}])
    assert [V.CHECKS[n](e)["veredicto"] for n in ("red", "endpoints", "rds_sin_ip_publica")] == ["ok", "ok", "ok"]


@pytest.mark.parametrize("kw,check", [
    ({"rutas": [{"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-1"}]}, "red"),
    ({"rutas": [{"DestinationCidrBlock": "0.0.0.0/0", "NatGatewayId": "nat-1"}]}, "red"),
    ({"rutas": [], "igw": ["igw-1"]}, "red"),
    ({"rutas": [], "sg_entrada": ["0.0.0.0/0"]}, "red"),
    ({"rutas": [], "politica": _cuenta_abierta()}, "endpoints"),
    ({"rutas": [], "politica": None}, "endpoints"),
    ({"rutas": [], "ip_publica": "203.0.113.10"}, "rds_sin_ip_publica"),
], ids=["ruta-igw", "ruta-nat", "igw", "sg-abierto", "endpoint-abierto", "endpoint-sin-politica", "rds-ip-publica"])
def test_red_mala_desde_ec2(kw, check):
    assert V.CHECKS[check](_red_desde_ec2(**kw))["veredicto"] == "hallazgo"


def _evento(nombre, rol):
    return {"EventName": nombre, "CloudTrailEvent": json.dumps({
        "eventName": nombre, "eventTime": "2026-11-22T10:00:00Z",
        "userIdentity": {"type": "AssumedRole", "sessionContext": {"sessionIssuer": {"userName": rol}}}})}


def test_cloudtrail_agrupa_por_evento_y_rol_y_detecta_un_rol_inesperado():
    c, s = _stub("cloudtrail")
    s.add_response("lookup_events", {"Events": [_evento("Converse", "semana19-computo-FuncionAgenteServiceRole-X"),
                                                _evento("Converse", "semana19-computo-FuncionAgenteServiceRole-X"),
                                                _evento("InvokeModel", "intruso"),
                                                _evento("GetGuardrail", "semana19-lectura")]},
                   {"LookupAttributes": [{"AttributeKey": "EventSource", "AttributeValue": "bedrock.amazonaws.com"}],
                    "StartTime": DESDE})
    e = estado_bueno()
    V._cloudtrail(V.Llamadas(clientes={"cloudtrail": c}), e, [
        {"tipo": "AWS::IAM::Role", "logico": "FuncionAgenteServiceRole7F9E6BDA",
         "fisico": "semana19-computo-FuncionAgenteServiceRole-X", "stack": "semana19-computo"}], DESDE)
    r = V.check_cloudtrail(e)
    assert r["veredicto"] == "hallazgo" and r["roles_inesperados"] == ["intruso"]
    assert r["runtime_por_evento_y_rol"] == [
        {"evento": "Converse", "rol": "semana19-computo-FuncionAgenteServiceRole-X", "n": 2},
        {"evento": "InvokeModel", "rol": "intruso", "n": 1}]
    assert r["plano_de_control"] == [{"evento": "GetGuardrail", "rol": "semana19-lectura", "n": 1}]


def test_el_estado_bueno_no_cambia_al_correr_los_checks():
    e = estado_bueno()
    antes = copy.deepcopy(e)
    for f in V.CHECKS.values():
        f(e)
    assert e == antes


# ---------- recolectar end to end, with canned responses (one per read operation) ----------

class _Paginador:
    def __init__(self, respuesta):
        self._r = respuesta

    def paginate(self, **kw):
        return [self._r(**kw) if callable(self._r) else self._r]


class _Falso:
    """Answers each read operation from a dict; an operation not in the dict fails the test."""

    def __init__(self, respuestas):
        self._r = respuestas

    def __getattr__(self, op):
        if op not in self._r:
            raise AssertionError(f"unexpected call {op}")
        r = self._r[op]
        return lambda **kw: r(**kw) if callable(r) else r

    def get_paginator(self, op):
        return _Paginador(self._r[op])


VB_ARN = f"arn:aws:s3vectors:us-east-1:{CUENTA}:bucket/semana19-kb"
RECURSOS = [
    ("semana19-datos", "DocsKb", "AWS::S3::Bucket", "semana19-datos-docs"),
    ("semana19-datos", "PostgreSQL", "AWS::RDS::DBInstance", "semana19-bd"),
    ("semana19-datos", "VectoresKb", "AWS::S3Vectors::VectorBucket", VB_ARN),
    ("semana19-datos", "KbLegado", "AWS::Bedrock::KnowledgeBase", "KB1"),
    ("semana19-datos", "Secreto", "AWS::SecretsManager::Secret", "arn:secret"),
    ("semana19-computo", "LogsAgente", "AWS::Logs::LogGroup", "/semana19/agente"),
    ("semana19-computo", "Aprobacion", "AWS::StepFunctions::StateMachine", "arn:sm"),
    ("semana19-computo", "Tokens", "AWS::DynamoDB::Table", "semana19-tokens"),
    ("semana19-computo", "FuncionAgente", "AWS::Lambda::Function", "semana19-agente"),
    ("semana19-computo", "FuncionAgenteServiceRole7F", "AWS::IAM::Role", "semana19-computo-FuncionAgenteServiceRole-X"),
    ("semana19-computo", "Api", "AWS::ApiGatewayV2::Api", "a1"),
    ("semana19-ia", "Guardrail", "AWS::CloudFormation::CustomResource", "gr1"),
    ("semana19-ia", "PromptES", "AWS::Bedrock::Prompt", "arn:prompt"),
    ("semana19-gateway", "Gateway", "AWS::BedrockAgentCore::Gateway", "gw1"),
    ("semana19-base", "Vpc", "AWS::EC2::VPC", "vpc-1"),
]


def _clientes():
    kms = {"Encryption": {"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": LLAVE}}
    return {
        "cloudformation": _Falso({
            "list_stacks": {"StackSummaries": [{"StackName": s, "StackStatus": "CREATE_COMPLETE"}
                                               for s in sorted({r[0] for r in RECURSOS})] +
                            [{"StackName": "CDKToolkit", "StackStatus": "CREATE_COMPLETE"}]},
            "list_stack_resources": lambda StackName: {"StackResourceSummaries": [
                {"LogicalResourceId": lo, "ResourceType": t, "PhysicalResourceId": f} for s, lo, t, f in RECURSOS
                if s == StackName]}}),
        "kms": _Falso({"describe_key": {"KeyMetadata": {"Arn": LLAVE, "KeyId": LLAVE_ID}},
                       "get_key_policy": {"Policy": json.dumps({"Statement": []})}}),
        "s3": _Falso({
            "get_bucket_encryption": {"ServerSideEncryptionConfiguration": {"Rules": [
                {"ApplyServerSideEncryptionByDefault": kms["Encryption"]}]}},
            "get_public_access_block": {"PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}},
            "get_bucket_policy": {"Policy": json.dumps({"Statement": []})},
            "get_bucket_policy_status": {"PolicyStatus": {"IsPublic": False}}}),
        "logs": _Falso({"describe_log_groups": lambda logGroupNamePrefix: {"logGroups": [
            {"logGroupName": "/semana19/agente", "kmsKeyId": LLAVE}] if logGroupNamePrefix == "/semana19/agente" else [
            {"logGroupName": "/aws/lambda/semana19-agente"}]}}),
        "rds": _Falso({"describe_db_instances": {"DBInstances": [{
            "StorageEncrypted": True, "KmsKeyId": LLAVE, "PubliclyAccessible": False,
            "DBSubnetGroup": {"VpcId": "vpc-1", "Subnets": [{"SubnetIdentifier": "subnet-a"}]}}]}}),
        "stepfunctions": _Falso({"describe_state_machine": {"encryptionConfiguration": {"type": "AWS_OWNED_KEY"}}}),
        "dynamodb": _Falso({"describe_table": {"Table": {"SSEDescription": {"Status": "ENABLED", "SSEType": "KMS",
                                                                             "KMSMasterKeyArn": LLAVE}}}}),
        "bedrock": _Falso({"get_guardrail": {"kmsKeyArn": LLAVE}}),
        "bedrock-agent": _Falso({
            "get_knowledge_base": {"knowledgeBase": {"storageConfiguration": {
                "type": "S3_VECTORS", "s3VectorsConfiguration": {"vectorBucketArn": VB_ARN}}}},
            "list_data_sources": {"dataSourceSummaries": [{"dataSourceId": "DS1"}]},
            "get_data_source": {"dataSource": {}},
            "get_prompt": {"customerEncryptionKeyArn": LLAVE}}),
        "s3vectors": _Falso({"get_vector_bucket": {"vectorBucket": {"encryptionConfiguration": {"sseType": "AES256"}}}}),
        "secretsmanager": _Falso({"describe_secret": {"KmsKeyId": LLAVE}, "get_resource_policy": {}}),
        "bedrock-agentcore-control": _Falso({"get_gateway": {"gatewayId": "gw1", "kmsKeyArn": LLAVE,
                                                             "authorizerType": "CUSTOM_JWT"}}),
        "lambda": _Falso({
            "get_function_configuration": {"Environment": {"Variables": {"TABLA": "t"}}},
            "list_function_url_configs": {"FunctionUrlConfigs": []},
            "get_policy": {"Policy": json.dumps({"Statement": []})}}),
        "apigatewayv2": _Falso({"get_routes": {"Items": [{"RouteKey": "POST /consultas", "AuthorizationType": "JWT"}]}}),
        "ec2": _Falso({
            "describe_route_tables": {"RouteTables": [{"RouteTableId": "rtb-1", "Routes": [
                {"DestinationCidrBlock": "10.0.0.0/16", "GatewayId": "local"}],
                "Associations": [{"SubnetId": "subnet-a", "Main": True}]}]},
            "describe_internet_gateways": {"InternetGateways": []},
            "describe_nat_gateways": {"NatGateways": []},
            "describe_security_groups": {"SecurityGroups": [{"GroupId": "sg-1", "IpPermissions": []}]},
            "describe_vpc_endpoints": {"VpcEndpoints": [{"VpcEndpointId": "vpce-1", "ServiceName": "logs",
                                                         "PolicyDocument": LIMITADA}]},
            "describe_network_interfaces": {"NetworkInterfaces": [{"NetworkInterfaceId": "eni-1"}]}}),
        "cloudtrail": _Falso({"lookup_events": {"Events": [_evento("Converse",
                                                                   "semana19-computo-FuncionAgenteServiceRole-X")]}}),
    }


def test_recolectar_de_punta_a_punta_con_respuestas_fijas():
    """The canned stack is the synth as it is: the known exceptions (H10) are listed with their reason, and a log group
    Lambda created outside CloudFormation (no key) is a finding, because nothing documents it."""
    ll = V.Llamadas(clientes=_clientes())
    e = V.recolectar(ll, CUENTA, DESDE)
    r = V.informe(e, ll, identidad="semana19-lectura", desde=DESDE)
    assert r["veredictos"] == {"cifrado": "hallazgo", "publico": "ok", "rds_sin_ip_publica": "ok", "red": "ok",
                               "endpoints": "ok", "cloudtrail": "ok"}
    assert r["sin_permiso"] == []
    otras = {(x["tipo"], x["llave"], x["razon"] is not None) for x in r["checks"]["cifrado"]["otra_llave"]}
    assert otras == {("AWS::StepFunctions::StateMachine", "AWS owned key", True),
                     ("AWS::S3Vectors::VectorBucket", "SSE-S3", True),
                     ("AWS::Bedrock::KnowledgeBase", "SSE-S3", True),
                     ("AWS::Bedrock::DataSource", "AWS owned key", True),
                     ("AWS::Lambda::Function", "aws/lambda (AWS managed)", True),
                     ("AWS::Logs::LogGroup", "CloudWatch Logs default", False)}
    assert r["checks"]["cifrado"]["recursos"] == 14
    assert CUENTA not in json.dumps(r)
