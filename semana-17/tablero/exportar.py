"""Week 17, activity 8: the static export of the dashboard for the repo ($0).

    cd semana-17 && uv run --group semana17 python -m tablero.exportar      # stack up; writes resultados/tablero/{datos.json,index.html}

A fixed eval run, not "whatever is in Langfuse today": the 84 paid tasks of activity 7 (`trayectorias_real.json`) and the 14 approval runs
of activity 6 exported for the dashboard (`tablero/corrida_hitl.json`). For those traces it reads cost, latency, tokens, tool errors and
scores from the Langfuse API, and the span events Langfuse does not show (guardrail, budget and HITL decisions) plus the `lab.*`
attributes from the Collector's file. The page is self-contained (inline SVG, no script, no external asset).
"""
from __future__ import annotations

import html
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from presupuestos.politica import Politica  # noqa: E402
from tablero import fuentes as F  # noqa: E402

SALIDA = F.RESULTADOS / "tablero"


def _p(valores, q):
    v = sorted(valores)
    if not v:
        return None
    return round(v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))], 4)


def tipo_de_paso(o: dict) -> str:
    if o["type"] == "GENERATION":
        return "model"
    if o["type"] == "TOOL":
        return "tool (client)"
    if o["type"] == "AGENT":
        return "whole run (agent)"
    nombre = o.get("name") or ""
    if nombre.startswith("SELECT"):
        return "SQL"
    if nombre in ("handle_tool", "authorize") or nombre.startswith("tools/"):
        return "MCP server"
    if nombre == "hitl decide":
        return "approval decision"
    return "other"


def conjunto_fijo() -> dict[str, list[str]]:
    pagada = json.loads((F.RESULTADOS / "trayectorias_real.json").read_text(encoding="utf-8"))["por_tarea"]
    hitl = json.loads((SALIDA / "corrida_hitl.json").read_text(encoding="utf-8"))["por_corrida"]
    return {"activity 7 paid run": [f["traza"] for f in pagada], "activity 6 approval runs": sorted({i for f in hitl for i in f["traza"]["ids"]})}


def construir() -> dict:
    grupos = conjunto_fijo()
    todas = {t for ts in grupos.values() for t in ts}
    archivo = F.por_traza(F.spans_del_archivo(todas))
    pol = Politica.desde_archivo()

    # ---------- Langfuse: observations ----------
    obs = {t: F.observaciones(t) for t in sorted(todas)}
    latencias: dict[str, list[float]] = defaultdict(list)
    por_herramienta: dict[str, list[float]] = defaultdict(list)
    tokens = Counter()
    errores, recuperados = Counter(), Counter()
    costo_traza = {}
    for t, lista in obs.items():
        lista = sorted(lista, key=lambda o: o.get("startTime") or "")
        costo_traza[t] = round(sum(o.get("totalCost") or 0 for o in lista if o["type"] == "GENERATION"), 8)
        for o in lista:
            if o.get("latency") is not None:
                latencias[tipo_de_paso(o)].append(float(o["latency"]))
            if o["type"] == "TOOL" and o.get("latency") is not None:
                por_herramienta[o["name"]].append(float(o["latency"]))
            if o["type"] == "GENERATION":
                for k, v in (o.get("usageDetails") or {}).items():
                    tokens[k] += int(v or 0)
        herramientas = [o for o in lista if o["type"] == "TOOL"]
        for i, o in enumerate(herramientas):
            if o.get("level") == "ERROR":
                errores[o["name"]] += 1
                if any(p["name"] == o["name"] and p.get("level") != "ERROR" for p in herramientas[i + 1:]):
                    recuperados[o["name"]] += 1

    # ---------- the Collector's file: lab attributes and events ----------
    tareas, dias = [], defaultdict(float)
    guardrails, observadas, presupuesto = Counter(), Counter(), Counter()
    hitl = {"solicitudes": 0, "niveles": Counter(), "montos_mxn": [], "decisiones": Counter(), "espera_ms": [], "reanudaciones": Counter()}
    for t, spans in archivo.items():
        agentes = sorted((s for s in spans if s["name"].startswith("invoke_agent")), key=lambda s: s["inicio"])
        if agentes:
            a = agentes[0]
            costo = sum(float(x["attrs"].get("lab.run.cost_usd") or 0) for x in agentes)
            dia = datetime.fromtimestamp(a["inicio"] / 1e9, timezone.utc).strftime("%Y-%m-%d")
            if not a["attrs"].get("lab.model.scripted"):      # a scripted model bills nothing: its cost is from recorded tokens
                dias[(a["attrs"].get("lab.tenant.id"), dia)] += costo
            tareas.append({"traza": t, "tarea": a["attrs"].get("lab.task.id"), "tenant": a["attrs"].get("lab.tenant.id"), "dia": dia,
                           "costo_usd": round(costo, 8), "costo_langfuse_usd": costo_traza.get(t),
                           "estado": agentes[-1]["attrs"].get("lab.outcome.status"), "motivo": agentes[-1]["attrs"].get("lab.outcome.reason"),
                           "segmentos": len(agentes)})
        for s in spans:
            for e in s["eventos"]:
                at = e["attrs"]
                if e["name"] == "gen_ai.guardrail.decision":
                    if at.get("lab.guardrail.decision") != "allow":
                        guardrails[f"{at.get('lab.guardrail.name')}: {at.get('lab.guardrail.decision')} ({at.get('lab.guardrail.reason')})"] += 1
                    elif at.get("lab.guardrail.reason") not in (None, "ok"):
                        observadas[f"{at.get('lab.guardrail.name')} ({at.get('lab.guardrail.reason')})"] += 1
                elif e["name"] == "gen_ai.budget.decision" and at.get("lab.budget.decision") != "allow":
                    presupuesto[f"{at.get('lab.budget.decision')} ({at.get('lab.budget.scope')})"] += 1
                elif e["name"] == "gen_ai.hitl.request":
                    hitl["solicitudes"] += 1
                    hitl["niveles"][at.get("lab.hitl.level")] += 1
                    hitl["montos_mxn"].append(at.get("lab.hitl.amount_mxn"))
                elif e["name"] == "gen_ai.hitl.decision":
                    hitl["decisiones"][f"{at.get('lab.hitl.decision')}: {'applied' if at.get('lab.hitl.applied') else 'refused'} ({at.get('lab.hitl.reason')})"] += 1
                    if at.get("lab.hitl.applied") and at.get("lab.hitl.wait_ms") is not None:
                        hitl["espera_ms"].append(at["lab.hitl.wait_ms"])
                elif e["name"] == "gen_ai.hitl.resume":
                    hitl["reanudaciones"][at.get("lab.hitl.state")] += 1

    # ---------- Langfuse: scores ----------
    puntuaciones = {}
    for nombre in ("trayectoria.ok", "trayectoria.puntaje", "respuesta.ok"):
        todas_s = F.scores(nombre)
        por_grupo = {}
        for g, ts in grupos.items():
            vals = [todas_s[F.id_de_score(t, nombre)]["value"] for t in ts if F.id_de_score(t, nombre) in todas_s]
            vals = [float(v) if not isinstance(v, bool) else float(v) for v in vals]
            por_grupo[g] = {"n": len(vals), "media": round(sum(vals) / len(vals), 4) if vals else None}
        puntuaciones[nombre] = por_grupo
    replay = json.loads((F.RESULTADOS / "trayectorias_reproduccion.json").read_text(encoding="utf-8"))["por_tarea"]
    todas_ok, todas_resp = F.scores("trayectoria.ok"), F.scores("respuesta.ok")
    en_el_tiempo = []
    for nombre_corrida, filas in (("week 13 turns replayed (activity 7, $0)", replay),
                                  ("paid run (activity 7)", json.loads((F.RESULTADOS / "trayectorias_real.json").read_text(encoding="utf-8"))["por_tarea"])):
        ok = [todas_ok[F.id_de_score(f["traza"], "trayectoria.ok")] for f in filas if F.id_de_score(f["traza"], "trayectoria.ok") in todas_ok]
        rs = [todas_resp[F.id_de_score(f["traza"], "respuesta.ok")] for f in filas if F.id_de_score(f["traza"], "respuesta.ok") in todas_resp]
        en_el_tiempo.append({"corrida": nombre_corrida, "cuando": min((s["timestamp"] for s in ok), default=None),
                             "trayectoria_ok": round(sum(float(s["value"]) for s in ok) / len(ok), 4) if ok else None,
                             "respuesta_ok": round(sum(float(s["value"]) for s in rs) / len(rs), 4) if rs else None, "n": len(ok)})

    costos_tarea = [x["costo_usd"] for x in tareas if x["tarea"]]
    return {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "conjunto": {g: len(ts) for g, ts in grupos.items()},
        "costo": {"limite_tarea_usd": pol.tarea.usd, "limite_tenant_dia_usd": pol.tenant_dia.usd if pol.tenant_dia else None,
                  "por_tarea_p50_usd": _p(costos_tarea, 0.5), "por_tarea_p95_usd": _p(costos_tarea, 0.95), "por_tarea_max_usd": max(costos_tarea),
                  "tareas_sobre_el_limite": sum(1 for c in costos_tarea if c > pol.tarea.usd),
                  "por_tenant_y_dia": [{"tenant": k[0], "dia": k[1], "usd": round(v, 6)} for k, v in sorted(dias.items())],
                  "langfuse_contra_el_bucle_max_diferencia_usd": round(max(abs((x["costo_langfuse_usd"] or 0) - x["costo_usd"]) for x in tareas), 8),
                  "tareas": sorted(tareas, key=lambda x: -x["costo_usd"])[:10]},
        "latencia": {"por_tipo_de_paso": {k: {"n": len(v), "p50_s": _p(v, 0.5), "p95_s": _p(v, 0.95)} for k, v in sorted(latencias.items())},
                     "por_herramienta": {k: {"n": len(v), "p50_s": _p(v, 0.5), "p95_s": _p(v, 0.95)} for k, v in sorted(por_herramienta.items())}},
        "tokens": dict(tokens),
        "errores_de_herramienta": {k: {"errores": n, "recuperados": recuperados[k]} for k, n in errores.most_common()},
        "guardrails": {"bloqueos": dict(guardrails.most_common()), "observaciones": dict(observadas.most_common())},
        "presupuesto": dict(presupuesto),
        "hitl": {"solicitudes": hitl["solicitudes"], "niveles": dict(hitl["niveles"]), "monto_mxn_p50": _p([m for m in hitl["montos_mxn"] if m], 0.5),
                 "decisiones": dict(hitl["decisiones"].most_common()), "espera_ms_p50": _p(hitl["espera_ms"], 0.5),
                 "espera_ms_max": max(hitl["espera_ms"]) if hitl["espera_ms"] else None, "reanudaciones": dict(hitl["reanudaciones"])},
        "scores": puntuaciones,
        "scores_en_el_tiempo": en_el_tiempo,
    }


# ---------- the page ----------

def _barras(datos: dict[str, float], unidad: str = "", ancho: int = 520) -> str:
    if not datos:
        return "<p class=muted>none in this run</p>"
    mx = max(datos.values()) or 1
    alto, filas = 22, []
    for i, (k, v) in enumerate(datos.items()):
        w = int((ancho - 230) * v / mx)
        filas.append(f'<text x="0" y="{i * alto + 15}" class=lbl>{html.escape(str(k))[:34]}</text>'
                     f'<rect x="230" y="{i * alto + 4}" width="{max(w, 1)}" height="14" class=bar />'
                     f'<text x="{236 + w}" y="{i * alto + 15}" class=val>{v:g}{unidad}</text>')
    return f'<svg viewBox="0 0 {ancho + 80} {len(datos) * alto + 6}" role="img">{"".join(filas)}</svg>'


def _tabla(filas: list[dict], columnas: list[str]) -> str:
    cab = "".join(f"<th>{html.escape(c)}</th>" for c in columnas)
    cuerpo = "".join("<tr>" + "".join(f"<td>{html.escape(str(f.get(c, '')))}</td>" for c in columnas) + "</tr>" for f in filas)
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table>"


def pagina(d: dict) -> str:
    c, lat, h = d["costo"], d["latencia"], d["hitl"]
    secciones = [
        ("Cost against the budget",
         f"<p>Per task: p50 ${c['por_tarea_p50_usd']}, p95 ${c['por_tarea_p95_usd']}, max ${c['por_tarea_max_usd']} against a cap of "
         f"${c['limite_tarea_usd']} ({c['tareas_sobre_el_limite']} over). Langfuse and the loop agree within ${c['langfuse_contra_el_bucle_max_diferencia_usd']} per trace.</p>"
         + _tabla([{**x, "cap": c["limite_tenant_dia_usd"]} for x in c["por_tenant_y_dia"]], ["tenant", "dia", "usd", "cap"])
         + "<h3>Most expensive tasks</h3>" + _tabla(c["tareas"], ["tarea", "costo_usd", "estado", "motivo", "segmentos"])),
        ("Latency by step type (seconds)", _barras({k: v["p95_s"] for k, v in lat["por_tipo_de_paso"].items()}, " s") + "<p class=muted>p95; p50 in datos.json</p>"
         + _tabla([{"step": k, **v} for k, v in lat["por_tipo_de_paso"].items()], ["step", "n", "p50_s", "p95_s"])),
        ("Slowest tools (p95, seconds)", _barras({k: v["p95_s"] for k, v in sorted(lat["por_herramienta"].items(), key=lambda x: -(x[1]["p95_s"] or 0))}, " s")),
        ("Tokens", _barras(d["tokens"]) + "<p class=muted>As Langfuse stores them (`usageDetails`). Cache read: none, the week 13 loop sets no prompt cache. Reasoning tokens are not reported separately by the API at effort `low`; they are inside `output`.</p>"),
        ("Tool errors and recovery", _tabla([{"tool": k, **v} for k, v in d["errores_de_herramienta"].items()], ["tool", "errores", "recuperados"])
         if d["errores_de_herramienta"] else "<p class=muted>none in this run</p>"),
        ("Guardrail blocks by type", _barras(d["guardrails"]["bloqueos"]) + "<h3>Observations (audit mode, allowed)</h3>" + _barras(d["guardrails"]["observaciones"])),
        ("Budget decisions other than allow", _barras(d["presupuesto"])),
        ("Human approval (HITL)",
         f"<p>{h['solicitudes']} requests, levels {h['niveles']}, median amount {h['monto_mxn_p50']} MXN; waiting time of applied decisions: "
         f"median {h['espera_ms_p50']} ms, max {h['espera_ms_max']} ms (simulated approver on an injected clock). Resumed as {h['reanudaciones']}.</p>"
         + _barras(h["decisiones"])),
        ("Trajectory and answer scores",
         _tabla(d["scores_en_el_tiempo"], ["corrida", "cuando", "n", "trayectoria_ok", "respuesta_ok"])),
    ]
    cuerpo = "".join(f"<section><h2>{html.escape(t)}</h2>{s}</section>" for t, s in secciones)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LegacyBridge dashboard</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--bar:#3b6fd8;--line:#e5e5ea}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151517;--fg:#f2f2f4;--muted:#a1a1a6;--bar:#7aa2f7;--line:#2c2c30}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:2rem;border-top:1px solid var(--line);padding-top:1rem}} h3{{font-size:1rem}}
table{{border-collapse:collapse;width:100%;font-size:13px;overflow-x:auto;display:block}} th,td{{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line)}}
svg{{width:100%;height:auto}} .bar{{fill:var(--bar)}} .lbl,.val{{fill:var(--fg);font-size:12px}} .muted{{color:var(--muted)}}
</style></head><body><h1>LegacyBridge dashboard</h1>
<p class=muted>Static snapshot generated {d['generado']} from the Langfuse API and the Collector's file, for a fixed run: {html.escape(json.dumps(d['conjunto']))}.
Regenerate with <code>python -m tablero.exportar</code>.</p>{cuerpo}</body></html>
"""


def main() -> int:
    d = construir()
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "datos.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (SALIDA / "index.html").write_text(pagina(d), encoding="utf-8")
    print(f"conjunto {d['conjunto']} · tasks over cap {d['costo']['tareas_sobre_el_limite']} · steps {list(d['latencia']['por_tipo_de_paso'])} · "
          f"guardrail blocks {sum(d['guardrails']['bloqueos'].values())} · hitl {d['hitl']['solicitudes']} · scores {d['scores_en_el_tiempo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
