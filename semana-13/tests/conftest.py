import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from herramientas import Contexto, Herramientas  # noqa: E402

HAY_BASE = bool(os.environ.get("NLQ_LEGADO_DSN") or os.environ.get("PG_ADMIN_DSN") or os.environ.get("PG_DSN"))


@pytest.fixture(scope="session")
def conexion():
    if not HAY_BASE:
        pytest.skip("no database (set PG_ADMIN_DSN, NLQ_LEGADO_DSN or PG_DSN)")
    from herramientas.conexion import conectar
    conn, rol = conectar()
    yield conn
    conn.close()


@pytest.fixture
def h_sin_base():
    return Herramientas(Contexto.de_usuario("analista"))


def herramientas(usuario, conn, **kw):
    return Herramientas(Contexto.de_usuario(usuario, conexion=conn, **kw))
