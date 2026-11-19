"""Week 19, activity 4: one-shot loader. Runs inside the VPC, never from the Mac.

Loads, in this order, and every step is idempotent (running it twice leaves the same data):
  1. the copilot schema (ddl_copilot.sql), only if the tables do not exist yet;
  2. the CI seed 42 (seed42_datos.sql.gz): TRUNCATE + INSERT in one transaction;
  3. the legado schema (legado.sql, drops and recreates its views) and artnot.sql (drops and recreates its table);
  4. the roles (created before step 3, granted after it): copilot_ro (read-only, IAM authentication, search_path legado) and order_writer (approval step only).
  5. optional, when the event carries docs_bucket: the legacy dictionary as documents in the KB bucket. The KB ingestion job
     is started from the operator terminal (no bedrock-agent endpoint in the VPC).

Credentials: the master password is read from Secrets Manager with the Lambda role; it is never logged or returned.
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import ssl
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))

import time  # noqa: E402

import boto3  # noqa: E402  (provided by the Lambda runtime)
from botocore.config import Config  # noqa: E402
import pg8000.native as pg  # noqa: E402  (vendored, pure Python)

# Table, columns and the SQL cast for each column (the dump is text; the cast happens in the database).
TABLAS = [
    ("suppliers", ["supplier_id", "name", "country", "lead_time_days"], ["int", "text", "text", "int"]),
    ("warehouses", ["warehouse_id", "name", "city"], ["int", "text", "text"]),
    ("products", ["sku", "name", "category", "unit_cost", "reorder_point", "critical", "supplier_id"],
     ["text", "text", "text", "numeric", "int", "boolean", "int"]),
    ("stock", ["sku", "warehouse_id", "on_hand"], ["text", "int", "int"]),
    ("sales_daily", ["sku", "day", "units"], ["text", "date", "int"]),
]
TAMANO_LOTE = 5000
BASE = "postgres"
PUERTO = 5432


INICIO = time.time()


def _paso(texto: str) -> None:
    """Progress marker in the function log (no secrets): shows where a run stops."""
    print(f"[cargador {time.time() - INICIO:6.1f}s] {texto}", flush=True)


def _secreto(arn: str) -> dict:
    _paso("leyendo el secreto")
    cliente = boto3.client("secretsmanager", config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}))
    return json.loads(cliente.get_secret_value(SecretId=arn)["SecretString"])


def _conectar(host: str, usuario: str, clave: str) -> pg.Connection:
    contexto = ssl.create_default_context(cafile=str(HERE / "rds-ca.pem"))
    contexto.check_hostname = True
    _paso(f"conectando a la base en {host}")
    return pg.Connection(usuario, host=host, port=PUERTO, database=BASE, password=clave, ssl_context=contexto)


def _leer_seed() -> dict[str, list[list[str]]]:
    datos: dict[str, list[list[str]]] = {}
    actual = None
    with gzip.open(HERE / "seed42_datos.sql.gz", "rt", encoding="utf-8") as f:
        for linea in f:
            linea = linea.rstrip("\n")
            if linea.startswith("COPY "):
                actual = linea.split()[1].split("(")[0]
                datos[actual] = []
            elif linea == "\\.":
                actual = None
            elif actual and linea:
                datos[actual].append(linea.split("\t"))
    return datos


def _existe_esquema_copilot(con: pg.Connection) -> bool:
    fila = con.run("SELECT to_regclass('public.suppliers') IS NOT NULL")
    return bool(fila[0][0])


def build_insert_sql(tabla: str, columnas: list[str], tipos: list[str]) -> str:
    """INSERT that reads text arrays with unnest and casts each column in the database."""
    alias = [f"a{i}" for i in range(len(columnas))]
    entradas = ", ".join(f":{a}::text[]" for a in alias)
    seleccion = ", ".join(f"{a}::{t}" for a, t in zip(alias, tipos))
    return (f"INSERT INTO {tabla} ({', '.join(columnas)}) "
            f"SELECT {seleccion} FROM unnest({entradas}) AS t({', '.join(alias)})")


def _cargar_seed(con: pg.Connection) -> dict[str, int]:
    seed = _leer_seed()
    conteos = {}
    con.run("BEGIN")
    try:
        con.run("TRUNCATE purchase_orders, sales_daily, stock, products, warehouses, suppliers RESTART IDENTITY CASCADE")
        for tabla, columnas, tipos in TABLAS:
            filas = seed[tabla]
            for inicio in range(0, len(filas), TAMANO_LOTE):
                lote = filas[inicio:inicio + TAMANO_LOTE]
                arreglos = [[fila[i] for fila in lote] for i in range(len(columnas))]
                params = {f"a{i}": arreglos[i] for i in range(len(columnas))}
                sql = build_insert_sql(tabla, columnas, tipos)
                con.run(sql, **params)
            # secuencias de las columnas SERIAL, insertadas con id explícito
            conteos[tabla] = len(filas)
        for tabla, pk in (("suppliers", "supplier_id"), ("warehouses", "warehouse_id")):
            con.run(f"SELECT setval(pg_get_serial_sequence('{tabla}', '{pk}'), (SELECT MAX({pk}) FROM {tabla}))")
        con.run("COMMIT")
    except Exception:
        con.run("ROLLBACK")
        raise
    return conteos


ROLES_CREAR = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'copilot_ro') THEN CREATE ROLE copilot_ro LOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'order_writer') THEN CREATE ROLE order_writer LOGIN; END IF;
END $$;
GRANT rds_iam TO copilot_ro;
GRANT rds_iam TO order_writer;
ALTER ROLE copilot_ro SET default_transaction_read_only = on;
ALTER ROLE copilot_ro SET search_path = legado;
"""

# Grants that need the legado schema or the copilot tables: run after legado.sql and artnot.sql.
ROLES_PERMISOS = """
GRANT USAGE ON SCHEMA public TO order_writer;
GRANT SELECT ON suppliers, warehouses, products, stock, sales_daily TO order_writer;
GRANT SELECT, INSERT, UPDATE ON purchase_orders TO order_writer;
GRANT USAGE ON SEQUENCE purchase_orders_po_id_seq TO order_writer;
"""
# The INSERT of a pending order takes its po_id from the SERIAL sequence: without USAGE it is refused (live, activity 6:
# "permission denied for sequence purchase_orders_po_id_seq"). No SELECT or UPDATE on the sequence (no setval).


def documentos_del_diccionario() -> dict[str, str]:
    """One markdown document per legacy view, from the week 10 dictionary (the week 16 audit's source)."""
    diccionario = json.loads((HERE / "diccionario_legado.json").read_text(encoding="utf-8"))
    docs = {}
    for vista, info in diccionario.items():
        lineas = [f"# legado.{vista} ({info.get('original', '')})", "", info.get("descripcion", ""), "", "## Columnas", ""]
        for columna, significado in info.get("columnas", {}).items():
            lineas.append(f"- **{columna}**: {significado}")
        docs[f"docs/legado_{vista}.md"] = "\n".join(lineas) + "\n"
    return docs


def subir_documentos(bucket: str) -> int:
    s3 = boto3.client("s3", config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}))
    docs = documentos_del_diccionario()
    for clave, texto in docs.items():
        s3.put_object(Bucket=bucket, Key=clave, Body=texto.encode("utf-8"), ContentType="text/markdown")
    return len(docs)


def _codigo_sql(error: Exception) -> str:
    """SQLSTATE of a server error (pg8000 keeps the fields in args[0]); '?' when unknown."""
    try:
        return str(error.args[0].get("C", "?"))
    except (AttributeError, IndexError, TypeError):
        return "?"


def _pruebas_permisos(con: pg.Connection) -> dict:
    """Live check of copilot_ro's privileges (activity 4). The master user switches to copilot_ro inside a
    transaction that is always rolled back. Limit: SET ROLE does not apply the ALTER ROLE defaults, so the denial
    below comes from privileges, not from default_transaction_read_only (the login path is not exercised here)."""
    resultado: dict = {"modo": "pruebas_permisos"}
    con.run("GRANT copilot_ro TO CURRENT_USER")  # SET ROLE needs membership; revoked below
    try:
        con.run("BEGIN")
        try:
            con.run("SET LOCAL ROLE copilot_ro")
            resultado["select_legado_prvmst"] = con.run("SELECT count(*) FROM legado.prvmst")[0][0]
            try:
                con.run("INSERT INTO legado.artnot (not_id, not_art, not_txt, not_fch) "
                        "VALUES (999999, 'X', 'x', '2026-01-01')")
                resultado["insert_legado_artnot"] = "PERMITIDO"
            except Exception as error:  # noqa: BLE001 - any refusal counts as a denial
                resultado["insert_legado_artnot"] = "DENEGADO"
                resultado["sqlstate"] = _codigo_sql(error)
        finally:
            con.run("ROLLBACK")
    finally:
        con.run("REVOKE copilot_ro FROM CURRENT_USER")
    _paso("pruebas de permisos terminadas")
    return resultado


COLUMNAS_ORDEN = ("po_id", "sku", "status", "requested_by", "decided_by", "decided_level", "required_level")
ROLES_A_REVISAR = ("copilot_ro", "order_writer")


def _leer_ordenes(con: pg.Connection, po_ids) -> dict:
    """Activity 8, approval end to end: the orders of the test, read in a READ ONLY transaction that is always rolled
    back, plus who may write the table. Only bound parameters; at most 20 ids; no other column leaves the database."""
    if not isinstance(po_ids, list) or not 1 <= len(po_ids) <= 20 or not all(
            isinstance(i, int) and not isinstance(i, bool) and i > 0 for i in po_ids):
        raise ValueError("po_ids debe ser una lista de 1 a 20 enteros positivos")
    con.run("BEGIN")
    try:
        con.run("SET TRANSACTION READ ONLY")
        filas = con.run(f"SELECT {', '.join(COLUMNAS_ORDEN)} FROM public.purchase_orders "
                        "WHERE po_id = ANY(CAST(:ids AS int[])) ORDER BY po_id", ids=po_ids)
        por_estado = con.run("SELECT status, count(*) FROM public.purchase_orders GROUP BY status ORDER BY status")
        privilegios = {}
        for rol in ROLES_A_REVISAR:
            privilegios[rol] = {p: bool(con.run("SELECT has_table_privilege(:r, 'public.purchase_orders', :p)",
                                                 r=rol, p=p)[0][0]) for p in ("SELECT", "INSERT", "UPDATE", "DELETE")}
    finally:
        con.run("ROLLBACK")
    _paso("órdenes leídas (solo lectura)")
    return {"modo": "leer_ordenes", "solo_lectura": True,
            "ordenes": [dict(zip(COLUMNAS_ORDEN, f)) for f in filas],
            "por_estado": {str(e): int(n) for e, n in por_estado}, "privilegios": privilegios}


MAX_CONSULTAS_ESPERADAS = 40
MAX_FILAS_ESPERADAS = 200
TIMEOUT_ESPERADOS_MS = 15000


def _valor(v):
    """The tools function's conversion (herramientas/handler._valor): NUMERIC to float, dates to ISO text."""
    import datetime as dt
    from decimal import Decimal
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _es_consulta(sql) -> bool:
    texto = sql.strip().rstrip(";").strip() if isinstance(sql, str) else ""
    return bool(texto) and ";" not in texto and texto.split(None, 1)[0].upper() in ("SELECT", "WITH")


def _esperados(con: pg.Connection, consultas) -> dict:
    """Activity 8: the golden keys' expected rows recomputed on this database, as week 13's CI recomputes them on its
    own (semana-13/ci/eval_ci.py: each key's sql_ref on the copilot schema). copilot_ro cannot read that schema, so the
    master user runs them here, each in a READ ONLY transaction with a statement timeout that is always rolled back.
    Only single SELECT or WITH statements; at most 40, and at most 200 rows each."""
    if not isinstance(consultas, dict) or not 1 <= len(consultas) <= MAX_CONSULTAS_ESPERADAS or not all(
            isinstance(k, str) and _es_consulta(v) for k, v in consultas.items()):
        raise ValueError("consultas debe mapear de 1 a 40 claves a una sola sentencia SELECT o WITH")
    salida = {}
    for clave, sql in consultas.items():
        con.run("BEGIN")
        try:
            con.run("SET TRANSACTION READ ONLY")
            con.run(f"SET LOCAL statement_timeout = {TIMEOUT_ESPERADOS_MS}")
            con.run("SET LOCAL search_path = public")
            filas = con.run(sql.strip().rstrip(";"))
        finally:
            con.run("ROLLBACK")
        if len(filas) > MAX_FILAS_ESPERADAS:
            raise ValueError(f"{clave}: más de {MAX_FILAS_ESPERADAS} filas")
        salida[clave] = [[_valor(v) for v in f] for f in filas]
    _paso(f"esperados recalculados: {len(salida)}")
    return {"modo": "esperados", "solo_lectura": True, "esperados": salida}


MODOS = ("pruebas_permisos", "leer_ordenes", "esperados", "permisos")


def handler(event, context):
    """event = {"secret_arn", "db_host", optional "docs_bucket"}: stack outputs, no secret in config.
    Activity 8 modes, both read-only: "leer_ordenes" takes "po_ids"; "esperados" takes "consultas" {clave: sql}.
    No "modo" is the full load. Any other "modo" is refused before the secret is read: in activity 8 a loader older
    than the caller took "esperados" for a full load and reloaded the seed (TRUNCATE included)."""
    if event.get("modo") is not None and event["modo"] not in MODOS:
        raise ValueError(f"modo desconocido: {event['modo']!r}; modos: {', '.join(MODOS)} o ninguno (carga completa)")
    secreto = _secreto(event["secret_arn"])
    con = _conectar(event["db_host"], secreto["username"], secreto["password"])
    try:
        if event.get("modo") == "pruebas_permisos":
            return _pruebas_permisos(con)
        if event.get("modo") == "leer_ordenes":
            return _leer_ordenes(con, event.get("po_ids"))
        if event.get("modo") == "esperados":
            return _esperados(con, event.get("consultas"))
        if event.get("modo") == "permisos":
            # Only the roles and their grants, on a database already loaded: no TRUNCATE, no seed, no legado reload.
            if not _existe_esquema_copilot(con):
                raise RuntimeError("la base no tiene el esquema copilot: corre el cargador completo primero")
            con.run(ROLES_CREAR)
            con.run(ROLES_PERMISOS)
            _paso("permisos aplicados")
            return {"modo": "permisos", "ok": True}
        resumen = {"esquema_creado": False}
        _paso("conectado; revisando esquema")
        if not _existe_esquema_copilot(con):
            con.run((HERE / "ddl_copilot.sql").read_text(encoding="utf-8"))
            resumen["esquema_creado"] = True
        _paso("cargando seed 42")
        resumen["filas"] = _cargar_seed(con)
        _paso("seed cargado; roles")
        con.run(ROLES_CREAR)
        _paso("legado y artnot")
        con.run((HERE / "legado.sql").read_text(encoding="utf-8"))
        con.run((HERE / "artnot.sql").read_text(encoding="utf-8"))
        con.run(ROLES_PERMISOS)
        resumen["ok"] = True
        _paso("base lista")
        if event.get("docs_bucket"):
            _paso("subiendo documentos a la KB")
            resumen["documentos"] = subir_documentos(event["docs_bucket"])
            _paso("documentos subidos")
        return resumen
    finally:
        con.close()
