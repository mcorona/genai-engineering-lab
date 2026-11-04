"""Week 17, activity 8: the dashboard, without Langfuse or Docker (the sources are read from a synthetic OTLP file and the committed export)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from aprobaciones import criterios as CA  # noqa: E402
from tablero import exportar as X  # noqa: E402
from tablero import fuentes as F  # noqa: E402
from tablero import langfuse_tablero as L  # noqa: E402

DATOS = json.loads((S17 / "resultados" / "tablero" / "datos.json").read_text(encoding="utf-8"))


def _linea(trace, nombre, attrs, eventos=()):
    def a(d):
        out = []
        for k, v in d.items():
            tipo = "boolValue" if isinstance(v, bool) else "intValue" if isinstance(v, int) else "doubleValue" if isinstance(v, float) else "stringValue"
            out.append({"key": k, "value": {tipo: str(v) if tipo == "intValue" else v}})
        return out
    return {"resourceSpans": [{"scopeSpans": [{"spans": [{
        "traceId": trace, "spanId": "ab" * 8, "name": nombre, "startTimeUnixNano": "1793750000000000000", "endTimeUnixNano": "1793750001000000000",
        "attributes": a(attrs), "events": [{"name": n, "attributes": a(e)} for n, e in eventos]}]}]}]}


def test_el_archivo_otlp_se_lee_con_sus_tipos_y_eventos(tmp_path):
    archivo = tmp_path / "trazas.jsonl"
    lineas = [_linea("11" * 16, "invoke_agent legacybridge", {"lab.task.id": "s01-es", "lab.run.cost_usd": 0.0025, "lab.run.steps": 3,
                                                              "lab.model.scripted": True},
                     [("gen_ai.hitl.request", {"lab.hitl.level": "gerente", "lab.hitl.amount_mxn": 56462.0})]),
              _linea("22" * 16, "chat claude-haiku-5-5", {"lab.step": 1})]
    archivo.write_text("".join(json.dumps(x) + "\n" for x in lineas), encoding="utf-8")
    todos = F.spans_del_archivo(archivo=archivo)
    assert len(todos) == 2
    s = F.spans_del_archivo({"11" * 16}, archivo=archivo)[0]
    assert s["attrs"] == {"lab.task.id": "s01-es", "lab.run.cost_usd": 0.0025, "lab.run.steps": 3, "lab.model.scripted": True}
    assert s["eventos"] == [{"name": "gen_ai.hitl.request", "attrs": {"lab.hitl.level": "gerente", "lab.hitl.amount_mxn": 56462.0}}]
    assert s["fin"] - s["inicio"] == 10**9 and F.por_traza(todos).keys() == {"11" * 16, "22" * 16}


def test_cada_observacion_cae_en_un_tipo_de_paso():
    casos = {("GENERATION", "chat"): "model", ("TOOL", "ejecutar_sql"): "tool (client)", ("AGENT", "invoke_agent"): "whole run (agent)",
             ("SPAN", "SELECT legado"): "SQL", ("SPAN", "handle_tool"): "MCP server", ("SPAN", "tools/call"): "MCP server",
             ("SPAN", "hitl decide"): "approval decision", ("SPAN", "otro"): "other"}
    for (tipo, nombre), esperado in casos.items():
        assert X.tipo_de_paso({"type": tipo, "name": nombre}) == esperado


def test_los_widgets_usan_solo_vistas_graficas_y_agregaciones_de_langfuse():
    vistas = {"observations", "scores-numeric", "scores-boolean", "scores-categorical"}
    graficas = {"LINE_TIME_SERIES", "AREA_TIME_SERIES", "BAR_TIME_SERIES", "HORIZONTAL_BAR", "VERTICAL_BAR", "PIE", "NUMBER", "HISTOGRAM", "PIVOT_TABLE"}
    aggs = {"sum", "avg", "count", "max", "min", "p50", "p75", "p90", "p95", "p99", "histogram", "uniq"}
    nombres = [w[0] for w in L.WIDGETS]
    assert len(nombres) == len(set(nombres)) == 11
    for nombre, vista, dims, metricas, filtros, grafica, (x, y, ancho, alto) in L.WIDGETS:
        assert vista in vistas and grafica in graficas and metricas and all(m["agg"] in aggs for m in metricas), nombre
        assert 0 <= x and x + ancho <= 12 and ancho > 0 and alto > 0
        assert all(f["operator"] == "any of" and isinstance(f["value"], list) for f in filtros)
    posiciones = {(w[6][0], w[6][1]) for w in L.WIDGETS}
    assert len(posiciones) == len(L.WIDGETS)                                            # no two widgets in the same place


def test_la_exportacion_es_de_la_corrida_fija_y_cuadra_con_sus_informes():
    assert DATOS["conjunto"] == {"activity 7 paid run": 84, "activity 6 approval runs": 14}
    c = DATOS["costo"]
    assert c["tareas_sobre_el_limite"] == 0 and c["por_tarea_max_usd"] <= c["limite_tarea_usd"]
    assert c["langfuse_contra_el_bucle_max_diferencia_usd"] < 1e-6                      # Langfuse and the loop price every trace the same
    pagado = json.loads((S17 / "resultados" / "trayectorias_real.json").read_text(encoding="utf-8"))["costo_usd"]
    assert c["por_tenant_y_dia"] == [{"tenant": "lab", "dia": "2026-11-04", "usd": round(pagado, 6)}]   # real model only
    tray = {x["corrida"]: x for x in DATOS["scores_en_el_tiempo"]}
    assert tray["paid run (activity 7)"]["trayectoria_ok"] == 0.9167 and tray["paid run (activity 7)"]["respuesta_ok"] == round(74 / 84, 4)
    assert {"model", "tool (client)", "MCP server", "SQL"} <= set(DATOS["latencia"]["por_tipo_de_paso"])


def test_el_panel_de_hitl_cuenta_lo_que_paso_en_los_14_escenarios():
    h = DATOS["hitl"]
    assert h["solicitudes"] == 2 * len(CA.ESCENARIOS) and h["niveles"] == {"gerente": 14}
    assert h["decisiones"]["approve: applied (ok)"] == 8 and h["decisiones"]["approve: refused (mismo_usuario)"] == 2
    assert h["decisiones"]["approve: refused (sin_nivel)"] == 2 and h["decisiones"]["reject: refused (ya_decidida)"] == 2
    assert h["reanudaciones"] == {"aprobada": 8, "rechazada": 2, "expirada": 4} and h["espera_ms_max"] == 61 * 60 * 1000


def test_la_pagina_es_autocontenida_y_tiene_los_siete_paneles():
    pagina = (S17 / "resultados" / "tablero" / "index.html").read_text(encoding="utf-8")
    assert "<script" not in pagina and not re.search(r'(src|href)="https?://', pagina)
    for titulo in ("Cost against the budget", "Latency by step type", "Tokens", "Tool errors and recovery", "Guardrail blocks by type",
                   "Human approval (HITL)", "Trajectory and answer scores"):
        assert titulo in pagina
    assert "prefers-color-scheme:dark" in pagina and "/Users/" not in pagina
    assert X.pagina(DATOS) == pagina.replace(pagina[pagina.index("generated "):pagina.index(" from the Langfuse")],
                                             "generated " + DATOS["generado"])


def test_el_runbook_responde_las_cinco_preguntas_en_menos_de_un_minuto():
    texto = (S17 / "resultados" / "tablero" / "runbook.md").read_text(encoding="utf-8")
    filas = [l for l in texto.splitlines() if l.startswith("| ") and "preguntar" in l]
    assert len(filas) == 5
    tiempos = [float(re.search(r"\| ([0-9.]+) s \|", l).group(1)) for l in filas]
    assert all(t < 60 for t in tiempos)
