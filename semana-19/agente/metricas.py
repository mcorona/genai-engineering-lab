"""Week 20, activity 2: the per-query CloudWatch metrics, in Embedded Metric Format (EMF), on the agent span's line.

The agent span (`invoke_agent`, week 17's locked shape) already carries the query's tokens, steps, cost and outcome.
This module turns them into EMF members of THE SAME log line: the `_aws` block, the dimensions and one number per
metric, at the line's top level (EMF does not read nested members). CloudWatch Logs extracts the metrics from the
spans log group; the Lambda makes no extra API call (PutLogEvents needs no header for EMF: CloudWatch guide,
CloudWatch_Embedded_Metric_Format_Generation_PutLogEvents).

The metric count is fixed here: each metric name times each combination of dimension values is one custom metric
(0.30 USD per metric-month beyond the 10 free, prorated by the hour; resultados/linea_base.md, section 4.7).
`metricas_posibles()` counts them and a test holds the count at the free tier.

The written list of dimensions is DIMENSIONES. The plan named three (route, model, language); language is out:
the agent never receives the question's language (the API takes only the text, and the span's `lab.task.language`
is a fixed "es"), so a language dimension would put every English task under "es". It comes back when the API
carries the language.

Week 20, activity 4 (ADR 0015, section 7): the router serves one query with up to three models, so a query has no
single model and the Modelo dimension is gone (the model of each call is on its chat span). Two directives on the
line: the 6 metrics of POR_CONSULTA with no dimension (an empty DimensionSet: "A DimensionSet MAY be empty", EMF
specification, read 2026-11-27), and CostoUSD and Respondida, the two that compare the routes, by Ruta ("fija" or
"r1"). 6 + 2 x 2 = 10 custom metrics, the free tier.
"""
from __future__ import annotations

import math

ESPACIO = "LegacyBridge"

# Dimension -> the values the code can emit. Ruta: "fija" without the router, "r1" with it (activity 4).
DIMENSIONES: dict[str, tuple[str, ...]] = {
    "Ruta": ("fija", "r1"),
}

# Metric -> (CloudWatch unit, where its value comes from). The agent span's attribute, or a value of the query.
METRICAS: dict[str, tuple[str, str]] = {
    "CostoUSD": ("None", "lab.run.cost_usd"),
    "TokensEntrada": ("Count", "lab.run.tokens.input"),
    "TokensSalida": ("Count", "lab.run.tokens.output"),
    "TokensCacheLectura": ("Count", "lab.run.tokens.cache_read"),
    "TokensCacheEscritura": ("Count", "lab.run.tokens.cache_creation"),
    "Pasos": ("Count", "lab.run.steps"),
    "LatenciaMs": ("Milliseconds", "latencia_ms"),          # the agent Lambda's own time for the query
    "Respondida": ("Count", "lab.outcome.status"),         # 1 when the outcome is "respondida", else 0
}


# The metrics that go by Ruta; every other one goes without dimensions.
POR_RUTA = ("CostoUSD", "Respondida")
POR_CONSULTA = tuple(n for n in METRICAS if n not in POR_RUTA)


def metricas_posibles() -> int:
    """The custom metrics the code can create: one per metric without dimensions, plus each metric by Ruta times
    the product of the dimension values."""
    return len(POR_CONSULTA) + len(POR_RUTA) * math.prod(len(v) for v in DIMENSIONES.values())


def _valor(nombre: str, atributos: dict, latencia_ms: float) -> float:
    origen = METRICAS[nombre][1]
    if origen == "latencia_ms":
        return round(float(latencia_ms), 1)
    if origen == "lab.outcome.status":
        return 1 if atributos.get(origen) == "respondida" else 0
    # A query stopped before any model call (the input guardrail) has no tokens or cost: it spent 0.
    return atributos.get(origen) or 0


def _directiva(nombres: tuple[str, ...], dimensiones: list[list[str]]) -> dict:
    return {"Namespace": ESPACIO, "Dimensions": dimensiones,
            "Metrics": [{"Name": n, "Unit": METRICAS[n][0]} for n in nombres]}


def miembros_emf(atributos: dict, *, latencia_ms: float, ruta: str, ahora_ms: int) -> dict:
    """The EMF members to add to the agent span's line. A dimension value outside DIMENSIONES is an error, so no
    metric can appear that the count above does not know."""
    dimensiones = {"Ruta": ruta}
    for clave, valor in dimensiones.items():
        if valor not in DIMENSIONES[clave]:
            raise ValueError(f"valor de dimensión no declarado: {clave}={valor!r}")
    return {
        "_aws": {"Timestamp": int(ahora_ms), "CloudWatchMetrics": [
            _directiva(POR_CONSULTA, [[]]), _directiva(POR_RUTA, [list(DIMENSIONES)])]},
        **dimensiones,
        **{n: _valor(n, atributos, latencia_ms) for n in METRICAS},
    }
