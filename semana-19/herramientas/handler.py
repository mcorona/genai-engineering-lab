"""Week 19, activity 6: the tools Lambda (in the VPC, outside nothing: it is the only one that talks to the database).

Tools (called by the agent Lambda, ADR 0004):
  describir_esquema   the legacy schema's tables and columns (copilot_ro, read-only)
  ejecutar_sql        one read-only SELECT, checked by the week 16 guard BEFORE any connection
  proponer_orden_compra  starts the approval state machine; writes nothing itself

Database access: the role copilot_ro with an IAM token (rds-db:connect for copilot_ro only), TLS with certificate
verification (the RDS CA bundle packaged with the function), statement_timeout, a read-only transaction and a row limit.
Everything external (connection, token, start of the state machine) is injected, so the tests run offline.
"""
from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any, Callable

from herramientas.guardia_sql import ToolError, guard

ESQUEMA = "legado"
OBJETOS = frozenset({"almmst", "artmst", "artnot", "exidet", "ocpcab", "prvmst", "vtadia"})
USUARIO = "copilot_ro"  # the only database user this function ever uses
LIMITE_FILAS = 200
TIMEOUT_MS = 5000
PUERTO = 5432
CA_BUNDLE = Path(__file__).resolve().parent / "rds-ca.pem"


def contexto_tls(cafile: str | Path = CA_BUNDLE) -> ssl.SSLContext:
    """TLS with the RDS CA bundle and hostname verification on: a connection without it is never made."""
    contexto = ssl.create_default_context(cafile=str(cafile))
    contexto.check_hostname = True
    contexto.verify_mode = ssl.CERT_REQUIRED
    return contexto


def describir_esquema(conectar: Callable[[], Any]) -> dict:
    con = conectar()
    try:
        filas = con.run(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :s ORDER BY table_name, ordinal_position", s=ESQUEMA)
    finally:
        con.close()
    tablas: dict[str, list[dict]] = {}
    for tabla, columna, tipo in filas:
        tablas.setdefault(tabla, []).append({"columna": columna, "tipo": tipo})
    return {"esquema": ESQUEMA, "tablas": tablas}


def ejecutar_sql(sql: str, conectar: Callable[[], Any]) -> dict:
    """The guard runs first. Only then a connection opens, in a read-only transaction with a statement timeout."""
    normalizado = guard(sql, ESQUEMA, set(OBJETOS))  # raises ToolError: no connection exists yet
    con = conectar()
    try:
        con.run(f"SET statement_timeout = {TIMEOUT_MS}")
        con.run("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        filas = con.run(f"SELECT * FROM ({normalizado}) AS consulta LIMIT {LIMITE_FILAS + 1}")
    finally:
        con.close()
    truncado = len(filas) > LIMITE_FILAS
    return {"filas": filas[:LIMITE_FILAS], "truncado": truncado, "limite": LIMITE_FILAS}


def proponer_orden_compra(entrada: dict, iniciar: Callable[[str], str]) -> dict:
    """Starts the approval workflow and returns its id. It does not write the order (the workflow's writer does)."""
    for campo in ("sku", "cantidad", "proveedor_id"):
        if campo not in entrada:
            raise ToolError("entrada_invalida", f"falta el campo {campo}")
    if not isinstance(entrada["cantidad"], int) or entrada["cantidad"] <= 0:
        raise ToolError("entrada_invalida", "cantidad debe ser un entero positivo")
    return {"solicitud_id": iniciar(json.dumps(entrada, sort_keys=True))}


def token_iam(host: str, generar: Callable[..., str], region: str) -> str:
    """Token for copilot_ro only. It is generated locally and never logged or returned to the caller."""
    return generar(DBHostname=host, Port=PUERTO, DBUsername=USUARIO, Region=region)


def handler(event: dict, context: Any, *, conectar: Callable[[], Any] | None = None,
            iniciar: Callable[[str], str] | None = None) -> dict:
    herramienta = event.get("herramienta")
    try:
        if herramienta == "describir_esquema":
            return describir_esquema(conectar)
        if herramienta == "ejecutar_sql":
            return ejecutar_sql(event["sql"], conectar)
        if herramienta == "proponer_orden_compra":
            return proponer_orden_compra(event["entrada"], iniciar)
        return {"error": "herramienta_desconocida"}
    except ToolError as error:
        return {"error": error.kind, "mensaje": error.message}
