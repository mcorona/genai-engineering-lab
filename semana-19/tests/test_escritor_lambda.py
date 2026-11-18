"""Week 19, activity 6: the order writer's Lambda handler, offline ($0): the connection is a fake."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from computo import escritor as E  # noqa: E402

SOLICITUD = {"sku": "SKU-0009", "cantidad": 3, "motivo": "stock", "solicitante": "sub-c", "cedis": 1,
             "fecha_requerida": "2026-12-05"}


class Conexion:
    def __init__(self):
        self.sql = []
        self.cerrada = False

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        if sql.startswith("INSERT"):
            return [[42, "PENDING_APPROVAL", Decimal("10.00"), "comprador"]]
        if sql.startswith("UPDATE"):
            return [[42, "REJECTED"]]
        return []

    def close(self):
        self.cerrada = True


def test_proponer_con_la_solicitud_como_texto_json_o_como_objeto():
    for solicitud in (json.dumps(SOLICITUD), SOLICITUD):
        con = Conexion()
        res = E.handler_escritor({"operacion": "proponer", "solicitud": solicitud}, None, conectar=lambda: con)
        assert res == {"po_id": 42, "estado": "PENDING_APPROVAL", "monto": "10.00", "nivel_requerido": "comprador"}
        assert con.sql[1][1]["requested_by"] == "sub-c" and con.cerrada
        json.dumps(res)   # the workflow carries it: it must be JSON (no Decimal)


def test_decidir_registra_la_decision_del_aprobador():
    con = Conexion()
    evento = {"operacion": "decidir", "po_id": 42,
              "decision": {"decision": "rechazar", "decidido_por": "sub-g", "nivel": "gerente", "nota": "no"}}
    assert E.handler_escritor(evento, None, conectar=lambda: con) == {"po_id": 42, "estado": "REJECTED"}


@pytest.mark.parametrize("evento", [
    {}, {"solicitud": SOLICITUD}, {"operacion": "aprobar", "solicitud": SOLICITUD},
    {"operacion": "proponer", "solicitud": "no es json"}, {"operacion": "proponer", "solicitud": 7},
    {"operacion": "proponer", "solicitud": {**SOLICITUD, "cedis": None}},
    {"operacion": "decidir", "po_id": 42, "decision": 7},
    {"operacion": "decidir", "po_id": 42, "decision": {"decision": "aprobar", "decidido_por": "x", "nivel": "jefe"}},
])
def test_entrada_invalida_no_abre_conexion(evento):
    llamadas = []
    with pytest.raises((ValueError, json.JSONDecodeError)):
        E.handler_escritor(evento, None, conectar=lambda: llamadas.append(1))
    assert llamadas == []


def test_conexion_real_usa_usuario_order_writer_y_la_ca_empaquetada():
    assert E.USUARIO == "order_writer"
    assert E.CA.exists()
