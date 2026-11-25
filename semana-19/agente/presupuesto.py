"""Week 19, activity 6: the week 17 budget policy applied to the agent's model calls.

The loop (semana-13) is reused as it is. This wrapper sits around its `api`: before each model call it asks the
week 17 policy `decidir` whether the call fits in what is left of the task budget. When it does not, the wrapper
answers with an empty, max_tokens-shaped response, so the loop ends with `limite_alcanzado`; the Lambda then reports
the motive of the week 17 policy (`presupuesto_usd` or `presupuesto_tokens`), never a 500.

The prompt estimate is the characters of the request divided by 3 (an upper estimate for Spanish and English text).
Costs come from the price table the caller passes in (USD per million tokens), not from the loop.

Week 20, activity 3: with a cache point, Converse's `inputTokens` counts only the uncached input; the tokens read
from and written to the cache come apart, at 0.1x and 1.25x the input price. The loop prices `input_tokens` and
`output_tokens` only, so the cache's cost is kept here (`costo_cache`) and the budget counts it, in USD and tokens.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "semana-17"))
from presupuestos.politica import Gasto, Politica, decidir  # noqa: E402


@dataclass
class Precios:
    entrada_1m: float
    salida_1m: float
    cache_lectura_1m: float | None = None      # None: Anthropic's ratios, 0.1x input to read
    cache_escritura_1m: float | None = None    # None: 1.25x input to write (the 5-minute TTL)

    def __post_init__(self):
        if self.cache_lectura_1m is None:
            self.cache_lectura_1m = round(0.1 * self.entrada_1m, 6)
        if self.cache_escritura_1m is None:
            self.cache_escritura_1m = round(1.25 * self.entrada_1m, 6)

    def usd(self, tin: int, tout: int) -> float:
        return tin * self.entrada_1m / 1e6 + tout * self.salida_1m / 1e6

    def usd_cache(self, lectura: int, escritura: int) -> float:
        return lectura * self.cache_lectura_1m / 1e6 + escritura * self.cache_escritura_1m / 1e6

    def tokens_equivalentes(self, lectura: int, escritura: int) -> int:
        """Cache tokens as the input tokens of the same price."""
        if not self.entrada_1m:
            return lectura + escritura
        return round((lectura * self.cache_lectura_1m + escritura * self.cache_escritura_1m) / self.entrada_1m)

    def estimar_entrada(self, est_in: int, cacheado: int) -> int:
        """The next call's prompt estimate when `cacheado` of it is expected to be read from the cache."""
        leido = min(max(cacheado, 0), est_in)
        return est_in - leido + self.tokens_equivalentes(leido, 0)


class Presupuesto:
    """Spent so far in the task and the motive of the last stop (None while the budget holds)."""

    def __init__(self, politica: Politica, modelo: str, precios: Precios):
        self.pol, self.modelo, self.precios = politica, modelo, precios
        self.gastado = Gasto()
        self.motivo: str | None = None
        self.llamadas = 0
        self.cache_lectura = 0      # activity 8: Converse's cache tokens, summed over the task (0 without a cachePoint)
        self.cache_escritura = 0
        self.costo_cache = 0.0      # activity 3: USD of those cache tokens (the loop's cost leaves them out)
        self._cacheado = 0          # the prefix the last call read or wrote: the next one should read it
        self.por_llamada: list[dict] = []   # activity 3: each model call's tokens, cost and duration (chat spans)

    def _restante(self) -> dict[str, Gasto]:
        return {"tarea": Gasto(usd=self.pol.tarea.usd - self.gastado.usd,
                               tokens=self.pol.tarea.tokens - self.gastado.tokens)}

    def envolver(self, api: Callable[[dict], dict]) -> Callable[[dict], dict]:
        def con_presupuesto(cuerpo: dict) -> dict:
            est_in = self.precios.estimar_entrada(len(json.dumps(cuerpo, ensure_ascii=False, default=str)) // 3,
                                                  self._cacheado)
            d = decidir(self.pol, self.modelo, est_in, self._restante(), self.gastado)
            if d.accion == "stop":
                self.motivo = f"presupuesto_{d.motivo}"
                return {"content": [], "stop_reason": "max_tokens", "usage": {"input_tokens": 0, "output_tokens": 0}}
            cuerpo = dict(cuerpo, max_tokens=d.max_tokens)
            t0 = time.monotonic()
            resp = api(cuerpo)
            ms = round((time.monotonic() - t0) * 1000, 1)
            self.llamadas += 1
            uso = resp.get("usage", {})
            tin, tout = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
            lectura = int(uso.get("cache_read_input_tokens") or 0)
            escritura = int(uso.get("cache_creation_input_tokens") or 0)
            self.cache_lectura += lectura
            self.cache_escritura += escritura
            self._cacheado = lectura + escritura
            cache_usd = self.precios.usd_cache(lectura, escritura)
            self.costo_cache += cache_usd
            self.gastado = Gasto(usd=self.gastado.usd + self.precios.usd(tin, tout) + cache_usd,
                                 tokens=self.gastado.tokens + tin + tout
                                 + self.precios.tokens_equivalentes(lectura, escritura))
            self.por_llamada.append({"paso": self.llamadas, "entrada": tin, "salida": tout, "lectura": lectura,
                                     "escritura": escritura, "usd": self.precios.usd(tin, tout) + cache_usd, "ms": ms})
            return resp
        return con_presupuesto
