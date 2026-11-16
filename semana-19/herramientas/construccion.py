"""Week 19, activity 6: the tools Lambda's real collaborators, built from its environment (fail closed).

Connection: an IAM token for `copilot_ro` only, generated locally, TLS verified against the RDS bundle in the asset.
Starter: starts the approval state machine (ARN_APROBACION) with the proposed order; the write happens there, not here.
Missing environment is an error before any client exists.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "infra" / "loader" / "vendor"))  # pg8000, vendored with the loader (pure Python)
sys.path.insert(0, str(RAIZ))

from herramientas import handler as H  # noqa: E402

REQUERIDAS = ("HOST_BD", "ARN_APROBACION", "AWS_REGION")
BASE = "postgres"


def exigir_entorno(entorno) -> None:
    faltan = [nombre for nombre in REQUERIDAS if not entorno.get(nombre)]
    if faltan:
        raise RuntimeError("falta el entorno de la función de herramientas: " + ", ".join(faltan))


def conectar_real(host: str, region: str, generar=None):
    if generar is None:
        import boto3
        generar = boto3.client("rds").generate_db_auth_token
    import pg8000.native as pg

    token = H.token_iam(host, generar, region)
    return pg.Connection(H.USUARIO, host=host, port=H.PUERTO, database=BASE, password=token,
                         ssl_context=H.contexto_tls())


def iniciar_real(arn: str, cliente=None):
    def iniciar(entrada_json: str) -> str:
        nonlocal cliente
        if cliente is None:  # created on first use, never at construction
            import boto3
            cliente = boto3.client("stepfunctions")
        id_solicitud = str(uuid.uuid4())
        cliente.start_execution(stateMachineArn=arn, name=id_solicitud,
                                input=json.dumps({"id": id_solicitud, "solicitud": json.loads(entrada_json)}))
        return id_solicitud

    return iniciar


def construir(entorno=None) -> dict:
    entorno = os.environ if entorno is None else entorno
    exigir_entorno(entorno)
    host, region = entorno["HOST_BD"], entorno["AWS_REGION"]
    return {"conectar": lambda: conectar_real(host, region), "iniciar": iniciar_real(entorno["ARN_APROBACION"])}


def handler_lambda(event: dict, context) -> dict:
    return H.handler(event, context, **construir())
