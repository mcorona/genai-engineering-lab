"""Week 17, activity 7 (part 1): from a source of tool calls to the abstract `Trayectoria`. Pure: it takes parsed records, reads nothing.

Today there is one source, the week 13 loop's own trace lines (`semana-13/resultados/trazas/*.jsonl`, written by `Agente._traza`): one
`herramienta` line per tool call (`paso` is the model step that issued it, `ok`, `error`, the arguments) and one `modelo` line per model
call. Part 2 adds the sources that matter in production: the `execute_tool` / `chat` spans of the OTLP file and of Langfuse, where the
step is `lab.step`, the status `lab.tool.status` and the arguments only a keyed hash (`lab.tool.args.hmac`). A span adapter only has to
fill the same three fields: tool, ok, turn, and an opaque identifier of the exact arguments.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias.evaluadores import Llamada, Trayectoria  # noqa: E402


def huella_de_argumentos(argumentos) -> str:
    """An opaque identifier of the exact arguments: equal arguments, equal value (canonical JSON, sorted keys)."""
    texto = json.dumps(argumentos if argumentos is not None else {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def por_corrida(lineas) -> dict[str, list[dict]]:
    """Group trace lines by run id, in the order they were written."""
    out: dict[str, list[dict]] = defaultdict(list)
    for linea in lineas:
        if linea.get("corrida"):
            out[linea["corrida"]].append(linea)
    return dict(out)


def desde_traza_del_bucle(lineas_de_una_corrida) -> Trayectoria:
    """The trajectory of one run from its trace lines. Model steps are the `modelo` lines (the parada line's count when there are none).

    Two dialects. The week 13 loop writes `paso` on each tool line and one `modelo` line per model call. The week 13 Agent SDK version
    writes no `paso` and one `modelo` line per assistant MESSAGE, and one API response can arrive as two messages (its text, then its
    tool use): there a `modelo` line that asks for no tool and is followed directly by another `modelo` line is the same model call, and
    the turn of a tool call is the number of model calls before it. (In the loop's dialect two consecutive `modelo` lines are two calls:
    the reminder to call `responder`.)"""
    lineas = list(lineas_de_una_corrida)
    sdk = any(x.get("tipo") == "herramienta" and x.get("paso") is None for x in lineas)
    llamadas, modelos_vistos = [], 0
    for i, x in enumerate(lineas):
        if x.get("tipo") == "modelo":
            siguiente = lineas[i + 1] if i + 1 < len(lineas) else {}
            if sdk and not x.get("herramientas_pedidas") and siguiente.get("tipo") == "modelo":
                continue                                    # the text half of a response whose tool half is the next line
            modelos_vistos += 1
        elif x.get("tipo") == "herramienta":
            turno = int(x["paso"]) if x.get("paso") is not None else max(1, modelos_vistos)
            llamadas.append(Llamada(x["herramienta"], bool(x.get("ok")), turno, huella_de_argumentos(x.get("argumentos")), x.get("error")))
    parada = next((x for x in lineas_de_una_corrida if x.get("tipo") == "parada"), {})
    pasos = modelos_vistos or int(parada.get("pasos") or 0)
    return Trayectoria(tuple(llamadas), max(1, pasos, max((c.turno for c in llamadas), default=1)))
