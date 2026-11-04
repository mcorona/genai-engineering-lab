"""Week 17, activity 8: the LegacyBridge dashboard in Langfuse, defined as code ($0).

    cd semana-17 && uv run --group semana17 python -m tablero.langfuse_tablero            # create or replace it (stack up)

Langfuse v4's dashboard API is `/api/public/unstable/...` (widgets, then a dashboard that places them). It is unstable by name, so this
script is idempotent (it deletes its own dashboard and widgets, found by name, and creates them again) and the static export
(`exportar.py`) does not depend on it: if the API changes, the dashboard is recreated by hand from `WIDGETS` below, and the runbook
still works from the static export.

What Langfuse can show is limited by its dimensions: observation type and name, model, time, level, user, session. It has no dimension for
the lab's task, tenant or outcome, and it does not show span events (activity 4, finding 3): guardrail decisions, budget decisions and
HITL steps are in the OTel backend (the Collector's file), and the static export reads them there.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias.correr_eval import LANGFUSE, _auth  # noqa: E402

TABLERO = "LegacyBridge (semana 17)"
PREFIJO = "LB · "


def _f(columna: str, valores: list[str]) -> dict:
    return {"column": columna, "operator": "any of", "value": valores, "type": "stringOptions"}


# (name, view, dimensions, metrics, filters, chart type, (x, y, width, height))
WIDGETS = [
    ("Cost per day (USD)", "observations", [], [{"measure": "totalCost", "agg": "sum"}], [], "BAR_TIME_SERIES", (0, 0, 6, 5)),
    ("Cost by model (USD)", "observations", [{"field": "providedModelName"}], [{"measure": "totalCost", "agg": "sum"}],
     [_f("type", ["GENERATION"])], "HORIZONTAL_BAR", (6, 0, 6, 5)),
    ("Latency p50 by step type (s)", "observations", [{"field": "type"}], [{"measure": "latency", "agg": "p50"}], [], "VERTICAL_BAR", (0, 5, 6, 5)),
    ("Latency p95 by step type (s)", "observations", [{"field": "type"}], [{"measure": "latency", "agg": "p95"}], [], "VERTICAL_BAR", (6, 5, 6, 5)),
    ("Latency p95 by tool (s)", "observations", [{"field": "name"}], [{"measure": "latency", "agg": "p95"}], [_f("type", ["TOOL"])],
     "HORIZONTAL_BAR", (0, 10, 6, 5)),
    ("Input tokens per day", "observations", [], [{"measure": "inputTokens", "agg": "sum"}], [_f("type", ["GENERATION"])],
     "LINE_TIME_SERIES", (6, 10, 3, 5)),
    ("Output tokens per day", "observations", [], [{"measure": "outputTokens", "agg": "sum"}], [_f("type", ["GENERATION"])],
     "LINE_TIME_SERIES", (9, 10, 3, 5)),
    ("Tool errors by tool", "observations", [{"field": "name"}], [{"measure": "count", "agg": "count"}],
     [_f("type", ["TOOL"]), _f("level", ["ERROR"])], "HORIZONTAL_BAR", (0, 15, 6, 5)),
    ("Runs that did not answer (agent spans at ERROR)", "observations", [], [{"measure": "count", "agg": "count"}],
     [_f("type", ["AGENT"]), _f("level", ["ERROR"])], "BAR_TIME_SERIES", (6, 15, 6, 5)),
    ("Trajectory score (mean) over time", "scores-numeric", [{"field": "name"}], [{"measure": "value", "agg": "avg"}],
     [_f("name", ["trayectoria.puntaje"])], "LINE_TIME_SERIES", (0, 20, 6, 5)),
    ("Trajectory ok and answer ok (rate)", "scores-boolean", [{"field": "name"}], [{"measure": "value", "agg": "avg"}],
     [_f("name", ["trayectoria.ok", "respuesta.ok"])], "VERTICAL_BAR", (6, 20, 6, 5)),
]


def _pedir(metodo: str, ruta: str, auth: str, cuerpo=None):
    req = urllib.request.Request(f"{LANGFUSE}/api/public/{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            texto = r.read().decode()
            return r.status, (json.loads(texto) if texto else {})
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        return e.code, (json.loads(texto) if texto.startswith("{") else {"raw": texto[:300]})


def _todos(ruta: str, auth: str) -> list[dict]:
    out, pagina = [], 1
    while True:
        c, b = _pedir("GET", f"{ruta}?page={pagina}&limit=50", auth)
        if c != 200:
            return out
        out += b.get("data") or []
        if pagina >= (b.get("meta") or {}).get("totalPages", 1):
            return out
        pagina += 1


def crear() -> dict:
    auth, _ = _auth()
    for d in _todos("unstable/dashboards", auth):
        if d["name"] == TABLERO:
            _pedir("DELETE", f"unstable/dashboards/{d['id']}", auth)
    for w in _todos("unstable/dashboard-widgets", auth):
        if w["name"].startswith(PREFIJO):
            _pedir("DELETE", f"unstable/dashboard-widgets/{w['id']}", auth)
    colocados, errores = [], []
    for nombre, vista, dims, metricas, filtros, grafica, (x, y, ancho, alto) in WIDGETS:
        c, w = _pedir("POST", "unstable/dashboard-widgets", auth, {
            "name": PREFIJO + nombre, "description": "LegacyBridge, week 17 activity 8", "view": vista, "dimensions": dims,
            "metrics": metricas, "filters": filtros, "chartType": grafica, "chartConfig": {"type": grafica}})
        if c not in (200, 201):
            errores.append({"widget": nombre, "http": c, "detalle": json.dumps(w)[:300]})
            continue
        colocados.append({"type": "widget", "id": w["id"], "widgetId": w["id"], "x": x, "y": y, "width": ancho, "height": alto})
    c, d = _pedir("POST", "unstable/dashboards", auth, {"name": TABLERO, "description": "Week 17 activity 8: cost, latency, tokens, tool errors, scores"})
    if c not in (200, 201):
        return {"ok": False, "error": d}
    c2, d2 = _pedir("PATCH", f"unstable/dashboards/{d['id']}", auth, {"definition": {"widgets": colocados}})
    return {"ok": c2 == 200 and not errores, "tablero": d["id"], "widgets": len(colocados), "errores": errores,
            "url": f"{LANGFUSE}/project/<project>/dashboards/{d['id']}"}


if __name__ == "__main__":
    r = crear()
    print(json.dumps(r, indent=1))
    raise SystemExit(0 if r["ok"] else 1)
