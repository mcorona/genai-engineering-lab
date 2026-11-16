"""Week 19, activity 6: the order writer. It runs as `order_writer` (rds_iam, granted by the loader), inside the VPC.

The approval workflow invokes it only after an approval (ADR 0011: this is the only step that writes purchase_orders).
Connection: IAM token generated locally (never logged or returned), TLS verified against the RDS bundle in the asset.
The input is the request the agent proposed: {"sku": "SKU-dddd", "cantidad": int, "motivo": str}, or the same as a JSON
string. The validation lives in agente/escritor_orden.py.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "infra" / "loader" / "vendor"))  # pg8000, vendored with the loader (pure Python)
sys.path.insert(0, str(RAIZ))

from agente.escritor_orden import escribir_orden  # noqa: E402

USUARIO = "order_writer"
BASE = "postgres"
PUERTO = 5432
CA = RAIZ / "infra" / "loader" / "rds-ca.pem"


def _conectar_real(host: str):
    import boto3
    import pg8000.native as pg

    token = boto3.client("rds").generate_db_auth_token(
        DBHostname=host, Port=PUERTO, DBUsername=USUARIO, Region=os.environ["AWS_REGION"])
    contexto = ssl.create_default_context(cafile=str(CA))
    contexto.check_hostname = True
    contexto.verify_mode = ssl.CERT_REQUIRED
    return pg.Connection(USUARIO, host=host, port=PUERTO, database=BASE, password=token, ssl_context=contexto)


def handler_escritor(event, context, *, conectar=None):
    solicitud = event.get("solicitud") if isinstance(event, dict) else None
    if isinstance(solicitud, str):
        solicitud = json.loads(solicitud)
    if not isinstance(solicitud, dict):
        raise ValueError("solicitud ausente o inválida")
    if conectar is None:
        host = os.environ["HOST_BD"]
        conectar = lambda: _conectar_real(host)  # noqa: E731
    return escribir_orden(solicitud, conectar)
