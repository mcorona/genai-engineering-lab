"""Week 17, activity 8: the runbook's five operator questions, answered from the dashboard's sources in seconds ($0).

    cd semana-17
    uv run --group semana17 python -m tablero.preguntar tarea c08-es                     # why did task X fail
    uv run --group semana17 python -m tablero.preguntar tenant lab --dia 2026-11-04      # what did tenant Y spend that day
    uv run --group semana17 python -m tablero.preguntar lenta                            # which tool is slowing things down
    uv run --group semana17 python -m tablero.preguntar orden OC-xxxxxxxxxx              # who approved order Z
    uv run --group semana17 python -m tablero.preguntar cambio                           # did the change make trajectories worse

Each answer says where it came from, so the same question can be answered in the Langfuse UI or the OTel backend by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from presupuestos.politica import Politica  # noqa: E402
from tablero import fuentes as F  # noqa: E402
from trayectorias import criterios as CT  # noqa: E402
from trayectorias.correr_eval import LANGFUSE, _auth  # noqa: E402

ESQUEMA_HITL = "hitl_tablero"


def _corrida_fija() -> dict[str, dict]:
    return {f["id"]: f for f in json.loads((F.RESULTADOS / "trayectorias_real.json").read_text(encoding="utf-8"))["por_tarea"]}


def tarea(id_: str) -> dict:
    f = _corrida_fija().get(id_)
    if f is None:
        return {"error": f"{id_} is not in the fixed run"}
    spans = F.spans_del_archivo({f["traza"]})
    agente = next(s for s in spans if s["name"].startswith("invoke_agent"))
    eventos = [e for s in spans for e in s["eventos"]]
    no_allow = [f"{e['attrs'].get('lab.guardrail.name')}:{e['attrs'].get('lab.guardrail.decision')}:{e['attrs'].get('lab.guardrail.reason')}"
                for e in eventos if e["name"] == "gen_ai.guardrail.decision" and e["attrs"].get("lab.guardrail.decision") != "allow"]
    paradas = [f"{e['attrs'].get('lab.budget.scope')}:{e['attrs'].get('lab.budget.reason')}" for e in eventos
               if e["name"] == "gen_ai.budget.decision" and e["attrs"].get("lab.budget.decision") == "stop"]
    errores = [s["name"].split(" ", 1)[1] for s in spans if s["name"].startswith("execute_tool") and s["attrs"].get("lab.tool.status") == "error"]
    puntajes = {}
    for n in ("ok", "puntaje", *CT.EVALUADORES_CON_REGLA):
        todos = F.scores(f"trayectoria.{n}")
        s = todos.get(F.id_de_score(f["traza"], f"trayectoria.{n}"))
        if s is not None:
            puntajes[n] = s["value"]
    resp = F.scores("respuesta.ok").get(F.id_de_score(f["traza"], "respuesta.ok"))
    a = agente["attrs"]
    return {"tarea": id_, "traza": f["traza"], "fuente": "Collector file (span attributes and events) + Langfuse v3 scores",
            "estado": a.get("lab.outcome.status"), "motivo": a.get("lab.outcome.reason"), "pasos": a.get("lab.run.steps"),
            "costo_usd": a.get("lab.run.cost_usd"), "respuesta_correcta": None if resp is None else bool(resp["value"]),
            "errores_de_herramienta": errores, "guardrails_no_allow": no_allow, "paradas_de_presupuesto": paradas,
            "evaluadores_de_trayectoria_bajo_1": {k: v for k, v in puntajes.items() if k not in ("ok", "puntaje") and float(v) < 1},
            "trayectoria_ok": puntajes.get("ok")}


def tenant(nombre: str, dia: str | None) -> dict:
    dia = dia or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total, corridas, guionadas = 0.0, 0, 0
    for s in F.spans_del_archivo():
        if s["name"].startswith("invoke_agent") and s["attrs"].get("lab.tenant.id") == nombre \
                and datetime.fromtimestamp(s["inicio"] / 1e9, timezone.utc).strftime("%Y-%m-%d") == dia:
            if s["attrs"].get("lab.model.scripted"):
                guionadas += 1          # a scripted or replayed model: its cost is computed from recorded tokens, nothing was billed
                continue
            total += float(s["attrs"].get("lab.run.cost_usd") or 0)
            corridas += 1
    pol = Politica.desde_archivo()
    limite = pol.tenant_dia.usd if pol.tenant_dia else None
    return {"tenant": nombre, "dia_utc": dia, "usd": round(total, 6), "limite_usd": limite, "corridas": corridas,
            "corridas_guionadas_excluidas": guionadas,
            "uso_del_limite": round(total / limite, 4) if limite else None,
            "fuente": "Collector file: sum of lab.run.cost_usd on the agent spans of that tenant and UTC day, real model only (lab.model.scripted excluded)"}


def lenta() -> dict:
    auth, peticion = _auth()
    q = {"view": "observations", "metrics": [{"measure": "latency", "aggregation": "p95"}, {"measure": "count", "aggregation": "count"}],
         "dimensions": [{"field": "name"}], "filters": [{"column": "type", "operator": "any of", "value": ["TOOL"], "type": "stringOptions"}],
         "fromTimestamp": "2026-11-01T00:00:00Z", "toTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    c, b = peticion(f"{LANGFUSE}/api/public/v2/metrics?query=" + urllib.parse.quote(json.dumps(q)), auth)
    filas = sorted(b.get("data") or [], key=lambda x: -(x.get("p95_latency") or 0))
    return {"fuente": "Langfuse v2/metrics: p95 latency of TOOL observations by name (the widget 'LB · Latency p95 by tool')",
            "http": c, "herramientas": [{"herramienta": x.get("name"), "p95_ms": round(float(x.get("p95_latency") or 0), 1),
                                         "llamadas": int(x.get("count_count") or 0)} for x in filas][:8]}


def orden(id_: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], row_factory=dict_row) as c:
        o = c.execute(f"SELECT * FROM {ESQUEMA_HITL}.ordenes WHERE id = %s", (id_,)).fetchone()
        if o is None:
            return {"error": f"no order {id_} in {ESQUEMA_HITL}"}
        s = c.execute(f"SELECT * FROM {ESQUEMA_HITL}.solicitudes WHERE id = %s", (o["solicitud_id"],)).fetchone()
        intentos = c.execute(f"SELECT sujeto, decision, aplicado, motivo, en FROM {ESQUEMA_HITL}.intentos WHERE solicitud_id = %s ORDER BY id",
                             (s["id"],)).fetchall()
    return {"orden": id_, "fuente": "the approvals store (system of record); the trace has only keyed hashes of the people",
            "aprobada_por": s["aprobador"], "nivel_del_aprobador": s["aprobador_nivel"], "nivel_requerido": s["nivel"],
            "pedida_por": s["solicitante"], "monto_mxn": float(s["monto_mxn"]), "sku": s["sku"], "cantidad": s["cantidad"],
            "pedida": s["creada_en"].isoformat(), "decidida": s["decidida_en"].isoformat(),
            "intentos": [{**i, "en": i["en"].isoformat()} for i in intentos],
            "traza": (s.get("traza") or "").split("-")[1] if s.get("traza") else None}


def cambio(antes: str, despues: str) -> dict:
    from trayectorias.analisis import diferencia, serie_de_informe
    a, b = serie_de_informe(antes), serie_de_informe(despues)
    d = diferencia(a, b)
    return {"antes": antes, "despues": despues, "fuente": "trajectory scores of the two runs, paired by task, bootstrap over tasks (week 13's method)",
            "trayectoria_ok_antes": round(sum(v["tray"][0] for v in a.values()) / len(a), 4),
            "trayectoria_ok_despues": round(sum(v["tray"][0] for v in b.values()) / len(b), 4),
            "diferencia": d["diferencia"], "ic95": d["ic95"],
            "veredicto": "worse" if d["ic95"][1] < 0 else ("better" if d["ic95"][0] > 0 else "no measurable change")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="pregunta", required=True)
    sub.add_parser("tarea").add_argument("id")
    t = sub.add_parser("tenant")
    t.add_argument("nombre")
    t.add_argument("--dia")
    sub.add_parser("lenta")
    sub.add_parser("orden").add_argument("id")
    c = sub.add_parser("cambio")
    c.add_argument("--antes", default="trayectorias_reproduccion.json")
    c.add_argument("--despues", default="trayectorias_real.json")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    r = {"tarea": lambda: tarea(a.id), "tenant": lambda: tenant(a.nombre, a.dia), "lenta": lenta, "orden": lambda: orden(a.id),
         "cambio": lambda: cambio(a.antes, a.despues)}[a.pregunta]()
    r["segundos"] = round(time.perf_counter() - t0, 2)
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
