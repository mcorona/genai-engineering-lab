"""Week 17, activity 6: the approval state machine. Pure: no database, no clock of its own, no model.

    pendiente --approve (level ok, not the requester, in time)--> aprobada   (the only way an order can exist)
    pendiente --reject  (any approver level, not the requester)--> rechazada
    pendiente --a decision or a sweep after `expira_en` ---------> expirada
    aprobada | rechazada | expirada                             ---> terminal: nothing leaves a terminal state

`evaluar` decides what one attempt does to one request and why. The store (`almacen.py`) applies it inside a transaction with the row
locked, and the database repeats the same rules as constraints and triggers, so a bug here cannot create an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import criterios as C

ESTADOS = ("pendiente", "aprobada", "rechazada", "expirada")
TERMINALES = ("aprobada", "rechazada", "expirada")
DECISIONES = ("approve", "reject")
NIVELES = ("comprador", "gerente", "director")                       # ascending
ROL_DE_NIVEL = {"comprador": "legado-aprobador-comprador", "gerente": "legado-aprobador-gerente",
                "director": "legado-aprobador-director"}
MOTIVOS = ("ok", "mismo_usuario", "sin_nivel", "token_invalido", "vencida", "ya_decidida", "no_existe", "decision_invalida")


def nivel_requerido(monto_mxn: float) -> str:
    """R-OC-APRUEBA. The boundaries are inclusive for the manager (50,000 to 250,000) and exclusive below and above."""
    if monto_mxn > C.UMBRAL_DIRECTOR_MXN:
        return "director"
    if monto_mxn >= C.UMBRAL_GERENTE_MXN:
        return "gerente"
    return "comprador"


def nivel_de(roles) -> str | None:
    """The highest approval level the roles carry, or None."""
    niveles = [n for n in NIVELES if ROL_DE_NIVEL[n] in set(roles)]
    return niveles[-1] if niveles else None


def alcanza(roles, nivel_necesario: str) -> bool:
    n = nivel_de(roles)
    return n is not None and NIVELES.index(n) >= NIVELES.index(nivel_necesario)


@dataclass(frozen=True)
class Identidad:
    """A verified caller: the token's `sub` and its realm roles. Built by `identidad.verificar_token`, never from a request body."""
    sub: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class Veredicto:
    """What one attempt does. `aplicado` False means the decision was refused; `estado_nuevo` may still be set (a late attempt
    expires the request)."""
    aplicado: bool
    motivo: str
    estado_nuevo: str | None = None


def evaluar(solicitud: dict, identidad: Identidad | None, decision: str, ahora: datetime) -> Veredicto:
    if solicitud is None:
        return Veredicto(False, "no_existe")
    if decision not in DECISIONES:
        return Veredicto(False, "decision_invalida")
    if solicitud["estado"] != "pendiente":
        return Veredicto(False, "ya_decidida")
    if ahora >= solicitud["expira_en"]:
        return Veredicto(False, "vencida", "expirada")
    if identidad is None or not identidad.sub:
        return Veredicto(False, "token_invalido")
    if identidad.sub == solicitud["solicitante"]:
        return Veredicto(False, "mismo_usuario")
    if decision == "approve":
        if not alcanza(identidad.roles, solicitud["nivel"]):
            return Veredicto(False, "sin_nivel")
        return Veredicto(True, "ok", "aprobada")
    if nivel_de(identidad.roles) is None:           # rejecting needs an approver role, at any level: the safe direction
        return Veredicto(False, "sin_nivel")
    return Veredicto(True, "ok", "rechazada")
