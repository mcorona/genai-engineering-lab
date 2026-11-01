"""Contrato común de la semana 15: el mismo `Resultado`, el mismo prompt, la misma respuesta final y el mismo costo que la
semana 13, para cualquier framework.

Se importa tanto en el entorno principal como en el entorno virtual de cada framework, que no tienen psycopg ni sqlglot:
`semana13()` carga `agente/loop.py` y `agente/respuesta.py` de la semana 13 con un sustituto vacío del paquete
`herramientas` (el loop solo lo usa al ejecutar herramientas en proceso). Así el prompt de sistema, el mensaje de la
tarea, `RespuestaFinal`, `revisar_final`, `Limites`, `Resultado` y la tabla de precios son los objetos de la semana 13,
no copias que puedan divergir.
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
    """El módulo `agente.loop` de la semana 13 (con su `SISTEMA`, `mensaje_tarea`, `revisar_final`, `costo`...)."""
    if str(S13) not in sys.path:
        sys.path.insert(0, str(S13))
    try:
        importlib.import_module("herramientas")
    except Exception:  # noqa: BLE001  entorno de un framework: sin psycopg/sqlglot
        sustituto = types.ModuleType("herramientas")
        sustituto.Herramientas = object
        sustituto.definiciones = lambda: []
        sys.modules["herramientas"] = sustituto
    return importlib.import_module("agente.loop")


def Resultado(**kw):  # noqa: N802  el dataclass de la semana 13, construido con nombres
    return semana13().Resultado(**{"estado": "error", "final": None, "pasos": 0, "herramientas": 0, "tokens_in": 0,
                                   "tokens_out": 0, "costo_usd": 0.0, "segundos": 0.0, **kw})


def resultado_a_dict(r) -> dict:
    return asdict(r)


def resultado_de_dict(d: dict):
    nombres = {f.name for f in fields(semana13().Resultado)}
    return semana13().Resultado(**{k: v for k, v in d.items() if k in nombres})


# ---------- uso y costo ----------

_CLAVES_ENTRADA = ("input_tokens", "inputTokens", "prompt_tokens", "prompt_token_count")
_CLAVES_SALIDA = ("output_tokens", "outputTokens", "completion_tokens", "candidates_token_count")


def normalizar_uso(uso) -> tuple[int, int]:
    """Tokens (entrada, salida) desde el formato de cualquier framework: Anthropic/LangChain (`input_tokens`),
    Strands/Bedrock (`inputTokens`), OpenAI/LiteLLM (`prompt_tokens`), Gemini/ADK (`prompt_token_count`).
    Acepta dicts u objetos con esos atributos; lo que falte cuenta 0. Nunca suma `total_tokens`."""
    if uso is None:
        return 0, 0
    leer = (lambda k: uso.get(k)) if isinstance(uso, dict) else (lambda k: getattr(uso, k, None))
    tin = next((leer(k) for k in _CLAVES_ENTRADA if leer(k) is not None), 0)
    tout = next((leer(k) for k in _CLAVES_SALIDA if leer(k) is not None), 0)
    if not all(isinstance(x, int) and x >= 0 for x in (tin, tout)):
        raise ValueError(f"uso inválido: {uso!r}")
    return tin, tout


def costo(modelo: str, tin: int, tout: int) -> float:
    """Precio de la semana 13 (semana-07/prices.json). Igual para todos los frameworks: los que reportan su propio costo
    (LiteLLM) se comparan contra este, no se usan."""
    return semana13().costo(modelo, tin, tout)


# ---------- validación del contrato ----------

def validar_resultado(r, tarea: dict | None = None, modelo: str = "claude-haiku-5-5") -> list[str]:
    """Problemas del `Resultado` frente al contrato (lista vacía = válido)."""
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
