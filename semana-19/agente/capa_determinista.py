"""Week 19, activity 6: the deterministic layer of the agent, the week 17 core applied in three places:

  1. input: the request (injection, out of scope) BEFORE any model call; a block answers `abstenida`, no model call;
  2. tool: each tool call (allowlist, argument schema, SQL guard, scopes from the token) BEFORE the tool runs; a block
     returns a week 13 style tool error to the model;
  3. output: the final answer (personal values redacted, ungrounded figures) AFTER the loop, in audit mode (shipped mode of
     week 17: an ungrounded figure is recorded as an observation, not refused).

Every decision is returned to the caller, so the Lambda can write it as a span event (gen_ai.guardrail.decision).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
S17 = RAIZ / "semana-17"
S13 = RAIZ / "semana-13"


def _es_herramientas(nombre: str) -> bool:
    return nombre == "herramientas" or nombre.startswith("herramientas.")


def _cargar_nucleo():
    """Loads week 17's core as `guardrails17`. The core imports week 13's package `herramientas`, which has the same name as
    this lab's own `herramientas` package: week 13's is loaded and then removed from sys.modules, so both can coexist.
    The core keeps references to the objects it imported, so removing the names afterwards is safe."""
    if "guardrails17" in sys.modules:
        return sys.modules["guardrails17"]
    guardados = {k: v for k, v in sys.modules.items() if _es_herramientas(k)}
    for k in guardados:
        del sys.modules[k]
    sys.path.insert(0, str(S17))
    sys.path.insert(0, str(S13))
    try:
        spec = importlib.util.spec_from_file_location("guardrails17", S17 / "guardrails" / "nucleo.py")
        modulo = importlib.util.module_from_spec(spec)
        sys.modules["guardrails17"] = modulo
        spec.loader.exec_module(modulo)
    finally:
        catalogo13 = sys.modules.get("herramientas")
        global DEFINICIONES_SEMANA13
        DEFINICIONES_SEMANA13 = list(catalogo13.definiciones()) if catalogo13 is not None else []
        # week 17's guardrails package adds week 13 to sys.path itself: remove every copy, so `herramientas` is ours again
        sys.path[:] = [q for q in sys.path if q != str(S13)]
        for k in [k for k in sys.modules if _es_herramientas(k)]:
            del sys.modules[k]
        sys.modules.update(guardados)
    return modulo


DEFINICIONES_SEMANA13: list = []
N = _cargar_nucleo()

# Activity 8: the same catalog as the tools Lambda (herramientas/contrato.py); the eval found the two week 13 read tools
# missing while the system prompt asked for them.
HERRAMIENTAS = ("describir_esquema", "buscar_regla_negocio", "muestrear_valores", "ejecutar_sql", "proponer_orden_compra")

# Week 19's contract for the proposal: week 13's fields plus the CEDIS and the required date, which the policy
# (semana-08/corpus/ordenes_de_compra.md, "Datos obligatorios") and the database (po_require_delivery) require. The
# requester is not a field: the agent Lambda adds the token's subject (agente/handler.py). The tools Lambda and the
# writer check the same contract (agente/escritor_orden.validar_propuesta).
DEFINICION_PROPONER = {
    "name": "proponer_orden_compra",
    "description": (
        "Register a purchase order PROPOSAL for human approval. It never creates, approves or executes an order: a person "
        "with the authorization level of the amount must approve it. Only for users with the purchasing role. Every field "
        "is required: if the user did not give the delivery CEDIS or the required date, ask for them (pregunta_aclaracion) "
        "instead of choosing one. cedis is legado.almmst.alm_id (look it up with ejecutar_sql when the user names a city "
        "or a CEDIS by name)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "sku": {"type": "string", "pattern": r"^SKU-\d{4}$", "description": "Item code, e.g. SKU-0009."},
            "cantidad": {"type": "integer", "minimum": 1, "maximum": 100000},
            "motivo": {"type": "string", "minLength": 1, "maxLength": 200,
                       "description": "Reason: reorden automático, compra urgente o proyecto especial, with a short note."},
            "cedis": {"type": "integer", "minimum": 1, "description": "Delivery CEDIS: legado.almmst.alm_id."},
            "fecha_requerida": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$",
                                "description": "Required date, AAAA-MM-DD, as the user gave it."},
        },
        "required": ["sku", "cantidad", "motivo", "cedis", "fecha_requerida"],
        "additionalProperties": False,
    },
}


def definiciones_semana19() -> list[dict]:
    """The agent's tools: week 13's catalog for the read tools, week 19's contract for the proposal."""
    defs = [d for d in DEFINICIONES_SEMANA13 if d["name"] in HERRAMIENTAS and d["name"] != DEFINICION_PROPONER["name"]]
    return [*defs, DEFINICION_PROPONER]


def revisar_entrada(texto: str) -> tuple[str | None, list]:
    """(motive of the first block or None, decisions). A block means: do not call the model."""
    decisiones = N.revisar_peticion(texto)
    bloqueo = next((d for d in decisiones if not d.permite), None)
    return (bloqueo.motivo if bloqueo else None), decisiones


def revisar_herramienta(nombre: str, args: dict, *, alcance, peticion: str, definiciones: list, idioma: str = "es"):
    """(error dict for the model or None, decisions). The call does NOT run when the first element is not None."""
    if nombre not in HERRAMIENTAS:
        return {"ok": False, "error": {"tipo": "herramienta_desconocida", "mensaje": nombre}}, []
    permitidas = {d["name"] for d in definiciones}
    decisiones = N.revisar_llamada(nombre, args, permitidas=permitidas, retiradas=set(), validadores=N._validadores(definiciones),
                                   peticion=peticion, alcance=alcance)
    bloqueo = next((d for d in decisiones if not d.permite), None)
    if bloqueo is None:
        return None, decisiones
    return N.error_de_herramienta(bloqueo, idioma), decisiones


def revisar_resultado(res: dict, idioma: str = "es") -> tuple[dict, list]:
    """(the result the model sees, decisions). Week 17's sanitizer: instruction-like sentences in a tool result are
    replaced by a marker, the structure is kept (H13, activity 9: the AWS port did not call it)."""
    limpio, decision = N.revisar_resultado(res, idioma)
    return limpio, [decision]


def revisar_final(final: dict | None, *, conocidas, herramientas_ok: int, idioma: str = "es"):
    """(final answer after redaction, decisions). Audit mode of week 17 for figures (shipped mode)."""
    return N.revisar_respuesta(final, conocidas=conocidas, herramientas_ok=herramientas_ok, idioma=idioma,
                               fundamentacion="auditar")


def conocidas_de(tarea: str):
    return N.R.Conocidas(tarea)
