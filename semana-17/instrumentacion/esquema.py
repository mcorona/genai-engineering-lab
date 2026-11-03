"""Week 17, activity 3: the LOCKED span shape of LegacyBridge.

Every attribute the lab itself puts on a span is declared here, with a validator. Nothing else may be written:

* no list-valued attributes (the Collector's `redaction` does not read lists, activity 2 finding 1);
* no free text: strings are identifiers, enumerations or fixed-width hashes, never prompts, SQL, rows, errors or tokens;
* sizes and keyed hashes (HMAC-SHA256, 16 hex) stand in for arguments, SQL text and users.

`fijar()` is the only door. In production an invalid key or value is dropped and counted in `OMITIDOS`; with
`ESTRICTO = True` (tests, `correr.py`) it raises, so a new attribute cannot appear without being added here first.

Spans created by the MCP SDK itself (client `MCP send ...`, server `tools/call ...`) are not written through `fijar()`;
their attribute keys are pinned in `ATRIBUTOS_SDK` (measured with SDK 2.3.0) and checked by the tests.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from collections import Counter

SCHEMA_VERSION = "1"
ESTRICTO = False
OMITIDOS: Counter = Counter()          # "tipo:clave" -> times a value was dropped (production mode)


class ErrorEsquema(ValueError):
    pass


# ---------- pseudonyms and hashes ----------

_SAL_PROCESO = secrets.token_hex(16)


def _sal() -> bytes:
    """Salt of the keyed hashes. `LAB_OBS_SALT` makes them stable across runs and hosts; without it each process draws its
    own (hashes then correlate inside one process only)."""
    return (os.environ.get("LAB_OBS_SALT") or _SAL_PROCESO).encode()


def seudonimo(valor: str) -> str:
    """HMAC-SHA256 of a value with the salt, 16 hex characters. A plain hash of 'analista' or 'SKU-0009' would fall to a
    dictionary; the keyed one does not without the salt."""
    return hmac.new(_sal(), str(valor).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def canonico(argumentos) -> str:
    import json
    return json.dumps(argumentos, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


# ---------- validators ----------

def _patron(rx: str):
    r = re.compile(rx)
    return lambda v: isinstance(v, str) and bool(r.fullmatch(v))


def _enum(*valores):
    conjunto = set(valores)
    return lambda v: isinstance(v, str) and v in conjunto


def _entero(maximo: int = 10**9):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= maximo


def _numero(maximo: float = 10**6):
    return lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= maximo


def _bool(v) -> bool:
    return isinstance(v, bool)


ID = _patron(r"[A-Za-z0-9_.:-]{1,64}")            # identifiers: tool, task, tenant, model, role
HEX16 = _patron(r"[0-9a-f]{16}")                   # pseudonyms and hashes
HEX12 = _patron(r"[0-9a-f]{12}")                   # the agent's run id
LISTA_SCOPES = _patron(r"(legado:[a-z]+(:[a-z]+)?)?( legado:[a-z]+(:[a-z]+)?)*")   # sorted, space separated, fixed vocabulary
COSTO_LANGFUSE = _patron(r'\{"total": [0-9]+(\.[0-9]+)?(e-[0-9]+)?\}')

ESTADOS = ("respondida", "requiere_aclaracion", "abstenida", "limite_alcanzado", "error")
MOTIVOS = ("responder", "max_pasos", "max_tokens_total", "max_segundos", "max_herramientas", "max_tokens_salida",
           "sin_responder", "errores_herramienta", "api_error", "otro")
DECISIONES = ("allow", "deny_no_token", "deny_bad_scheme", "deny_invalid_token", "deny_insufficient_scope")
METODOS_MCP = ("tools/call", "tools/list", "resources/read", "resources/list", "prompts/get", "prompts/list", "other")
FINALIZACIONES = ("end_turn", "tool_use", "max_tokens", "stop_sequence", "pause_turn", "refusal", "other")

# Lab-owned span kinds -> allowed attribute -> validator.
ATRIBUTOS: dict[str, dict] = {
    "invoke_agent": {
        "gen_ai.operation.name": _enum("invoke_agent"),
        "gen_ai.agent.name": ID,
        "gen_ai.request.model": ID,
        "user.id": HEX16,                                  # keyed hash of the token subject (Langfuse reads user.id)
        "lab.tenant.id": ID,
        "lab.task.id": ID,
        "lab.task.language": _enum("es", "en"),
        "lab.run.id": HEX12,
        "lab.schema.version": _enum(SCHEMA_VERSION),
        "lab.model.scripted": _bool,
        "lab.budget.max_steps": _entero(), "lab.budget.max_tool_calls": _entero(),
        "lab.budget.max_tokens_total": _entero(), "lab.budget.max_seconds": _numero(),
        "lab.budget.max_output_tokens": _entero(),
        "lab.outcome.status": _enum(*ESTADOS), "lab.outcome.reason": _enum(*MOTIVOS),
        "lab.run.steps": _entero(), "lab.run.tool_calls": _entero(), "lab.run.tool_errors": _entero(),
        "lab.run.tokens.input": _entero(), "lab.run.tokens.output": _entero(),
        "lab.run.tokens.cache_read": _entero(), "lab.run.tokens.cache_creation": _entero(),
        "lab.run.cost_usd": _numero(),
        "error.type": _enum(*ESTADOS, "other"),
    },
    "chat": {
        "gen_ai.operation.name": _enum("chat"),
        "gen_ai.provider.name": _enum("anthropic"),
        "gen_ai.request.model": ID,
        "gen_ai.request.max_tokens": _entero(),
        "gen_ai.request.reasoning.level": _enum("low", "medium", "high", "max"),
        "gen_ai.response.model": ID,
        "gen_ai.response.id": ID,
        "gen_ai.response.finish_reasons": lambda v: isinstance(v, (list, tuple)) and len(v) <= 1
                                                    and all(x in FINALIZACIONES for x in v),   # fixed vocabulary only
        "gen_ai.usage.input_tokens": _entero(), "gen_ai.usage.output_tokens": _entero(),
        "gen_ai.usage.cache_read.input_tokens": _entero(),
        "gen_ai.usage.cache_creation.input_tokens": _entero(),   # semconv name (util-genai 1.3b0 says cache_write; Langfuse 4.72
                                                                 # reads both, measured, so the semconv one is locked)
        "server.address": _patron(r"[a-z0-9.-]{1,64}"), "server.port": _entero(65535),
        "lab.step": _entero(), "lab.cost.usd": _numero(), "lab.model.scripted": _bool,
        "langfuse.observation.cost_details": COSTO_LANGFUSE,
        "error.type": ID,
    },
    "execute_tool": {
        "gen_ai.operation.name": _enum("execute_tool"),
        "gen_ai.tool.name": ID, "gen_ai.tool.type": _enum("function", "extension", "datastore"),
        "gen_ai.tool.call.id": ID,
        "lab.step": _entero(), "lab.tool.known": _bool,
        "lab.tool.args.chars": _entero(), "lab.tool.args.hmac": HEX16,
        "lab.tool.result.chars": _entero(), "lab.tool.status": _enum("ok", "error"),
        "error.type": ID,
    },
    "autorizacion": {
        "lab.authz.decision": _enum(*DECISIONES),
        "mcp.method.name": _enum(*METODOS_MCP),
        "lab.tool.name": ID,              # NOT gen_ai.tool.name: Langfuse would turn this span into a TOOL observation
        "lab.authz.scopes.required": LISTA_SCOPES, "lab.authz.scopes.granted": LISTA_SCOPES,
        "lab.authz.scopes.missing": LISTA_SCOPES,
        "lab.authz.client": ID,
        "user.id": HEX16,
        "error.type": _enum("invalid_token", "insufficient_scope", "no_token", "bad_scheme"),
    },
    "herramienta_servidor": {
        "lab.tool.name": ID, "lab.tool.known": _bool,       # same reason: gen_ai.tool.name would make it a TOOL
        "lab.tool.args.chars": _entero(), "lab.tool.args.hmac": HEX16,
        "lab.tool.result.chars": _entero(), "lab.tool.status": _enum("ok", "error"),
        "user.id": HEX16,
        "error.type": ID,
    },
    "sql": {
        "db.system.name": _enum("postgresql"), "db.namespace": _enum("legado"),
        "db.operation.name": _enum("SELECT", "EXPLAIN"),
        "db.response.returned_rows": _entero(),
        "lab.db.query.chars": _entero(), "lab.db.query.hmac": HEX16,
        "lab.db.tables": _patron(r"([a-z0-9_]{1,16})?( [a-z0-9_]{1,16})*"),
        "lab.db.role": ID,
        "error.type": ID,
    },
}

# Attribute keys of the spans the MCP SDK 2.3.0 creates, as measured in activity 3 (tests/test_instrumentacion.py pins
# them): the client span `MCP send <method>` carries two, the server span `<method>` five. When a request fails the client
# span adds `error.type` and `rpc.response.status_code` (measured on the 403 of the boundary).
ATRIBUTOS_SDK = {
    "mcp_cliente": {"mcp.method.name", "jsonrpc.request.id", "error.type", "rpc.response.status_code"},
    "mcp_servidor": {"mcp.method.name", "mcp.protocol.version", "jsonrpc.request.id", "gen_ai.operation.name",
                     "gen_ai.tool.name", "error.type"},
}


def claves_permitidas() -> set[str]:
    """Every attribute key of the locked shape (lab-owned and SDK): the allowlist for the Collector's `redaction`
    (`allow_all_keys: false`) once the shape is final (activity 9). Resource keys are added by the caller."""
    claves = {k for tipo in ATRIBUTOS.values() for k in tipo}
    for conjunto in ATRIBUTOS_SDK.values():
        claves |= conjunto
    return claves


def validar(tipo: str, clave: str, valor) -> bool:
    regla = ATRIBUTOS.get(tipo, {}).get(clave)
    return regla is not None and bool(regla(valor))


def fijar(span, tipo: str, atributos: dict) -> None:
    """Writes lab attributes onto a span through the locked shape. `None` values are skipped."""
    for clave, valor in atributos.items():
        if valor is None:
            continue
        if not validar(tipo, clave, valor):
            if ESTRICTO:
                raise ErrorEsquema(f"{tipo}: attribute {clave!r} is not in the locked shape or its value is not valid")
            OMITIDOS[f"{tipo}:{clave}"] += 1
            continue
        span.set_attribute(clave, valor)


def clasificar_motivo(motivo: str) -> str:
    """The agent's free-text stop reason ('api: <message>') to the fixed vocabulary."""
    if motivo.startswith("api:"):
        return "api_error"
    return motivo if motivo in MOTIVOS else "otro"


def tipo_error(tipo) -> str | None:
    """A tool's error type (already an identifier in week 13) in the shape of `ID`, or None."""
    return tipo if isinstance(tipo, str) and ID(tipo) else None


def violaciones(span_resumen: dict, tipo: str) -> list[str]:
    """Check an already finished span (as `resumen_spans` shows it) against the locked shape of a lab-owned kind.
    Keys the util-genai handler or the SDK add on their own are not allowed to hide: they must be listed too."""
    malas = []
    for k, v in span_resumen["attrs"].items():
        if not validar(tipo, k, v):
            malas.append(f"{span_resumen['name']}: {k}={v!r}")
    return malas
