"""Week 19, activity 4: one-shot loader. Runs inside the VPC, never from the Mac.

Loads, in this order, and every step is idempotent (running it twice leaves the same data):
  1. the copilot schema (ddl_copilot.sql), only if the tables do not exist yet;
  2. the CI seed 42 (seed42_datos.sql.gz): TRUNCATE + INSERT in one transaction;
  3. the legado schema (legado.sql, drops and recreates its views) and artnot.sql (drops and recreates its table);
  4. the roles (created before step 3, granted after it): copilot_ro (read-only, IAM authentication, search_path legado) and order_writer (approval step only).
  5. optional, when the event carries them: the legacy dictionary as documents in the KB bucket, and the KB ingestion job.

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

import boto3  # noqa: E402  (provided by the Lambda runtime)
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


def _secreto(arn: str) -> dict:
    return json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"])


def _conectar(host: str, usuario: str, clave: str) -> pg.Connection:
    contexto = ssl.create_default_context(cafile=str(HERE / "rds-ca.pem"))
    contexto.check_hostname = True
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
"""


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
    s3 = boto3.client("s3")
    docs = documentos_del_diccionario()
    for clave, texto in docs.items():
        s3.put_object(Bucket=bucket, Key=clave, Body=texto.encode("utf-8"), ContentType="text/markdown")
    return len(docs)


def lanzar_ingesta(kb_id: str, ds_id: str) -> str:
    trabajo = boto3.client("bedrock-agent").start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)
    return trabajo["ingestionJob"]["ingestionJobId"]


def handler(event, context):
    """event = {"secret_arn", "db_host", optional "docs_bucket", "kb_id", "ds_id"}: stack outputs, no secret in config."""
    secreto = _secreto(event["secret_arn"])
    con = _conectar(event["db_host"], secreto["username"], secreto["password"])
    try:
        resumen = {"esquema_creado": False}
        if not _existe_esquema_copilot(con):
            con.run((HERE / "ddl_copilot.sql").read_text(encoding="utf-8"))
            resumen["esquema_creado"] = True
        resumen["filas"] = _cargar_seed(con)
        con.run(ROLES_CREAR)
        con.run((HERE / "legado.sql").read_text(encoding="utf-8"))
        con.run((HERE / "artnot.sql").read_text(encoding="utf-8"))
        con.run(ROLES_PERMISOS)
        resumen["ok"] = True
        if event.get("docs_bucket"):
            resumen["documentos"] = subir_documentos(event["docs_bucket"])
        if event.get("kb_id") and event.get("ds_id"):
            resumen["ingesta"] = lanzar_ingesta(event["kb_id"], event["ds_id"])
        return resumen
    finally:
        con.close()
