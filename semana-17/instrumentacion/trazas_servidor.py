"""Week 17, activity 3: server-side spans that continue the agent's trace, without editing the week 13/14 server code.

    MCP send tools/call X (client, MCP SDK)
      authorize                      boundary decision: token, scopes required / granted / missing, 401 or 403 or allow
      tools/call X (server, MCP SDK) continues the trace from `_meta.traceparent`
        handle_tool X                the tool call: size + keyed hash of the arguments, status, result size
          SELECT legado              the SQL: db.* attributes, query size + keyed hash (never the text), rows, role

The MCP SDK puts the trace context in the JSON-RPC body (`params._meta.traceparent`), not in HTTP headers, so the
boundary (`Frontera`, an ASGI app that rejects with 401/403 BEFORE the SDK sees the request) has to read it from the body:
`PeticionASGI` tees the body that the boundary reads anyway, and the `Autorizador.evaluar` wrapper builds the `authorize`
span under that parent. A request without `_meta` starts a new trace.

The tool name goes in `lab.tool.name` on `authorize` and `handle_tool`, never in `gen_ai.tool.name`: measured on Langfuse
v4, any span with that key becomes a TOOL observation and is renamed after the tool, so `authorize` would vanish as a name.

`InstrumentorServidor` patches in the style of the OTel instrumentors (`instrument()` / `uninstrument()`): `crear_app` of
`servidor.lab`, and `Herramientas.llamar` / `Herramientas._correr` of week 13. Nothing is recorded that is not in `esquema.py`.
"""
from __future__ import annotations

import contextvars
import functools
import json
import re
import sys
from pathlib import Path

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from . import esquema as E

S14 = Path(__file__).resolve().parents[2] / "semana-14"
if str(S14) not in sys.path:
    sys.path.insert(0, str(S14))

import servidor.lab as servidor_lab  # noqa: E402  (adds semana-13 to sys.path through primitivas)
from servidor.oauth import PERMISOS, SCOPES, scopes_requeridos  # noqa: E402

from herramientas.herramientas import ENTRADAS, TABLAS, Herramientas  # noqa: E402

TRAZADOR = "legacybridge.instrumentation"
_PETICION: contextvars.ContextVar = contextvars.ContextVar("legacybridge_peticion", default=None)
_MAX_CUERPO_LEIDO = 1_000_000


def _tracer():
    return trace.get_tracer(TRAZADOR, E.SCHEMA_VERSION)


def _span(nombre: str, tipo=SpanKind.INTERNAL, contexto=None):
    # No exception event and no exception text on the span: the lab records the type through `error.type` only.
    return _tracer().start_as_current_span(nombre, context=contexto, kind=tipo, record_exception=False,
                                           set_status_on_exception=False)


# ---------- the HTTP boundary ----------

class PeticionASGI:
    """ASGI middleware around the boundary: keeps a copy of the request body that the boundary reads, so the authorizer
    can find `params._meta.traceparent` in it. It does not alter the traffic."""

    def __init__(self, app):
        self.app = app

    def __getattr__(self, nombre):
        return getattr(self.app, nombre)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        peticion = {"cuerpo": bytearray()}

        async def receive_copia():
            m = await receive()
            if m["type"] == "http.request" and len(peticion["cuerpo"]) < _MAX_CUERPO_LEIDO:
                peticion["cuerpo"] += m.get("body", b"")
            return m

        token = _PETICION.set(peticion)
        try:
            await self.app(scope, receive_copia, send)
        finally:
            _PETICION.reset(token)


def contexto_padre():
    """OTel context taken from `params._meta` of the JSON-RPC body of the current request, or None."""
    peticion = _PETICION.get()
    if not peticion:
        return None
    try:
        cuerpo = json.loads(bytes(peticion["cuerpo"]))
        meta = cuerpo["params"]["_meta"]
        portador = {k: meta[k] for k in ("traceparent", "tracestate") if isinstance(meta.get(k), str)}
    except (ValueError, KeyError, TypeError):
        return None
    return TraceContextTextMapPropagator().extract(portador) if "traceparent" in portador else None


def _decision(rechazo) -> str:
    if rechazo is None:
        return "allow"
    motivo = rechazo.motivo
    if motivo == "sin_token":
        return "deny_no_token"
    if motivo == "esquema_no_bearer":
        return "deny_bad_scheme"
    if motivo.startswith("token_invalido"):
        return "deny_invalid_token"
    return "deny_insufficient_scope"


_ERROR_DE = {"deny_no_token": "no_token", "deny_bad_scheme": "bad_scheme", "deny_invalid_token": "invalid_token",
             "deny_insufficient_scope": "insufficient_scope"}


def _lista(scopes) -> str:
    return " ".join(sorted(s for s in scopes if s in SCOPES or s == PERMISOS["scope_base"]))


def envolver_evaluar(evaluar):
    async def evaluar_trazado(encabezados, metodo, nombre):
        with _span("authorize", contexto=contexto_padre()) as span:
            at, rechazo = await evaluar(encabezados, metodo, nombre)
            decision = _decision(rechazo)
            requeridos = scopes_requeridos(metodo, nombre if isinstance(nombre, str) else None)
            otorgados = set(at.scopes) if at is not None else set()
            conocida = metodo == "tools/call" and isinstance(nombre, str) and nombre in PERMISOS["herramientas"]
            E.fijar(span, "autorizacion", {
                "lab.authz.decision": decision,
                "mcp.method.name": metodo if metodo in E.METODOS_MCP else "other",
                "lab.tool.name": nombre if conocida else None,
                "lab.authz.scopes.required": _lista(requeridos), "lab.authz.scopes.granted": _lista(otorgados),
                "lab.authz.scopes.missing": _lista(requeridos - otorgados) if rechazo and rechazo.estado == 403 else None,
                "lab.authz.client": at.client_id if at is not None and E.ID(at.client_id or "") else None,
                "user.id": E.seudonimo(at.subject) if at is not None and at.subject else None,
                "error.type": _ERROR_DE.get(decision)})
            if rechazo is not None:
                span.set_status(Status(StatusCode.ERROR, decision))
            return at, rechazo
    return evaluar_trazado


# ---------- the tools ----------

def envolver_llamar(llamar):
    @functools.wraps(llamar)
    def llamar_trazado(self, nombre, argumentos):
        conocida = nombre in ENTRADAS
        etiqueta = nombre if conocida else "_unknown"
        with _span(f"handle_tool {etiqueta}") as span:
            res = llamar(self, nombre, argumentos)
            ok = bool(res.get("ok", False))
            tipo = E.tipo_error((res.get("error") or {}).get("tipo")) if not ok else None
            E.fijar(span, "herramienta_servidor", {
                "lab.tool.name": etiqueta, "lab.tool.known": conocida,
                "lab.tool.args.chars": len(E.canonico(argumentos or {})),
                "lab.tool.args.hmac": E.seudonimo(E.canonico(argumentos or {})),
                "lab.tool.result.chars": len(json.dumps(res, ensure_ascii=False, default=str)),
                "lab.tool.status": "ok" if ok else "error", "user.id": E.seudonimo(self.ctx.usuario),
                "error.type": tipo})
            if not ok:
                span.set_status(Status(StatusCode.ERROR, tipo or "tool_error"))
            return res
    return llamar_trazado


def _tablas_en(sql: str) -> str:
    return " ".join(t for t in TABLAS if re.search(rf"\b{re.escape(t)}\b", sql, re.IGNORECASE))


def envolver_correr(correr):
    @functools.wraps(correr)
    def correr_trazado(self, sql, explicar=False):
        operacion = "EXPLAIN" if explicar else "SELECT"
        with _span(f"{operacion} legado", SpanKind.CLIENT) as span:
            rol = getattr(self.ctx.conexion, "rol", None)
            E.fijar(span, "sql", {
                "db.system.name": "postgresql", "db.namespace": "legado", "db.operation.name": operacion,
                "lab.db.query.chars": len(sql), "lab.db.query.hmac": E.seudonimo(sql), "lab.db.tables": _tablas_en(sql),
                "lab.db.role": rol if isinstance(rol, str) and E.ID(rol) else None})
            try:
                columnas, filas = correr(self, sql, explicar)
            except Exception as e:   # noqa: BLE001  only the tool's error type (an identifier), never its message
                tipo = E.tipo_error(getattr(e, "tipo", None)) or type(e).__name__
                E.fijar(span, "sql", {"error.type": tipo})
                span.set_status(Status(StatusCode.ERROR, tipo))
                raise
            E.fijar(span, "sql", {"db.response.returned_rows": len(filas)})
            return columnas, filas
    return correr_trazado


# ---------- install / uninstall ----------

class InstrumentorServidor:
    """`instrument()` before creating the servers (the app is built then); `uninstrument()` restores everything."""

    def __init__(self):
        self._originales: dict = {}

    def instrument(self) -> "InstrumentorServidor":
        if self._originales:
            return self
        o = self._originales
        o["crear_app"] = servidor_lab.crear_app
        o["llamar"], o["correr"] = Herramientas.llamar, Herramientas._correr
        crear_app = o["crear_app"]

        def crear_app_trazada(*a, **kw):
            app = crear_app(*a, **kw)
            autorizador = getattr(app, "autorizador", None)
            if autorizador is not None:
                autorizador.evaluar = envolver_evaluar(autorizador.evaluar)
            return PeticionASGI(app)

        servidor_lab.crear_app = crear_app_trazada
        Herramientas.llamar = envolver_llamar(o["llamar"])
        Herramientas._correr = envolver_correr(o["correr"])
        return self

    def uninstrument(self) -> None:
        o, self._originales = self._originales, {}
        if o:
            servidor_lab.crear_app = o["crear_app"]
            Herramientas.llamar, Herramientas._correr = o["llamar"], o["correr"]

    def __enter__(self):
        return self.instrument()

    def __exit__(self, *a):
        self.uninstrument()
