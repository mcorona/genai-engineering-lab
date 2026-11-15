"""An MCP client with the same interface as `Herramientas` (llamar and definiciones), so that the agent uses the
tools through the MCP server without changing the loop.

The MCP SDK is asynchronous (anyio) and the agent loop is synchronous: the client runs in a thread with its own event
loop, and a single task opens the session, serves the requests from a queue and closes it (anyio requires contexts to
be opened and closed in the same task).
"""
import asyncio
import concurrent.futures
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVIDOR = Path(__file__).resolve().parent / "servidor.py"


@dataclass
class _Ctx:
    usuario: str
    idioma: str
    llamadas: list = field(default_factory=list)


class HerramientasMCP:
    def __init__(self, usuario: str = "analista", idioma: str = "es", env: dict | None = None):
        self.ctx = _Ctx(usuario, idioma)
        entorno = {**os.environ, **(env or {}), "MCP_USUARIO": usuario, "MCP_IDIOMA": idioma}
        self._params = StdioServerParameters(command=sys.executable, args=[str(SERVIDOR)], env=entorno)
        self._loop = asyncio.new_event_loop()
        self._listo = concurrent.futures.Future()
        self._hilo = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._hilo.start()
        self._tarea = asyncio.run_coroutine_threadsafe(self._sesion(), self._loop)
        self._listo.result(timeout=60)

    async def _sesion(self):
        self._cola = asyncio.Queue()
        try:
            async with stdio_client(self._params) as (lectura, escritura), ClientSession(lectura, escritura) as sesion:
                await sesion.initialize()
                self._listo.set_result(True)
                while True:
                    item = await self._cola.get()
                    if item is None:
                        break
                    funcion, futuro = item
                    try:
                        futuro.set_result(await funcion(sesion))
                    except Exception as e:  # noqa: BLE001
                        futuro.set_exception(e)
        except Exception as e:  # noqa: BLE001
            if not self._listo.done():
                self._listo.set_exception(e)
            raise

    def _pedir(self, funcion, timeout=120):
        futuro = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._cola.put_nowait, (funcion, futuro))
        return futuro.result(timeout=timeout)

    def definiciones(self) -> list[dict]:
        r = self._pedir(lambda s: s.list_tools())
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in r.tools]

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        r = self._pedir(lambda s: s.call_tool(nombre, argumentos))
        texto = "".join(c.text for c in r.content if getattr(c, "type", "") == "text")
        try:
            res = json.loads(texto)
        except json.JSONDecodeError:
            res = {"ok": False, "error": {"tipo": "error_mcp", "mensaje": texto[:500], "sugerencia": ""}}
        self.ctx.llamadas.append({"herramienta": nombre, "argumentos": argumentos, "ok": res.get("ok"),
                                  "error": (res.get("error") or {}).get("tipo"), "is_error": r.is_error})
        return res

    def cerrar(self):
        self._loop.call_soon_threadsafe(self._cola.put_nowait, None)
        try:
            self._tarea.result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._hilo.join(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()
