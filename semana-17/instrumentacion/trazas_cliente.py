"""Week 17, activity 3: the MCP client keeps the agent's trace context.

Finding of activity 1: the MCP SDK injects the W3C trace context (`traceparent`) into `_meta` of every request, but the
week 14 client (`cliente/seguro.py`) runs each call in a session thread with its own event loop, handed over through a
queue. The coroutine is awaited by the session's long-lived task, whose context is the one it had when the session was
opened, so the SDK's `MCP send tools/call X` span became a root of a different trace and the server spans after it.

`ClienteInstrumentado` closes that gap without editing the week 14 file: every `pedir(fn)` captures the caller's OTel context
and re-attaches it inside the coroutine, so the SDK span becomes a child of the agent's `execute_tool` span.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

from opentelemetry import context as otel_context

S14 = Path(__file__).resolve().parents[2] / "semana-14"
if str(S14) not in sys.path:
    sys.path.insert(0, str(S14))

from cliente.seguro import ClienteSeguro  # noqa: E402


def propagar_contexto(sesion) -> None:
    """Instance-level wrapper of `_Sesion.pedir`: the coroutine runs under the OTel context of the thread that asked."""
    pedir_original = sesion.pedir

    def pedir(self, fn, timeout=120):
        contexto = otel_context.get_current()

        async def con_contexto(cliente):
            token = otel_context.attach(contexto)
            try:
                return await fn(cliente)
            finally:
                otel_context.detach(token)
        return pedir_original(con_contexto, timeout)

    sesion.pedir = types.MethodType(pedir, sesion)


class ClienteInstrumentado(ClienteSeguro):
    """`ClienteSeguro` whose sessions propagate the trace context across the thread hand-off."""

    def abrir(self) -> "ClienteInstrumentado":
        super().abrir()
        for sesion in self._sesiones.values():
            if not getattr(sesion, "_contexto_propagado", False):
                propagar_contexto(sesion)
                sesion._contexto_propagado = True
        return self
