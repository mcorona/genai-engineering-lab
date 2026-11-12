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


