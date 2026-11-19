"""Week 19, activity 7: the agent Lambda as an MCP client of the AgentCore Gateway (CAMINO_HERRAMIENTAS=gateway).

The USER's access token travels with the request (ADR 0007, "The token on the asynchronous path"): the HTTP API's
JWT authorizer verified it, the questions function passes it in the asynchronous event, and this client sends it as
`Authorization: Bearer` to the gateway, which verifies it again (CUSTOM_JWT: the pool's discovery URL, the app client,
the scope legado/leer) and evaluates the Cedar policies with its claims. The token is never logged, stored or returned.

One MCP session per question: opened at the first tool call (initialize), reused for the rest of the loop, closed when
the question ends. The loop is synchronous, so the session lives in an anyio blocking portal (a thread with its event
loop). The tools are the same: the gateway's target is the tools Lambda, with its gateway adapter.

Fail closed:
- a token that has expired (or expires within MARGEN_S) is never sent: TokenVencido, before the call;
- a 401 from the gateway is TokenVencido too. The handler ends the question with the week 17 state `error`
  (agente/handler.tratar_pregunta): the loop does not go on with a session it can no longer use;
- any other failure of the gateway or the transport is a closed tool error for the model, like a failed lambda.invoke.
"""
from __future__ import annotations

import base64
import contextlib
import json
import time
from typing import Any, Callable

from herramientas import contrato

MARGEN_S = 5   # seconds before `exp` at which the token counts as expired (the gateway's clock and ours differ)


RECHAZO_DEL_GATEWAY = "rechazada_por_el_gateway"


def _cadena(error: BaseException):
    """The exception and everything inside it: exception groups (the MCP client nests the error two groups deep,
    seen live 2026-11-18), causes and contexts, each once."""
    vistos, pendientes = set(), [error]
    while pendientes:
        e = pendientes.pop()
        if id(e) in vistos:
            continue
        vistos.add(id(e))
        yield e
        pendientes += list(getattr(e, "exceptions", ()) or ()) + [x for x in (e.__cause__, e.__context__) if x]


def _codigo_jsonrpc(error: BaseException) -> int | None:
    """The code of an MCP error answer anywhere in the exception (mcp.shared.exceptions.MCPError carries it in
    .error.code), or None."""
    for e in _cadena(error):
        codigo = getattr(getattr(e, "error", None), "code", None)
        if isinstance(codigo, int):
            return codigo
    return None


class TokenVencido(Exception):
    """The user's token expired before or during the loop: the question ends, nothing more is sent."""


def claims(token: str) -> dict:
    """The token's claims, read without verifying (the gateway verifies the signature); {} if it is not a JWT."""
    try:
        carga = token.split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        return datos if isinstance(datos, dict) else {}
    except (AttributeError, IndexError, ValueError, TypeError):
        return {}


def expiracion(token: str) -> int | None:
    """The token's `exp`: only to fail before sending."""
    try:
        return int(claims(token)["exp"])
    except (KeyError, ValueError, TypeError):
        return None


def _no_autorizado(error: BaseException) -> bool:
    """A 401 anywhere in the exception (httpx's HTTPStatusError, inside an exception group or as a cause)."""
    return any(getattr(getattr(e, "response", None), "status_code", None) == 401 for e in _cadena(error))


def _abrir_mcp(url: str, token: str):
    """The real session: streamable HTTP with the user's token, then initialize."""
    @contextlib.asynccontextmanager
    async def abrir():
        from mcp import ClientSession
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

        async with create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as http:
            async with streamable_http_client(url, http_client=http) as (leer, escribir, *_):
                async with ClientSession(leer, escribir) as sesion:
                    await sesion.initialize()
                    yield sesion
    return abrir


def _al_contrato(resultado: Any, al_contrato: Callable) -> dict:
    """CallToolResult -> the week 13 contract. The Lambda target's JSON arrives as the first text content."""
    textos = [getattr(c, "text", None) for c in getattr(resultado, "content", None) or []]
    try:
        cuerpo = json.loads(next(t for t in textos if t))
    except (StopIteration, ValueError, TypeError):
        cuerpo = getattr(resultado, "structured_content", None)
    return al_contrato(cuerpo, fallo=bool(getattr(resultado, "is_error", False)) and not isinstance(cuerpo, dict))


class LlamadorGateway:
    """Same signature as the direct caller (agente/construccion.llamador_de_herramientas): (name, args, requester)."""

    def __init__(self, url: str, token: str, *, al_contrato: Callable, abrir: Callable | None = None,
                 reloj: Callable[[], float] = time.time):
        if not url or not token:
            raise RuntimeError("camino gateway sin URL o sin token")
        self._abrir = abrir if abrir is not None else _abrir_mcp(url, token)
        self._exp = expiracion(token)
        self._reloj, self._al_contrato = reloj, al_contrato
        self._pila: contextlib.ExitStack | None = None
        self._portal = self._sesion = None
        self.llamadas = 0

    def _vigente(self) -> None:
        if self._exp is None or self._reloj() >= self._exp - MARGEN_S:
            raise TokenVencido()

    def _abierta(self):
        if self._sesion is None:
            from anyio.from_thread import start_blocking_portal
            self._pila = contextlib.ExitStack()
            self._portal = self._pila.enter_context(start_blocking_portal())
            self._sesion = self._pila.enter_context(self._portal.wrap_async_context_manager(self._abrir()))
        return self._sesion

    def __call__(self, nombre: str, args: dict, solicitante: str | None = None) -> dict:
        self._vigente()
        argumentos = dict(args)
        if nombre == "proponer_orden_compra":
            argumentos[contrato.SOLICITANTE] = solicitante   # from the verified token; Cedar checks it is the caller
        self.llamadas += 1
        try:
            sesion = self._abierta()
            resultado = self._portal.call(sesion.call_tool, contrato.nombre_en_gateway(nombre), argumentos)
        except Exception as error:  # noqa: BLE001 — transport or gateway failure: closed, never the raw message
            if _no_autorizado(error):
                raise TokenVencido() from None
            codigo = _codigo_jsonrpc(error)
            if codigo is not None:   # the gateway answered with a JSON-RPC error (a Cedar deny among them)
                return {"ok": False, "error": {"tipo": RECHAZO_DEL_GATEWAY, "codigo": codigo,
                                               "mensaje": "El gateway rechazó la llamada.",
                                               "sugerencia": "No reintentes la misma llamada; responde con lo que tengas."}}
            return self._al_contrato(None, fallo=True)
        return _al_contrato(resultado, self._al_contrato)

    def cerrar(self) -> None:
        """Ends the MCP session (DELETE) and the portal. Safe to call twice or when no session was opened."""
        pila, self._pila, self._sesion, self._portal = self._pila, None, None, None
        if pila is not None:
            with contextlib.suppress(Exception):
                pila.close()


# ---------------------------------------------------------------- the live Policy test (agentes/comparar.py)

def _en_sesion(url: str, token: str, accion: Callable, abrir: Callable | None = None):
    import anyio
    abrir = abrir or _abrir_mcp(url, token)

    async def correr():
        async with abrir() as sesion:
            return await accion(sesion)
    return anyio.run(correr)


def probar_como(url: str, token: str, argumentos: dict, *, abrir: Callable | None = None) -> dict:
    """One proposal through the gateway as this user. Whether the Policy let it through: a JSON-RPC error or an
    error result that is not the tool's own JSON means it did not; the tool's answer (even its error) means it did.
    Only the code and the tool's error kind are returned, never a message."""
    async def accion(sesion):
        return await sesion.call_tool(contrato.nombre_en_gateway("proponer_orden_compra"), argumentos)
    try:
        r = _en_sesion(url, token, accion, abrir)
    except BaseException as error:  # noqa: BLE001 - JSON-RPC errors may arrive inside an exception group
        codigo = _codigo_jsonrpc(error)
        if codigo is None:
            raise
        return {"paso": False, "forma": "jsonrpc", "codigo": codigo, "error_herramienta": None}
    cuerpo = _texto_json(r)
    if cuerpo is None:
        return {"paso": False, "forma": "resultado_sin_json", "codigo": None, "error_herramienta": None,
                "is_error": bool(getattr(r, "is_error", False))}
    return {"paso": True, "forma": "resultado", "codigo": None, "error_herramienta": cuerpo.get("error")}


def listar_como(url: str, token: str, *, abrir: Callable | None = None) -> list[str]:
    """The tools this user sees (the Policy filters tools/list by what the principal may call)."""
    async def accion(sesion):
        return [t.name for t in (await sesion.list_tools()).tools]
    return _en_sesion(url, token, accion, abrir)


def _texto_json(resultado: Any) -> dict | None:
    for c in getattr(resultado, "content", None) or []:
        try:
            datos = json.loads(getattr(c, "text", "") or "")
        except (TypeError, ValueError):
            continue
        if isinstance(datos, dict):
            return datos
    return None
