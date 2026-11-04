"""Week 17, activity 5: the false positives of the guardrails on the 84 golden tasks.

    cd semana-17
    uv run --group semana17 python -m guardrails.correr_eval --reproduccion          # $0: replays the recorded model turns
    uv run --group semana17 python -m guardrails.correr_eval --confirmo-gasto        # the real model: costs money

All 84 tasks are benign (read-only questions, some ambiguous, some without an answer in the data). A guardrail that takes ANY decision other
than `allow` on one of them is a false positive (`criterios.py`: more than 1 task of 84 per guardrail is rejected or tuned, both numbers
reported). The run is the activity 4 one (real loop, real tools, real database, calibrated budget) through `AgenteGuardado`.

* `--reproduccion` ($0): the turns recorded in the week 13 evaluation, repetition 0 of each task. The model never answers anything new, so
  what changes is only what the guardrails do: each task runs twice on the same recorded trajectory, with the guardrails on and off
  (`AgentePresupuestado` of activity 4), and the two outcomes are compared task by task.
* `--confirmo-gasto`: Claude Haiku 5.5, effort `low`. About $0.24 (the activity 4 run cost $0.2344); the budget caps it as before.

The report has numbers and words of the fixed lists only: no prompt, SQL, answer or row.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from guardrails import criterios as C  # noqa: E402
from guardrails import nucleo as N  # noqa: E402
from guardrails.agente import AgenteGuardado, resumen_de_decisiones  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import configurar_trazas, resumen  # noqa: E402
from presupuestos.agente_presupuestado import AgentePresupuestado  # noqa: E402
from presupuestos.almacen import AlmacenGasto  # noqa: E402
from presupuestos.correr_eval import CARO, ESFUERZO, MODELO, TAREAS_POR_SESION, TENANT, Reproduccion, base_semana_13  # noqa: E402
from presupuestos.politica import Politica  # noqa: E402

from agente.correr import cargar_tareas  # noqa: E402
from agente.loop import api_anthropic  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402


def totales_actividad_4(real: bool) -> dict | None:
    """The activity 4 run in the same mode (budget only, no guardrails), as its committed report states it: totals only."""
    ruta = S17 / "resultados" / ("presupuestos_eval.json" if real else "presupuestos_eval_reproduccion.json")
    if not ruta.exists():
        return None
    informe = json.loads(ruta.read_text(encoding="utf-8"))
    return {"exitos": informe["resultado"]["exitos"], "tareas": informe["tareas"], "usd": informe["costo"]["total_usd"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reproduccion", action="store_true", help="$0: replay the recorded turns of week 13 (the default)")
    ap.add_argument("--confirmo-gasto", action="store_true", help="use the real model; costs money")
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--tareas", nargs="*", help="base ids (s03, r02...); none: all 84")
    ap.add_argument("--fundamentacion", choices=N.MODOS_FUNDAMENTACION, default="auditar",
                    help="`rechazar` refuses an answer with an ungrounded figure (the mode the paid run measured and rejected); `auditar` only records it")
    ap.add_argument("--salida", help="report path (default resultados/guardrails_falsos_positivos[_reproduccion].json)")
    a = ap.parse_args(argv)
    real = a.confirmo_gasto
    if real and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[eval] --confirmo-gasto needs ANTHROPIC_API_KEY in the environment", file=sys.stderr)
        return 2
    salida = Path(a.salida) if a.salida else S17 / "resultados" / ("guardrails_falsos_positivos.json" if real else "guardrails_falsos_positivos_reproduccion.json")
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = not real
    E.OMITIDOS.clear()
    exp = configurar_trazas()
    politica = Politica.desde_archivo()
    trabajos = cargar_tareas(a.tareas, ["es", "en"])
    reproduccion = None if real else Reproduccion()
    estimado = len(trabajos) * base_semana_13()["k3"]["usd"]["media"]
    print(f"{len(trabajos)} runs · {'REAL model' if real else 'replay of the recorded turns'} · {MODELO} {ESFUERZO} · guardrails ON · "
          f"expected ${estimado:.3f}", flush=True)

    almacen = AlmacenGasto(Path(tempfile.mkdtemp(prefix="gasto-s17-g-")) / "gasto.sqlite")
    almacen_sin = AlmacenGasto(Path(tempfile.mkdtemp(prefix="gasto-s17-s-")) / "gasto.sqlite")
    conn0, _ = conectar()
    locales, candado, conexiones, filas, estados = threading.local(), threading.Lock(), [conn0], [], []

    def una(indice: int, t: dict):
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
            with candado:
                conexiones.append(locales.conn)
        herramientas = Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=t["lang"]))
        api = api_anthropic if real else reproduccion.para(t["id"])
        agente = AgenteGuardado(herramientas, api=api, tenant=TENANT, politica=politica, almacen=almacen, modelo=MODELO,
                                esfuerzo=ESFUERZO, simulado=not real, fundamentacion=a.fundamentacion)
        r = agente.resolver({**t, "rep": 0}, "analista", sesion=f"sesion-{indice // TAREAS_POR_SESION:02d}")
        g, est = agente.ultima_guardia, agente.ultimo
        v = verificar(t, r.final, locales.conn, r.estado)
        sin = None
        if not real:        # the same recorded trajectory without the guardrails: the activity 4 agent
            h2 = Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=t["lang"]))
            a2 = AgentePresupuestado(h2, api=reproduccion.para(t["id"]), tenant=TENANT, politica=politica, almacen=almacen_sin,
                                     modelo=MODELO, esfuerzo=ESFUERZO, simulado=True)
            r2 = a2.resolver({**t, "rep": 0}, "analista", sesion=f"sesion-{indice // TAREAS_POR_SESION:02d}")
            sin = {"exito": verificar(t, r2.final, locales.conn, r2.estado)["exito"], "estado": r2.estado}
        tomadas = [{"guardrail": d.guardrail, "accion": d.accion, "motivo": d.motivo} for d in g.decisiones if not d.permite]
        fila = {"id": t["id"], "tipo": t["tipo"], "corrida": r.corrida, "estado": r.estado, "esperado": t["estado_esperado"],
                "exito": v["exito"], "motivo": r.motivo, "pasos": r.pasos, "herramientas": r.herramientas,
                "usd": round(est.gasto.usd, 8), "decisiones": resumen_de_decisiones(g), "eventos": len(g.decisiones), "no_allow": tomadas,
                "observadas": [{"guardrail": d.guardrail, "motivo": d.motivo} for d in g.decisiones if d.permite and d.motivo != "ok"],
                "sin_guardrails": sin}
        with candado:
            filas.append(fila)
            estados.append(g)
            marca = "  <-- " + ", ".join(f"{d['guardrail']}:{d['accion']}:{d['motivo']}" for d in tomadas) if tomadas else ""
            print(f"{t['id']:<8} {t['tipo']:<13} {r.estado:<19} exito={'si' if v['exito'] else 'NO':<3} ${est.gasto.usd:.5f}{marca}", flush=True)

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, i, t) for i, t in enumerate(trabajos)]):
                fut.result()
    finally:
        for c in conexiones:
            c.close()
    filas.sort(key=lambda f: f["id"])

    spans = resumen(exp.get_finished_spans())
    agentes = {s["attrs"].get("lab.run.id"): s for s in spans if s["name"].startswith("invoke_agent")}
    un_evento_por_decision = all(
        f["corrida"] in agentes and sum(1 for e in agentes[f["corrida"]]["eventos"] if e["name"] == E.EVENTO_GUARDRAIL) == f["eventos"]
        for f in filas)
    por_guardrail = {}
    for g in C.GUARDRAILS:
        ids = sorted({f["id"] for f in filas if any(d["guardrail"] == g for d in f["no_allow"])})
        por_guardrail[g] = {"tareas": len(ids), "tasa": round(len(ids) / len(filas), 4), "ids": ids,
                            "acciones": dict(Counter(d["accion"] for f in filas for d in f["no_allow"] if d["guardrail"] == g)),
                            "supera_el_limite": len(ids) > C.MAX_TAREAS_AFECTADAS,
                            "observadas": sorted({f["id"] for f in filas if any(o["guardrail"] == g for o in f["observadas"])})}
    afectadas = sorted({f["id"] for f in filas if f["no_allow"]})
    pareadas = [f for f in filas if f["sin_guardrails"]]
    nuevas_fallas = sorted(f["id"] for f in pareadas if f["sin_guardrails"]["exito"] and not f["exito"])
    nuevos_aciertos = sorted(f["id"] for f in pareadas if not f["sin_guardrails"]["exito"] and f["exito"])
    total = sum(f["usd"] for f in filas)
    informe = {
        "fecha": time.strftime("%Y-%m-%d"), "modo": "modelo real" if real else "reproduccion de la semana 13 (sin modelo)",
        "modelo": MODELO, "esfuerzo": ESFUERZO, "fundamentacion": a.fundamentacion, "tareas": len(filas), "segundos": round(time.time() - t0, 1),
        "limite": {"tasa": C.TASA_MAXIMA_DE_FALSOS_POSITIVOS, "tareas_por_guardrail": C.MAX_TAREAS_AFECTADAS},
        "falsos_positivos": {
            "por_guardrail": por_guardrail, "tareas_afectadas": len(afectadas), "ids_afectadas": afectadas,
            "guardrails_sobre_el_limite": [g for g, v in por_guardrail.items() if v["supera_el_limite"]]},
        "resultado": {
            "exito": round(sum(f["exito"] for f in filas) / len(filas), 4), "exitos": sum(f["exito"] for f in filas),
            "estados": dict(Counter(f["estado"] for f in filas)), "motivos_de_parada": dict(Counter(f["motivo"] for f in filas if f["motivo"] != "responder")),
            "pareado_sin_guardrails": {
                "exitos_sin": sum(f["sin_guardrails"]["exito"] for f in pareadas), "exitos_con": sum(f["exito"] for f in pareadas),
                "fallan_ahora_y_pasaban": nuevas_fallas, "pasan_ahora_y_fallaban": nuevos_aciertos} if pareadas else None,
            "actividad_4_informe_confirmado": totales_actividad_4(real)},
        "decisiones": {g: dict(sum((Counter(f["decisiones"].get(g, {})) for f in filas), Counter())) for g in C.GUARDRAILS},
        "garantias": {"un_evento_por_decision": un_evento_por_decision, "omisiones_del_esquema": dict(E.OMITIDOS)},
        "costo": {"total_usd": round(total, 6), "media_por_tarea": round(total / len(filas), 6)},
        "por_corrida": [{k: f[k] for k in ("id", "tipo", "estado", "esperado", "exito", "motivo", "pasos", "herramientas", "usd", "no_allow", "sin_guardrails")} for f in filas]}
    informe["ok"] = bool(un_evento_por_decision and not E.OMITIDOS and not informe["falsos_positivos"]["guardrails_sobre_el_limite"])
    salida.write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nsuccess {informe['resultado']['exitos']}/{len(filas)} · tasks with a non-allow decision {len(afectadas)} · guardrails over the "
          f"limit {informe['falsos_positivos']['guardrails_sobre_el_limite'] or 'none'} · cost ${total:.4f} · ok={informe['ok']}")
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
