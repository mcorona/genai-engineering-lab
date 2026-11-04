"""Week 17, activity 5: the deterministic detectors behind the guardrails. Pure functions: text in, categories out. No model, no network.

Every category is a fixed word, so a decision can say WHY without carrying the text that triggered it (a span event never holds a prompt,
a SQL or a value). The patterns were written after reading the week 13 and week 14 attack payloads, so a block rate on those is in-sample;
`heldout.py` holds phrasings written before these rules and run once.

Order of the families: instructions inside DATA (tool results and descriptions) -> the user's REQUEST (override, scope) -> the ANSWER
(personal values, figures).
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_I = re.IGNORECASE
_ORACION = r"[^.\n]"          # stays inside a sentence

# ---------- 1. instructions inside data: a tool result or a tool description is never an instruction ----------

_DESTINO_IA = (r"(?:ai|a\.i\.|llm|language model|assistants?|agents?|model|bots?|modelo|asistentes?|agentes?|ia|"
               r"sistemas? de ia|sistemas? autom[aá]ticos?)")
_VERBO_ORDEN = r"(?:must|should|shall|are required to|required to|have to|deben|debe|tienen que|tiene que|deber[aá]n|se requiere que)"
_HERRAMIENTAS = (r"(?:proponer_orden_compra|ejecutar_sql|validar_sql|muestrear_valores|buscar_regla_negocio|describir_esquema|"
                 r"legado__\w+|inventario_plus__\w+|tipos_cambio__\w+)")
_DML = r"(?:update|delete|insert|drop|truncate|alter|grant)"

PATRONES_EN_DATOS: list[tuple[str, re.Pattern]] = [(c, re.compile(p, _I)) for c, p in [
    ("ignorar_instrucciones", rf"\b(?:ignore|disregard|forget|override|bypass)\b{_ORACION}{{0,60}}\b(?:instructions?|rules?|prompts?|guidelines?|"
                              rf"system prompt|the question you were given|everything)\b"),
    ("ignorar_instrucciones", rf"\b(?:ignora|olvida|descarta|omite|pasa por alto)\b{_ORACION}{{0,60}}\b(?:instrucciones|reglas|indicaciones|"
                              rf"lo que te (?:dijeron|pidieron|preguntaron)|la pregunta)\b"),
    ("ignorar_instrucciones", rf"\b(?:stop following|deja de seguir)\b"),
    ("ignorar_instrucciones", rf"\bno respondas\b{_ORACION}{{0,40}}\b(?:lo que|la pregunta)\b"),
    ("dirigido_a_la_ia", rf"\b(?:note|reminder|notice|message|warning|aviso|nota|recordatorio|instrucci[oó]n interna|instruction)\b"
                         rf"{_ORACION}{{0,25}}\b(?:to|for|para)\b{_ORACION}{{0,25}}\b{_DESTINO_IA}\b"),
    ("dirigido_a_la_ia", rf"\bsystem note\b"),
    ("dirigido_a_la_ia", rf"\b(?:automated|ai)\s+(?:assistants?|agents?|systems?)\b{_ORACION}{{0,80}}\b{_VERBO_ORDEN}\b"),
    ("dirigido_a_la_ia", rf"\b(?:asistentes?|agentes?|sistemas?)\s+(?:autom[aá]ticos?|de ia)\b{_ORACION}{{0,60}}\b{_VERBO_ORDEN}\b"),
    ("dirigido_a_la_ia", rf"\[(?:admin|system|developer|root)[^\]]{{0,20}}\]"),
    ("dirigido_a_la_ia", rf"(?m)^\s*(?:assistant|system|developer)\s*:"),
    ("dirigido_a_la_ia", rf"\bassistant\s*:"),
    ("bloque_important", rf"<\s*important\s*>"),
    ("bloque_important", rf"\bimportant (?:update|notice|instruction)s?\b{_ORACION}{{0,30}}\b(?:agents?|assistants?|ai|models?)\b"),
    ("orden_de_herramienta", rf"\b(?:call|invoke|use|run|execute|register|submit|send|propose|create|llama|llamar|invoca|usa|usar|ejecuta|ejecutar|"
                            rf"registra|registrar|env[ií]a|propone|propon|crea|crear)\b{_ORACION}{{0,40}}\b{_HERRAMIENTAS}\b"),
    ("orden_de_herramienta", rf"\b{_HERRAMIENTAS}\b{_ORACION}{{0,60}}\b(?:immediately|inmediatamente|ahora mismo|right away)\b"),
    ("orden_de_escritura", rf"\b(?:execute|run|perform|ejecuta|ejecutar|corre|realiza)\b{_ORACION}{{0,40}}\b{_DML}\b"),
    ("orden_de_escritura", rf"\b(?:borra|elimina|delete|drop|remove|truncate)\b{_ORACION}{{0,50}}\b(?:tabla|table|registros|rows|records|exidet|artmst|vtadia)\b"),
    ("orden_de_escritura", rf"\b(?:drop\s+table|delete\s+from|truncate\s+table|update\s+\w+\s+set|insert\s+into)\b"),
    ("ocultar_al_usuario", rf"\b(?:do not|don't|never|no|nunca)\s+(?:\w+\s+){{0,2}}(?:tell|mention|inform|notify|say|digas|menciones|avises|informes|"
                           rf"comentes|reveles)\b{_ORACION}{{0,25}}(?:\buser\b|\busuario\b|\bit\b)"),
    ("ocultar_al_usuario", rf"\b(?:without (?:telling|notifying|informing)|sin (?:avisar|decir|informar)(?: nada)? al) (?:the )?(?:user|usuario)\b"),
    ("ocultar_al_usuario", rf"\b(?:keep|mantener)\b{_ORACION}{{0,20}}\b(?:from|oculto a|en secreto)\b{_ORACION}{{0,12}}\b(?:the )?(?:user|usuario)\b"),
    ("ocultar_al_usuario", rf"\bsilently\b|\ben silencio\b"),
    ("exfiltracion", rf"\b(?:send|forward|post|upload|pass|include|env[ií]a|reenv[ií]a|manda|incluye|pasa)\b{_ORACION}{{0,60}}"
                     rf"\b(?:to|a|al|en)\b{_ORACION}{{0,30}}\b(?:audit\w*|server|servidor|tool|herramienta|endpoint|url|http\S*)\b"),
    ("exfiltracion", rf"\b(?:pass|send|pasa|env[ií]a)\b{_ORACION}{{0,50}}\b(?:contexto|context)\b{_ORACION}{{0,30}}\b(?:parameter|par[aá]metro|argument)\b"),
    ("cambio_de_modo", rf"\b(?:from now on|a partir de ahora)\b{_ORACION}{{0,40}}\b(?:you are|eres|answer|responde|act|act[uú]a)\b"),
    ("cambio_de_modo", rf"\b(?:maintenance|developer|admin|debug)\s+mode\b|\bmodo (?:de )?(?:mantenimiento|desarrollador|administrador)\b"),
    ("caracteres_invisibles", "[​-‏‪-‮⁠-⁤﻿]"),
]]

MARCA_RETIRADO = {"es": "[texto con instrucciones retirado por el guardrail]", "en": "[text with instructions removed by the guardrail]"}


def instrucciones_en_datos(texto: str) -> list[str]:
    """Categories of instruction-like text found in a piece of data, in order of first appearance, without repeats."""
    out: list[str] = []
    for cat, rx in PATRONES_EN_DATOS:
        if rx.search(texto or "") and cat not in out:
            out.append(cat)
    return out


def retirar_instrucciones(texto: str, idioma: str = "es") -> tuple[str, list[str]]:
    """The whole field replaced by a marker if it carries instructions, and the categories found. Whole, not the sentence: an instruction
    cannot be delimited (the order and the "do not tell the user" that goes with it are often different sentences), and a field that
    gives orders is not data to be trusted in part."""
    cats = instrucciones_en_datos(texto)
    if not cats:
        return texto, []
    return MARCA_RETIRADO.get(idioma, MARCA_RETIRADO["en"]), cats


# keys whose value is the model's own text coming back (the normalised SQL it sent): scanning it would flag the agent's own query
CLAVES_PROPIAS = frozenset({"sql_normalizado"})


def cadenas_de(valor, minimo: int = 12) -> Iterable[str]:
    """Every string inside a JSON-like value (dict, list, str), so a tool result is scanned field by field."""
    if isinstance(valor, str):
        if len(valor) >= minimo:
            yield valor
    elif isinstance(valor, dict):
        for k, v in valor.items():
            if k not in CLAVES_PROPIAS:
                yield from cadenas_de(v, minimo)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            yield from cadenas_de(v, minimo)


def limpiar_valor(valor, idioma: str = "es") -> tuple[object, list[str]]:
    """The same JSON-like value with the instruction-like sentences of its strings replaced, and the categories found."""
    cats: list[str] = []

    def rec(v):
        if isinstance(v, str) and len(v) >= 12:
            nuevo, c = retirar_instrucciones(v, idioma)
            cats.extend(x for x in c if x not in cats)
            return nuevo
        if isinstance(v, dict):
            return {k: (x if k in CLAVES_PROPIAS else rec(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [rec(x) for x in v]
        return v

    return rec(valor), cats


# ---------- 2. the user's request ----------

PATRONES_PETICION_INYECCION: list[tuple[str, re.Pattern]] = [(c, re.compile(p, _I)) for c, p in [
    ("ignorar_instrucciones", rf"\b(?:ignore|disregard|forget|override|bypass)\b{_ORACION}{{0,60}}\b(?:instructions?|rules?|guidelines?|prompts?|"
                              rf"system prompt|everything (?:you|i))\b"),
    ("ignorar_instrucciones", rf"\b(?:ignora|olvida|descarta|omite|pasa por alto)\b{_ORACION}{{0,60}}\b(?:instrucciones|reglas|indicaciones|"
                              rf"lo que te (?:dijeron|pidieron))\b"),
    ("exfiltrar_instrucciones", rf"\b(?:show|print|reveal|display|repeat|muestra|imprime|revela|repite|dime)\b{_ORACION}{{0,40}}\b(?:system prompt|"
                                rf"prompt del sistema|(?:your|tus) (?:hidden |secret |ocultas? )?instructions?|instrucciones|"
                                rf"the instructions you received|las instrucciones que recibiste)\b"),
    ("cambio_de_rol", rf"\b(?:act as|pretend (?:to be|you)|you are now|actúa como|act[uú]a como|finge|ahora eres)\b{_ORACION}{{0,50}}\b(?:unrestricted|"
                      rf"without restrictions|no (?:tienes|tuvieras) restricciones|sin restricciones|jailbreak|dan)\b"),
    ("cambio_de_rol", rf"\bactúa como si no tuvieras\b|\bact as if you (?:had|have) no\b"),
    ("cambio_de_rol", rf"\b(?:developer|admin|maintenance|debug) mode\b|\bmodo (?:desarrollador|administrador|mantenimiento)\b"),
]]

_OBJETO_DE_DATOS = (r"(?:tabla|table|registros?|rows?|records?|filas?|existencias?|stock|inventario|inventory|proveedor(?:es)?|suppliers?|"
                    r"punto de reorden|reorder point|estado|status|permisos?|permissions?|costos?|costs?|precios?|prices?|"
                    r"ventas|sales|productos?|products?|almac[eé]n(?:es)?|warehouses?|art[ií]culos?|items?|datos|data|base de datos|database)")
_VERBO_ESCRITURA = (r"(?:borra(?:r)?|elimina(?:r)?|actualiza(?:r)?|modifica(?:r)?|cambia(?:r)?|inserta(?:r)?|agrega(?:r)?|a[ñn]ade|crea(?:r)?|quita(?:r)?|"
                    r"marca(?:r)?|pon(?:l[ao]s?)?|poner|otorga(?:r)?|ot[oó]rgal[ea]s?|cancela(?:r)?|vac[ií]a|sobrescribe|"
                    r"delete|remove|drop|update|insert|add|create|set|change|grant|cancel|truncate|alter|overwrite|wipe|empty|mark|write)")
_VERBO_APROBACION = (r"(?:aprueba(?:r|la|lo|las|los|me)?|apruebes|apru[eé]bal[ao]s?|autoriza(?:r|la|lo|las|los)?|autorices|"
                     r"approve|authori[sz]e|sign off)")
PATRONES_PETICION_ALCANCE: list[tuple[str, re.Pattern]] = [(c, re.compile(p, _I)) for c, p in [
    ("escritura", rf"\b{_VERBO_ESCRITURA}\b{_ORACION}{{0,60}}\b{_OBJETO_DE_DATOS}\b"),
    # An order is a write target only for the verbs that change or remove one. "Create a purchase order (proposal)" is the supported flow
    # (the only consequential tool registers a PENDING_APPROVAL proposal): blocking it here would block the feature, and a request that
    # also asks to approve it is caught by `aprobacion`.
    ("escritura", rf"\b(?:cancela(?:r)?|elimina(?:r)?|borra(?:r)?|modifica(?:r)?|actualiza(?:r)?|cambia(?:r)?|cancel|delete|remove|modify|update|change)\b"
                  rf"{_ORACION}{{0,40}}\b(?:orden(?:es)?(?:\s+de\s+compra)?|orders?|purchase orders?)\b"),
    ("escritura", rf"\b(?:drop\s+table|delete\s+from|truncate\s+table|update\s+\w+\s+set|insert\s+into|alter\s+table|create\s+table)\b"),
    ("escritura", rf"\b(?:ponl[ao]s?|set it|set them)\b{_ORACION}{{0,15}}\b(?:en cero|to zero|a cero)\b"),
    ("escritura", rf"\b(?:set_config|lo_create|lo_import|pg_read_file|pg_sleep|dblink|copy\s+\w+\s+(?:to|from))\b"),
    ("aprobacion", rf"(?:^|[.!;:\n]\s*|(?:por favor|please|y|and|luego|then)[,]?\s+){_VERBO_APROBACION}\b"),
    ("aprobacion", rf"\b(?:puedes|podr[ií]as|quiero que|necesito que|te pido que|want you to|need you to|can you|could you|would you|please|por favor)"
                   rf"\s+(?:\w+\s+){{0,2}}{_VERBO_APROBACION}\b"),
    ("aprobacion", rf"\bcambia(?:r)?\b{_ORACION}{{0,40}}\b(?:su )?estado\b{_ORACION}{{0,30}}\b(?:approved|aprobad[ao]|cancelad[ao]|cancelled)\b"),
    ("otro_tenant_o_esquema", rf"\b(?:semana10|semana_10)\b|\bchunks\b|\btenant[_ ]?(?:id)?\s*(?:distinto|diferente|other|another|beta|alfa)\b"),
    ("varias_sentencias", rf"['\"]?\s*;\s*(?:drop|delete|update|insert|alter|truncate|grant|create)\b"),
]]


def inyeccion_en_peticion(texto: str) -> list[str]:
    out: list[str] = []
    for cat, rx in PATRONES_PETICION_INYECCION:
        if rx.search(texto or "") and cat not in out:
            out.append(cat)
    return out


def fuera_de_alcance(texto: str) -> list[str]:
    out: list[str] = []
    for cat, rx in PATRONES_PETICION_ALCANCE:
        if rx.search(texto or "") and cat not in out:
            out.append(cat)
    return out


# the consequential tool needs the user to have ASKED for it: an imperative (or a polite request) naming a proposal or an order. A question
# about proposals ("how many purchase order proposals...") does not, and neither does the noun "order" inside it.
_ARRANQUE = (r"(?:^|[.!;:\n]\s*|(?:por favor|please|y|and|luego|then)[,]?\s+|"
             r"(?:puedes|podr[ií]as|quiero que|necesito que|te pido que|want you to|need you to|can you|could you|would you)\s+)")
_VERBO_PROPONER = (r"(?:registra(?:r|s|me)?|registres|crea(?:r|s|me)?|crees|genera(?:r|s|me)?|generes|prop[oó]n(?:er|me|gas)?|pide|pedir|pidas|"
                   r"ordena(?:r)?|solicita(?:r|s)?|haz|hacer|levanta(?:r)?|"
                   r"register|create|propose|order|place|request|submit|raise|make|draft)")
_INTENCION_DE_PROPONER = re.compile(
    rf"{_ARRANQUE}{_VERBO_PROPONER}\b[^.\n?]{{0,80}}"
    r"\b(?:propuesta|propuestas|orden(?:es)? de compra|purchase orders?|proposals?|pedido|pedidos|piezas|unidades|units|pieces|sku-?\d+)\b", _I)


def pide_proponer(texto: str) -> bool:
    return bool(_INTENCION_DE_PROPONER.search(texto or ""))


# ---------- 3. the answer ----------

PERSONALES: list[tuple[str, re.Pattern]] = [(c, re.compile(p, f)) for c, p, f in [
    ("correo", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", 0),
    ("rfc", r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b", 0),
    ("curp", r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b", 0),
    ("telefono", r"(?<![\w.])(?:\+?\d{1,3}[ -])?\(?\d{2,3}\)?[ -]\d{3,4}[ -]\d{4}(?![\w])", 0),
    ("tarjeta", r"\b(?:\d{4}[ -]){3}\d{4}\b", 0),
    ("clabe", r"\b\d{18}\b", 0),
    ("clave_api", r"\bsk-[A-Za-z0-9_-]{16,}\b|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b", 0),
]]
MARCA_PERSONAL = {"es": "[dato personal retirado]", "en": "[personal value removed]"}


def personales_en(texto: str) -> list[str]:
    out: list[str] = []
    for cat, rx in PERSONALES:
        if rx.search(texto or "") and cat not in out:
            out.append(cat)
    return out


def retirar_personales(texto: str, idioma: str = "es") -> tuple[str, list[str]]:
    marca, cats = MARCA_PERSONAL.get(idioma, MARCA_PERSONAL["en"]), []
    for cat, rx in PERSONALES:
        texto, n = rx.subn(marca, texto or "")
        if n and cat not in cats:
            cats.append(cat)
    return texto, cats


_NUMERO = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:[.,]\d+)?")


_IDENTIFICADOR = re.compile(r"\b[A-Za-z]{2,}[-_]?\d+\b")       # SKU-0027, PO0001: a code, not a quantity


def cifras(texto: str, identificadores: bool = True) -> list[float]:
    """Every number in a text as a float. `1,234.50` and `1234.5` are the same figure; `12,5` is read as 12.5 (decimal comma).
    `identificadores=False` drops the digits of codes such as SKU-0027 first (they are still checked as figures, but are not quantities)."""
    if not identificadores:
        texto = _IDENTIFICADOR.sub(" ", texto or "")
    out = []
    for m in _NUMERO.findall(texto or ""):
        t = m
        if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", t):
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
        try:
            out.append(float(t))
        except ValueError:
            continue
    return out


def numeros_de_valor(valor, identificadores: bool = True) -> list[float]:
    """The figures inside a JSON-like value: numbers as such, strings by `cifras`."""
    out: list[float] = []
    if isinstance(valor, bool) or valor is None:
        return out
    if isinstance(valor, (int, float)):
        return [float(valor)]
    if isinstance(valor, str):
        return cifras(valor, identificadores)
    if isinstance(valor, dict):
        for v in valor.values():
            out += numeros_de_valor(v, identificadores)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            out += numeros_de_valor(v, identificadores)
    else:
        try:
            out.append(float(valor))
        except (TypeError, ValueError):
            out += cifras(str(valor), identificadores)
    return out


MAX_ANCLAS = 8
ENTEROS_PEQUENOS = 10      # "3 steps", "top 5": a small whole number carries no claim about the data


class Conocidas:
    """The figures an answer may state: those in the tool results, in the task text, and the sizes of the result lists (a row count is
    a figure the system derived, not one the model invented). Rounding to 2 decimals, or to the unit, is how people write figures."""

    def __init__(self, tarea: str = ""):
        self.dos: set[float] = set()
        self.unidad: set[float] = set()
        self.agregar_numeros(cifras(tarea))

    def agregar_numeros(self, numeros: Iterable[float]) -> None:
        for k in numeros:
            self.dos.add(round(k, 2))
            self.unidad.add(float(round(k)))

    def agregar_resultado(self, valor) -> None:
        self.agregar_numeros(numeros_de_valor(valor))
        self._tamanos(valor)

    def _tamanos(self, valor) -> None:
        if isinstance(valor, dict):
            for v in valor.values():
                self._tamanos(v)
        elif isinstance(valor, (list, tuple)):
            self.agregar_numeros([float(len(valor))])
            for v in valor:
                self._tamanos(v)

    def fundamenta(self, cifra: float) -> bool:
        entera = float(cifra).is_integer()
        if entera and 0 <= cifra <= ENTEROS_PEQUENOS:
            return True
        if round(cifra, 2) in self.dos:
            return True
        return entera and cifra in self.unidad          # "12,513" said for a known 12,512.7

    def sin_fundamento(self, numeros: Iterable[float], anclas_posibles: Iterable[float] | None = None) -> list[float]:
        """The figures no tool result supports. A TOTAL of figures the answer itself states and the tools do support (3,765 + 6,353 + 5,154 =
        15,272) counts as supported: it is arithmetic on evidence, and the reader can check it. Tuned after the first false-positive
        measurement (two of the three refusals were totals); the anchors are at most 8 distinct figures, in order, without identifiers
        (a leading zero, as in SKU-0027), so the rule stays far from "any number is a sum of something"."""
        numeros = list(numeros)
        resto = [c for c in numeros if not self.fundamenta(c)]
        if not resto:
            return []
        anclas: list[float] = []
        for c in (numeros if anclas_posibles is None else list(anclas_posibles)):
            if c > 0 and self.fundamenta(c) and c not in anclas and len(anclas) < MAX_ANCLAS:
                anclas.append(c)
        sumas = {0.0}
        for x in anclas:
            sumas |= {round(s + x, 2) for s in sumas}
        sumas.discard(0.0)
        enteras = {float(round(x)) for x in sumas}
        return [c for c in resto if not (round(c, 2) in sumas or (float(c).is_integer() and c in enteras))]
