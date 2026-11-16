"""Week 19, activity 6: the order writer's Lambda handler, offline ($0): the connection is a fake."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from computo import escritor as E  # noqa: E402


class Conexion:
    def __init__(self):
        self.sql = []
        self.cerrada = False

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        return [[42]] if sql.startswith("INSERT") else []

    def close(self):
        self.cerrada = True


def test_solicitud_como_texto_json_se_escribe_aprobada():
    con = Conexion()
    evento = {"solicitud": json.dumps({"sku": "SKU-0009", "cantidad": 3, "motivo": "stock"})}
    assert E.handler_escritor(evento, None, conectar=lambda: con) == {"po_id": 42}
    assert con.sql[1][1] == {"sku": "SKU-0009", "qty": 3} and con.cerrada


def test_solicitud_como_objeto_tambien_sirve():
    con = Conexion()
    assert E.handler_escritor({"solicitud": {"sku": "SKU-0009", "cantidad": 3}}, None, conectar=lambda: con) == {"po_id": 42}


@pytest.mark.parametrize("evento", [{}, {"solicitud": "no es json"}, {"solicitud": 7}, {"solicitud": {"sku": "A", "cantidad": 1}}])
def test_entrada_invalida_no_abre_conexion(evento):
    llamadas = []
    with pytest.raises((ValueError, json.JSONDecodeError)):
        E.handler_escritor(evento, None, conectar=lambda: llamadas.append(1))
    assert llamadas == []


def test_conexion_real_usa_usuario_order_writer_y_la_ca_empaquetada():
    assert E.USUARIO == "order_writer"
    assert E.CA.exists()
