"""Week 19, activity 6: the agent's span exporter (CloudWatch Logs for now; X-Ray comes in week 20).

Each finished span is checked against the LOCKED shape of week 17 (semana-17/instrumentacion/esquema.py, activity 3):
attributes that are not in the shape, or whose value does not validate, are DROPPED and counted, never exported.
In tests (`ESTRICTO`) the same violation raises, so a new attribute cannot appear without being declared first.

Output: one JSON line per span on the sink (in Lambda, stdout goes to CloudWatch Logs). No lists of text, no free text.

Week 20, activity 2: the agent span's line may also carry the query's EMF members (agente/metricas.py) at its top
level, beside the span's own keys and never in place of them. The span's attributes are checked as before.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "semana-17"))
from instrumentacion import esquema  # noqa: E402

OMITIDOS: Counter = Counter()


def _limpio(span: dict) -> tuple[dict, list[str]]:
    """Keeps the attributes the locked shape accepts for the span's kind; returns (kept, dropped keys)."""
    tipo = span["tipo"]
    if tipo not in esquema.ATRIBUTOS:
        raise esquema.ErrorEsquema(f"tipo de span desconocido: {tipo!r}")
    malas = esquema.violaciones({"name": span["name"], "attrs": span["attrs"]}, tipo)
    if malas and esquema.ESTRICTO:
        raise esquema.ErrorEsquema("; ".join(malas))
    claves_malas = {m.split(": ", 1)[1].split("=", 1)[0] for m in malas}
    kept = {k: v for k, v in span["attrs"].items() if k not in claves_malas}
    for k in claves_malas:
        OMITIDOS[f"{tipo}:{k}"] += 1
    return kept, sorted(claves_malas)


class ExportadorSpans:
    def __init__(self, escribir: Callable[[str], None] = None):
        self.escribir = escribir or (lambda linea: print(linea, flush=True))
        self.exportados = 0

    def exportar(self, spans: list[dict], emf: dict | None = None, extra: dict | None = None) -> int:
        """spans: [{"name", "tipo", "attrs"}]. `emf`: the EMF members of the invoke_agent line (or None). `extra`:
        other top-level fields of that line, outside the locked attributes (week 20, activity 3: each model call's
        duration, `duracion_pasos_ms`). Returns how many were written."""
        for span in spans:
            kept, dropped = _limpio(span)
            linea = {"schema": esquema.SCHEMA_VERSION, "span": span["name"], "tipo": span["tipo"],
                     "attrs": kept, "omitidos": dropped}
            if emf and span["tipo"] == "invoke_agent":
                choque = set(emf) & set(linea)
                if choque:
                    raise ValueError(f"EMF no puede reemplazar claves del span: {sorted(choque)}")
                linea.update(emf)
            if extra and span["tipo"] == "invoke_agent":
                choque = set(extra) & set(linea)
                if choque:
                    raise ValueError(f"extra no puede reemplazar claves del span: {sorted(choque)}")
                linea.update(extra)
            self.escribir(json.dumps(linea, ensure_ascii=False, sort_keys=True))
            self.exportados += 1
        return len(spans)
