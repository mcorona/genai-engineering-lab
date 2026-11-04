"""Week 17, activity 4: the 84 tasks of week 13 under the calibrated budget.

    cd semana-17
    uv run --group semana17 python -m presupuestos.correr_eval --reproduccion            # $0: replays the recorded model turns
    uv run --group semana17 python -m presupuestos.correr_eval --confirmo-gasto          # the real model: costs money, see below

Both modes run the real week 13 loop with the real tools and the real database, through `AgentePresupuestado`, and score every
task with the week 13 verifier. They differ only in who answers the model call:

* `--reproduccion` (the default, $0): the turns recorded in the week 13 evaluation (`semana-13/resultados/trazas/eval_haiku_low.jsonl`,
  repetition 0 of each task): the same tool calls, the same arguments, the same token counts. It rehearses the whole pipeline, and it
  shows what the budget does to a recorded trajectory.
* `--confirmo-gasto`: Anthropic's API with Claude Haiku 5.5, effort `low`, the model and setting of the week 13 agent. Expected cost
  about $0.24 (84 tasks at the $0.00286 mean of week 13); the budget itself caps it: $0.0063 per task, $0.039 per session of ten
  tasks, $0.32 for the tenant's day. It needs `ANTHROPIC_API_KEY` and the flag, so it cannot run by accident.

The report (`resultados/presupuestos_eval*.json`) has numbers and ids only: no prompt, SQL, answer or row.
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

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import configurar_trazas, resumen  # noqa: E402
from presupuestos import calibracion as CAL  # noqa: E402
from presupuestos import estimacion as EST  # noqa: E402
from presupuestos.agente_presupuestado import AgentePresupuestado  # noqa: E402
from presupuestos.almacen import AlmacenGasto  # noqa: E402
from presupuestos.politica import Politica  # noqa: E402

from agente.correr import cargar_tareas  # noqa: E402
from agente.loop import api_anthropic  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402

S13 = EST.S13
MODELO, ESFUERZO, TENANT = "claude-haiku-5-5", "low", "lab"
CARO = "claude-sonnet-5-5"          # --degradar builds the agent with this one; the policy names MODELO as its cheaper model
TAREAS_POR_SESION = 10


class Reproduccion:
    """The model of week 13, replayed: the recorded turns of one run per task (repetition 0). It answers like the API: the output is
    cut at `max_tokens`, and a turn with no recorded tool call is a text turn."""

    def __init__(self, corrida: str = "eval_haiku_low"):
        detalle = [json.loads(l) for l in open(S13 / "resultados" / f"{corrida}_detalle.jsonl", encoding="utf-8")]
        self.base = {r["id"]: r for r in detalle if r["rep"] == 0}
        ids = {r["corrida"] for r in self.base.values()}
        self.pasos: dict[str, dict] = defaultdict(lambda: {"modelo": {}, "herramientas": defaultdict(list)})
        for linea in open(S13 / "resultados" / "trazas" / f"{corrida}.jsonl", encoding="utf-8"):
            e = json.loads(linea)
            if e["corrida"] not in ids:
                continue
            if e["tipo"] == "modelo":
                self.pasos[e["corrida"]]["modelo"][e["paso"]] = e
            elif e["tipo"] == "herramienta":
                self.pasos[e["corrida"]]["herramientas"][e["paso"]].append(e)

    def para(self, tarea_id: str):
        corrida = self.base[tarea_id]["corrida"]
        p = self.pasos[corrida]
        contador = [0]

        def api(cuerpo: dict) -> dict:
            contador[0] += 1
            m = p["modelo"][contador[0]]
            tin, tout = m["tokens_in"], m["tokens_out"]
            if tout > cuerpo["max_tokens"]:
                return {"id": "msg_replay", "role": "assistant", "model": cuerpo["model"], "stop_reason": "max_tokens",
                        "content": [{"type": "text", "text": "..."}], "usage": {"input_tokens": tin, "output_tokens": cuerpo["max_tokens"]}}
            usos = p["herramientas"].get(contador[0], [])
            contenido = [{"type": "tool_use", "id": f"toolu_replay_{contador[0]:02d}_{k + 1}", "name": h["herramienta"],
                          "input": h["argumentos"] or {}} for k, h in enumerate(usos)] or [{"type": "text", "text": "..."}]
            return {"id": f"msg_replay_{contador[0]:03d}", "role": "assistant", "model": cuerpo["model"],
                    "stop_reason": m["stop_reason"], "content": contenido, "usage": {"input_tokens": tin, "output_tokens": tout}}
        return api


def base_semana_13() -> dict:
    """Week 13 on the same 84 tasks, repetition 0 and all three: what the budget is compared against."""
    filas = [json.loads(l) for l in open(S13 / "resultados" / "eval_haiku_low_detalle.jsonl", encoding="utf-8")]
    def resumen_de(rs):
        costos = [r["costo_usd"] for r in rs]
        return {"corridas": len(rs), "exito": round(sum(r["exito"] for r in rs) / len(rs), 4),
                "usd": {"media": round(sum(costos) / len(costos), 6), "p50": round(CAL.percentil(costos, 50), 6),
                        "p95": round(CAL.percentil(costos, 95), 6), "max": round(max(costos), 6), "total": round(sum(costos), 4)}}
    return {"repeticion_0": resumen_de([r for r in filas if r["rep"] == 0]), "k3": resumen_de(filas)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reproduccion", action="store_true", help="$0: replay the recorded turns of week 13 (the default)")
    ap.add_argument("--confirmo-gasto", action="store_true", help="use the real model; costs money")
    ap.add_argument("--degradar", action="store_true", help="the agent is built with Sonnet and the policy names Haiku as its cheaper model")
    ap.add_argument("--repeticiones", type=int, default=1, help="runs of each task (the replay only has repetition 0)")
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--tareas", nargs="*", help="base ids (s03, r02...); none: all 84")
    ap.add_argument("--salida", help="report path (default resultados/presupuestos_eval[_reproduccion].json)")
    a = ap.parse_args(argv)
    real = a.confirmo_gasto
    if real and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[eval] --confirmo-gasto needs ANTHROPIC_API_KEY in the environment", file=sys.stderr)
        return 2
    if not real and a.repeticiones != 1:
        print("[eval] the replay has one recorded run per task: --repeticiones needs --confirmo-gasto", file=sys.stderr)
        return 2
    modelo_del_agente = CARO if a.degradar else MODELO
    salida = Path(a.salida) if a.salida else S17 / "resultados" / ("presupuestos_eval.json" if real else "presupuestos_eval_reproduccion.json")
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = not real          # a schema violation in a paid run is counted, not fatal; the replay is where it must be zero
    E.OMITIDOS.clear()
    exp = configurar_trazas()
    politica = Politica.desde_archivo(degradar={CARO: MODELO} if a.degradar else {})
    trabajos = [(t, r) for r in range(a.repeticiones) for t in cargar_tareas(a.tareas, ["es", "en"])]
    reproduccion = None if real else Reproduccion()
    estimado = len(trabajos) * base_semana_13()["k3"]["usd"]["media"]
    print(f"{len(trabajos)} runs · {'REAL model' if real else 'replay of the recorded turns'} · "
          f"{modelo_del_agente + ' degrading to ' + MODELO if a.degradar else MODELO} {ESFUERZO} · "
          f"expected ${estimado:.3f} · caps: task ${politica.tarea.usd}, session ${politica.sesion.usd} (every {TAREAS_POR_SESION} tasks), "
          f"tenant day ${politica.tenant_dia.usd}", flush=True)

    ruta = Path(tempfile.mkdtemp(prefix="gasto-s17-")) / "gasto.sqlite"
    almacen = AlmacenGasto(ruta)
    conn0, rol = conectar()
    locales, candado, conexiones, filas, estados = threading.local(), threading.Lock(), [conn0], [], []

    def una(indice: int, trabajo: tuple):
        t, repeticion = trabajo
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
            with candado:
                conexiones.append(locales.conn)
        herramientas = Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=t["lang"]))
        api = api_anthropic if real else reproduccion.para(t["id"])
        agente = AgentePresupuestado(herramientas, api=api, tenant=TENANT, politica=politica, almacen=almacen, modelo=modelo_del_agente,
                                     esfuerzo=ESFUERZO, simulado=not real)
        sesion = f"sesion-{indice // TAREAS_POR_SESION:02d}"
        r = agente.resolver({**t, "rep": repeticion}, "analista", sesion=sesion)
        est = agente.ultimo
        v = verificar(t, r.final, locales.conn, r.estado)
        acciones = Counter(d.accion for d in est.decisiones)
        fila = {"id": t["id"], "rep": repeticion, "tipo": t["tipo"], "sesion": sesion, "corrida": r.corrida, "estado": r.estado, "esperado": t["estado_esperado"],
                "exito": v["exito"], "motivo": r.motivo, "pasos": r.pasos, "herramientas": r.herramientas,
                "tokens": r.tokens_in + r.tokens_out, "usd": round(est.gasto.usd, 8), "usd_del_bucle": round(r.costo_usd, 8),
                "decisiones": dict(acciones), "modelos": dict(Counter(est.modelos)), "max_tokens_minimo": min((d.max_tokens for d in est.decisiones if d.accion != "stop"), default=None),
                "subestimaciones": len(est.subestimaciones), "sobregasto": len(est.sobregasto), "segundos": r.segundos}
        with candado:
            filas.append(fila)
            estados.append(est)
            print(f"{t['id']:<8} {t['tipo']:<13} {r.estado:<19} exito={'si' if v['exito'] else 'NO':<3} pasos={r.pasos:<2} ${est.gasto.usd:.5f} "
                  f"{r.motivo}  [acumulado ${sum(f['usd'] for f in filas):.4f}]", flush=True)

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, i, w) for i, w in enumerate(trabajos)]):
                fut.result()
    finally:
        for c in conexiones:
            c.close()
    segundos = round(time.time() - t0, 1)
    filas.sort(key=lambda f: (f["id"], f["rep"]))

    spans = resumen(exp.get_finished_spans())
    agentes = {s["attrs"].get("lab.run.id"): s for s in spans if s["name"].startswith("invoke_agent")}
    eventos_ok = all(
        f["corrida"] in agentes and
        sum(1 for e in agentes[f["corrida"]]["eventos"] if e["name"] == E.EVENTO_PRESUPUESTO) == sum(f["decisiones"].values())
        for f in filas)
    hoy = time.strftime("%Y-%m-%d", time.gmtime())
    por_sesion: dict[str, float] = defaultdict(float)
    for f in filas:
        por_sesion[f["sesion"]] += f["usd"]
    total = sum(f["usd"] for f in filas)
    contable = {
        "dia_del_tenant_en_el_almacen": round(almacen.gastado(("tenant_day", TENANT, hoy)).usd, 8),
        "suma_de_las_tareas": round(total, 8),
        "sesiones_en_el_almacen": {s: round(almacen.gastado(("session", s, "")).usd, 8) for s in sorted(por_sesion)},
        "reservas_vivas": almacen.reservado()}
    coincide = abs(contable["dia_del_tenant_en_el_almacen"] - total) < 1e-6 and all(
        abs(contable["sesiones_en_el_almacen"][s] - v) < 1e-6 for s, v in por_sesion.items())
    parciales = [f for f in filas if f["motivo"].startswith("presupuesto_")]
    usd = [f["usd"] for f in filas]
    informe = {
        "fecha": time.strftime("%Y-%m-%d"), "modo": "modelo real" if real else "reproduccion de la semana 13 (sin modelo)",
        "modelo": MODELO, "esfuerzo": ESFUERZO, "tareas": len(filas), "repeticiones": a.repeticiones, "paralelo": a.paralelo,
        "segundos": segundos,
        "politica": json.loads((S17 / "presupuestos" / "politica_calibrada.json").read_text(encoding="utf-8")),
        "resultado": {
            "exito": round(sum(f["exito"] for f in filas) / len(filas), 4), "exitos": sum(f["exito"] for f in filas),
            "respuestas_parciales": len(parciales), "motivos_de_parada": dict(Counter(f["motivo"] for f in parciales)),
            "de_ellas_esperaban_responder": sum(1 for f in parciales if f["esperado"] == "respondida"),
            "estados": dict(Counter(f["estado"] for f in filas)),
            "decisiones": dict(sum((Counter(f["decisiones"]) for f in filas), Counter())),
            "modelos_de_las_llamadas": dict(sum((Counter(f["modelos"]) for f in filas), Counter())),
            "por_tipo": {tipo: {"tareas": len(g), "exito": round(sum(x["exito"] for x in g) / len(g), 3),
                                "parciales": sum(1 for x in g if x["motivo"].startswith("presupuesto_"))}
                         for tipo, g in sorted({k: [f for f in filas if f["tipo"] == k] for k in {f["tipo"] for f in filas}}.items())}},
        "costo": {"total_usd": round(total, 6), "por_tarea": {"media": round(total / len(filas), 6), "p50": round(CAL.percentil(usd, 50), 6),
                                                              "p95": round(CAL.percentil(usd, 95), 6), "max": round(max(usd), 6)},
                  "estimado_antes_usd": round(estimado, 4), "maximo_posible_usd": politica.tenant_dia.usd},
        "garantias": {
            "ninguna_tarea_pasa_de_su_tope": max(usd) <= politica.tarea.usd + 1e-12, "gasto_maximo_de_una_tarea_usd": round(max(usd), 8),
            "tokens_maximos_de_una_tarea": max(f["tokens"] for f in filas),
            "ninguna_sesion_pasa_de_su_tope": max(por_sesion.values()) <= politica.sesion.usd + 1e-12,
            "gasto_maximo_de_una_sesion_usd": round(max(por_sesion.values()), 8),
            "el_dia_no_pasa_de_su_tope": total <= politica.tenant_dia.usd + 1e-12,
            "subestimaciones_de_la_entrada": sum(f["subestimaciones"] for f in filas),
            "llamadas_mas_caras_que_su_estimado": sum(f["sobregasto"] for f in filas),
            "gasto_del_bucle_igual_al_del_presupuesto": all(abs(f["usd"] - f["usd_del_bucle"]) < 1e-6 for f in filas),
            "un_evento_por_decision": eventos_ok, "omisiones_del_esquema": dict(E.OMITIDOS),
            "contabilidad": contable, "la_contabilidad_coincide": coincide},
        "base_semana_13": base_semana_13(),
        "tareas_cortadas": [{k: f[k] for k in ("id", "tipo", "esperado", "motivo", "pasos", "tokens", "usd")} for f in parciales],
        "por_corrida": [{k: f[k] for k in ("id", "rep", "estado", "exito", "motivo", "pasos", "tokens", "usd", "decisiones", "modelos",
                                           "max_tokens_minimo")} for f in filas]}
    if a.degradar:
        llamadas_caras = sum(f["modelos"].get(CARO, 0) for f in filas)
        informe["degradacion"] = {
            "modelo_del_agente": CARO, "modelo_barato": MODELO, "corridas": len(filas),
            "corridas_con_una_degradacion": sum(1 for f in filas if f["decisiones"].get("degrade", 0) == 1),
            "llamadas_hechas_con_el_modelo_caro": llamadas_caras,
            "costo_de_la_corrida_al_precio_del_modelo_que_respondio": all(abs(f["usd"] - f["usd_del_bucle"]) < 1e-6 for f in filas),
            "ok": bool(llamadas_caras == 0 and all(f["decisiones"].get("degrade", 0) == 1 for f in filas))}
    g = informe["garantias"]
    informe["ok"] = bool(g["ninguna_tarea_pasa_de_su_tope"] and g["ninguna_sesion_pasa_de_su_tope"] and g["el_dia_no_pasa_de_su_tope"]
                         and g["subestimaciones_de_la_entrada"] == 0 and g["llamadas_mas_caras_que_su_estimado"] == 0
                         and g["gasto_del_bucle_igual_al_del_presupuesto"] and g["un_evento_por_decision"] and not g["omisiones_del_esquema"]
                         and g["la_contabilidad_coincide"] and g["contabilidad"]["reservas_vivas"] == 0
                         and (not a.degradar or informe["degradacion"]["ok"]))
    salida.write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    r = informe["resultado"]
    print(f"\nsuccess {r['exitos']}/{len(filas)} · partial answers {r['respuestas_parciales']} · cost ${total:.4f} "
          f"(expected ${estimado:.3f}) · max per task ${max(usd):.5f} (cap ${politica.tarea.usd}) · ok={informe['ok']}")
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
