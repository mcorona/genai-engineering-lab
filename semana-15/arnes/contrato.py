"""Week 15's common contract: the same `Resultado`, prompt, final answer and cost as
week 13, for any framework.

It is imported both in the main environment and in each framework's virtual environment, which have no psycopg or sqlglot:
`semana13()` loads week 13's `agente/loop.py` and `agente/respuesta.py` with an empty stand-in for the
`herramientas` package (the loop only uses it when executing tools in-process). That way the system prompt, the task
message, `RespuestaFinal`, `revisar_final`, `Limites`, `Resultado` and the price table are week 13's objects,
not copies that could diverge.
"""
from __future__ import annotations

import importlib
import json
import math
import sys
import types
from dataclasses import asdict, fields
from functools import lru_cache
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
S13 = S15.parent / "semana-13"
ESTADOS = ("respondida", "requiere_aclaracion", "abstenida", "limite_alcanzado", "error")


@lru_cache(maxsize=1)
def semana13():
    """Week 13's `agente.loop` module (with its `SISTEMA`, `mensaje_tarea`, `revisar_final`, `costo`...)."""
    if str(S13) not in sys.path:
        sys.path.insert(0, str(S13))
    try:
        importlib.import_module("herramientas")
    except Exception:  # noqa: BLE001  a framework's environment: no psycopg/sqlglot
        sustituto = types.ModuleType("herramientas")
        sustituto.Herramientas = object
        sustituto.definiciones = lambda: []
        sys.modules["herramientas"] = sustituto
    return importlib.import_module("agente.loop")


def Resultado(**kw):  # noqa: N802  week 13's dataclass, built with names
    return semana13().Resultado(**{"estado": "error", "final": None, "pasos": 0, "herramientas": 0, "tokens_in": 0,
                                   "tokens_out": 0, "costo_usd": 0.0, "segundos": 0.0, **kw})


def resultado_a_dict(r) -> dict:
    return asdict(r)


def resultado_de_dict(d: dict):
    nombres = {f.name for f in fields(semana13().Resultado)}
    return semana13().Resultado(**{k: v for k, v in d.items() if k in nombres})


# ---------- usage and cost ----------

_CLAVES_ENTRADA = ("input_tokens", "inputTokens", "prompt_tokens", "prompt_token_count")
_CLAVES_SALIDA = ("output_tokens", "outputTokens", "completion_tokens", "candidates_token_count")


def normalizar_uso(uso) -> tuple[int, int]:
    """Tokens (input, output) from any framework's format: Anthropic/LangChain (`input_tokens`),
    Strands/Bedrock (`inputTokens`), OpenAI/LiteLLM (`prompt_tokens`), Gemini/ADK (`prompt_token_count`).
    It accepts dicts or objects with those attributes; anything missing counts as 0. It never adds `total_tokens`."""
    if uso is None:
        return 0, 0
    leer = (lambda k: uso.get(k)) if isinstance(uso, dict) else (lambda k: getattr(uso, k, None))
    tin = next((leer(k) for k in _CLAVES_ENTRADA if leer(k) is not None), 0)
    tout = next((leer(k) for k in _CLAVES_SALIDA if leer(k) is not None), 0)
    if not all(isinstance(x, int) and x >= 0 for x in (tin, tout)):
        raise ValueError(f"uso inválido: {uso!r}")
    return tin, tout


def costo(modelo: str, tin: int, tout: int) -> float:
    """Week 13's price (semana-07/prices.json). The same for every framework: those that report their own cost
    (LiteLLM) are compared against it, not used."""
    return semana13().costo(modelo, tin, tout)


# ---------- contract validation ----------

def validar_resultado(r, tarea: dict | None = None, modelo: str = "claude-haiku-5-5") -> list[str]:
    """Problems of the `Resultado` against the contract (an empty list = valid)."""
    problemas = []
    if r.estado not in ESTADOS:
        problemas.append(f"estado desconocido: {r.estado!r}")
    for campo in ("pasos", "herramientas", "tokens_in", "tokens_out", "errores_herramienta", "turnos_paralelos"):
        v = getattr(r, campo)
        if not (isinstance(v, int) and v >= 0):
            problemas.append(f"{campo} debe ser entero ≥ 0: {v!r}")
    if not (isinstance(r.segundos, (int, float)) and r.segundos >= 0):
        problemas.append(f"segundos inválido: {r.segundos!r}")
    esperado = costo(modelo, r.tokens_in, r.tokens_out) if not problemas else None
    if esperado is not None and not math.isclose(r.costo_usd, esperado, rel_tol=1e-9, abs_tol=1e-12):
        problemas.append(f"costo_usd {r.costo_usd} ≠ costo de sus tokens {esperado}")
    if r.estado in ("respondida", "requiere_aclaracion", "abstenida"):
        if not r.final:
            problemas.append("estado del modelo sin respuesta final")
        else:
            l13 = semana13()
            try:
                final = l13.RespuestaFinal.model_validate(r.final).model_dump()
                if final["estado"] != r.estado:
                    problemas.append("el estado del Resultado no coincide con el de la respuesta final")
                if tarea is not None and (p := l13.revisar_final(final, tarea)):
                    problemas.append(p)
            except Exception as e:  # noqa: BLE001
                problemas.append(f"respuesta final inválida: {e}"[:300])
    elif r.final is not None:
        problemas.append(f"{r.estado} no lleva respuesta final")
    if r.pasos == 0 and r.estado != "error":
        problemas.append("ningún paso del modelo")
    json.dumps(resultado_a_dict(r), default=str)
    return problemas
