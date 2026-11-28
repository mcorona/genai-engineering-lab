"""Week 20, activity 4, R1: the in-house router behind `modelo.invocar` (ADR 0015).

The task starts on the cheapest candidate. A signal moves the rest of the task one model up; it never goes back down,
and at most `max_escalamientos` times per task. Two kinds of signal:
- request signals, read in the next call's body (the loop's whole history): that call already goes to the next model;
- response signals, read in a model's raw Converse response: the same request is sent again to the next model and
  the loop only sees the stronger model's answer (the discarded call is still reported, so the budget pays it).

Never a signal: the Bedrock guardrail's intervention (its decision is final) and `max_tokens` (the budget sets it).
The state is per task: a body with one message is a new task.

Pure: no AWS here. `llamar` is the real Converse call or a fake; `permitir`, set by the budget, says whether a
resend fits and with which max_tokens (None: it does not, and the cheap answer stands).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from agente.converse_adaptador import peticion_a_converse, respuesta_a_anthropic

# The deterministic layer's error types (agente/capa_determinista.py, week 17's core): a block, not a tool failure.
TIPOS_BLOQUEO = ("guardrail", "herramienta_desconocida")
# The loop's own error type when `responder`'s input does not validate (semana-13/agente/loop.py).
TIPO_RESPUESTA_INVALIDA = "respuesta_invalida"
ESTADOS_SIN_RESPUESTA = ("abstenida", "requiere_aclaracion")
# The eval appends an English block with the output keys to every task (semana-13 `mensaje_tarea`); the task's own
# language is read before it.
_CORTE_TAREA = "\n\nOutput keys to report"
_PALABRAS = {
    "es": {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "por", "para", "con", "es", "son",
           "hay", "se", "su", "sus", "al", "lo", "como", "más", "está", "están", "fue", "cuántos", "cuántas", "qué",
           "cuál", "cuáles"},
    # No SQL keywords (from, and, in, on, by, not, is), so a SQL text decides nothing.
    "en": {"the", "of", "to", "are", "what", "which", "how", "many", "much", "for", "with", "there", "this", "that",
           "it", "be", "has", "have", "were", "was", "items", "total"},
}


def idioma_de(texto: str) -> str | None:
    """"es", "en" or None (too little text, or no clear winner): at least 3 function words, twice the other's."""
    palabras = re.findall(r"[a-záéíóúñü]+", (texto or "").lower())
    es = sum(p in _PALABRAS["es"] for p in palabras)
    en = sum(p in _PALABRAS["en"] for p in palabras)
    if es + en < 3:
        return None
    if es >= 2 * en and es > en:
        return "es"
    if en >= 2 * es and en > es:
        return "en"
    return None


@dataclass(frozen=True)
class Candidato:
    """One model of the router: its id (the us. profile: prices, spans and cache mode go by it), what the call
    names as modelId (its application profile ARN, or the id), its cache mode and whether it is Nova."""
    id: str
    llamar_como: str
    cache: str = "off"
    nova: bool = False


def _contenido(resultado: dict) -> dict:
    try:
        valor = json.loads(resultado.get("content") or "{}")
    except (TypeError, ValueError):
        return {}
    return valor if isinstance(valor, dict) else {}


def senales_de_peticion(cuerpo: dict) -> list[str]:
    """The event signals in the message the loop just appended: tool results with an error, a block, an invalid
    answer, or no rows."""
    ultimo = cuerpo["messages"][-1] if cuerpo.get("messages") else {}
    if ultimo.get("role") != "user" or not isinstance(ultimo.get("content"), list):
        return []
    senales = []
    for b in ultimo["content"]:
        if b.get("type") != "tool_result":
            continue
        valor = _contenido(b)
        tipo = (valor.get("error") or {}).get("tipo")
        if b.get("is_error") or valor.get("ok") is False:
            senales.append("bloqueo_capa" if tipo in TIPOS_BLOQUEO else
                           "respuesta_invalida" if tipo == TIPO_RESPUESTA_INVALIDA else "error_herramienta")
        elif "filas" in valor and not valor["filas"]:
            senales.append("resultado_vacio")
    return senales


def _tarea(cuerpo: dict) -> str:
    primero = cuerpo["messages"][0]["content"]
    texto = primero if isinstance(primero, str) else " ".join(b.get("text", "") for b in primero if isinstance(b, dict))
    return texto.split(_CORTE_TAREA, 1)[0]


def senales_de_respuesta(crudo: dict, idioma_tarea: str | None) -> list[str]:
    """The signals in a raw Converse response. Never for the guardrail's intervention or for max_tokens."""
    if crudo.get("stopReason") in ("guardrail_intervened", "max_tokens"):
        return []
    bloques = (crudo.get("output") or {}).get("message", {}).get("content") or []
    usos = [b["toolUse"] for b in bloques if "toolUse" in b]
    if not usos:
        return ["respuesta_vacia"] if crudo.get("stopReason") in ("end_turn", None) else []
    final = next((u.get("input") or {} for u in usos if u.get("name") == "responder"), None)
    if final is None:
        return []
    if final.get("estado") in ESTADOS_SIN_RESPUESTA:
        return ["abstencion"]
    idioma = idioma_de(str(final.get("respuesta", "")))
    if idioma_tarea and idioma and idioma != idioma_tarea:
        return ["idioma"]
    return []


def _tokens(crudo: dict) -> int:
    u = crudo.get("usage") or {}
    return sum(int(u.get(k) or 0) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                             "cacheWriteInputTokens"))


class Enrutador:
    """The `api=` of the loop when RUTEO is r1. Per task: the model in use, the escalations and their reasons."""

    def __init__(self, llamar: Callable[[dict], dict], *, candidatos: tuple[Candidato, ...], reglas: dict,
                 guardrail: dict | None = None, ttl: str = "5m"):
        self._llamar, self.candidatos, self.reglas = llamar, candidatos, reglas
        self.guardrail, self.ttl = guardrail, ttl
        self.senales = set(reglas["senales"])
        self.permitir: Callable[[str, dict], int | None] | None = None
        self._nueva_tarea("")

    def _nueva_tarea(self, tarea: str) -> None:
        self.indice = 0
        self.escalamientos = 0
        self.motivos: list[str] = []      # the signal of each escalation, in order
        self.ignoradas: list[str] = []    # signals after the maximum, recorded and ignored
        self.tokens_vistos = 0
        self._presiones: set[str] = set()
        self._evaluado = -1               # the message count whose request signals were already read
        self._motivo_pendiente: str | None = None
        self.idioma_tarea = idioma_de(tarea)
        self.ultimas_llamadas: list[dict] = []

    @property
    def actual(self) -> Candidato:
        return self.candidatos[self.indice]

    def _escalar(self, motivo: str) -> bool:
        if self.escalamientos >= self.reglas["max_escalamientos"] or self.indice >= len(self.candidatos) - 1:
            self.ignoradas.append(motivo)
            return False
        self.indice += 1
        self.escalamientos += 1
        self.motivos.append(motivo)
        return True

    def siguiente(self, cuerpo: dict) -> str:
        """The id of the model the next call of this body goes to. Reads the request signals once per body."""
        n = len(cuerpo["messages"])
        if n == 1 and self._evaluado != 1:
            self._nueva_tarea(_tarea(cuerpo))
        if n == self._evaluado:
            return self.actual.id
        self._evaluado = n
        senales = [s for s in senales_de_peticion(cuerpo) if s in self.senales]
        turnos = sum(m.get("role") == "assistant" for m in cuerpo["messages"])
        for presion, alcanzada in (("presion_pasos", turnos >= self.reglas["pasos_presion"]),
                                   ("presion_tokens", self.tokens_vistos >= self.reglas["tokens_presion"])):
            if alcanzada and presion in self.senales and presion not in self._presiones:
                self._presiones.add(presion)
                senales.append(presion)
        if senales and self._escalar(senales[0]):
            self._motivo_pendiente = senales[0]
        return self.actual.id

    def _ruta(self, motivo: str | None) -> dict:
        return {"inicial": self.candidatos[0].id, "escalado": self.indice > 0, "motivo": motivo}

    def _una(self, cuerpo: dict, motivo: str | None) -> tuple[dict, dict]:
        c = self.actual
        req = peticion_a_converse(cuerpo, modelo_id=c.llamar_como, guardrail=self.guardrail, cache=c.cache,
                                  ttl=self.ttl, nova=c.nova)
        crudo = self._llamar(req)
        self.tokens_vistos += _tokens(crudo)
        llamada = {"modelo": c.id, "usage": respuesta_a_anthropic(crudo)["usage"], "ruta": self._ruta(motivo),
                   "descartada": False}
        return crudo, llamada

    def __call__(self, cuerpo: dict) -> dict:
        self.siguiente(cuerpo)
        motivo, self._motivo_pendiente = self._motivo_pendiente, None
        crudo, llamada = self._una(cuerpo, motivo)
        llamadas = [llamada]
        while True:
            senales = [s for s in senales_de_respuesta(crudo, self.idioma_tarea) if s in self.senales]
            if not senales or self.escalamientos >= self.reglas["max_escalamientos"] \
                    or self.indice >= len(self.candidatos) - 1:
                self.ignoradas += senales
                break
            proximo = self.candidatos[self.indice + 1].id
            max_tokens = cuerpo["max_tokens"] if self.permitir is None else self.permitir(proximo, cuerpo)
            if max_tokens is None:
                llamadas[-1]["ruta"]["motivo"] = "sin_presupuesto"
                break
            self._escalar(senales[0])
            llamadas[-1]["descartada"] = True
            crudo, llamada = self._una(dict(cuerpo, max_tokens=max_tokens), senales[0])
            llamadas.append(llamada)
        self.ultimas_llamadas = llamadas
        resp = respuesta_a_anthropic(crudo)
        resp["usage"] = {k: sum(x["usage"].get(k, 0) for x in llamadas) for k in resp["usage"]}
        resp["_llamadas"] = llamadas
        return resp
