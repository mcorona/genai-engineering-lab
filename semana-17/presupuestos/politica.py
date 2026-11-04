"""Week 17, activity 4: the budget policy, as one pure function.

Three scopes, each with a USD limit and a token limit (input plus output, the loop's own definition):

* `task`        one `resolver` call; kept in memory by the agent;
* `session`     a conversation (several tasks of one user); kept in the store;
* `tenant_day`  one tenant, one UTC day; kept in the store.

Before every model call `decidir` gets the upper estimate of the prompt and what is left in each scope, and answers:

* `allow`   with the `max_tokens` the call is sent with: the largest output the tightest scope can still pay for, never above
            the loop's own output limit. The output of the call therefore cannot cost more than the budget allowed;
* `degrade` the same, on the cheaper model the policy names for this one, because the current model's call does not fit but the
            cheaper one's does (or, if `umbral_degradar` is set, because that fraction of the task budget is already spent);
* `stop`    nothing fits: the agent ends the task with a partial answer that names the scope and the limit. It never retries
            with a smaller prompt, a later time or another model that the policy does not name.

The function has no clock, no store and no model: the live agent, the offline replay of week 13 and the tests all call this one.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .estimacion import precio

ALCANCES = ("task", "session", "tenant_day")


@dataclass(frozen=True)
class Limite:
    usd: float
    tokens: int


@dataclass(frozen=True)
class Gasto:
    usd: float = 0.0
    tokens: int = 0


@dataclass(frozen=True)
class Politica:
    tarea: Limite
    sesion: Limite | None = None
    tenant_dia: Limite | None = None
    min_salida: int = 1300                  # a call is not made if the budget cannot pay for at least this many output tokens
    max_salida: int = 4000                  # the loop's own `max_tokens_salida`
    degradar: dict = field(default_factory=dict)          # model -> cheaper model
    umbral_degradar: float | None = None    # fraction of the task USD budget after which the cheaper model is used first

    @classmethod
    def desde_archivo(cls, ruta=None, **cambios) -> "Politica":
        """The calibrated policy (`politica_calibrada.json`, written by `calibracion.py`); `cambios` override fields."""
        ruta = ruta or Path(__file__).with_name("politica_calibrada.json")
        return cls.desde_archivo_dict(json.loads(Path(ruta).read_text(encoding="utf-8")), **cambios)

    @classmethod
    def desde_archivo_dict(cls, d: dict, **cambios) -> "Politica":
        lim = lambda x: Limite(x["usd"], x["tokens"]) if x else None   # noqa: E731
        base = dict(tarea=lim(d["tarea"]), sesion=lim(d.get("sesion")), tenant_dia=lim(d.get("tenant_dia")),
                    min_salida=d["min_salida"], max_salida=d["max_salida"])
        return cls(**{**base, **cambios})

    def limites(self) -> dict[str, Limite]:
        return {a: l for a, l in (("task", self.tarea), ("session", self.sesion), ("tenant_day", self.tenant_dia)) if l}


@dataclass(frozen=True)
class Decision:
    accion: str                  # allow | degrade | stop
    alcance: str                 # the scope that limits the call (the tightest one) or that stopped it
    motivo: str                  # ok | degradado | usd | tokens
    modelo: str                  # model the call is made with (the current one on stop)
    modelo_origen: str | None    # the model it was degraded from
    max_tokens: int              # 0 on stop
    estimado_entrada: int
    estimado_usd: float          # upper cost of THIS call: estimated prompt plus `max_tokens` of output
    estimado_tokens: int
    restante_usd: float          # what the limiting scope had left before the call
    restante_tokens: int


def _holgura(modelo: str, est_in: int, restante: dict[str, Gasto]) -> tuple[int, str, str, float, int]:
    """Largest output (tokens) the tightest scope still pays for with `modelo`, which scope and which dimension limit it."""
    p_in, p_out = precio(modelo, est_in)
    mejor = (math.inf, "", "", 0.0, 0)
    for alcance, rest in restante.items():
        por_usd = (rest.usd - est_in * p_in / 1e6) / (p_out / 1e6)
        por_tokens = rest.tokens - est_in
        sal, dim = (por_usd, "usd") if por_usd <= por_tokens else (por_tokens, "tokens")
        if sal < mejor[0]:
            mejor = (sal, alcance, dim, rest.usd, rest.tokens)
    sal = -1 if mejor[0] == math.inf else math.floor(mejor[0])
    return sal, mejor[1], mejor[2], mejor[3], mejor[4]


def decidir(pol: Politica, modelo: str, est_in: int, restante: dict[str, Gasto], gastado_tarea: Gasto = Gasto()) -> Decision:
    """`restante` is what each active scope has left (spent and reserved already taken out). `est_in` is the upper estimate
    of this call's prompt in tokens."""
    candidatos = [modelo]
    barato = pol.degradar.get(modelo)
    if barato:
        usado = pol.umbral_degradar is not None and gastado_tarea.usd >= pol.umbral_degradar * pol.tarea.usd
        candidatos = [barato] if usado else [modelo, barato]
    ultimo = None
    for m in candidatos:
        sal, alcance, dim, rest_usd, rest_tok = _holgura(m, est_in, restante)
        ultimo = (sal, alcance, dim, rest_usd, rest_tok)
        if sal >= pol.min_salida:
            maximo = min(sal, pol.max_salida)
            p_in, p_out = precio(m, est_in)
            degradado = m != modelo
            return Decision("degrade" if degradado else "allow", alcance, "degradado" if degradado else "ok", m,
                            modelo if degradado else None, maximo, est_in, (est_in * p_in + maximo * p_out) / 1e6,
                            est_in + maximo, rest_usd, rest_tok)
    sal, alcance, dim, rest_usd, rest_tok = ultimo
    p_in, p_out = precio(candidatos[-1], est_in)
    return Decision("stop", alcance, dim, modelo, None, 0, est_in, (est_in * p_in + pol.min_salida * p_out) / 1e6,
                    est_in + pol.min_salida, rest_usd, rest_tok)
