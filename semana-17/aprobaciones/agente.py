"""Week 17, activity 6: a purchase-order proposal pauses the run until a person with the right level decides.

`AgenteAprobable` is activity 5's `AgenteGuardado` (instrumented, budgeted, guarded) with one more layer, without editing the week 13
loop:

1. **Request.** When the model calls `proponer_orden_compra` and every guardrail allowed it, the tool runs as before (week 13/14
   validations, `PENDING_APPROVAL` in its own memory) and then an approval request is written to the store (`almacen.py`): what, why,
   how much (computed here), which evidence, who asked, the level R-OC-APRUEBA needs and a deadline. The loop gets a placeholder result
   so its turn finishes normally. A `gen_ai.hitl.request` event goes on the agent span.
2. **Pause.** Before the NEXT model call (outside the budget, so nothing is reserved or billed) the transcript is snapshotted and the
   call raises `EsperaAprobacion`. The loop turns that into a stop, this layer names it `en_espera` / `espera_aprobacion` and writes
   the checkpoint (transcript, counters, spend, trace context). Nothing the model said is shown to anyone as an answer.
3. **Decision.** `servicio.Aprobaciones.decidir(id, token, decision)`: a verified token, not the requester, with the level. The order
   is created in the same transaction as the approval, or not at all.
4. **Resume.** `reanudar(id)` takes the checkpoint once (and deletes it), puts the decision where the placeholder was (approved with the
   order number, rejected, or expired), and runs the same loop on that transcript: the first model call of the resumed run is sent
   with the whole transcript. The task's spend so far is carried into the budget and the evidence into the output guardrails; the
   resumed agent span is a child of the paused one (same trace) and carries a `gen_ai.hitl.resume` event with the waiting time.

The model has no tool that approves, and nothing it reads or writes reaches `decidir`: approval needs a token it never holds.
"""
from __future__ import annotations

import contextvars
import copy
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from opentelemetry import context as otel_context
from opentelemetry import propagate, trace

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from aprobaciones.almacen import Almacen  # noqa: E402
from guardrails.agente import AgenteConGuardrails, AgenteGuardado  # noqa: E402
from guardrails.nucleo import nombre_base  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from presupuestos.politica import Gasto  # noqa: E402

_HITL: contextvars.ContextVar = contextvars.ContextVar("legacybridge_hitl", default=None)
TTL_S = 24 * 3600                      # a request nobody decides in a day expires
PROPUESTA = "proponer_orden_compra"
EVIDENCIA = ("ejecutar_sql", "buscar_regla_negocio", "validar_sql", "muestrear_valores")
MARCA = "esperando_aprobacion"


class EsperaAprobacion(Exception):
    """Raised instead of the model call that would follow a proposal. The loop turns it into a stop."""


@dataclass
class EstadoAprobacion:
    almacen: Almacen
    sujeto: str
    tenant: str
    tarea: dict
    sesion: str | None
    ttl_s: float
    solicitud: dict | None = None             # the request created in this segment
    transcripcion: list | None = None         # the messages at the pause
    continuacion: list | None = None          # a resumed segment: the transcript to send on its first call
    reanudado: bool = False
    evidencia: list = field(default_factory=list)
    rechazadas: list = field(default_factory=list)   # SKUs already rejected or expired in this task: not proposed again
    ms_checkpoint: float | None = None


def _idioma(tarea: dict) -> str:
    lang = tarea.get("lang") or str(tarea.get("id", "")).rsplit("-", 1)[-1]
    return "en" if lang == "en" else "es"


def _error(tipo: str, es: str, en: str, idioma: str) -> dict:
    return {"ok": False, "error": {"tipo": tipo, "mensaje": en if idioma == "en" else es}}


class HerramientasConAprobacion:
    """Inside the guardrails: a proposal that reaches here was allowed by all of them."""

    def __init__(self, base):
        self._base = base

    def __getattr__(self, nombre):
        return getattr(self._base, nombre)

    def definiciones(self) -> list[dict]:
        return self._base.definiciones()

    def llamar(self, nombre: str, argumentos: dict) -> dict:
        est: EstadoAprobacion | None = _HITL.get()
        base = nombre_base(nombre)
        if est is None or base != PROPUESTA:
            res = self._base.llamar(nombre, argumentos)
            if est is not None and base in EVIDENCIA and res.get("ok"):
                est.evidencia.append({"herramienta": base, "entrada": argumentos,
                                      "filas": res.get("total_filas"), "regla": res.get("id") or res.get("regla")})
            return res
        idioma = _idioma(est.tarea)
        if est.solicitud is not None:
            return _error("una_aprobacion_a_la_vez", "Ya hay una propuesta esperando aprobación en esta tarea; espera su decisión.",
                          "A proposal of this task is already waiting for approval; wait for its decision.", idioma)
        sku = str((argumentos or {}).get("sku", ""))
        if sku in est.rechazadas:
            return _error("propuesta_rechazada", f"La propuesta de {sku} ya fue rechazada o venció en esta tarea; no se vuelve a proponer.",
                          f"The proposal for {sku} was already rejected or expired in this task; it is not proposed again.", idioma)
        res = self._base.llamar(nombre, argumentos)
        if not res.get("ok"):
            return res
        p = res.get("propuesta") or {}
        carrier: dict = {}
        propagate.inject(carrier)
        s = est.almacen.crear_solicitud(
            corrida=(carrier.get("traceparent") or "--sin-traza").split("-")[1][:12] or "sin-traza", tenant=est.tenant, tarea=str(est.tarea.get("id", "")),
            solicitante=est.sujeto, sku=str(p.get("sku", sku)), cantidad=int(p.get("cantidad", argumentos.get("cantidad", 0))),
            motivo=str(p.get("motivo", argumentos.get("motivo", ""))), evidencia=est.evidencia, ttl_s=est.ttl_s,
            traza=carrier.get("traceparent"))
        est.solicitud = s
        from instrumentacion.trazas_agente import _ESTADO
        corrida = _ESTADO.get()
        E.fijar_evento(trace.get_current_span(), E.EVENTO_HITL_SOLICITUD, {
            "lab.hitl.request_id": s["id"], "lab.hitl.requester": E.seudonimo(est.sujeto), "lab.hitl.level": s["nivel"],
            "lab.hitl.amount_mxn": float(s["monto_mxn"]), "lab.hitl.quantity": s["cantidad"], "lab.hitl.evidence": len(est.evidencia),
            "lab.hitl.ttl_s": float(est.ttl_s), "lab.hitl.step": corrida.paso if corrida else 0})
        return {"ok": True, "estado": MARCA, "solicitud": s["id"]}


def api_con_pausa(api):
    """Outside the budget: the resumed transcript goes in here, and the pause comes out here."""

    def llamar(cuerpo: dict) -> dict:
        est: EstadoAprobacion | None = _HITL.get()
        if est is None:
            return api(cuerpo)
        if est.continuacion is not None and not est.reanudado:
            cuerpo["messages"][:] = est.continuacion      # the loop's own list: what it appends next follows the transcript
            est.reanudado = True
        if est.solicitud is not None and est.transcripcion is None:
            est.transcripcion = copy.deepcopy(cuerpo["messages"])
            raise EsperaAprobacion(est.solicitud["id"])
        return api(cuerpo)

    return llamar


def texto_en_espera(s: dict, idioma: str) -> str:
    if idioma == "en":
        return (f"The purchase order proposal ({s['cantidad']} units of {s['sku']}, {float(s['monto_mxn']):,.2f} MXN) is waiting for "
                f"approval by the {s['nivel']} level. Nothing was ordered; the task continues once a person decides.")
    return (f"La propuesta de orden de compra ({s['cantidad']} unidades de {s['sku']}, {float(s['monto_mxn']):,.2f} MXN) espera la "
            f"aprobación del nivel {s['nivel']}. No se ordenó nada; la tarea continúa cuando una persona decida.")


class AgenteConAprobacion(AgenteConGuardrails):
    """The loop class: names the pause and writes the checkpoint, and marks the resume on the agent span."""

    def resolver(self, tarea: dict):
        est: EstadoAprobacion | None = _HITL.get()
        if est is not None and est.continuacion is not None:
            E.fijar_evento(trace.get_current_span(), E.EVENTO_HITL_REANUDACION, est.tarea.get("_reanudacion", {}))
        r = super().resolver(tarea)
        if est is None or est.solicitud is None:
            return r
        s = est.solicitud
        if est.transcripcion is None:
            # the loop ended (a limit) between the proposal and the next model call: there is no run to resume, so the request
            # must not wait for one. It expires now and leaves nothing.
            est.almacen.anular(s["id"])
            return r
        t0 = time.perf_counter()
        est.almacen.guardar_checkpoint(s["id"], {
            "mensajes": est.transcripcion, "tarea": {k: v for k, v in est.tarea.items() if not k.startswith("_")},
            "sujeto": est.sujeto, "sesion": est.sesion, "rechazadas": est.rechazadas, "traza": s.get("traza"),
            "contadores": {"pasos": r.pasos, "herramientas": r.herramientas, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                           "costo_usd": r.costo_usd, "segundos": r.segundos, "errores_herramienta": r.errores_herramienta}})
        est.ms_checkpoint = round(1000 * (time.perf_counter() - t0), 2)
        r.estado, r.motivo = "en_espera", "espera_aprobacion"
        r.final = {"estado": "en_espera", "respuesta": texto_en_espera(s, _idioma(est.tarea)), "solicitud": s["id"],
                   "resultados": [], "evidencia": [], "supuestos": []}
        self._traza({"corrida": r.corrida, "tarea": tarea.get("id", ""), "tipo": "parada", "estado": r.estado, "motivo": r.motivo,
                     "corrige": "the loop wrote `error`: the run paused for a human approval", "solicitud": s["id"]})
        return r


def resultado_de_decision(s: dict, orden: dict | None, idioma: str) -> dict:
    """What the model reads where the placeholder was. Fixed text and the request's own numbers; never who decided."""
    if s["estado"] == "aprobada":
        return {"ok": True, "estado": "aprobada", "orden": orden["id"] if orden else None, "sku": s["sku"], "cantidad": s["cantidad"],
                "monto_mxn": float(s["monto_mxn"]), "nivel": s["nivel"],
                "nota": ("A person with the required level approved the proposal; the order is confirmed." if idioma == "en" else
                         "Una persona con el nivel requerido aprobó la propuesta; la orden quedó confirmada.")}
    if s["estado"] == "rechazada":
        return _error("propuesta_rechazada", "La persona que aprueba rechazó la propuesta. No se ordenó nada; no la vuelvas a proponer.",
                      "The approver rejected the proposal. Nothing was ordered; do not propose it again.", idioma)
    return _error("aprobacion_vencida", "Nadie decidió antes del plazo; la propuesta venció y no se ordenó nada.",
                  "Nobody decided before the deadline; the proposal expired and nothing was ordered.", idioma)


def _reemplazar_marca(mensajes: list, solicitud_id: str, nuevo: dict) -> int:
    n = 0
    for m in mensajes:
        if m.get("role") != "user" or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if b.get("type") != "tool_result":
                continue
            try:
                c = json.loads(b.get("content") or "")
            except (TypeError, ValueError):
                continue
            if isinstance(c, dict) and c.get("estado") == MARCA and c.get("solicitud") == solicitud_id:
                b["content"] = json.dumps(nuevo, ensure_ascii=False)
                b["is_error"] = not nuevo.get("ok", False)
                n += 1
    return n


def _resultados_previos(mensajes: list) -> list[dict]:
    out = []
    for m in mensajes:
        if m.get("role") != "user" or not isinstance(m.get("content"), list):
            continue
        for b in m["content"]:
            if b.get("type") == "tool_result" and not b.get("is_error"):
                try:
                    c = json.loads(b.get("content") or "")
                except (TypeError, ValueError):
                    continue
                if isinstance(c, dict) and c.get("ok") and c.get("estado") != MARCA:
                    out.append(c)
    return out


class AgenteAprobable(AgenteGuardado):
    """`resolver(tarea, sujeto, sesion=None)` may end `en_espera`; `reanudar(solicitud_id)` continues it once it is decided."""

    def __init__(self, herramientas, *, api, tenant: str, almacen: Almacen | None = None, ttl_s: float = TTL_S, **kw):
        self.aprobaciones = almacen or Almacen()
        self.ttl_s = ttl_s
        super().__init__(herramientas, api=api, tenant=tenant, agente_clase=AgenteConAprobacion, capa_interna=HerramientasConAprobacion,
                         api_externa=api_con_pausa, **kw)
        self.ultima_aprobacion: EstadoAprobacion | None = None

    def resolver(self, tarea: dict, sujeto: str, sesion: str | None = None, *, _estado: EstadoAprobacion | None = None, **kw):
        est = _estado or EstadoAprobacion(self.aprobaciones, sujeto, self.tenant, dict(tarea), sesion, self.ttl_s)
        token = _HITL.set(est)
        try:
            r = super().resolver(tarea, sujeto, sesion, **kw)
        finally:
            _HITL.reset(token)
        self.ultima_aprobacion = est
        return r

    def reanudar(self, solicitud_id: str):
        """Continues a paused task once its request is decided (raises `YaReanudada` if it is pending or already resumed)."""
        s, cp = self.aprobaciones.tomar_checkpoint(solicitud_id)
        tarea, idioma = cp["tarea"], _idioma(cp["tarea"])
        mensajes = cp["mensajes"]
        if _reemplazar_marca(mensajes, solicitud_id, resultado_de_decision(s, self.aprobaciones.orden_de(solicitud_id), idioma)) != 1:
            raise ValueError("the checkpoint does not hold this request's placeholder")
        previos = cp["contadores"]
        espera_ms = int((s["decidida_en"] - s["creada_en"]).total_seconds() * 1000)
        est = EstadoAprobacion(self.aprobaciones, cp["sujeto"], self.tenant,
                               {**tarea, "_reanudacion": {"lab.hitl.request_id": s["id"], "lab.hitl.state": s["estado"],
                                                          "lab.hitl.wait_ms": espera_ms}},
                               cp.get("sesion"), self.ttl_s, continuacion=mensajes,
                               rechazadas=list(cp.get("rechazadas") or []) + ([] if s["estado"] == "aprobada" else [s["sku"]]))
        ctx = propagate.extract({"traceparent": cp["traza"]}) if cp.get("traza") else otel_context.get_current()
        tok = otel_context.attach(ctx)
        try:
            r = self.resolver(tarea, cp["sujeto"], cp.get("sesion"), _estado=est,
                              gasto_previo=Gasto(previos["costo_usd"], previos["tokens_in"] + previos["tokens_out"]),
                              resultados_previos=_resultados_previos(mensajes))
        finally:
            otel_context.detach(tok)
        # the task's totals are both segments: what the paused run did plus what the resumed one did
        r.pasos += previos["pasos"]
        r.herramientas += previos["herramientas"]
        r.tokens_in += previos["tokens_in"]
        r.tokens_out += previos["tokens_out"]
        r.costo_usd += previos["costo_usd"]
        r.errores_herramienta += previos.get("errores_herramienta", 0)
        r.segmentos = 2
        r.espera_ms = espera_ms
        return r
