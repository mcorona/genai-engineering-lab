"""Week 17, activity 6: the approvals service, the only way a request is decided.

`Aprobaciones.decidir(id, token, decision)` verifies the token (`identidad.py`), applies the decision in the store in one transaction
(`almacen.decidir`) and records the attempt as a `hitl decide` span in the paused run's trace, with a `gen_ai.hitl.decision` event:
who (keyed hash), the level, what happened and why, and the waiting time. `expirar()` is the sweep that expires the requests past
their deadline, each with its own `expire` event. A refused attempt is recorded the same way as an applied one.
"""
from __future__ import annotations

import sys
from pathlib import Path

from opentelemetry import propagate, trace

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from aprobaciones import maquina as M  # noqa: E402
from aprobaciones.almacen import Almacen  # noqa: E402
from aprobaciones.identidad import ErrorToken, VerificadorAprobador  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402

_TRAZADOR = trace.get_tracer("legacybridge.aprobaciones")


def _espera_ms(s: dict | None) -> int | None:
    if not s or s.get("decidida_en") is None:
        return None
    return int((s["decidida_en"] - s["creada_en"]).total_seconds() * 1000)


class Aprobaciones:
    def __init__(self, almacen: Almacen, verificador: VerificadorAprobador):
        self.almacen, self.verificador = almacen, verificador

    def _span(self, s: dict | None):
        ctx = propagate.extract({"traceparent": s["traza"]}) if s and s.get("traza") else None
        return _TRAZADOR.start_as_current_span("hitl decide", context=ctx)

    def decidir(self, solicitud_id: str, token: str, decision: str) -> tuple[M.Veredicto, dict | None]:
        try:
            identidad = self.verificador.verificar(token)
        except ErrorToken:
            identidad = None
        antes = self.almacen.obtener(solicitud_id)
        with self._span(antes) as span:
            v, s = self.almacen.decidir(solicitud_id, identidad, decision)
            E.fijar_evento(span, E.EVENTO_HITL_DECISION, {
                "lab.hitl.request_id": solicitud_id if E.HEX12(solicitud_id) else None,
                "lab.hitl.decision": "expire" if v.estado_nuevo == "expirada" else (decision if decision in M.DECISIONES else None),
                "lab.hitl.applied": v.aplicado, "lab.hitl.reason": v.motivo,
                "lab.hitl.approver": E.seudonimo(identidad.sub) if identidad else None,
                "lab.hitl.approver_level": M.nivel_de(identidad.roles) if identidad else None,
                "lab.hitl.state": s["estado"] if s else None,
                "lab.hitl.wait_ms": _espera_ms(s) if (v.aplicado or v.estado_nuevo) else None})
        return v, s

    def expirar(self) -> list[str]:
        ids = self.almacen.expirar_vencidas()
        for i in ids:
            s = self.almacen.obtener(i)
            with self._span(s) as span:
                E.fijar_evento(span, E.EVENTO_HITL_DECISION, {
                    "lab.hitl.request_id": i, "lab.hitl.decision": "expire", "lab.hitl.applied": True, "lab.hitl.reason": "vencida",
                    "lab.hitl.state": "expirada", "lab.hitl.wait_ms": _espera_ms(s)})
        return ids
