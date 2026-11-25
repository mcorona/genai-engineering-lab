import asyncio
import os
import sys
from pathlib import Path

import pytest

S14 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S14))
sys.path.insert(0, str(S14.parent / "semana-13"))

from herramientas import Contexto, Herramientas  # noqa: E402

HAY_BASE = bool(os.environ.get("NLQ_LEGADO_DSN") or os.environ.get("PG_ADMIN_DSN") or os.environ.get("PG_DSN"))
USUARIOS = ("analista", "almacenista", "vendedor")


@pytest.fixture(scope="session")
def conexion():
    if not HAY_BASE:
        pytest.skip("no database (set PG_ADMIN_DSN, NLQ_LEGADO_DSN or PG_DSN)")
    from herramientas.conexion import conectar
    conn, _ = conectar()
    yield conn
    conn.close()


def con_cliente(servidor, fn):
    """Runs `fn(cliente)` with an in-memory MCP client (protocol 2026-07-28) against `servidor`."""
    from mcp import Client

    async def _correr():
        async with Client(servidor) as c:
            return await fn(c)
    try:
        return asyncio.run(_correr())
    except BaseExceptionGroup as g:  # the client runs in an anyio task group: the protocol error propagates
        hojas = []

        def _hojas(e):
            for x in e.exceptions:
                _hojas(x) if isinstance(x, BaseExceptionGroup) else hojas.append(x)
        _hojas(g)
        if len(hojas) == 1:
            raise hojas[0] from None
        raise


def fabrica(usuario, conexion=None, idioma="es"):
    """A single instance per server, as in a real process (the call log and the proposals belong to the context)."""
    h = Herramientas(Contexto.de_usuario(usuario, conexion=conexion, idioma=idioma))
    return lambda: h


from servidor.lab import ServidorHTTP  # noqa: E402,F401  (it lives in servidor/lab.py; the eval also uses it)
