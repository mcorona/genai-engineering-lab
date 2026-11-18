"""Week 19, activity 6: the tools Lambda (in the VPC, outside nothing: it is the only one that talks to the database).

Tools (called by the agent Lambda, ADR 0004; since activity 7 also by the AgentCore Gateway and by Bedrock Agents,
each format through its adapter in herramientas/adaptadores.py):
  describir_esquema   the legacy schema's tables and columns (copilot_ro, read-only)
  ejecutar_sql        one read-only SELECT, checked by the week 16 guard BEFORE any connection
  proponer_orden_compra  starts the approval state machine; writes nothing itself

Database access: the role copilot_ro with an IAM token (rds-db:connect for copilot_ro only), TLS with certificate
verification (the RDS CA bundle packaged with the function), statement_timeout, a read-only transaction and a row limit.
Everything external (connection, token, start of the state machine) is injected, so the tests run offline.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import ssl
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from agente.escritor_orden import validar_propuesta  # the writer's own checks: one contract on both sides
from herramientas import adaptadores as A
from herramientas.guardia_sql import ToolError, guard

ESQUEMA = "legado"
OBJETOS = frozenset({"almmst", "artmst", "artnot", "exidet", "ocpcab", "prvmst", "vtadia"})
USUARIO = "copilot_ro"  # the only database user this function ever uses
SKU_RE = re.compile(r"SKU-\d{4}")
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
    return {"filas": [[_valor(v) for v in f] for f in filas[:LIMITE_FILAS]], "truncado": truncado, "limite": LIMITE_FILAS}


def _valor(v):
    """pg8000 returns NUMERIC as Decimal and DATE/TIMESTAMP as date objects: the Lambda runtime cannot serialize them
    (the call would fail as a whole). Same conversion as week 13's tools (semana-13/herramientas/herramientas.py)."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, str) and len(v) > 200:
        return v[:200] + "…"
    return v


CAMPOS_PROPUESTA = frozenset({"sku", "cantidad", "motivo", "cedis", "fecha_requerida"})


def _revisar_contra_la_base(sku: str, cedis: int, conectar: Callable[[], Any]) -> None:
    """Read-only checks as copilot_ro, so the agent hears now what the workflow's insert would refuse later: the SKU and
    the CEDIS exist and the SKU has no pending order (po_one_pending_per_sku). The database checks all of it again."""
    con = conectar()
    try:
        con.run(f"SET statement_timeout = {TIMEOUT_MS}")
        sku_existe = con.run("SELECT 1 FROM legado.artmst WHERE art_cd = :sku", sku=sku)
        cedis_existe = con.run("SELECT 1 FROM legado.almmst WHERE alm_id = :cedis", cedis=cedis)
        pendiente = con.run("SELECT 1 FROM legado.ocpcab WHERE ocp_art = :sku AND ocp_sts = 'PENDING_APPROVAL'", sku=sku)
    finally:
        con.close()
    if not sku_existe:
        raise ToolError("sku_desconocido", f"No existe el artículo {sku}.")
    if not cedis_existe:
        raise ToolError("cedis_desconocido", f"No existe el CEDIS {cedis} (legado.almmst.alm_id).")
    if pendiente:
        raise ToolError("orden_pendiente_existente", f"{sku} ya tiene una orden en espera de aprobación.")


def proponer_orden_compra(entrada: dict, iniciar: Callable[[str], str], *, solicitante: str,
                          conectar: Callable[[], Any] | None = None) -> dict:
    """Starts the approval workflow and returns its id. It does not write the order (the workflow's writer does).
    The contract is week 19's (agente/capa_determinista.DEFINICION_PROPONER): sku SKU-dddd, cantidad 1..100000,
    motivo 1..200 characters, cedis (legado.almmst.alm_id) and fecha_requerida AAAA-MM-DD, the data the policy requires.
    Any other field is refused. `solicitante` is the token's subject, set by the agent Lambda, never by the model."""
    if not isinstance(entrada, dict) or set(entrada) - CAMPOS_PROPUESTA:
        raise ToolError("entrada_invalida", "solo se admiten " + ", ".join(sorted(CAMPOS_PROPUESTA)))
    if not isinstance(solicitante, str) or not 1 <= len(solicitante) <= 128:
        raise ToolError("sin_solicitante", "la propuesta no trae quien la pide")
    propuesta = {**entrada, "solicitante": solicitante}
    try:
        validar_propuesta(propuesta)
    except ValueError as error:
        raise ToolError("entrada_invalida", str(error)) from None
    if conectar is not None:
        _revisar_contra_la_base(propuesta["sku"], propuesta["cedis"], conectar)
    return {"solicitud_id": iniciar(json.dumps(propuesta, sort_keys=True, ensure_ascii=False)),
            "estado": "PENDING_APPROVAL",
            "nota": "Solo se registró la propuesta; una persona con el nivel de autorización del monto debe aprobarla."}


def token_iam(host: str, generar: Callable[..., str], region: str) -> str:
    """Token for copilot_ro only. It is generated locally and never logged or returned to the caller."""
    return generar(DBHostname=host, Port=PUERTO, DBUsername=USUARIO, Region=region)


def handler(event: dict, context: Any, *, conectar: Callable[[], Any] | None = None,
            iniciar: Callable[[str], str] | None = None) -> dict:
    """One entry for the three callers (herramientas/adaptadores.py): each format becomes the same internal call."""
    fmt = A.formato(event, context)
    if fmt == "directo":
        return _ejecutar(event, conectar, iniciar)
    try:
        interno = A.desde_gateway(event, context) if fmt == "gateway" else A.desde_agentes(event)
    except (ValueError, KeyError, TypeError):
        resultado = {"error": "entrada_invalida", "mensaje": "llamada mal formada"}
    else:
        resultado = _ejecutar(interno, conectar, iniciar)
    return A.respuesta_agentes(event, resultado) if fmt == "agentes" else resultado


def _ejecutar(event: dict, conectar: Callable[[], Any] | None, iniciar: Callable[[str], str] | None) -> dict:
    herramienta = event.get("herramienta")
    try:
        if herramienta == "describir_esquema":
            return describir_esquema(conectar)
        if herramienta == "ejecutar_sql":
            return ejecutar_sql(event["sql"], conectar)
        if herramienta == "proponer_orden_compra":
            return proponer_orden_compra(event["entrada"], iniciar, solicitante=event.get("solicitante"),
                                         conectar=conectar)
        return {"error": "herramienta_desconocida"}
    except ToolError as error:
        return {"error": error.kind, "mensaje": error.message}
