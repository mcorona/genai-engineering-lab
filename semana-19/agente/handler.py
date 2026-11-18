"""Week 19, activity 6: the agent Lambda's request path, with its collaborators injected.

Order of one request (each step is a guard of the lab's plan):
  1. identity: the scopes and tenant come from the token claims, never from the request (week 17 `Alcance`);
  2. input guardrail (deterministic, week 17 core) BEFORE any model call: a block answers `abstenida` at no model cost;
  3. the week 17 budget around the model calls (`Presupuesto`);
  4. the agent loop (week 13, reused through `agente_factory`), its tools wrapped by the deterministic layer;
  5. output guardrail on the final answer (audit mode, the shipped mode of week 17);
  6. one `invoke_agent` span through the exporter (locked shape), with the subject as a keyed hash, never the token.

The Lambda binding to the real loop and tools is `construir_deps()`; it is not written yet and raises until it is.
Everything here is pure orchestration and is tested offline with fakes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable

from agente import capa_determinista as C
from agente.exportador import ExportadorSpans
from agente.presupuesto import Politica, Precios, Presupuesto
from instrumentacion import esquema

N = C.N
MODELO = "claude-haiku-4-5-20251001"
AGENTE = "legadobridge"
MOTIVO_PRESUPUESTO = {"presupuesto_usd": "presupuesto_tarea", "presupuesto_tokens": "presupuesto_tarea"}


# The token's data scopes (resource server `legado`, see computo/tokens.py) to the week 17 vocabulary.
SCOPES_DE_TOKEN = {
    "legado/leer": "legado:leer",
    "legado/proveedores": "legado:proveedores",
    "legado/ventas": "legado:ventas",
    "legado/compras_proponer": "legado:compras:proponer",
}


def alcance_desde_claims(claims: dict) -> "N.Alcance":
    """Scopes and tenant from the token. Unknown scopes are dropped; a missing tenant is refused."""
    if not claims.get("sub") or not claims.get("tenant"):
        raise PermissionError("el token no trae sujeto o tenant")
    scopes = frozenset(SCOPES_DE_TOKEN[s] for s in str(claims.get("scope", "")).split() if s in SCOPES_DE_TOKEN)
    return N.Alcance(claims["sub"], claims["tenant"], scopes, "es")


@dataclass
class Resultado:
    estado: str
    respuesta: str
    decisiones: list
    spans: list


def _decision(d) -> dict:
    return {"guardrail": d.guardrail, "etapa": d.etapa, "accion": d.accion, "motivo": d.motivo}


class HerramientasCapadas:
    """What the loop sees as its tools: each call passes the deterministic layer before it runs."""

    def __init__(self, llamar, definiciones, alcance, pregunta, decisiones):
        self._llamar, self._defs, self.alcance, self.pregunta = llamar, definiciones, alcance, pregunta
        self.decisiones = decisiones
        self.llamadas = 0

    def definiciones(self):
        return self._defs

    def llamar(self, nombre: str, args: dict) -> dict:
        self.llamadas += 1
        error, decisiones = C.revisar_herramienta(nombre, args, alcance=self.alcance, peticion=self.pregunta,
                                                  definiciones=self._defs)
        self.decisiones.extend(decisiones)
        if error is not None:
            return error
        if nombre == "proponer_orden_compra":   # the requester comes from the verified token, never from the model
            return self._llamar(nombre, args, solicitante=self.alcance.usuario)
        return self._llamar(nombre, args)


def tratar_pregunta(pregunta: str, alcance, *, agente_factory: Callable, llamar_herramienta: Callable, definiciones: list,
                    api_modelo: Callable, politica: Politica, precios: Precios, exportar: Callable[[str], None],
                    run_id: str | None = None) -> Resultado:
    run_id = run_id or uuid.uuid4().hex[:12]
    decisiones: list = []
    motivo, de_entrada = C.revisar_entrada(pregunta)
    decisiones.extend(de_entrada)
    if motivo is not None:
        texto = N.texto_de_rechazo_de_entrada(motivo, "es")
        return _cerrar(run_id, alcance, "abstenida", texto, decisiones, None, None, exportar, politica, "guardrail_entrada")

    presupuesto = Presupuesto(politica, MODELO, precios)
    herramientas = HerramientasCapadas(llamar_herramienta, definiciones, alcance, pregunta, decisiones)
    agente = agente_factory(presupuesto.envolver(api_modelo), herramientas)
    tarea = {"id": f"consulta-{run_id}", "tarea": pregunta}
    r = agente.resolver(tarea)

    final = r.final
    if final is not None:
        final, de_salida = C.revisar_final(final, conocidas=C.conocidas_de(pregunta),
                                           herramientas_ok=herramientas.llamadas)
        decisiones.extend(de_salida)
    estado = r.estado if final is None else final["estado"]
    texto = (final or {}).get("respuesta", "")
    motivo_fin = r.motivo
    if presupuesto.motivo is not None:
        estado, motivo_fin = "limite_alcanzado", MOTIVO_PRESUPUESTO[presupuesto.motivo]
    return _cerrar(run_id, alcance, estado, texto, decisiones, r, presupuesto, exportar, politica, motivo_fin,
                   herramientas=herramientas)


def _cerrar(run_id, alcance, estado, texto, decisiones, r, presupuesto, exportar, politica, motivo, herramientas=None):
    atributos = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": AGENTE,
        "gen_ai.request.model": MODELO,
        "user.id": esquema.seudonimo(alcance.usuario),
        "lab.tenant.id": alcance.tenant,
        "lab.task.id": f"consulta-{run_id}",
        "lab.task.language": "es",
        "lab.run.id": run_id,
        "lab.schema.version": esquema.SCHEMA_VERSION,
        "lab.model.scripted": False,
        "lab.outcome.status": estado,
        "lab.outcome.reason": motivo if motivo in esquema.MOTIVOS else "otro",
        "lab.run.steps": getattr(r, "pasos", None),
        "lab.run.tool_calls": herramientas.llamadas if herramientas else None,
        "lab.run.tool_errors": getattr(r, "errores_herramienta", None),
        "lab.run.tokens.input": getattr(r, "tokens_in", None),
        "lab.run.tokens.output": getattr(r, "tokens_out", None),
        "lab.run.cost_usd": getattr(r, "costo_usd", None),
    }
    spans = [{"name": f"invoke_agent {AGENTE}", "tipo": "invoke_agent",
              "attrs": {k: v for k, v in atributos.items() if v is not None}}]
    ExportadorSpans(escribir=exportar).exportar(spans)
    return Resultado(estado, texto, [_decision(d) for d in decisiones], spans)


def construir_deps():
    """The Lambda's real collaborators (agente/construccion.py). The environment is checked before any client exists."""
    import os

    import boto3  # provided by the Lambda runtime

    from agente import construccion
    construccion.exigir_entorno(os.environ)
    return construccion.construir(cliente_converse=boto3.client("bedrock-runtime"), cliente_lambda=boto3.client("lambda"),
                                  cliente_logs=boto3.client("logs"))


def handler(event: dict, context, deps: dict | None = None) -> dict:
    """event = {"claims": {...}, "pregunta": str}. The claims come from the API's authorizer (verified there)."""
    alcance = alcance_desde_claims(event.get("claims", {}))
    d = deps or construir_deps()
    try:
        res = tratar_pregunta(event["pregunta"], alcance, **d)
    finally:
        _vaciar_spans(d.get("exportar"))
    return {"estado": res.estado, "respuesta": res.respuesta, "decisiones": res.decisiones}


def _vaciar_spans(exportar) -> None:
    """The CloudWatch sink sends in batches; what is pending goes out before the invocation ends (the Lambda may be frozen
    or recycled right after). A failure to send is logged by type only and never changes the answer."""
    vaciar = getattr(exportar, "vaciar", None)
    if vaciar is None:
        return
    try:
        vaciar()
    except Exception as error:  # noqa: BLE001 — observability must not fail the question
        import logging
        logging.getLogger(__name__).error("spans no enviados: %s", type(error).__name__)
