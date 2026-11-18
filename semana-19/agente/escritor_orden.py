"""Week 19, activity 6: the approval workflow's two writes to purchase_orders (only this step writes, ADR 0011).

Runs in the VPC as the `order_writer` role. The database rules (ddl_copilot.sql) decide, not this code:
  proponer  INSERT of the proposal. The trigger po_before_insert forces PENDING_APPROVAL and computes unit_cost, amount
            and required_level; po_require_delivery requires the CEDIS and the required date; po_one_pending_per_sku
            allows one pending order per SKU.
  decidir   UPDATE of that pending row to APPROVED or REJECTED with who decided and at which level. The trigger
            po_before_update refuses a level below the order's required level and any change to the proposal.
            Separation of duties is checked here too: the row is not updated when the decider is the requester.

Every value is a bound parameter. The policy (semana-08/corpus/ordenes_de_compra.md) requires SKU, quantity, CEDIS,
required date and reason; supplier and unit cost come from the product row (the trigger).
"""
from __future__ import annotations

import datetime as dt
import re

SKU_RE = re.compile(r"SKU-\d{4}")
FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
NIVELES = ("comprador", "gerente", "director")      # po_level_rank: 1, 2, 3
ESTADOS = {"aprobar": "APPROVED", "rechazar": "REJECTED"}


class OrdenNoDecidida(Exception):
    """The pending row was not found, was already decided, or the decider is the requester (no update happened)."""


def _texto(valor, nombre: str, maximo: int) -> str:
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= maximo:
        raise ValueError(f"{nombre} debe tener de 1 a {maximo} caracteres")
    return valor.strip()


def _entero(valor, nombre: str, minimo: int, maximo: int) -> int:
    if not isinstance(valor, int) or isinstance(valor, bool) or not minimo <= valor <= maximo:
        raise ValueError(f"{nombre} debe ser un entero de {minimo} a {maximo}")
    return valor


def fecha_valida(valor) -> str:
    """YYYY-MM-DD and a real calendar day. Not compared with today: the seed uses a fixed anchor date (ddl_copilot.sql)."""
    if not isinstance(valor, str) or not FECHA_RE.fullmatch(valor):
        raise ValueError("fecha_requerida debe tener la forma AAAA-MM-DD")
    try:
        dt.date.fromisoformat(valor)
    except ValueError:
        raise ValueError("fecha_requerida no es una fecha del calendario") from None
    return valor


def validar_propuesta(solicitud: dict) -> dict:
    """The proposal as the workflow received it. Raises ValueError before any connection."""
    if not isinstance(solicitud, dict):
        raise ValueError("solicitud ausente o inválida")
    sku = solicitud.get("sku")
    if not isinstance(sku, str) or not SKU_RE.fullmatch(sku):
        raise ValueError("sku debe tener la forma SKU-dddd")
    return {"sku": sku,
            "qty": _entero(solicitud.get("cantidad"), "cantidad", 1, 100000),
            "reason": _texto(solicitud.get("motivo"), "motivo", 200),
            "requested_by": _texto(solicitud.get("solicitante"), "solicitante", 128),
            "warehouse": _entero(solicitud.get("cedis"), "cedis", 1, 1_000_000),
            "required_date": fecha_valida(solicitud.get("fecha_requerida"))}


def _en_transaccion(conectar, trabajo):
    con = conectar()
    try:
        con.run("BEGIN")
        try:
            resultado = trabajo(con)
            con.run("COMMIT")
        except Exception:
            con.run("ROLLBACK")
            raise
    finally:
        con.close()
    return resultado


def proponer_orden(solicitud: dict, conectar) -> dict:
    """INSERT of the pending order. Returns its id, amount and required level, as the database computed them."""
    p = validar_propuesta(solicitud)

    def trabajo(con):
        return con.run(
            "INSERT INTO purchase_orders (sku, qty, reason, requested_by, delivery_warehouse_id, required_date) "
            "VALUES (:sku, :qty, :reason, :requested_by, :warehouse, CAST(:required_date AS date)) "
            "RETURNING po_id, status, amount, required_level", **p)

    po_id, estado, monto, nivel = _en_transaccion(conectar, trabajo)[0]
    if estado != "PENDING_APPROVAL" or nivel not in NIVELES:
        raise RuntimeError("la base no dejó la orden pendiente con un nivel válido")
    return {"po_id": int(po_id), "estado": estado, "monto": str(monto), "nivel_requerido": nivel}


def decidir_orden(po_id, decision: dict, conectar) -> dict:
    """UPDATE of the pending row. decision = {"decision": "aprobar"|"rechazar", "decidido_por", "nivel", "nota"}.
    A rejection needs its reason in `nota` (the policy records it)."""
    po_id = _entero(po_id, "po_id", 1, 2**31 - 1)
    if not isinstance(decision, dict) or decision.get("decision") not in ESTADOS:
        raise ValueError("decision debe ser aprobar o rechazar")
    if decision.get("nivel") not in NIVELES:
        raise ValueError("nivel debe ser comprador, gerente o director")
    estado = ESTADOS[decision["decision"]]
    nota = decision.get("nota")
    if estado == "REJECTED" or nota is not None:
        nota = _texto(nota, "nota", 200)
    params = {"po_id": po_id, "status": estado, "decided_level": decision["nivel"], "note": nota,
              "decided_by": _texto(decision.get("decidido_por"), "decidido_por", 128)}

    def trabajo(con):
        return con.run(
            "UPDATE purchase_orders SET status = :status, decided_by = :decided_by, decided_level = :decided_level, "
            "decision_note = :note WHERE po_id = :po_id AND status = 'PENDING_APPROVAL' "
            "AND requested_by IS DISTINCT FROM :decided_by RETURNING po_id, status", **params)

    filas = _en_transaccion(conectar, trabajo)
    if not filas:
        raise OrdenNoDecidida(f"la orden {po_id} no está pendiente o quien decide es quien la pidió")
    return {"po_id": int(filas[0][0]), "estado": filas[0][1]}
