"""Week 17, activity 5: the guardrails in the loop, without editing it.

`AgenteGuardado` is the activity 4 agent (instrumented, budgeted) with three layers added around what already exists:

* INPUT, before the first model call: the request is checked (`revisar_peticion`). A blocked request ends the task as `abstenida` with the
  reason `guardrail_entrada` and a fixed refusal; no model call is made, so it costs nothing. The tool DESCRIPTIONS are checked too (when
  the tools are wrapped): a tool whose description carries instructions is dropped from the catalogue the model sees.
* TOOL, around each call: the four tool guardrails run before the call, the result is cleaned after it. A blocked call is not executed;
  the model gets a tool error in week 13's shape and can still answer. A result with instruction-like sentences reaches the model with
  those sentences replaced by a marker.
* OUTPUT, after the loop: personal values are redacted; an answer with a figure no tool result supports, or with no tool result behind
  it, is replaced by a refusal (`abstenida`, `guardrail_salida`).

Every decision is a `gen_ai.guardrail.decision` event on the agent span (`esquema.py`): guardrail, stage, action, a reason from a fixed
list, and the model step. The wrapper sits OUTSIDE the instrumented tools, so a blocked call leaves an event on the agent span and no
`execute_tool` span: nothing was executed.

State lives in a ContextVar set by `resolver`, like the activity 3 and 4 layers: concurrent tasks on one instance do not mix.
"""
from __future__ import annotations

import contextvars
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from opentelemetry import trace

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from guardrails import nucleo as N  # noqa: E402
from guardrails import reglas as R  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.trazas_agente import _ESTADO  # noqa: E402
from presupuestos.agente_presupuestado import AgentePresupuestado, AgenteConPresupuesto  # noqa: E402

from agente.loop import Resultado  # noqa: E402  (semana-13 is on sys.path through trazas_agente)

_GUARDIA: contextvars.ContextVar = contextvars.ContextVar("legacybridge_guardia", default=None)


@dataclass
class EstadoGuardia:
    """State of one `resolver` call."""
    alcance: N.Alcance
    peticion: str
    conocidas: R.Conocidas
    herramientas_ok: int = 0                  # tool calls that returned `ok` (the evidence behind an answer)
    fundamentacion: str = "auditar"           # `nucleo.MODOS_FUNDAMENTACION`
    decisiones: list = field(default_factory=list)

    def registrar(self, span, d: N.Decision, paso: int | None = None) -> None:
        if paso is None:
            est = _ESTADO.get()
            paso = est.paso if est else 0
        self.decisiones.append(d)
        E.fijar_evento(span, E.EVENTO_GUARDRAIL, {
            "lab.guardrail.name": d.guardrail, "lab.guardrail.stage": d.etapa, "lab.guardrail.decision": d.accion,
            "lab.guardrail.reason": d.motivo, "lab.guardrail.step": paso})


class HerramientasGuardadas:
    """The tools source behind the tool guardrails. `definiciones()` is the catalogue WITHOUT the tools that must not reach the model: those
    of a server that is not on the allowlist, and those whose description carries instructions. `llamar()` decides, executes if allowed,
    and cleans the result. Without a run in progress it is transparent.

    `servidores_permitidos` is the allowlist of servers, decided by the system. The origin of each tool is read from the client when it
    knows it (`ClienteSeguro._mapa`, which also resolves name collisions the way the naive client does); a source of native tools has no
    origin and is not filtered."""

    def __init__(self, base, servidores_permitidos=None):
        self._base = base
        defs = base.definiciones()
        mapa = getattr(base, "_mapa", None) or {}
        self.decisiones_de_definiciones: list[N.Decision] = []
        fuera = set()
        if servidores_permitidos is not None:
            for d in defs:
                origen = mapa.get(d["name"], (None, None))[0]
                if origen is not None and origen not in servidores_permitidos:
                    fuera.add(d["name"])
                    self.decisiones_de_definiciones.append(N.Decision("tool_allowlist", "tool", "block", "herramienta_retirada"))
        self._defs, retiradas, decisiones = N.revisar_definiciones([d for d in defs if d["name"] not in fuera])
        self.retiradas = retiradas | fuera
        self.decisiones_de_definiciones += decisiones
        self.permitidas = {d["name"] for d in self._defs}
        self._validadores = N._validadores(self._defs)

    def __getattr__(self, nombre):
        return getattr(self._base, nombre)

    def definiciones(self) -> list[dict]:
        return self._defs

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        est: EstadoGuardia | None = _GUARDIA.get()
        if est is None:
            return self._base.llamar(nombre, argumentos)
        span = trace.get_current_span()
        decisiones = N.revisar_llamada(nombre, argumentos, permitidas=self.permitidas, retiradas=self.retiradas,
                                       validadores=self._validadores, peticion=est.peticion, alcance=est.alcance)
        for d in decisiones:
            est.registrar(span, d)
        cierre = decisiones[-1]
        if not cierre.permite:
            return N.error_de_herramienta(cierre, est.alcance.idioma)
        res = self._base.llamar(nombre, argumentos)
        limpio, d = N.revisar_resultado(res, est.alcance.idioma)
        est.registrar(span, d)
        if limpio.get("ok"):
            est.conocidas.agregar_resultado({k: v for k, v in limpio.items() if k != "sql_normalizado"})
            est.herramientas_ok += 1
        return limpio


class AgenteConGuardrails(AgenteConPresupuesto):
    """The loop with the input check before it and the output check after it."""

    def resolver(self, tarea: dict):
        est: EstadoGuardia | None = _GUARDIA.get()
        if est is None:
            return super().resolver(tarea)
        span = trace.get_current_span()
        for d in getattr(self.h, "decisiones_de_definiciones", []):
            est.registrar(span, d, 0)
        decisiones = N.revisar_peticion(est.peticion)
        for d in decisiones:
            est.registrar(span, d, 0)
        bloqueo = next((d for d in decisiones if not d.permite), None)
        if bloqueo is not None:
            return self._rechazo_de_entrada(tarea, bloqueo, est.alcance.idioma)
        r = super().resolver(tarea)
        if r.final is None or r.estado == "limite_alcanzado":
            return r                    # a budget or a loop limit ended it: the fixed text of that stop is not an answer to check
        final, decisiones = N.revisar_respuesta(r.final, conocidas=est.conocidas, herramientas_ok=est.herramientas_ok,
                                                idioma=est.alcance.idioma, fundamentacion=est.fundamentacion)
        for d in decisiones:
            est.registrar(span, d, r.pasos)
        rechazo = next((d for d in decisiones if d.accion == "refuse"), None)
        r.final = final
        if rechazo is not None:
            r.estado, r.motivo = "abstenida", "guardrail_salida"
            self._traza({"corrida": r.corrida, "tarea": tarea.get("id", ""), "tipo": "parada", "estado": r.estado, "motivo": r.motivo,
                         "corrige": "the answer was refused by an output guardrail; the model's own answer was not delivered",
                         "guardrail": rechazo.guardrail, "razon": rechazo.motivo})
        return r

    def _rechazo_de_entrada(self, tarea: dict, d: N.Decision, idioma: str):
        corrida = uuid.uuid4().hex[:12]
        final = {"estado": "abstenida", "respuesta": N.texto_de_rechazo_de_entrada(d.motivo, idioma), "resultados": [], "evidencia": [],
                 "supuestos": [], "pregunta_aclaracion": None}
        r = Resultado("abstenida", final, 0, 0, 0, 0, 0.0, 0.0, motivo="guardrail_entrada", corrida=corrida)
        self._traza({"corrida": corrida, "tarea": tarea.get("id", ""), "tipo": "parada", "estado": r.estado, "motivo": r.motivo,
                     "guardrail": d.guardrail, "razon": d.motivo, "pasos": 0, "herramientas": 0, "tokens_in": 0, "tokens_out": 0,
                     "costo_usd": 0.0})
        return r


def _idioma(tarea: dict) -> str:
    lang = tarea.get("lang") or str(tarea.get("id", "")).rsplit("-", 1)[-1]
    return lang if lang in ("es", "en") else "es"


class AgenteGuardado(AgentePresupuestado):
    """`AgentePresupuestado` with the guardrails. `resolver(tarea, sujeto, sesion=None)`: `sujeto` is the token subject; the scopes the
    guardrails enforce come from it (`nucleo.SCOPES_DE`), never from the request."""

    def __init__(self, herramientas, *, api, tenant: str, servidores_permitidos=None, fundamentacion: str = "auditar", **kw):
        if fundamentacion not in N.MODOS_FUNDAMENTACION:
            raise ValueError(f"fundamentacion must be one of {N.MODOS_FUNDAMENTACION}")
        self.fundamentacion = fundamentacion
        super().__init__(herramientas, api=api, tenant=tenant, agente_clase=AgenteConGuardrails,
                         envolver=lambda h: HerramientasGuardadas(h, servidores_permitidos), **kw)
        self.ultima_guardia: EstadoGuardia | None = None

    def resolver(self, tarea: dict, sujeto: str, sesion: str | None = None):
        texto = tarea.get("tarea", "")
        alcance = N.Alcance(sujeto, self.tenant, N.SCOPES_DE.get(sujeto, frozenset({N.SCOPE_BASE})), _idioma(tarea))
        est = EstadoGuardia(alcance, texto, R.Conocidas(texto), fundamentacion=self.fundamentacion)
        token = _GUARDIA.set(est)
        try:
            r = super().resolver(tarea, sujeto, sesion)
        finally:
            _GUARDIA.reset(token)
        self.ultima_guardia = est
        return r


def resumen_de_decisiones(est: EstadoGuardia) -> dict:
    """Counts by guardrail and action, for the evaluation reports: numbers and words of the fixed lists only."""
    out: dict[str, dict[str, int]] = {}
    for d in est.decisiones:
        out.setdefault(d.guardrail, {}).setdefault(d.accion, 0)
        out[d.guardrail][d.accion] += 1
    return json.loads(json.dumps(out))
