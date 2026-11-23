"""Week 20, preparation: `modelo.invocar`, the one place where the agent calls the model.

Week 20 puts prompt caching (activity 3) and model routing (activity 4) behind this seam, so the week 13 loop, the
budgets and the guardrails do not change. Today it is exactly the week 19 path: the loop's body (Anthropic format) is
translated by `converse_adaptador`, sent once to Converse with the pinned guardrail, and translated back. No cache
point, no router.

`llamar` is the real Converse call (`cliente.converse(**req)`) or a fake in tests. Pure: no AWS here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agente.converse_adaptador import peticion_a_converse, respuesta_a_anthropic


@dataclass(frozen=True)
class ConfigModelo:
    """What one model call needs: the inference profile id and the guardrail config (or None)."""
    modelo_id: str
    guardrail: dict | None = None


def invocar(llamar: Callable[[dict], dict], cuerpo: dict, *, config: ConfigModelo) -> dict:
    """One model call: the loop's body in, the loop's response shape out."""
    return respuesta_a_anthropic(llamar(peticion_a_converse(cuerpo, modelo_id=config.modelo_id,
                                                            guardrail=config.guardrail)))


def api(llamar: Callable[[dict], dict], *, config: ConfigModelo) -> Callable[[dict], dict]:
    """The `api=` the week 13 loop receives, bound to `invocar`."""
    return lambda cuerpo: invocar(llamar, cuerpo, config=config)
