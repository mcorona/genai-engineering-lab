"""Week 17, activity 4: the week 13 loop under a token and cost budget, without editing it.

`AgentePresupuestado` is the activity 3 instrumented agent with one more layer around the model call. Before every call it:

1. estimates the upper cost of the prompt (`estimacion.py`) and reads what is left in each scope: the task (memory) and, if given,
   the session and the tenant's day (the store, with reservations, so tasks running at once cannot both spend the last cent);
2. asks `politica.decidir`: allow with a `max_tokens` the budget can pay for, degrade to the cheaper model the policy names, or stop;
3. records the decision as a `gen_ai.budget.decision` event on the agent span, with the spend, the limit and the estimate;
4. sends the call with that `max_tokens` (and that model), or raises `PresupuestoAgotado` and does not call.

When it stops, the task ends `limite_alcanzado` with the reason `presupuesto_tarea`, `presupuesto_sesion` or `presupuesto_tenant_dia`
and a PARTIAL ANSWER written by the agent, not by the model: it names the scope, the limit, the spend and the work done. It
never retries: the model is not asked again with a smaller prompt, later, or on a model the policy does not name. A call that
fails (an API error) releases its reservation and costs nothing; a response cut by the budget's `max_tokens` is a stop.

The model's answer and the tool results are never written anywhere by this layer.
"""
from __future__ import annotations

import contextvars
import itertools
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry import trace

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.trazas_agente import AgenteInstrumentado, api_instrumentada  # noqa: E402
from presupuestos import estimacion as EST  # noqa: E402
from presupuestos.almacen import AlmacenGasto, Cuenta  # noqa: E402
from presupuestos.politica import Decision, Gasto, Politica, decidir  # noqa: E402

from agente.loop import Agente, costo as costo_del_bucle  # noqa: E402  (semana-13 is on sys.path through trazas_agente)

NOMBRE_EN = {"task": "task", "session": "session", "tenant_day": "daily tenant"}
NOMBRE_ES = {"task": "de la tarea", "session": "de la sesión", "tenant_day": "diario del tenant"}
MOTIVO_DE = {"task": "presupuesto_tarea", "session": "presupuesto_sesion", "tenant_day": "presupuesto_tenant_dia"}
_PRES: contextvars.ContextVar = contextvars.ContextVar("legacybridge_presupuesto", default=None)
_GRUPOS = itertools.count(1)


class PresupuestoAgotado(Exception):
    """Raised instead of making a model call the budget cannot pay for. The loop turns any exception of the model call into a
    stop; `AgenteConPresupuesto` then names it for what it is."""

    def __init__(self, decision: Decision):
        super().__init__(f"{decision.alcance} budget: {decision.motivo}")
        self.decision = decision


@dataclass
class EstadoPresupuesto:
    """State of one `resolver` call (a ContextVar, so concurrent tasks on one instance do not mix)."""
    politica: Politica
    almacen: AlmacenGasto | None
    cuentas: dict
    gasto: Gasto = Gasto()
    paso: int = 0
    entrada_previa: int = 0
    salida_previa: int = 0
    modelo: str | None = None                    # sticky: after a degrade the cheaper model is the model of the task
    parada: Decision | None = None
    recortada: Decision | None = None            # the response was cut by the budget's `max_tokens`
    decisiones: list = field(default_factory=list)
    subestimaciones: list = field(default_factory=list)      # calls where the estimate was below what the API reported
    sobregasto: list = field(default_factory=list)           # calls that cost more than their own upper estimate
    llamadas: int = 0
    modelos: list = field(default_factory=list)              # the model each call was really made with
    costos_del_bucle: list = field(default_factory=list)     # each call's cost by the loop's own definition, at ITS model's price


def _evento(span, d: Decision, paso: int, pol: Politica) -> None:
    limite = pol.limites()[d.alcance]
    E.fijar_evento(span, E.EVENTO_PRESUPUESTO, {
        "lab.budget.decision": d.accion, "lab.budget.scope": d.alcance, "lab.budget.reason": d.motivo, "lab.budget.step": paso,
        "lab.budget.spent_usd": round(limite.usd - d.restante_usd, 8), "lab.budget.limit_usd": limite.usd,
        "lab.budget.estimate_usd": round(d.estimado_usd, 8),
        "lab.budget.spent_tokens": max(0, limite.tokens - d.restante_tokens), "lab.budget.limit_tokens": limite.tokens,
        "lab.budget.estimate_tokens": d.estimado_tokens, "lab.budget.max_tokens": d.max_tokens,
        "gen_ai.request.model": d.modelo if E.ID(d.modelo) else None,
        "lab.budget.model.from": d.modelo_origen if d.modelo_origen and E.ID(d.modelo_origen) else None})


def api_presupuestada(api):
    """The model call behind the budget. `api` is the (instrumented) model call of the loop."""

    def llamar(cuerpo: dict) -> dict:
        est: EstadoPresupuesto | None = _PRES.get()
        if est is None:
            return api(cuerpo)
        est.paso += 1
        pol = est.politica
        modelo = est.modelo or cuerpo.get("model", "")
        est_in = EST.entrada_inicial(cuerpo) if est.paso == 1 else \
            EST.entrada_siguiente(est.entrada_previa, est.salida_previa, cuerpo["messages"][-1])
        span = trace.get_current_span()
        grupo = f"{id(est)}-{next(_GRUPOS)}"
        reservado, escaso = False, None
        for _ in range(3):      # a reservation can lose a race with another task: decide again with fresh numbers, then stop
            restante = {"task": Gasto(pol.tarea.usd - est.gasto.usd, pol.tarea.tokens - est.gasto.tokens)}
            if est.almacen and est.cuentas:
                restante.update(est.almacen.restante(est.cuentas, pol.limites()))
            d = decidir(pol, modelo, est_in, restante, est.gasto)
            if d.accion == "stop":
                break
            if not (est.almacen and est.cuentas):
                break
            reservado, alcance, dimension = est.almacen.reservar(est.cuentas, pol.limites(), d.estimado_usd, d.estimado_tokens, grupo)
            if reservado:
                break
            escaso = (alcance, dimension)
        else:                   # three lost races in a row: the shared scope has no room for this call
            d = replace(d, accion="stop", alcance=escaso[0], motivo=escaso[1], max_tokens=0, modelo_origen=None)
        est.decisiones.append(d)
        _evento(span, d, est.paso, pol)
        if d.accion == "stop":
            est.parada = d
            raise PresupuestoAgotado(d)
        est.modelo = d.modelo
        est.llamadas += 1
        try:
            r = api({**cuerpo, "model": d.modelo, "max_tokens": d.max_tokens})
        except BaseException:
            if reservado:
                est.almacen.liberar(grupo)      # nothing was billed: the reservation goes away, and nothing is retried here
            raise
        uso = r.get("usage") or {}
        usd, tok = EST.costo_real(d.modelo, uso)
        entrada = tok - (uso.get("output_tokens") or 0)
        if entrada > est_in:
            est.subestimaciones.append({"paso": est.paso, "estimado": est_in, "real": entrada})
        if usd > d.estimado_usd + 1e-12:
            est.sobregasto.append({"paso": est.paso, "estimado_usd": d.estimado_usd, "real_usd": usd})
        est.gasto = Gasto(est.gasto.usd + usd, est.gasto.tokens + tok)
        est.modelos.append(d.modelo)
        est.costos_del_bucle.append(costo_del_bucle(d.modelo, uso.get("input_tokens", 0), uso.get("output_tokens", 0)))
        est.entrada_previa, est.salida_previa = entrada, uso.get("output_tokens") or 0
        if reservado:
            est.almacen.liquidar(est.cuentas, grupo, usd, tok)
        if r.get("stop_reason") == "max_tokens" and d.max_tokens < pol.max_salida:
            est.recortada = d       # the budget, not the loop's own limit, decided how long the answer could be
        return r

    return llamar


def respuesta_parcial(est: EstadoPresupuesto, r, tarea: dict, d: Decision) -> dict:
    """What the agent says when a budget ends the task. Fixed text with numbers: no model output, no tool result."""
    limite = est.politica.limites()[d.alcance]
    gastado = limite.usd - d.restante_usd
    if tarea.get("lang") == "es" or str(tarea.get("id", "")).endswith("-es"):
        texto = (f"No pude terminar: el presupuesto {NOMBRE_ES[d.alcance]} ({limite.usd:g} USD, {limite.tokens} tokens) no alcanza para la "
                 f"siguiente llamada al modelo (gastado {gastado:.6f} USD; la siguiente costaría hasta {d.estimado_usd:.6f}). "
                 f"Llevaba {r.pasos} llamadas al modelo y {r.herramientas} a herramientas, sin respuesta final.")
    else:
        texto = (f"Stopped without a final answer: the {NOMBRE_EN[d.alcance]} budget ({limite.usd:g} USD, {limite.tokens} tokens) cannot pay "
                 f"for the next model call (spent {gastado:.6f} USD; the next call would cost up to {d.estimado_usd:.6f}). "
                 f"Work done so far: {r.pasos} model calls and {r.herramientas} tool calls, no final answer.")
    return {"estado": "limite_alcanzado", "motivo": MOTIVO_DE[d.alcance], "respuesta": texto, "resultados": [], "evidencia": [],
            "supuestos": [], "presupuesto": {"alcance": d.alcance, "limite_usd": limite.usd, "limite_tokens": limite.tokens,
                                              "gastado_usd": round(gastado, 8), "estimado_usd": round(d.estimado_usd, 8)}}


class AgenteConPresupuesto(Agente):
    """The loop, plus the translation of a budget stop into the loop's own vocabulary."""

    def resolver(self, tarea: dict):
        r = super().resolver(tarea)
        est: EstadoPresupuesto | None = _PRES.get()
        if est is None:
            return r
        if est.costos_del_bucle:
            # the loop prices every call at ITS OWN model (`self.modelo`); after a degrade the calls were made with another one
            r.costo_usd = sum(est.costos_del_bucle)
            if any(m != self.modelo for m in est.modelos):
                self._traza({"corrida": r.corrida, "tarea": tarea.get("id", ""), "tipo": "costo", "modelos": est.modelos,
                             "corrige": "the loop priced the calls at the model it was built with; these are the models that answered",
                             "costo_usd": round(r.costo_usd, 6)})
        d = est.parada or (est.recortada if r.estado == "limite_alcanzado" and r.motivo == "max_tokens_salida" else None)
        if d is not None:
            r.estado, r.motivo, r.final = "limite_alcanzado", MOTIVO_DE[d.alcance], respuesta_parcial(est, r, tarea, d)
            self._traza({"corrida": r.corrida, "tarea": tarea.get("id", ""), "tipo": "parada", "estado": r.estado, "motivo": r.motivo,
                         "corrige": "the loop wrote `error` or `max_tokens_salida`; this is the budget's stop",
                         "pasos": r.pasos, "herramientas": r.herramientas, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                         "costo_usd": round(r.costo_usd, 6)})
        return r


class AgentePresupuestado(AgenteInstrumentado):
    """`AgenteInstrumentado` under a budget. `resolver(tarea, sujeto, sesion=None)`: `sesion` names the conversation whose budget
    the task draws on (none: only the task and the tenant's day apply)."""

    def __init__(self, herramientas, *, api, tenant: str, politica: Politica | None = None, almacen: AlmacenGasto | None = None,
                 modelo: str = "claude-haiku-5-5", esfuerzo: str = "low", simulado: bool = False, reloj=time.time, **kw):
        self.politica = politica or Politica.desde_archivo()
        self.almacen, self.reloj = almacen, reloj
        limites = kw.pop("limites", None)
        from agente.loop import Limites
        limites = replace(limites or Limites(), max_tokens_total=min((limites or Limites()).max_tokens_total, self.politica.tarea.tokens))
        super().__init__(herramientas, api=api, tenant=tenant, modelo=modelo, esfuerzo=esfuerzo, limites=limites,
                         simulado=simulado, **kw)
        self.agente = AgenteConPresupuesto(self.herramientas, modelo, esfuerzo, self.limites,
                                           api=api_presupuestada(api_instrumentada(api, simulado=simulado)), trazas=kw.get("trazas"))
        self.ultimo: EstadoPresupuesto | None = None

    def _cuentas(self, sujeto: str, sesion: str | None) -> dict[str, Cuenta]:
        cuentas: dict[str, Cuenta] = {}
        if sesion and self.politica.sesion:
            cuentas["session"] = ("session", sesion, "")
        if self.politica.tenant_dia:
            cuentas["tenant_day"] = ("tenant_day", self.tenant, datetime.fromtimestamp(self.reloj(), timezone.utc).strftime("%Y-%m-%d"))
        return cuentas

    def resolver(self, tarea: dict, sujeto: str, sesion: str | None = None):
        cuentas = self._cuentas(sujeto, sesion)
        est = EstadoPresupuesto(self.politica, self.almacen if cuentas else None, cuentas, modelo=None)
        token = _PRES.set(est)
        try:
            r = super().resolver(tarea, sujeto)
        finally:
            _PRES.reset(token)
        self.ultimo = est
        return r
