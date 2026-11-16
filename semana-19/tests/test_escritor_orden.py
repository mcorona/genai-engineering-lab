"""Week 19, activity 6: the approval step's order writer, offline ($0): the connection is a fake."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import escritor_orden as W  # noqa: E402


class Conexion:
    def __init__(self, fallo=False):
        self.sql = []
        self.cerrada = False
        self.fallo = fallo

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        if sql.startswith("INSERT") and self.fallo:
            raise RuntimeError("violación de restricción")
        if sql.startswith("INSERT"):
            return [[7]]
        return []

    def close(self):
        self.cerrada = True


def test_orden_valida_se_inserta_aprobada_con_parametros_y_transaccion():
    con = Conexion()
    res = W.escribir_orden({"sku": "SKU-0009", "cantidad": 3, "motivo": "stock"}, lambda: con)
    assert res == {"po_id": 7}
    sql, params = con.sql[1]
    assert sql.startswith("INSERT INTO purchase_orders (sku, qty, status)") and "'APPROVED'" in sql
    assert params == {"sku": "SKU-0009", "qty": 3}
    assert [s for s, _ in con.sql] == ["BEGIN", sql, "COMMIT"] and con.cerrada


def test_fallo_del_insert_hace_rollback_y_cierra_la_conexion():
    con = Conexion(fallo=True)
    with pytest.raises(RuntimeError):
        W.escribir_orden({"sku": "SKU-0009", "cantidad": 3}, lambda: con)
    assert "ROLLBACK" in [s for s, _ in con.sql] and con.cerrada


@pytest.mark.parametrize("entrada", [
    {"sku": "A1", "cantidad": 3},
    {"sku": "SKU-0009", "cantidad": 0},
    {"sku": "SKU-0009", "cantidad": True},
    {"sku": "SKU-0009"},
])
def test_entrada_invalida_no_abre_conexion(entrada):
    llamadas = []
    with pytest.raises(ValueError):
        W.escribir_orden(entrada, lambda: llamadas.append(1))
    assert llamadas == []
