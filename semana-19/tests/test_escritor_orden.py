"""Week 19, activity 6: the approval workflow's two writes, offline ($0): the connection is a fake.

The database's own rules (triggers, unique index, sequence grant) are exercised against PostgreSQL in
test_escritor_orden_pg.py (marked `vivo`, a local throwaway cluster).
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import escritor_orden as W  # noqa: E402

PROPUESTA = {"sku": "SKU-0009", "cantidad": 3, "motivo": "reorden automático", "solicitante": "sub-comprador",
             "cedis": 2, "fecha_requerida": "2026-12-05"}
DECISION = {"decision": "aprobar", "decidido_por": "sub-gerente", "nivel": "gerente"}


class Conexion:
    def __init__(self, fallo=False, filas=None):
        self.sql = []
        self.cerrada = False
        self.fallo = fallo
        self.filas = filas

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        if sql.startswith(("INSERT", "UPDATE")) and self.fallo:
            raise RuntimeError("violación de restricción")
        if sql.startswith("INSERT"):
            return self.filas if self.filas is not None else [[7, "PENDING_APPROVAL", Decimal("1234.50"), "comprador"]]
        if sql.startswith("UPDATE"):
            return self.filas if self.filas is not None else [[7, "APPROVED"]]
        return []

    def close(self):
        self.cerrada = True


def test_la_propuesta_se_inserta_pendiente_con_parametros_y_devuelve_lo_que_calculo_la_base():
    con = Conexion()
    res = W.proponer_orden(PROPUESTA, lambda: con)
    assert res == {"po_id": 7, "estado": "PENDING_APPROVAL", "monto": "1234.50", "nivel_requerido": "comprador"}
    sql, params = con.sql[1]
    assert sql.startswith("INSERT INTO purchase_orders (sku, qty, reason, requested_by, delivery_warehouse_id, required_date)")
    assert "status" not in sql.split("RETURNING")[0] and "APPROVED" not in sql    # the trigger sets the status
    assert params == {"sku": "SKU-0009", "qty": 3, "reason": "reorden automático", "requested_by": "sub-comprador",
                      "warehouse": 2, "required_date": "2026-12-05"}
    assert [s for s, _ in con.sql] == ["BEGIN", sql, "COMMIT"] and con.cerrada


def test_si_la_base_no_la_deja_pendiente_es_un_error():
    con = Conexion(filas=[[7, "APPROVED", Decimal("1"), "comprador"]])
    with pytest.raises(RuntimeError):
        W.proponer_orden(PROPUESTA, lambda: con)


def test_fallo_del_insert_hace_rollback_y_cierra_la_conexion():
    con = Conexion(fallo=True)
    with pytest.raises(RuntimeError):
        W.proponer_orden(PROPUESTA, lambda: con)
    assert [s for s, _ in con.sql][-1] == "ROLLBACK" and con.cerrada


@pytest.mark.parametrize("cambio", [
    {"sku": "A1"}, {"cantidad": 0}, {"cantidad": True}, {"cantidad": 100001}, {"motivo": ""}, {"motivo": "x" * 201},
    {"solicitante": ""}, {"solicitante": None}, {"cedis": 0}, {"cedis": "2"}, {"fecha_requerida": "05/12/2026"},
    {"fecha_requerida": "2026-02-30"}, {"fecha_requerida": None},
])
def test_propuesta_invalida_no_abre_conexion(cambio):
    llamadas = []
    with pytest.raises(ValueError):
        W.proponer_orden({**PROPUESTA, **cambio}, lambda: llamadas.append(1))
    assert llamadas == []


def test_la_decision_actualiza_solo_la_fila_pendiente_y_no_si_quien_decide_la_pidio():
    con = Conexion()
    assert W.decidir_orden(7, DECISION, lambda: con) == {"po_id": 7, "estado": "APPROVED"}
    sql, params = con.sql[1]
    assert sql.startswith("UPDATE purchase_orders SET status = :status, decided_by = :decided_by")
    assert "status = 'PENDING_APPROVAL'" in sql and "requested_by IS DISTINCT FROM :decided_by" in sql
    assert params == {"po_id": 7, "status": "APPROVED", "decided_by": "sub-gerente", "decided_level": "gerente",
                      "note": None}
    assert [s for s, _ in con.sql] == ["BEGIN", sql, "COMMIT"] and con.cerrada


def test_rechazo_registra_el_motivo():
    con = Conexion(filas=[[7, "REJECTED"]])
    res = W.decidir_orden(7, {**DECISION, "decision": "rechazar", "nota": " sin presupuesto "}, lambda: con)
    assert res == {"po_id": 7, "estado": "REJECTED"}
    assert con.sql[1][1]["status"] == "REJECTED" and con.sql[1][1]["note"] == "sin presupuesto"


def test_sin_fila_actualizada_es_un_error_explicito():
    con = Conexion(filas=[])
    with pytest.raises(W.OrdenNoDecidida):
        W.decidir_orden(7, DECISION, lambda: con)
    assert "COMMIT" in [s for s, _ in con.sql] and con.cerrada   # nothing changed; the transaction ends cleanly


@pytest.mark.parametrize("po_id,decision", [
    (0, DECISION), ("7", DECISION), (7, {**DECISION, "decision": "tal-vez"}), (7, {**DECISION, "nivel": "jefe"}),
    (7, {**DECISION, "decidido_por": ""}), (7, {**DECISION, "decision": "rechazar"}), (7, "aprobar"),
])
def test_decision_invalida_no_abre_conexion(po_id, decision):
    llamadas = []
    with pytest.raises(ValueError):
        W.decidir_orden(po_id, decision, lambda: llamadas.append(1))
    assert llamadas == []
