"""Week 19, activity 6: the order writer. It runs as `order_writer` (rds_iam, granted by the loader), inside the VPC.

The approval workflow invokes it twice (ADR 0011: this is the only step that writes purchase_orders): first to write the
proposal as PENDING_APPROVAL, then, after the approver's decision, to record it (APPROVED or REJECTED).
Connection: IAM token generated locally (never logged or returned), TLS verified against the RDS bundle in the asset.
The validation and the SQL live in agente/escritor_orden.py.
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

from agente.escritor_orden import decidir_orden, proponer_orden, validar_propuesta  # noqa: E402

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


def _objeto(valor, nombre: str) -> dict:
    if isinstance(valor, str):
        valor = json.loads(valor)
    if not isinstance(valor, dict):
        raise ValueError(f"{nombre} ausente o inválida")
    return valor


def handler_escritor(event, context, *, conectar=None):
    """event = {"operacion": "proponer", "solicitud": {...}} (first state of the workflow) or
    {"operacion": "decidir", "po_id": int, "decision": {...}} (after the approver's decision). Invalid input raises before
    any connection; the workflow then fails and nothing was written."""
    if not isinstance(event, dict) or event.get("operacion") not in ("proponer", "decidir"):
        raise ValueError("operacion debe ser proponer o decidir")
    if event["operacion"] == "proponer":
        solicitud = _objeto(event.get("solicitud"), "solicitud")
        validar_propuesta(solicitud)
    else:
        decision = _objeto(event.get("decision"), "decision")
    if conectar is None:
        host = os.environ["HOST_BD"]
        conectar = lambda: _conectar_real(host)  # noqa: E731
    if event["operacion"] == "proponer":
        return proponer_orden(solicitud, conectar)
    return decidir_orden(event.get("po_id"), decision, conectar)
