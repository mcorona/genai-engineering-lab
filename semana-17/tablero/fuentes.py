"""Week 17, activity 8: the two sources of the dashboard, read-only.

* **Langfuse** (public API): observations per trace (`v2/observations`: type, name, latency, cost, usage, level, the span attributes in
  `metadata`) and scores (`v3/scores`).
* **The OTel backend**, here the Collector's file exporter (`observabilidad/datos/trazas.jsonl`, OTLP JSON): the span EVENTS Langfuse does
  not show (guardrail, budget and HITL decisions) and every `lab.*` attribute.

Also `publicar_exito`: the golden verdict of each run of activity 7 as a `respuesta.ok` score next to its `trayectoria.*` scores.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import uuid
from collections import defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias.correr_eval import LANGFUSE, _auth  # noqa: E402

ARCHIVO = S17 / "observabilidad" / "datos" / "trazas.jsonl"
RESULTADOS = S17 / "resultados"


def _valor(v: dict):
    for k in ("stringValue", "boolValue", "doubleValue"):
        if k in v:
            return v[k]
    if "intValue" in v:
        return int(v["intValue"])
    return None


def _atributos(lista) -> dict:
    return {a["key"]: _valor(a.get("value") or {}) for a in lista or []}


def spans_del_archivo(trazas: set[str] | None = None, archivo: Path = ARCHIVO) -> list[dict]:
    """Every span of the Collector's file (optionally only those of `trazas`), flattened."""
    out = []
    with open(archivo, encoding="utf-8") as f:
        for linea in f:
            for rs in json.loads(linea).get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []):
                    for s in ss.get("spans", []):
                        if trazas is not None and s["traceId"] not in trazas:
                            continue
                        out.append({"trace": s["traceId"], "span": s["spanId"], "parent": s.get("parentSpanId") or None,
                                    "name": s["name"], "inicio": int(s["startTimeUnixNano"]), "fin": int(s["endTimeUnixNano"]),
                                    "estado": (s.get("status") or {}).get("code"), "attrs": _atributos(s.get("attributes")),
                                    "eventos": [{"name": e["name"], "attrs": _atributos(e.get("attributes"))} for e in s.get("events") or []]})
    return out


def por_traza(spans: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        out[s["trace"]].append(s)
    return dict(out)


def observaciones(traza: str) -> list[dict]:
    auth, peticion = _auth()
    out, cursor = [], None
    while True:
        url = f"{LANGFUSE}/api/public/v2/observations?traceId={traza}&fields=core,basic,usage,model,metadata&limit=100"
        codigo, cuerpo = peticion(url + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""), auth)
        if codigo != 200:
            return out
        out += cuerpo.get("data") or []
        cursor = (cuerpo.get("meta") or {}).get("cursor")
        if not cursor or not cuerpo.get("data"):
            return out


def scores(nombre: str) -> dict[str, dict]:
    """Every score with this name, by its id (the lab's ids are derived from (trace, name), see `id_de_score`)."""
    auth, peticion = _auth()
    out, cursor = {}, None
    while True:
        url = f"{LANGFUSE}/api/public/v3/scores?name={urllib.parse.quote(nombre)}&limit=100"
        codigo, cuerpo = peticion(url + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""), auth)
        if codigo != 200:
            return out
        for d in cuerpo.get("data") or []:
            out[d["id"]] = d
        cursor = (cuerpo.get("meta") or {}).get("cursor")
        if not cursor or not cuerpo.get("data"):
            return out


def id_de_score(traza: str, nombre: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{traza}/{nombre}"))


def publicar_exito(informes=("trayectorias_reproduccion.json", "trayectorias_real.json")) -> dict:
    """`respuesta.ok` (week 13's execution-based check of the answer) on each scored trace of activity 7. Idempotent."""
    auth, peticion = _auth()
    escritos = errores = 0
    for nombre in informes:
        for f in json.loads((RESULTADOS / nombre).read_text(encoding="utf-8"))["por_tarea"]:
            c, _ = peticion(f"{LANGFUSE}/api/public/scores", auth, {
                "id": id_de_score(f["traza"], "respuesta.ok"), "traceId": f["traza"], "name": "respuesta.ok",
                "value": 1 if f["exito"] else 0, "dataType": "BOOLEAN", "source": "API"})
            escritos += c in (200, 201)
            errores += c not in (200, 201)
    return {"escritos": escritos, "errores": errores}


if __name__ == "__main__":
    print(publicar_exito())
