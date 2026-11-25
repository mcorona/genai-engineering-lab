"""Week 19, activity 6: the agent Lambda's request path, with its collaborators injected.

Order of one request (each step is a guard of the lab's plan):
  1. identity: the scopes and tenant come from the token claims, never from the request (week 17 `Alcance`);
  2. input guardrail (deterministic, week 17 core) BEFORE any model call: a block answers `abstenida` at no model cost;
  3. the week 17 budget around the model calls (`Presupuesto`);
  4. the agent loop (week 13, reused through `agente_factory`), its tools wrapped by the deterministic layer;
  5. output guardrail on the final answer (audit mode, the shipped mode of week 17);
  6. one `invoke_agent` span through the exporter (locked shape), with the subject as a keyed hash, never the token,
     and on the same line the query's EMF metrics (week 20, activity 2: agente/metricas.py).

The Lambda binding to the real loop and tools is `construir_deps()`; it is not written yet and raises until it is.
Everything here is pure orchestration and is tested offline with fakes.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable

from agente import capa_determinista as C
from agente import metricas
from agente.cliente_gateway import TokenVencido
from agente.exportador import ExportadorSpans
from agente.presupuesto import Politica, Precios, Presupuesto
from instrumentacion import esquema

N = C.N
MODELO = "claude-haiku-4-5-20251001"
AGENTE = "legadobridge"
RUTA = "fija"      # week 20, activity 2: the route dimension of the metrics; activity 4's router sets it per call
MOTIVO_PRESUPUESTO = {"presupuesto_usd": "presupuesto_tarea", "presupuesto_tokens": "presupuesto_tarea"}
# The tools path in the execute_tool span, with week 17's locked attribute and values (no new key): OpenTelemetry's
# gen_ai.tool.type "function" for the direct call, "extension" for a tool reached through the gateway (agent side,
# bridging to an external API). Activity 7.
TIPO_DE_HERRAMIENTA = {"directo": "function", "gateway": "extension"}
TEXTO_TOKEN_VENCIDO = "Tu sesión venció antes de terminar la consulta. Vuelve a iniciar sesión y repite la pregunta."


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
    resultados: list = field(default_factory=list)   # the answer's keys: clave, sql, valor (after the final checks)


def run_id_de(id_consulta: str | None) -> str | None:
    """The spans' lab.run.id for a question: the first 12 hex digits of its id (a UUID), so a question's spans can be
    found from its id (activity 7, comparison). Anything else gets a random run id, as before."""
    digitos = re.sub(r"[^0-9a-f]", "", str(id_consulta or "").lower())
    return digitos[:12] if len(digitos) >= 12 else None


def _decision(d) -> dict:
    return {"guardrail": d.guardrail, "etapa": d.etapa, "accion": d.accion, "motivo": d.motivo}


class HerramientasCapadas:
    """What the loop sees as its tools: each call passes the deterministic layer before it runs."""

    def __init__(self, llamar, definiciones, alcance, pregunta, decisiones, camino: str = "directo"):
        self._llamar, self._defs, self.alcance, self.pregunta = llamar, definiciones, alcance, pregunta
        self.decisiones = decisiones
        self.llamadas = 0
        self.tipo = TIPO_DE_HERRAMIENTA[camino]
        self.spans: list[dict] = []

    def definiciones(self):
        return self._defs

    def llamar(self, nombre: str, args: dict) -> dict:
        self.llamadas += 1
        error, decisiones = C.revisar_herramienta(nombre, args, alcance=self.alcance, peticion=self.pregunta,
                                                  definiciones=self._defs)
        self.decisiones.extend(decisiones)
        if error is not None:
            return self._span(nombre, args, error)
        try:
            if nombre == "proponer_orden_compra":   # the requester comes from the verified token, never from the model
                res = self._llamar(nombre, args, solicitante=self.alcance.usuario)
            else:
                res = self._llamar(nombre, args)
        except TokenVencido:
            self._span(nombre, args, {"ok": False, "error": {"tipo": "token_vencido"}})
            raise
        # H13 (activity 9): the result passes week 17's sanitizer before the model sees it, as in semana-17/guardrails/agente.py.
        res, de_resultado = C.revisar_resultado(res, getattr(self.alcance, "idioma", "es"))
        self.decisiones.extend(de_resultado)
        return self._span(nombre, args, res)

    def _span(self, nombre: str, args: dict, res: dict) -> dict:
        """One execute_tool span per call in week 17's locked shape: arguments as size and keyed hash, never text."""
        import json
        conocida = nombre in C.HERRAMIENTAS
        ok = bool(res.get("ok", False))
        canon = esquema.canonico(args or {})
        atributos = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": nombre if conocida else None,
                     "gen_ai.tool.type": self.tipo, "lab.step": self.llamadas, "lab.tool.known": conocida,
                     "lab.tool.args.chars": len(canon), "lab.tool.args.hmac": esquema.seudonimo(canon),
                     "lab.tool.result.chars": len(json.dumps(res, ensure_ascii=False, default=str)),
                     "lab.tool.status": "ok" if ok else "error",
                     "error.type": None if ok else esquema.tipo_error((res.get("error") or {}).get("tipo"))}
        self.spans.append({"name": f"execute_tool {nombre if conocida else '_unknown'}", "tipo": "execute_tool",
                           "attrs": {k: v for k, v in atributos.items() if v is not None}})
        return res


def tratar_pregunta(pregunta: str, alcance, *, agente_factory: Callable, llamar_herramienta: Callable, definiciones: list,
                    api_modelo: Callable, politica: Politica, precios: Precios, exportar: Callable[[str], None],
                    run_id: str | None = None, camino: str = "directo", cerrar: Callable | None = None) -> Resultado:
    """`cerrar` ends the tools session (the gateway's MCP session) when the question ends, whatever the outcome."""
    try:
        return _tratar(pregunta, alcance, agente_factory=agente_factory, llamar_herramienta=llamar_herramienta,
                       definiciones=definiciones, api_modelo=api_modelo, politica=politica, precios=precios,
                       exportar=exportar, run_id=run_id or uuid.uuid4().hex[:12], camino=camino,
                       inicio=time.monotonic())
    finally:
        if cerrar is not None:
            cerrar()


def _tratar(pregunta, alcance, *, agente_factory, llamar_herramienta, definiciones, api_modelo, politica, precios,
            exportar, run_id, camino, inicio) -> Resultado:
    decisiones: list = []
    motivo, de_entrada = C.revisar_entrada(pregunta)
    decisiones.extend(de_entrada)
    if motivo is not None:
        texto = N.texto_de_rechazo_de_entrada(motivo, "es")
        return _cerrar(run_id, alcance, "abstenida", texto, decisiones, None, None, exportar, politica, "guardrail_entrada",
                       inicio=inicio)

    presupuesto = Presupuesto(politica, MODELO, precios)
    herramientas = HerramientasCapadas(llamar_herramienta, definiciones, alcance, pregunta, decisiones, camino)
    agente = agente_factory(presupuesto.envolver(api_modelo), herramientas)
    tarea = {"id": f"consulta-{run_id}", "tarea": pregunta}
    try:
        r = agente.resolver(tarea)
    except TokenVencido:   # fail closed: the loop stops here, with week 17's state for a run that could not finish
        return _cerrar(run_id, alcance, "error", TEXTO_TOKEN_VENCIDO, decisiones, None, presupuesto, exportar, politica,
                       "otro", herramientas=herramientas, inicio=inicio)

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
    resultados = list((final or {}).get("resultados") or []) if estado == "respondida" else []
    return _cerrar(run_id, alcance, estado, texto, decisiones, r, presupuesto, exportar, politica, motivo_fin,
                   herramientas=herramientas, resultados=resultados, inicio=inicio)


def _spans_chat(llamadas: list[dict]) -> list[dict]:
    """One `chat` span per model call (week 17's locked shape), with its tokens, cache tokens and cost (week 20,
    activity 3: the cache read and written per step). The call's duration is not an attribute of that shape; it goes on
    the agent line as `duracion_pasos_ms`."""
    return [{"name": f"chat {MODELO}", "tipo": "chat", "attrs": {
        "gen_ai.operation.name": "chat", "gen_ai.request.model": MODELO, "lab.step": x["paso"],
        "gen_ai.usage.input_tokens": x["entrada"], "gen_ai.usage.output_tokens": x["salida"],
        "gen_ai.usage.cache_read.input_tokens": x["lectura"],
        "gen_ai.usage.cache_creation.input_tokens": x["escritura"], "lab.cost.usd": x["usd"]}} for x in llamadas]


def _costo(r, presupuesto) -> float | None:
    """The query's model cost: the loop's (input and output tokens) plus the prompt cache's, which the loop does not
    price (week 20, activity 3). Without a cache point the second term is 0 and the cost is week 19's."""
    base = getattr(r, "costo_usd", None)
    if base is None:
        return None
    return base + (getattr(presupuesto, "costo_cache", 0.0) or 0.0)


def _cerrar(run_id, alcance, estado, texto, decisiones, r, presupuesto, exportar, politica, motivo, herramientas=None,
            resultados=None, inicio=None):
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
        "lab.run.cost_usd": _costo(r, presupuesto),
        "lab.run.tokens.cache_read": getattr(presupuesto, "cache_lectura", None),
        "lab.run.tokens.cache_creation": getattr(presupuesto, "cache_escritura", None),
    }
    llamadas = list(getattr(presupuesto, "por_llamada", None) or [])
    spans = [*(herramientas.spans if herramientas else []), *_spans_chat(llamadas),
             {"name": f"invoke_agent {AGENTE}", "tipo": "invoke_agent",
              "attrs": {k: v for k, v in atributos.items() if v is not None}}]
    latencia_ms = (time.monotonic() - inicio) * 1000 if inicio is not None else 0.0
    emf = metricas.miembros_emf(atributos, latencia_ms=latencia_ms, modelo=MODELO, ruta=RUTA,
                                ahora_ms=int(time.time() * 1000))
    ExportadorSpans(escribir=exportar).exportar(spans, emf=emf,
                                                extra={"duracion_pasos_ms": [x["ms"] for x in llamadas]})
    return Resultado(estado, texto, [_decision(d) for d in decisiones], spans, resultados or [])


def construir_deps(token: str | None = None):
    """The Lambda's real collaborators (agente/construccion.py). The environment is checked before any client exists."""
    import os

    import boto3  # provided by the Lambda runtime

    from agente import construccion
    construccion.exigir_entorno(os.environ)
    return construccion.construir(cliente_converse=boto3.client("bedrock-runtime"), cliente_lambda=boto3.client("lambda"),
                                  cliente_logs=boto3.client("logs"), token=token)


def handler(event: dict, context, deps: dict | None = None) -> dict:
    """event = {"claims": {...}, "pregunta": str, "token": str}. The claims come from the API's authorizer (verified
    there); the token is the user's access token, used only on the gateway path and never logged or stored."""
    alcance = alcance_desde_claims(event.get("claims", {}))
    d = deps or construir_deps(event.get("token"))
    try:
        res = tratar_pregunta(event["pregunta"], alcance, run_id=run_id_de(event.get("id")), **d)
    finally:
        _vaciar_spans(d.get("exportar"))
    return {"estado": res.estado, "respuesta": res.respuesta, "decisiones": res.decisiones, "resultados": res.resultados}


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
