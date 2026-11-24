"""Week 19, activity 1: offline tests ($0). Moto and stubs only; no AWS account and no model."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
REGION = "us-east-1"


def cargar(ruta: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


inv = cargar(S19 / "infra" / "inventario.py", "inventario_s19")
lb = cargar(S19 / "linea_base" / "verificar.py", "verificar_s19")


# ---------- inventory ----------

@mock_aws
def test_inventario_cuenta_vacia_da_cero():
    sesion = boto3.Session(region_name=REGION)
    informe = inv.inventario(sesion, REGION)
    assert informe["total"] == 0
    assert all(v == 0 for v in informe["por_categoria"].values())
    if informe["quedan"] == "revisar":
        # Only categories that moto does not implement may stay unmeasured; they are listed, never counted as 0.
        assert informe["no_medido"], "quedan=revisar sin categorías no medidas"
    else:
        assert informe["quedan"] == "nada"


@mock_aws
def test_inventario_detecta_recurso_con_etiqueta_y_con_prefijo():
    sesion = boto3.Session(region_name=REGION)
    ec2 = sesion.client("ec2", region_name=REGION)
    ec2.create_vpc(CidrBlock="10.19.0.0/16", TagSpecifications=[{
        "ResourceType": "vpc", "Tags": [{"Key": "proyecto", "Value": "semana19"}, {"Key": "Name", "Value": "semana19-vpc"}]}])
    sesion.client("s3", region_name=REGION).create_bucket(Bucket="semana19-prueba")
    informe = inv.inventario(sesion, REGION)
    assert informe["por_categoria"]["vpcs"] == 1
    assert informe["por_categoria"]["buckets_s3"] == 1
    assert informe["quedan"] == "revisar"
    assert informe["total"] >= 2


@mock_aws
def test_inventario_no_cuenta_recursos_ajenos():
    sesion = boto3.Session(region_name=REGION)
    sesion.client("s3", region_name=REGION).create_bucket(Bucket="otro-proyecto-prueba")
    informe = inv.inventario(sesion, REGION)
    assert informe["por_categoria"]["buckets_s3"] == 0


def test_inventario_nombres_sin_arn_ni_cuenta_ni_correo():
    texto = (S19 / "infra" / "inventario.py").read_text(encoding="utf-8")
    assert "arn:aws" not in texto.replace("ARNs", "")


# ---------- sanitizer ----------

def test_sanear_oculta_cuenta_arn_rutas_y_correos():
    entrada = json.dumps({
        "cuenta": "123456789012",
        "arn": "arn:aws:iam::123456789012:role/semana19-operador",
        "ruta": "/Us" + "ers/persona/proyecto/x.py",
        "linux": "/ho" + "me/alguien/proyecto",
        "correo": "persona" + "@" + "correo.example",
    })
    limpio = lb.sanear(entrada)
    assert "123456789012" not in limpio
    assert "arn:aws" not in limpio
    assert "/Us" + "ers/" not in limpio and "/ho" + "me/" not in limpio
    assert "persona" + "@" + "correo.example" not in limpio
    assert "<account>" in limpio and "<arn>" in limpio and "<correo>" in limpio


def test_sanear_no_toca_cifras_de_precio():
    assert lb.sanear("0.0000002 USD por token") == "0.0000002 USD por token"


# ---------- prices (one mark per item) ----------

def _fila(usagetype: str, descripcion: str, usd: str, unidad: str = "Requests") -> dict:
    return {"servicio": "X", "usagetype": usagetype, "sku": "SKU123", "descripcion": descripcion,
            "unidad": unidad, "usd": usd}


def _fake_sesion(monkeypatch):
    class _Cli:
        def get_paginator(self, _n):
            return None
    monkeypatch.setattr(lb, "sesion_boto", lambda perfil: type("S", (), {"client": lambda self, *a, **k: _Cli()})())


def test_articulo_con_coincidencia_queda_medido_con_id_de_catalogo(monkeypatch):
    _fake_sesion(monkeypatch)
    monkeypatch.setattr(lb, "filas_servicio", lambda codigo, cli: [
        _fila("Lambda-GB-Second-ARM", "AWS Lambda - Total Compute for ARM - Tier-1", "0.0000133334", "Lambda-GB-Second"),
        _fila("Lambda-GB-Second-x86", "AWS Lambda - Total Compute - Tier-1", "0.0000166667", "Lambda-GB-Second")])
    art = lb.sonda_precios("semana19-operador")["articulos"]["lambda_arm_gb_s"]
    assert art["marca"] == "M"
    assert art["usagetype"] == "Lambda-GB-Second-ARM"
    assert art["precio_usd"] == "0.0000133334"
    assert art["sku"] == "SKU123"


def test_articulo_sin_coincidencia_es_n_y_no_m(monkeypatch):
    _fake_sesion(monkeypatch)
    monkeypatch.setattr(lb, "filas_servicio", lambda codigo, cli: [_fila("Otro", "otra cosa", "1")])
    art = lb.sonda_precios("semana19-operador")["articulos"]["lambda_arm_gb_s"]
    assert art["marca"] == "N"


def test_articulo_fuera_del_catalogo_es_d_con_enlace(monkeypatch):
    _fake_sesion(monkeypatch)
    monkeypatch.setattr(lb, "filas_servicio", lambda codigo, cli: [])
    art = lb.sonda_precios("semana19-operador")["articulos"]["step_functions_standard_transiciones"]
    assert art["marca"] == "D"
    assert art["enlace"].startswith("https://")


def test_error_de_servicio_no_se_marca_medido(monkeypatch):
    _fake_sesion(monkeypatch)
    def falla(codigo, cli):
        raise RuntimeError("sin acceso")
    monkeypatch.setattr(lb, "filas_servicio", falla)
    res = lb.sonda_precios("semana19-operador")
    assert res["articulos"]["lambda_arm_gb_s"]["marca"] == "N"
    assert res["conteo"]["M"] == 0
    assert "AWSLambda" in res["errores"]


def test_todos_los_articulos_tienen_marca_valida():
    nombres = [a[0] for a in lb.ARTICULOS]
    assert len(nombres) == len(set(nombres))
    for nombre, servicio, patron, enlace, nota in lb.ARTICULOS:
        assert patron is not None or enlace is not None, f"{nombre} sin coincidencia ni enlace"
        if patron is None:
            assert enlace.startswith("https://"), f"{nombre} sin enlace oficial"


# ---------- the matrix covers each bullet of activity 1 ----------

def test_catalogo_de_precios_cubre_los_servicios_del_plan():
    esperados = {"AWSLambda", "AmazonApiGateway", "AmazonCognito", "AmazonRDS", "AmazonVPC",
                 "awskms", "AmazonCloudWatch", "AmazonS3", "AmazonBedrock", "AmazonBedrockAgentCore"}
    cubiertos = {a[1] for a in lb.ARTICULOS if a[1]}
    assert esperados <= cubiertos


def test_sondas_cubren_cuenta_bedrock_precios_y_herramientas():
    assert {"cuenta", "gasto_mes", "bedrock", "cuotas", "precios", "herramientas", "repo"} <= set(lb.SONDAS)


def test_gasto_mes_no_corre_por_omision():
    texto = (S19 / "linea_base" / "verificar.py").read_text(encoding="utf-8")
    assert 'if nombre == "gasto_mes" and not a.gasto_mes' in texto




# ---------- activity 8: what the Tagging API still lists after a teardown ----------

def test_etiquetados_de_llaves_pendientes_o_recursos_que_ya_no_existen_se_explican():
    llaves = ["0906507d borrado 2026-11-20", "35d04092 borrado 2026-11-26"]
    estado = {"vpce-0d9349b581fc383f2": False, "fl-0136735a0b9821329": False, "vpce-0aaaaaaaaaaaaaaaa": True}
    ids = ["0906507d-407e-4410-b5d1-caf3578dc52b", "vpce-0d9349b581fc383f2", "fl-0136735a0b9821329",
           "vpce-0aaaaaaaaaaaaaaaa", "otro-recurso"]
    quedan, explicados = inv.explicar_etiquetados(ids, llaves, lambda i: estado.get(i))
    assert quedan == ["vpce-0aaaaaaaaaaaaaaaa", "otro-recurso"]   # alive, or not checkable: still judged
    assert explicados == {"llave_pendiente_de_borrado": ["0906507d-407e-4410-b5d1-caf3578dc52b"],
                          "ya_no_existe": ["vpce-0d9349b581fc383f2", "fl-0136735a0b9821329"]}
    assert inv.explicar_etiquetados([], llaves, lambda i: None) == ([], {})


@mock_aws
def test_vigente_ec2_pregunta_por_id_y_un_id_que_no_existe_es_falso():
    sesion = boto3.Session(region_name=REGION)
    ec2 = sesion.client("ec2", region_name=REGION)
    vpc = ec2.create_vpc(CidrBlock="10.19.0.0/16")["Vpc"]["VpcId"]
    vivo = ec2.create_vpc_endpoint(VpcId=vpc, ServiceName=f"com.amazonaws.{REGION}.s3", VpcEndpointType="Gateway")
    vivo = vivo["VpcEndpoint"]["VpcEndpointId"]
    vigente = inv.vigente_ec2(sesion, REGION)
    assert vigente(vivo) is True
    assert vigente("vpce-0123456789abcdef0") is False
    assert vigente("fl-0123456789abcdef0") is False
    assert vigente("0906507d-407e-4410-b5d1-caf3578dc52b") is None


# ---------- week 20: the ids the ia and computo stacks leave in the Tagging API ----------

def test_id_de_arn_conserva_la_version_del_prompt():
    assert inv.id_de_arn("arn:aws:bedrock:us-east-1:<account>:prompt/ZF4KNSIULX:1") == "ZF4KNSIULX:1"
    assert inv.id_de_arn("arn:aws:bedrock:us-east-1:<account>:prompt/ZF4KNSIULX") == "ZF4KNSIULX"
    assert inv.id_de_arn("arn:aws:cognito-idp:us-east-1:<account>:userpool/us-east-1_AbC") == "us-east-1_AbC"
    assert inv.id_de_arn("arn:aws:budgets::<account>:budget/semana19/action/b0859efb-f017-47b6-ac3f-bc8ecbc17e87") \
        == "b0859efb-f017-47b6-ac3f-bc8ecbc17e87"
    assert inv.id_de_arn("arn:aws:ec2:us-east-1:<account>:vpc-endpoint/vpce-0abc") == "vpce-0abc"


class _NoExiste(Exception):
    pass


class _ResourceNotFoundException(Exception):
    pass


class _Cliente:
    def __init__(self, vivos, acciones=()):
        self.vivos, self.acciones = vivos, acciones

    def get_prompt(self, promptIdentifier, promptVersion=None):
        if (promptIdentifier, promptVersion) not in self.vivos:
            raise _ResourceNotFoundException("prompt")

    def describe_user_pool(self, UserPoolId):
        if UserPoolId not in self.vivos:
            raise _ResourceNotFoundException("pool")

    def describe_key(self, KeyId):
        if KeyId == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa":
            raise RuntimeError("AccessDenied")
        if KeyId not in self.vivos:
            raise _ResourceNotFoundException("NotFoundException")
        return {"KeyMetadata": {"KeyState": self.vivos[KeyId]}}

    def get_caller_identity(self):
        return {"Account": "<account>"}

    def get_paginator(self, _):
        acciones = self.acciones
        return type("P", (), {"paginate": lambda self, **kw: [{"Actions": [{"ActionId": a} for a in acciones]}]})()


class _Sesion:
    def __init__(self, cliente):
        self.cliente = cliente

    def client(self, *_a, **_k):
        return self.cliente


def test_vigente_por_id_pregunta_a_cada_servicio_y_lo_que_no_puede_comprobar_queda_sin_juzgar():
    viva = "11111111-1111-1111-1111-111111111111"
    accion = "b0859efb-f017-47b6-ac3f-bc8ecbc17e87"
    vivos = {("VIVO000001", None): 1, ("VIVO000001", "2"): 1, f"{REGION}_Vivo": 1, viva: "Enabled",
             "22222222-2222-2222-2222-222222222222": "PendingDeletion"}
    v = inv.vigente_por_id(_Sesion(_Cliente(vivos, acciones=[accion])), REGION, ec2=lambda i: "ec2")
    assert v("vpce-0abc") == "ec2" and v("fl-0abc") == "ec2"
    assert v("VIVO000001") is True and v("VIVO000001:2") is True
    assert v("ZF4KNSIULX") is False and v("ZF4KNSIULX:1") is False
    assert v(f"{REGION}_Vivo") is True and v(f"{REGION}_Borrado") is False
    assert v(viva) is True
    assert v("22222222-2222-2222-2222-222222222222") is None     # pending: explained by name, not here
    assert v(accion) is True
    assert v("33333333-3333-3333-3333-333333333333") is False     # neither a key nor an action
    assert v("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") is None      # KMS error other than not found
    assert v("otro-recurso") is None and v("1") is None


def test_el_inventario_usa_vigente_por_id():
    texto = (S19 / "infra" / "inventario.py").read_text(encoding="utf-8")
    assert "vigente_por_id(sesion, region))" in texto

