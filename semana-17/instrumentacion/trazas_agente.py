"""Week 17, activity 3: agent-side spans for the week 13 loop, without touching its code.

    invoke_agent legacybridge            one per task: who, which task, budget, outcome, run totals
      chat claude-haiku-5-5              one per model call: tokens (cache included), cost, finish reason
      execute_tool legado__ejecutar_sql  one per tool call: arguments as size + keyed hash, status, result size

The loop (`semana-13/agente/loop.py`) takes the model call (`api`) and the tools source as injectable pieces, so the
instrumentation wraps both and wraps `resolver`. No prompt, tool argument, SQL, row or error message is ever recorded.

Token convention: `gen_ai.usage.input_tokens` is the TOTAL input (uncached + cache read + cache creation), as the OTel
GenAI conventions define it. The Anthropic API reports `input_tokens` as the uncached part only, and Langfuse subtracts the
cached tokens again (activity 2), so summing here is what makes the stored numbers right. The run totals on the
`invoke_agent` span use the loop's own counters (uncached), so the tests can check that the children add up.
"""
from __future__ import annotations

import contextvars
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import Error

from . import esquema as E

S13 = Path(__file__).resolve().parents[2] / "semana-13"
if str(S13) not in sys.path:
    sys.path.insert(0, str(S13))

from agente.loop import Agente, Limites, costo  # noqa: E402

PROVEEDOR = "anthropic"
AGENTE = "legacybridge"
SERVIDOR_API = ("api.anthropic.com", 443)


@dataclass
class EstadoCorrida:
    """State of one `resolver` call. Kept in a ContextVar, so concurrent tasks on one instance do not mix."""
    paso: int = 0
    pendientes: deque = field(default_factory=deque)       # (tool name, args hmac, tool_use id) asked by the model
    cache_lectura: int = 0
    cache_creacion: int = 0


_ESTADO: contextvars.ContextVar = contextvars.ContextVar("legacybridge_estado", default=None)


def _entero(valor) -> int:
    return int(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor >= 0 else 0


def _finalizacion(razon) -> str | None:
    if razon is None:
        return None
    return razon if razon in E.FINALIZACIONES else "other"


def api_instrumentada(api, *, simulado: bool = False, proveedor: str = PROVEEDOR):
    """The model call wrapped in a `chat {model}` span. `simulado` marks scripted models so no dashboard mistakes them for
    real calls (`lab.model.scripted`)."""

    def llamar(cuerpo: dict) -> dict:
        est = _ESTADO.get()
        modelo = cuerpo.get("model", "unknown")
        if est is not None:
            est.paso += 1
        inf = get_telemetry_handler().inference(proveedor, request_model=modelo, server_address=SERVIDOR_API[0],
                                                server_port=SERVIDOR_API[1])
        try:
            d = api(cuerpo)
        except BaseException as e:   # noqa: BLE001  the message of an API error can echo the request: only the class is kept
            E.fijar(inf.span, "chat", {"lab.step": est.paso if est else None, "lab.model.scripted": simulado or None})
            inf.fail(Error(message=type(e).__name__, type=type(e).__name__))
            raise
        u = d.get("usage") or {}
        tin, tout = _entero(u.get("input_tokens")), _entero(u.get("output_tokens"))
        lectura, creacion = _entero(u.get("cache_read_input_tokens")), _entero(u.get("cache_creation_input_tokens"))
        inf.input_tokens = tin + lectura + creacion
        inf.output_tokens = tout
        if lectura:
            inf.cache_read_input_tokens = lectura
        if creacion:   # semconv name; util-genai 1.3b0 would write `cache_write` (see esquema.py and resultados)
            E.fijar(inf.span, "chat", {"gen_ai.usage.cache_creation.input_tokens": creacion})
        razon = _finalizacion(d.get("stop_reason"))
        inf.finish_reasons = [razon] if razon else None
        if E.ID(str(d.get("model", ""))):
            inf.response_model_name = d["model"]
        if E.ID(str(d.get("id", ""))):
            inf.response_id = d["id"]
        inf.max_tokens = _entero(cuerpo.get("max_tokens")) or None
        nivel = (cuerpo.get("output_config") or {}).get("effort")
        gasto = costo(modelo, tin, tout) if f"anthropic:{modelo}" in _precios() else None
        atributos = {"gen_ai.request.reasoning.level": nivel, "lab.step": est.paso if est else None,
                     "lab.model.scripted": simulado or None, "lab.cost.usd": round(gasto, 8) if gasto is not None else None,
                     "langfuse.observation.cost_details": f'{{"total": {round(gasto, 8)}}}' if gasto is not None else None}
        E.fijar(inf.span, "chat", atributos)
        if est is not None:
            est.cache_lectura += lectura
            est.cache_creacion += creacion
            for b in d.get("content", []):
                if b.get("type") == "tool_use":
                    est.pendientes.append((b.get("name"), E.seudonimo(E.canonico(b.get("input") or {})), b.get("id")))
        inf.stop()
        return d

    return llamar


def _precios() -> dict:
    from agente.loop import PRECIOS
    return PRECIOS


class HerramientasInstrumentadas:
    """Tools source wrapped in `execute_tool {name}` spans. `definiciones()`/`llamar()` are all the loop needs; the rest
    (`llamadas`, `eventos`, ...) passes through to the wrapped source."""

    def __init__(self, base):
        self._base = base
        self._conocidas: set[str] = set()

    def __getattr__(self, nombre):
        return getattr(self._base, nombre)

    def definiciones(self) -> list[dict]:
        if hasattr(self._base, "definiciones"):
            defs = self._base.definiciones()
        else:
            from herramientas import definiciones
            defs = definiciones()
        self._conocidas = {d["name"] for d in defs}
        return defs

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        est = _ESTADO.get()
        conocida = nombre in self._conocidas
        # The name comes from the model: an unknown one never becomes part of a span name.
        etiqueta = nombre if conocida else "_unknown"
        hmac_args = E.seudonimo(E.canonico(argumentos or {}))
        llamada_id = None
        if est is not None:
            for i, (n, h, uid) in enumerate(est.pendientes):
                if n == nombre and h == hmac_args:
                    llamada_id = uid
                    del est.pendientes[i]
                    break
        inv = get_telemetry_handler().tool(etiqueta, tool_type="function")
        try:
            res = self._base.llamar(nombre, argumentos)
        except BaseException as e:   # noqa: BLE001
            inv.fail(Error(message=type(e).__name__, type=type(e).__name__))
            raise
        ok = bool(res.get("ok", False))
        tipo = E.tipo_error((res.get("error") or {}).get("tipo")) if not ok else None
        import json
        E.fijar(inv.span, "execute_tool", {
            "gen_ai.tool.call.id": llamada_id if llamada_id and E.ID(str(llamada_id)) else None,
            "lab.step": est.paso if est else None, "lab.tool.known": conocida,
            "lab.tool.args.chars": len(E.canonico(argumentos or {})), "lab.tool.args.hmac": hmac_args,
            "lab.tool.result.chars": len(json.dumps(res, ensure_ascii=False, default=str)),
            "lab.tool.status": "ok" if ok else "error"})
        if ok:
            inv.stop()
        else:
            inv.fail(Error(message=tipo or "tool_error", type=tipo or "tool_error"))
        return res


class AgenteInstrumentado:
    """`Agente` of week 13 with the `invoke_agent` / `chat` / `execute_tool` spans. Same `resolver(tarea) -> Resultado`."""

    def __init__(self, herramientas, *, api, tenant: str, modelo: str = "claude-haiku-5-5", esfuerzo: str = "low",
                 limites: Limites | None = None, simulado: bool = False, nombre: str = AGENTE, trazas: Path | None = None):
        self.nombre, self.modelo, self.tenant, self.simulado = nombre, modelo, tenant, simulado
        self.limites = limites or Limites()
        self.herramientas = HerramientasInstrumentadas(herramientas)
        self.agente = Agente(self.herramientas, modelo, esfuerzo, self.limites,
                             api=api_instrumentada(api, simulado=simulado), trazas=trazas)

    def resolver(self, tarea: dict, sujeto: str):
        """`sujeto` is the token subject (`sub`) of the user the run acts for; only its keyed hash is recorded."""
        est = EstadoCorrida()
        token = _ESTADO.set(est)
        lim = self.limites
        inv = get_telemetry_handler().invoke_local_agent(agent_name=self.nombre, request_model=self.modelo)
        E.fijar(inv.span, "invoke_agent", {
            "user.id": E.seudonimo(sujeto), "lab.tenant.id": self.tenant, "lab.task.id": str(tarea.get("id", "")),
            "lab.task.language": tarea.get("lang") or (str(tarea.get("id", "")).rsplit("-", 1)[-1] or None),
            "lab.schema.version": E.SCHEMA_VERSION, "lab.model.scripted": self.simulado or None,
            "lab.budget.max_steps": lim.max_pasos, "lab.budget.max_tool_calls": lim.max_herramientas,
            "lab.budget.max_tokens_total": lim.max_tokens_total, "lab.budget.max_seconds": lim.max_segundos,
            "lab.budget.max_output_tokens": lim.max_tokens_salida})
        try:
            r = self.agente.resolver(tarea)
        except BaseException as e:   # noqa: BLE001
            inv.fail(Error(message="other", type="other"))
            raise
        finally:
            _ESTADO.reset(token)
        E.fijar(inv.span, "invoke_agent", {
            "lab.run.id": r.corrida, "lab.outcome.status": r.estado, "lab.outcome.reason": E.clasificar_motivo(r.motivo or ""),
            "lab.run.steps": r.pasos, "lab.run.tool_calls": r.herramientas, "lab.run.tool_errors": r.errores_herramienta,
            "lab.run.tokens.input": r.tokens_in, "lab.run.tokens.output": r.tokens_out,
            "lab.run.tokens.cache_read": est.cache_lectura, "lab.run.tokens.cache_creation": est.cache_creacion,
            "lab.run.cost_usd": round(r.costo_usd, 8)})
        if r.estado in ("limite_alcanzado", "error"):
            inv.fail(Error(message=r.estado, type=r.estado))
        else:
            inv.stop()
        return r
