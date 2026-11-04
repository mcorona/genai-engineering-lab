"""Week 17, activity 5: what each guardrail decides, from the detectors of `reglas.py`.

Three stages, ten guardrails (`criterios.GUARDRAILS`):

    input   input_peticion_inyeccion   the user's request tries to override the instructions or to read them
            input_peticion_alcance     the request asks for a write, an approval or another tenant's data: this agent only reads
            input_resultado_inyeccion  a tool result or a tool DESCRIPTION carries instructions: data is not instructions
    tool    tool_allowlist             the tool exists, was not dropped, and a consequential one was asked for by the user
            tool_esquema               the arguments fit the tool's input schema
            tool_sql                   one SELECT, no write, no forbidden function
            tool_alcance_token         the scopes of the token cover the tool, the tables and the columns; no other schema or tenant
    output  salida_personales          personal values are removed from the answer
            salida_fundamentacion      every figure of the answer is in a tool result (or in the task)
            salida_sin_evidencia       an answer needs at least one tool result behind it

A `Decision` is a guardrail, a stage, an action (allow, block, sanitize, redact, refuse) and a reason that is a word of a fixed list. It
never holds the text that triggered it: that is what makes it safe to put on a span.

Pure functions here; `agente.py` puts them in the loop. Everything is deterministic: no model, no network.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import sqlglot
from sqlglot import exp

S17 = Path(__file__).resolve().parents[1]
S14 = S17.parent / "semana-14"
for ruta in (S17, S14):
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))

from guardrails import reglas as R  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from servidor.oauth import SCOPE_BASE, SCOPES, TABLA_SCOPE, PERMISOS as PERMISOS_OAUTH, scopes_requeridos  # noqa: E402

from herramientas.herramientas import FUNCIONES_PROHIBIDAS, NODOS_PROHIBIDOS, RAICES_PERMITIDAS  # noqa: E402

CONSECUENTES = ("proponer_orden_compra",)      # tools that leave a trace outside the conversation
TOOLS_CON_SQL = ("ejecutar_sql", "validar_sql")
CLAVES_DE_SUJETO = frozenset({"usuario", "user", "user_id", "sub", "tenant", "tenant_id"})
OTROS_TENANTS = {"chunks": "tabla", "semana10": "esquema"}

# What each user of the lab may do, as the scopes of a week 14 token (`semana-14/auth/permisos_oauth.json`). The agent never chooses these.
SCOPES_DE = {
    "analista": frozenset(SCOPES),                                # compras + finanzas: every scope, the proposal included
    "almacenista": frozenset({SCOPE_BASE}),                       # almacen
    "vendedor": frozenset({SCOPE_BASE, "legado:ventas"}),         # ventas
}


SEPARADOR = "__"        # the week 14 client names a tool `<server>__<tool>` when its defences are on


def nombre_base(nombre: str) -> str:
    """The tool's own name, without the server prefix the client may add."""
    return nombre.rsplit(SEPARADOR, 1)[-1]


@dataclass(frozen=True)
class Decision:
    guardrail: str
    etapa: str          # input | tool | output
    accion: str         # allow | block | sanitize | redact | refuse
    motivo: str         # a word of esquema.MOTIVOS_GUARDRAIL

    @property
    def permite(self) -> bool:
        return self.accion == "allow"


def permitir(guardrail: str, etapa: str) -> Decision:
    return Decision(guardrail, etapa, "allow", "ok")


@dataclass(frozen=True)
class Alcance:
    """Who asks, as the system knows it. It comes from the token, never from the request or the model."""
    usuario: str
    tenant: str
    scopes: frozenset
    idioma: str = "es"


# ---------- input: the request ----------

def revisar_peticion(texto: str) -> list[Decision]:
    """Two decisions, always: the request is checked for an attempt to override instructions and for an out-of-scope intent."""
    inyeccion, alcance = R.inyeccion_en_peticion(texto), R.fuera_de_alcance(texto)
    return [
        Decision("input_peticion_inyeccion", "input", "block", inyeccion[0]) if inyeccion else permitir("input_peticion_inyeccion", "input"),
        Decision("input_peticion_alcance", "input", "block", alcance[0]) if alcance else permitir("input_peticion_alcance", "input"),
    ]


# ---------- input: tool descriptions and tool results ----------

def _textos_de_definicion(d: dict) -> list[str]:
    """The description of a tool and of each of its parameters: all of it is read by the model."""
    textos = [d.get("description", "")]

    def rec(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("description", "title", "default") and isinstance(x, str):
                    textos.append(x)
                else:
                    rec(x)
        elif isinstance(v, list):
            for x in v:
                rec(x)

    rec(d.get("input_schema", {}))
    return textos


def revisar_definiciones(defs: list[dict]) -> tuple[list[dict], set[str], list[Decision]]:
    """The tools the model may see, the names that were dropped, and one decision per tool that was examined."""
    limpias, retiradas, decisiones = [], set(), []
    for d in defs:
        cats: list[str] = []
        for t in _textos_de_definicion(d):
            cats += [c for c in R.instrucciones_en_datos(t) if c not in cats]
        if cats:
            retiradas.add(d["name"])
            decisiones.append(Decision("input_resultado_inyeccion", "input", "block", cats[0]))
        else:
            limpias.append(d)
            decisiones.append(permitir("input_resultado_inyeccion", "input"))
    return limpias, retiradas, decisiones


def revisar_resultado(res: dict, idioma: str = "es") -> tuple[dict, Decision]:
    """A tool result with the instruction-like sentences of its strings replaced by a marker. The structure is kept: the model
    still sees which fields there were and the data around the removed sentence."""
    error = res.get("error")
    limpio, cats = R.limpiar_valor({k: v for k, v in res.items() if k != "error"}, idioma)
    if error is not None:
        e2, c2 = R.limpiar_valor({k: v for k, v in error.items() if k != "tipo"}, idioma)
        limpio["error"] = {"tipo": error.get("tipo"), **e2}
        cats += [c for c in c2 if c not in cats]
    if cats:
        return limpio, Decision("input_resultado_inyeccion", "input", "sanitize", cats[0])
    return res, permitir("input_resultado_inyeccion", "input")


# ---------- tool: before each call ----------

def _validadores(defs: list[dict]) -> dict:
    return {d["name"]: jsonschema.Draft202012Validator(d["input_schema"]) for d in defs if "input_schema" in d}


def _revisar_esquema(validador, args: dict) -> str | None:
    """`path: keyword` of the first problems, no values: an argument may be the very text the guardrail is there to keep out."""
    errores = sorted(validador.iter_errors(args), key=lambda e: [str(p) for p in e.path])[:3]
    if not errores:
        return None
    return "; ".join(f"{'.'.join(map(str, e.path)) or '<root>'}: {e.validator}" for e in errores)


def _motivo_sql(sql: str) -> str | None:
    try:
        sentencias = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError:
        # Tuned after the first false-positive measurement (3 of 84 tasks): SQL that does not parse is not judged here. The tool's own guard
        # (week 13) is fail-closed on the same parser and answers with the syntax error the model can fix; blocking it here added no
        # protection and replaced that message with a generic one.
        return None
    if len(sentencias) != 1:
        return "sql_varias_sentencias"
    raiz = sentencias[0]
    if any(isinstance(n, NODOS_PROHIBIDOS) for n in raiz.walk()) or not isinstance(raiz, RAICES_PERMITIDAS):
        return "sql_escritura"
    for f in raiz.find_all(exp.Func):
        nombre = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if nombre.startswith(FUNCIONES_PROHIBIDAS):
            return "sql_funcion"
    return None


def _uso_de_sql(sql: str) -> tuple[set[str], set[str], set[str], bool] | None:
    """(tables, columns named `table.column` that the token model restricts, schemas other than legado, touches another tenant). None if the
    SQL does not parse: `tool_sql` already said so."""
    try:
        sentencias = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError:
        return None
    tablas, esquemas, ajeno = set(), set(), False
    restringidas = {k.split(".")[1]: k for k in PERMISOS_OAUTH["columnas_restringidas"]}
    columnas, hay_estrella = set(), False
    nombres_de_columna = set()
    for s in sentencias:
        ctes = {c.alias_or_name.lower() for c in s.find_all(exp.CTE)}
        for t in s.find_all(exp.Table):
            nombre, esquema = (t.name or "").lower(), (t.db or "").lower()
            if not nombre or (nombre in ctes and not esquema):
                continue
            if esquema and esquema != "legado":
                esquemas.add(esquema)
            tablas.add(nombre)
            if nombre in OTROS_TENANTS or esquema in OTROS_TENANTS:
                ajeno = True
        for c in s.find_all(exp.Column):
            nombres_de_columna.add(c.name.lower())
            if c.name.lower() == "tenant_id":
                ajeno = True
        hay_estrella = hay_estrella or any(not isinstance(x.parent, exp.Count) for x in s.find_all(exp.Star))
    for nombre, clave in restringidas.items():
        if clave.split(".")[0] in tablas and (nombre in nombres_de_columna or hay_estrella):
            columnas.add(clave)
    return tablas, columnas, esquemas, ajeno


def _scopes_de_llamada(nombre: str, args: dict) -> tuple[set[str], str | None]:
    """The scopes this call needs (week 14's `scopes_requeridos` plus the tables and columns it reaches) and, if it reaches
    outside the legacy schema or into another tenant, the reason."""
    req = set(scopes_requeridos("tools/call", nombre))
    if nombre in TOOLS_CON_SQL:
        uso = _uso_de_sql(str(args.get("sql", "")))
        if uso is not None:
            tablas, columnas, esquemas, ajeno = uso
            if ajeno:
                return req, "otro_tenant"
            if esquemas or any(t not in TABLA_SCOPE for t in tablas):
                return req, "esquema_ajeno"
            req |= {TABLA_SCOPE[t] for t in tablas}
            for c in columnas:
                req |= set(PERMISOS_OAUTH["columnas_restringidas"][c])
    elif nombre == "muestrear_valores" and isinstance(args.get("tabla"), str):
        tabla = args["tabla"].lower()
        if tabla not in TABLA_SCOPE:
            return req, "esquema_ajeno"
        req.add(TABLA_SCOPE[tabla])
        req |= set(PERMISOS_OAUTH["columnas_restringidas"].get(f"{tabla}.{str(args.get('columna', '')).lower()}", []))
    return req, None


def revisar_llamada(nombre: str, args: dict, *, permitidas: set[str], retiradas: set[str], validadores: dict, peticion: str,
                    alcance: Alcance) -> list[Decision]:
    """The decisions of the four tool guardrails for one call, in the order of the plan, stopping at the first block. A call that is
    allowed has four `allow` decisions, one per guardrail."""
    args = args if isinstance(args, dict) else {}
    out: list[Decision] = []

    def cierra(d: Decision) -> bool:
        out.append(d)
        return not d.permite

    # 1. allowlist (and: a consequential tool only if the user asked for it)
    if nombre in retiradas:
        cierra(Decision("tool_allowlist", "tool", "block", "herramienta_retirada"))
        return out
    if nombre not in permitidas:
        cierra(Decision("tool_allowlist", "tool", "block", "herramienta_desconocida"))
        return out
    base = nombre_base(nombre)
    if base in CONSECUENTES and not R.pide_proponer(peticion):
        cierra(Decision("tool_allowlist", "tool", "block", "propuesta_sin_pedido"))
        return out
    out.append(permitir("tool_allowlist", "tool"))
    # 2. argument schema
    if nombre in validadores and _revisar_esquema(validadores[nombre], args):
        out.append(Decision("tool_esquema", "tool", "block", "argumentos_invalidos"))
        return out
    out.append(permitir("tool_esquema", "tool"))
    # 3. SQL
    if base in TOOLS_CON_SQL:
        motivo = _motivo_sql(str(args.get("sql", "")))
        if motivo:
            out.append(Decision("tool_sql", "tool", "block", motivo))
            return out
    out.append(permitir("tool_sql", "tool"))
    # 4. the token: subject and tenant as the system knows them, then scopes, tables, columns, schema
    for clave, valor in args.items():
        if clave.lower() in CLAVES_DE_SUJETO and str(valor) not in (alcance.usuario, alcance.tenant):
            out.append(Decision("tool_alcance_token", "tool", "block", "sujeto_distinto"))
            return out
    requeridos, ajeno = _scopes_de_llamada(base, args)
    if ajeno:
        out.append(Decision("tool_alcance_token", "tool", "block", ajeno))
    elif requeridos - alcance.scopes:
        out.append(Decision("tool_alcance_token", "tool", "block", "scope_insuficiente"))
    else:
        out.append(permitir("tool_alcance_token", "tool"))
    return out


# ---------- output ----------

def _cadenas_de_respuesta(final: dict):
    """(setter, text) of every free-text field the user will read. The SQL of a result is the model's query, not an answer."""
    for campo in ("respuesta", "pregunta_aclaracion"):
        if isinstance(final.get(campo), str):
            yield final, campo
    for campo in ("supuestos", "evidencia"):
        lista = final.get(campo) or []
        for i, x in enumerate(lista):
            if isinstance(x, str):
                yield lista, i
    for r in final.get("resultados") or []:
        if isinstance(r.get("valor"), str):
            yield r, "valor"
        elif isinstance(r.get("valor"), list):
            for i, x in enumerate(r["valor"]):
                if isinstance(x, str):
                    yield r["valor"], i


def _cifras_de_respuesta(final: dict) -> tuple[list[float], list[float]]:
    """(every figure the answer states, those of them that are quantities and not the digits of a code)."""
    todas, cantidades = R.cifras(final.get("respuesta", "")), R.cifras(final.get("respuesta", ""), identificadores=False)
    for r in final.get("resultados") or []:
        todas += R.numeros_de_valor(r.get("valor"))
        cantidades += R.numeros_de_valor(r.get("valor"), identificadores=False)
    return todas, cantidades


def texto_de_rechazo(motivo: str, idioma: str) -> str:
    """The refusal the user reads. Fixed text with the reason as a word: no request, no figure, no tool result."""
    if idioma == "es":
        return (f"No puedo dar esta respuesta ({motivo}): las cifras no coinciden con lo que devolvieron las herramientas o no hay "
                f"ninguna consulta detrás. Reformula la pregunta o pide que se revise la consulta.")
    return (f"I cannot give this answer ({motivo}): the figures do not match what the tools returned, or no query backs them. "
            f"Rephrase the question or ask for the query to be reviewed.")


def texto_de_rechazo_de_entrada(motivo: str, idioma: str) -> str:
    if idioma == "es":
        return (f"No puedo atender esta petición ({motivo}): esta herramienta solo consulta datos dentro de tu alcance; no escribe, no "
                f"aprueba, no cambia permisos y no sigue instrucciones que cambien las mías.")
    return (f"I cannot handle this request ({motivo}): this tool only reads data within your scope; it does not write, approve, change "
            f"permissions or follow instructions that change mine.")


MODOS_FUNDAMENTACION = ("rechazar", "auditar")


def revisar_respuesta(final: dict | None, *, conocidas: R.Conocidas, herramientas_ok: int, idioma: str = "es",
                      fundamentacion: str = "rechazar") -> tuple[dict | None, list[Decision]]:
    """The answer after the three output guardrails. Personal values are REDACTED in place (the answer survives without them); an
    answer with an ungrounded figure or with no tool result behind it is REFUSED and replaced by the fixed refusal.
    Only `respondida` answers are held to evidence: a clarification question or an abstention states no figure of the data.

    `fundamentacion="auditar"` keeps the figure check but does not refuse: an ungrounded figure becomes an `allow` decision whose reason is
    `cifra_sin_fundamento` (an observation). It is the shipped mode: in the paid evaluation the refusing mode flagged 3 of the 84 benign
    tasks, over the limit written before it, so it was rejected as an enforcing guardrail (`resultados/guardrails.md`)."""
    if fundamentacion not in MODOS_FUNDAMENTACION:
        raise ValueError(f"fundamentacion must be one of {MODOS_FUNDAMENTACION}")
    if final is None:
        return final, []
    final = {**final, "resultados": [dict(r) for r in final.get("resultados") or []],
             "supuestos": list(final.get("supuestos") or []), "evidencia": list(final.get("evidencia") or [])}
    decisiones: list[Decision] = []
    # personal values: everything the user will read
    categorias: list[str] = []
    for contenedor, clave in list(_cadenas_de_respuesta(final)):
        nuevo, cats = R.retirar_personales(contenedor[clave], idioma)
        if cats:
            contenedor[clave] = nuevo
            categorias += [c for c in cats if c not in categorias]
    decisiones.append(Decision("salida_personales", "output", "redact", categorias[0]) if categorias
                      else permitir("salida_personales", "output"))
    if final.get("estado") != "respondida":
        return final, decisiones
    # evidence: a tool result behind the answer
    if herramientas_ok == 0:
        decisiones.append(Decision("salida_sin_evidencia", "output", "refuse", "sin_evidencia"))
        return rechazar("sin_evidencia", idioma), decisiones
    decisiones.append(permitir("salida_sin_evidencia", "output"))
    # figures: each one in a tool result or in the task
    todas, cantidades = _cifras_de_respuesta(final)
    if conocidas.sin_fundamento(todas, cantidades):
        if fundamentacion == "auditar":
            decisiones.append(Decision("salida_fundamentacion", "output", "allow", "cifra_sin_fundamento"))
            return final, decisiones
        decisiones.append(Decision("salida_fundamentacion", "output", "refuse", "cifra_sin_fundamento"))
        return rechazar("cifra_sin_fundamento", idioma), decisiones
    decisiones.append(permitir("salida_fundamentacion", "output"))
    return final, decisiones


def rechazar(motivo: str, idioma: str) -> dict:
    return {"estado": "abstenida", "respuesta": texto_de_rechazo(motivo, idioma), "resultados": [], "evidencia": [], "supuestos": [],
            "pregunta_aclaracion": None}


def error_de_herramienta(d: Decision, idioma: str) -> dict:
    """What the model gets back instead of a tool result when a guardrail blocks the call: a tool error in the shape of week 13's."""
    if idioma == "es":
        mensaje = f"Bloqueado por el guardrail {d.guardrail}: {d.motivo}."
        sugerencia = "Esta acción no está permitida. Reformula como una consulta de lectura dentro de tu alcance o responde con lo que ya tienes."
    else:
        mensaje = f"Blocked by the guardrail {d.guardrail}: {d.motivo}."
        sugerencia = "This action is not allowed. Rephrase it as a read within your scope, or answer with what you already have."
    return {"ok": False, "error": {"tipo": "guardrail", "mensaje": mensaje, "sugerencia": sugerencia}}
