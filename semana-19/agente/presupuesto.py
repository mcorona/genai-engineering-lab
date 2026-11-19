"""Week 19, activity 6: the week 17 budget policy applied to the agent's model calls.

The loop (semana-13) is reused as it is. This wrapper sits around its `api`: before each model call it asks the
week 17 policy `decidir` whether the call fits in what is left of the task budget. When it does not, the wrapper
answers with an empty, max_tokens-shaped response, so the loop ends with `limite_alcanzado`; the Lambda then reports
the motive of the week 17 policy (`presupuesto_usd` or `presupuesto_tokens`), never a 500.

The prompt estimate is the characters of the request divided by 3 (an upper estimate for Spanish and English text).
Costs come from the price table the caller passes in (USD per million tokens), not from the loop.
"""
from __future__ import annotations

import json
import sys
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

    def usd(self, tin: int, tout: int) -> float:
        return tin * self.entrada_1m / 1e6 + tout * self.salida_1m / 1e6


class Presupuesto:
    """Spent so far in the task and the motive of the last stop (None while the budget holds)."""

    def __init__(self, politica: Politica, modelo: str, precios: Precios):
        self.pol, self.modelo, self.precios = politica, modelo, precios
        self.gastado = Gasto()
        self.motivo: str | None = None
        self.llamadas = 0
        self.cache_lectura = 0      # activity 8: Converse's cache tokens, summed over the task (0 without a cachePoint)
        self.cache_escritura = 0

    def _restante(self) -> dict[str, Gasto]:
        return {"tarea": Gasto(usd=self.pol.tarea.usd - self.gastado.usd,
                               tokens=self.pol.tarea.tokens - self.gastado.tokens)}

    def envolver(self, api: Callable[[dict], dict]) -> Callable[[dict], dict]:
        def con_presupuesto(cuerpo: dict) -> dict:
            est_in = len(json.dumps(cuerpo, ensure_ascii=False, default=str)) // 3
            d = decidir(self.pol, self.modelo, est_in, self._restante(), self.gastado)
            if d.accion == "stop":
                self.motivo = f"presupuesto_{d.motivo}"
                return {"content": [], "stop_reason": "max_tokens", "usage": {"input_tokens": 0, "output_tokens": 0}}
            cuerpo = dict(cuerpo, max_tokens=d.max_tokens)
            resp = api(cuerpo)
            self.llamadas += 1
            uso = resp.get("usage", {})
            tin, tout = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
            self.cache_lectura += int(uso.get("cache_read_input_tokens") or 0)
            self.cache_escritura += int(uso.get("cache_creation_input_tokens") or 0)
            self.gastado = Gasto(usd=self.gastado.usd + self.precios.usd(tin, tout),
                                 tokens=self.gastado.tokens + tin + tout)
            return resp
        return con_presupuesto
