"""Week 17, activity 3: the lab bench shared by the tests and `correr.py`.

Real pieces: the week 13 agent loop, the week 14 MCP client, a real Streamable HTTP server behind the OAuth boundary (a
lab issuer signs RS256 tokens) and the PostgreSQL legacy schema. Scripted piece: the model.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from . import esquema as E
from .modelo_guionado import TAREA, ModeloGuionado
from .trazas_agente import AgenteInstrumentado
from .trazas_cliente import ClienteInstrumentado
from .trazas_servidor import InstrumentorServidor

S14 = Path(__file__).resolve().parents[2] / "semana-14"
SERVICIO = "legacybridge"

from servidor.primitivas import manifiesto  # noqa: E402  (semana-14 is on sys.path through trazas_cliente)

from cliente.seguro import ServidorMCP  # noqa: E402

_PROVEEDOR: dict = {}


def configurar_trazas(otlp_http: str | None = None) -> InMemorySpanExporter:
    """Global TracerProvider (once per process): an in-memory exporter for the checks and, if `otlp_http` is given, the
    OTLP HTTP exporter to the Collector. Calling it again returns the same exporter."""
    if "exportador" in _PROVEEDOR:
        return _PROVEEDOR["exportador"]
    memoria = InMemorySpanExporter()
    proveedor = TracerProvider(resource=Resource.create({"service.name": SERVICIO, "service.version": E.SCHEMA_VERSION}))
    proveedor.add_span_processor(SimpleSpanProcessor(memoria))
    if otlp_http:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        proveedor.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_http)))
    trace.set_tracer_provider(proveedor)
    _PROVEEDOR.update(exportador=memoria, proveedor=proveedor)
    return memoria


def vaciar_exportador() -> None:
    proveedor = _PROVEEDOR.get("proveedor")
    if proveedor is not None:
        proveedor.force_flush()
    _PROVEEDOR["exportador"].clear()


def cerrar_trazas() -> None:
    proveedor = _PROVEEDOR.get("proveedor")
    if proveedor is not None:
        proveedor.force_flush()


def cargar_entorno(emisor: str = "prueba"):
    spec = importlib.util.spec_from_file_location("correr_seguridad14_s17", S14 / "seguridad" / "correr.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Entorno(emisor, con_base=True)


def sujeto_de(token: str) -> str:
    """`sub` of a token the agent holds (read without verifying: the server verifies it)."""
    import jwt
    return jwt.decode(token, options={"verify_signature": False})["sub"]


class Laboratorio:
    """Instruments the server, starts it (with the database) and builds instrumented agents for a profile."""

    def __init__(self, tenant: str = "lab"):
        self.tenant = tenant
        self.instrumentor = InstrumentorServidor().instrument()
        self.entorno = None
        self.clientes: list[ClienteInstrumentado] = []
        try:
            self.entorno = cargar_entorno("prueba")
        except BaseException:
            self.instrumentor.uninstrument()
            raise

    def correr(self, turnos: list[dict], *, usuario: str = "analista", tarea: dict | None = None, modelo_falla: int | None = None,
               mensaje_de_falla: str = "scripted API failure", cliente_clase=ClienteInstrumentado,
               catalogo_obsoleto: dict | None = None, **kw):
        """One task with the scripted model. Returns (Resultado, ModeloGuionado, client).
        `catalogo_obsoleto` adds tools to the client's name map after the catalog was read, as if the token's scopes had
        shrunk since a cached `tools/list`: the call reaches the server and the boundary answers 403."""
        srv = self.entorno.servidores["normal"]
        token = self.entorno.token(usuario)
        cliente = cliente_clase([ServidorMCP("legado", srv.url, token)],
                                allowlist={"legado": {"pins": manifiesto()["herramientas"]}}, defensas=True).abrir()
        self.clientes.append(cliente)
        modelo = ModeloGuionado(turnos, falla_en=modelo_falla, mensaje_de_falla=mensaje_de_falla)
        agente = AgenteInstrumentado(cliente, api=modelo, tenant=self.tenant, simulado=True, **kw)
        if catalogo_obsoleto:
            cliente._mapa.update(catalogo_obsoleto)
        r = agente.resolver(tarea or TAREA, sujeto_de(token))
        return r, modelo, cliente

    def token(self, usuario: str) -> str:
        return self.entorno.token(usuario)

    def cerrar(self):
        for c in self.clientes:
            try:
                c.cerrar()
            except Exception:   # noqa: BLE001
                pass
        self.clientes.clear()
        try:
            if self.entorno is not None:
                self.entorno.cerrar()
        finally:
            self.instrumentor.uninstrument()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()


def resumen(spans) -> list[dict]:
    return [{"name": s.name, "kind": s.kind.name, "trace": format(s.context.trace_id, "032x"),
             "span": format(s.context.span_id, "016x"),
             "parent": format(s.parent.span_id, "016x") if s.parent else None,
             "inicio": s.start_time, "fin": s.end_time,
             "estado": s.status.status_code.name, "descripcion_estado": s.status.description,
             "eventos": [{"name": ev.name, "attrs": dict(ev.attributes or {})} for ev in s.events],
             "recurso": dict(s.resource.attributes), "alcance": s.instrumentation_scope.name if s.instrumentation_scope else "",
             "attrs": dict(s.attributes or {})} for s in spans]


if __name__ == "__main__":      # quick look: python -m instrumentacion.laboratorio (from semana-17)
    from .modelo_guionado import turnos_principal
    exp = configurar_trazas()
    E.ESTRICTO = True
    with Laboratorio() as lab:
        r, modelo, cliente = lab.correr(turnos_principal())
    print(json.dumps({"estado": r.estado, "pasos": r.pasos, "tokens": [r.tokens_in, r.tokens_out], "costo": r.costo_usd}))
    for s in resumen(exp.get_finished_spans()):
        print(s["trace"][:6], (s["parent"] or "-")[:6], s["span"][:6], s["kind"], s["name"], s["estado"])
