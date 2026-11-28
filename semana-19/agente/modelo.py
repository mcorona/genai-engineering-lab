"""Week 20, preparation: `modelo.invocar`, the one place where the agent calls the model.

Week 20 puts prompt caching (activity 3) and model routing (activity 4) behind this seam, so the week 13 loop, the
budgets and the guardrails do not change. The loop's body (Anthropic format) is translated by `converse_adaptador`,
sent once to Converse with the pinned guardrail, and translated back. The cache points are placed by the adapter
(`ConfigModelo.cache`, the CACHE_PROMPT value; ADR 0014). With RUTEO=r1 the loop's `api` is the in-house router
instead (agente/ruteo.py, ADR 0015), built by agente/construccion.py; this seam is the RUTEO=off path.

`llamar` is the real Converse call (`cliente.converse(**req)`) or a fake in tests. Pure: no AWS here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agente.converse_adaptador import MODOS_CACHE, TTLS_CACHE, peticion_a_converse, respuesta_a_anthropic


@dataclass(frozen=True)
class ConfigModelo:
    """What one model call needs: the inference profile id, the guardrail config (or None) and the cache mode."""
    modelo_id: str
    guardrail: dict | None = None
    cache: str = "off"
    ttl: str = "5m"

    def __post_init__(self):
        if self.cache not in MODOS_CACHE:
            raise ValueError(f"modo de caché desconocido: {self.cache}")
        if self.ttl not in TTLS_CACHE:
            raise ValueError(f"TTL de caché desconocido: {self.ttl}")


def invocar(llamar: Callable[[dict], dict], cuerpo: dict, *, config: ConfigModelo) -> dict:
    """One model call: the loop's body in, the loop's response shape out."""
    return respuesta_a_anthropic(llamar(peticion_a_converse(cuerpo, modelo_id=config.modelo_id,
                                                            guardrail=config.guardrail, cache=config.cache,
                                                            ttl=config.ttl)))


def api(llamar: Callable[[dict], dict], *, config: ConfigModelo) -> Callable[[dict], dict]:
    """The `api=` the week 13 loop receives, bound to `invocar`."""
    return lambda cuerpo: invocar(llamar, cuerpo, config=config)
