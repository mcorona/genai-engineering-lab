"""Week 19, activity 6: the approval step writes the order (only this step writes to the database, ADR 0011).

Runs in the VPC as the `order_writer` role. The table purchase_orders has no reason column (week 7 schema): the reason
of the proposal stays in the approval record, not in the database. Status is APPROVED, as the schema allows.
"""
from __future__ import annotations

import re

SKU_RE = re.compile(r"SKU-\d{4}")


def escribir_orden(evento: dict, conectar) -> dict:
    sku, cantidad = evento.get("sku"), evento.get("cantidad")
    if not isinstance(sku, str) or not SKU_RE.fullmatch(sku):
        raise ValueError("sku debe tener la forma SKU-dddd")
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or not 1 <= cantidad <= 100000:
        raise ValueError("cantidad debe ser un entero de 1 a 100000")
    con = conectar()
    try:
        con.run("BEGIN")
        try:
            fila = con.run("INSERT INTO purchase_orders (sku, qty, status) VALUES (:sku, :qty, 'APPROVED') RETURNING po_id",
                           sku=sku, qty=cantidad)
            con.run("COMMIT")
        except Exception:
            con.run("ROLLBACK")
            raise
    finally:
        con.close()
    return {"po_id": fila[0][0]}
