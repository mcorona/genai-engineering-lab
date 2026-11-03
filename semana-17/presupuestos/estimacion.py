"""Week 17, activity 4: what the next model call can cost, at most, before it is made.

The week 16 computer-use loop stops when `spent + upper estimate of the next request > cap`. The same idea here, for the week 13
loop: the next prompt is the previous prompt, plus what the model answered, plus what was appended since (the tool results),
all charged at the full input price (the loop does not use caching, and if a response ever reports cached tokens they are
charged as input too, which is an upper bound). The output side is not estimated: it is *capped*, because the call is sent with
a `max_tokens` that the remaining budget allows, so the output of the call cannot cost more than the cap said.

Text has no tokenizer here, so characters stand in for tokens with a deliberately low divisor (`CHARS_POR_TOKEN`).
`calibracion.py` measures it against the 252 runs of week 13 and `politica_calibrada.json` records the value in use; the paid
evaluation checks, call by call, that the estimate was never below the tokens the API reported.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

S13 = Path(__file__).resolve().parents[2] / "semana-13"
PRECIOS = json.loads((S13.parent / "semana-07" / "prices.json").read_text(encoding="utf-8"))

# Characters per input token used for the upper estimate. The real ratio of the loop's requests is about 2.7 characters per
# token on the first call and between 1.5 and 3 on the content added later (measured, `politica_calibrada.json`); a divisor
# below the real one makes the estimate larger than the truth.
CHARS_POR_TOKEN = 1.5
# Safety factor on the whole estimated prompt, for what characters cannot see (the tokenizer, the ids of the tool calls, the
# wrapper of each result). Without it the estimate was 1.001 times the real prompt at its tightest in the 678 later calls of
# week 13: a bound that tight is not a bound.
MARGEN_ENTRADA = 1.10


def precio(modelo: str, entrada_tokens: int = 0) -> tuple[float, float]:
    """(USD per million input tokens, per million output tokens) for a call whose prompt has `entrada_tokens`.
    Haiku 5.5 charges more above 100,000 prompt tokens; the estimate uses the tier the estimate itself falls in."""
    p = PRECIOS.get(f"anthropic:{modelo}")
    if not p or p.get("in") is None or p.get("out") is None:
        raise KeyError(f"no verified price for {modelo}: the budget cannot be enforced without one")
    umbral = p.get("umbral_prompt_tokens")
    if umbral and entrada_tokens > umbral:
        return p["in_prompt_mas_100k"], p["out_prompt_mas_100k"]
    return p["in"], p["out"]


def costo_real(modelo: str, uso: dict) -> tuple[float, int]:
    """(USD, tokens) of a finished call from its `usage`. Cache tokens count as input; the tier uses the whole prompt."""
    tin = (uso.get("input_tokens") or 0) + (uso.get("cache_creation_input_tokens") or 0) + (uso.get("cache_read_input_tokens") or 0)
    tout = uso.get("output_tokens") or 0
    p_in, p_out = precio(modelo, tin)
    return (tin * p_in + tout * p_out) / 1e6, tin + tout


def tokens_superiores(caracteres: int) -> int:
    return math.ceil(caracteres / CHARS_POR_TOKEN)


def _largo(objeto) -> int:
    return len(json.dumps(objeto, ensure_ascii=False, default=str))


def entrada_inicial(cuerpo: dict) -> int:
    """First call of a task: the whole request body (system, tools, the task)."""
    return math.ceil(MARGEN_ENTRADA * tokens_superiores(_largo({k: v for k, v in cuerpo.items() if k != "model"})))


def entrada_siguiente_caracteres(entrada_previa: int, salida_previa: int, caracteres_nuevos: int) -> int:
    return math.ceil(MARGEN_ENTRADA * (entrada_previa + salida_previa + tokens_superiores(caracteres_nuevos)))


def entrada_siguiente(entrada_previa: int, salida_previa: int, mensaje_nuevo) -> int:
    """Later calls: the previous prompt (all of it, uncached), the previous answer, and the message appended since."""
    return entrada_siguiente_caracteres(entrada_previa, salida_previa, _largo(mensaje_nuevo))
