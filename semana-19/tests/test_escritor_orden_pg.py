"""Week 19, activity 6: the approval workflow's writes against PostgreSQL's own rules, as order_writer.

Live, local only (marked `vivo`, needs S19_DSN_LOCAL; CI deselects it): a throwaway database on a local cluster at
127.0.0.1:55432 (trust authentication, the same as test_loader.py), never the lab database. It gets the lab's DDL
(ddl_copilot.sql without the pgvector table, which a plain local cluster does not have), seed 42, the legado views and
the loader's roles and grants. Then order_writer runs agente/escritor_orden.py: the triggers, the unique index and the
grants decide, as in RDS.
"""
from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
CARGADOR = S19 / "infra" / "loader"
sys.path.insert(0, str(CARGADOR / "vendor"))
sys.path.insert(0, str(S19))

from agente import escritor_orden as W  # noqa: E402

LIVE = os.environ.get("S19_DSN_LOCAL")
HOST, PUERTO = "127.0.0.1", 55432
pytestmark = [pytest.mark.vivo,
              pytest.mark.skipif(not LIVE, reason="live test: set S19_DSN_LOCAL to a local test database")]


def _loader():
    spec = importlib.util.spec_from_file_location("handler_loader_pg", CARGADOR / "handler.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _ddl_sin_pgvector() -> str:
    ddl = (CARGADOR / "ddl_copilot.sql").read_text(encoding="utf-8")
    ddl = ddl.replace("CREATE EXTENSION IF NOT EXISTS vector;", "")
    ddl = re.sub(r"CREATE TABLE doc_chunks \(.*?\);\s*CREATE INDEX ON doc_chunks[^;]*;", "", ddl, flags=re.S)
    assert "vector(" not in ddl and "CREATE EXTENSION" not in ddl and "doc_chunks" not in ddl
    return ddl


@pytest.fixture(scope="module")
def base():
    import pg8000.native as pg
    nombre = f"s19_escritor_{uuid.uuid4().hex[:8]}"
    admin = pg.Connection("postgres", host=HOST, port=PUERTO, database="postgres")
    admin.run(f"CREATE DATABASE {nombre}")
    admin.run("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rds_iam') THEN CREATE ROLE rds_iam; END IF; END $$")
    H = _loader()
    con = pg.Connection("postgres", host=HOST, port=PUERTO, database=nombre)
    con.run(_ddl_sin_pgvector())
    H._cargar_seed(con)
    con.run(H.ROLES_CREAR)
    con.run((CARGADOR / "legado.sql").read_text(encoding="utf-8"))
    con.run(H.ROLES_PERMISOS)

    def conectar():
        return pg.Connection("order_writer", host=HOST, port=PUERTO, database=nombre)

    yield con, conectar, nombre
    con.close()
    admin.run(f"DROP DATABASE {nombre} WITH (FORCE)")
    admin.close()


def _cantidad_para(con, sku: str, monto: float) -> int:
    costo = float(con.run("SELECT unit_cost FROM products WHERE sku = :s", s=sku)[0][0])
    return math.ceil(monto / costo)


def _propuesta(sku, cantidad, solicitante="sub-comprador", cedis=1):
    return {"sku": sku, "cantidad": cantidad, "motivo": "reorden automático", "solicitante": solicitante,
            "cedis": cedis, "fecha_requerida": "2026-12-05"}


def _skus(con, n):
    return [f[0] for f in con.run("SELECT sku FROM products ORDER BY sku LIMIT :n", n=n)]


def test_la_propuesta_queda_pendiente_con_el_nivel_que_calcula_la_base(base):
    con, conectar, _ = base
    (sku,) = _skus(con, 1)
    res = W.proponer_orden(_propuesta(sku, _cantidad_para(con, sku, 60000)), conectar)
    assert res["estado"] == "PENDING_APPROVAL" and res["nivel_requerido"] == "gerente" and float(res["monto"]) >= 60000
    fila = con.run("SELECT status, requested_by, delivery_warehouse_id, required_date::text, reason, unit_cost IS NOT NULL "
                   "FROM purchase_orders WHERE po_id = :p", p=res["po_id"])[0]
    assert fila == ["PENDING_APPROVAL", "sub-comprador", 1, "2026-12-05", "reorden automático", True]

    # one pending order per SKU (po_one_pending_per_sku)
    with pytest.raises(Exception, match="po_one_pending_per_sku|duplicate key"):
        W.proponer_orden(_propuesta(sku, 1), conectar)

    # the requester cannot decide it (no row updated), whatever the level
    with pytest.raises(W.OrdenNoDecidida):
        W.decidir_orden(res["po_id"], {"decision": "aprobar", "decidido_por": "sub-comprador", "nivel": "director"}, conectar)

    # a level below the order's required level: the database refuses
    with pytest.raises(Exception, match="Nivel insuficiente"):
        W.decidir_orden(res["po_id"], {"decision": "aprobar", "decidido_por": "sub-cmp", "nivel": "comprador"}, conectar)

    ok = W.decidir_orden(res["po_id"], {"decision": "aprobar", "decidido_por": "sub-gerente", "nivel": "gerente"}, conectar)
    assert ok == {"po_id": res["po_id"], "estado": "APPROVED"}
    fila = con.run("SELECT status, decided_by, decided_level, decided_at IS NOT NULL FROM purchase_orders WHERE po_id = :p",
                   p=res["po_id"])[0]
    assert fila == ["APPROVED", "sub-gerente", "gerente", True]

    # decided once: a second decision updates nothing
    with pytest.raises(W.OrdenNoDecidida):
        W.decidir_orden(res["po_id"], {"decision": "rechazar", "decidido_por": "sub-d", "nivel": "director", "nota": "x"},
                        conectar)


def test_el_rechazo_guarda_quien_su_nivel_y_el_motivo(base):
    con, conectar, _ = base
    sku = _skus(con, 2)[1]
    res = W.proponer_orden(_propuesta(sku, 1), conectar)
    assert res["nivel_requerido"] == "comprador"
    W.decidir_orden(res["po_id"], {"decision": "rechazar", "decidido_por": "sub-cmp", "nivel": "comprador",
                                   "nota": "sin presupuesto"}, conectar)
    fila = con.run("SELECT status, decided_by, decided_level, decision_note FROM purchase_orders WHERE po_id = :p",
                   p=res["po_id"])[0]
    assert fila == ["REJECTED", "sub-cmp", "comprador", "sin presupuesto"]


def test_un_cedis_que_no_existe_lo_rechaza_la_base(base):
    con, conectar, _ = base
    sku = _skus(con, 3)[2]
    with pytest.raises(Exception, match="foreign key|violates"):
        W.proponer_orden(_propuesta(sku, 1, cedis=999999), conectar)


def test_order_writer_no_puede_saltarse_el_estado_pendiente_ni_borrar(base):
    con, conectar, _ = base
    sku = _skus(con, 4)[3]
    w = conectar()
    try:
        fila = w.run("INSERT INTO purchase_orders (sku, qty, status, delivery_warehouse_id, required_date) "
                     "VALUES (:s, 1, 'APPROVED', 1, DATE '2026-12-05') RETURNING status", s=sku)
        assert fila == [["PENDING_APPROVAL"]]     # the trigger forces the status
        with pytest.raises(Exception, match="permission denied"):
            w.run("DELETE FROM purchase_orders")
    finally:
        w.close()


def test_el_modo_permisos_del_cargador_aplica_los_grants_sin_tocar_datos(base):
    con, _, nombre = base
    import pg8000.native as pg
    H = _loader()
    antes = con.run("SELECT count(*) FROM purchase_orders")[0][0]
    H._secreto = lambda arn: {"username": "postgres", "password": ""}
    H._conectar = lambda h, u, c: pg.Connection("postgres", host=HOST, port=PUERTO, database=nombre)
    con.run("REVOKE USAGE ON SEQUENCE purchase_orders_po_id_seq FROM order_writer")
    assert H.handler({"secret_arn": "local", "db_host": "local", "modo": "permisos"}, None) == {"modo": "permisos", "ok": True}
    assert con.run("SELECT has_sequence_privilege('order_writer', 'purchase_orders_po_id_seq', 'USAGE')")[0][0] is True
    assert con.run("SELECT count(*) FROM purchase_orders")[0][0] == antes
