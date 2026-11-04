"""Week 17, activity 7 (part 2): the trajectory eval on the trace, with the scores written back to Langfuse.

    cd semana-17
    uv run --group semana17 python -m trayectorias.correr_eval                          # $0: week 13's recorded turns through the stack
    uv run --group semana17 python -m trayectorias.correr_eval --langfuse               # the same, exporting the traces and writing scores
    uv run --group semana17 python -m trayectorias.correr_eval --confirmo-gasto --langfuse   # Claude Haiku 5.5 `low`, about $0.24

The 84 golden tasks run through activity 5's agent (instrumented, budgeted, guardrails in the shipped audit mode). For each run:

1. the trajectory is rebuilt FROM THE SPANS (`execute_tool` spans: tool, `lab.step`, `lab.tool.status`, `lab.tool.args.hmac`; `chat` spans:
   the model steps), the same way it would be read from the Collector's file or from Langfuse;
2. it is checked against the loop's own trace lines of the same run (tools, turns, ok, steps), so the span adapter is validated on every
   run, not assumed;
3. the deterministic graders score it against the frozen reference (`referencias.jsonl`);
4. with `--langfuse`, the spans go to the Collector and on to Langfuse, the scores are written with `POST /api/public/scores` (one per
   grader with a pass rule, plus the composite and the overall verdict, on the run's trace id) and read back from the public API.

No LLM judge: every grader here is decided by code. The report says what a judge would be needed for and why it was not built.
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
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from guardrails.agente import AgenteGuardado  # noqa: E402
from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import cerrar_trazas, configurar_trazas, resumen  # noqa: E402
from presupuestos.almacen import AlmacenGasto  # noqa: E402
from presupuestos.correr_eval import ESFUERZO, MODELO, TAREAS_POR_SESION, TENANT, Reproduccion  # noqa: E402
from presupuestos.politica import Politica  # noqa: E402
from trayectorias import adaptadores as AD  # noqa: E402
from trayectorias import construir_referencias as CR  # noqa: E402
from trayectorias import criterios as C  # noqa: E402
from trayectorias.evaluadores import Llamada, Trayectoria, evaluar, normalizar  # noqa: E402

from agente.correr import cargar_tareas  # noqa: E402
from agente.loop import api_anthropic  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402

LANGFUSE = "http://127.0.0.1:3100"
OTLP_HTTP = "http://127.0.0.1:4318/v1/traces"
PREFIJO_SCORE = "trayectoria."


def desde_spans(spans_de_una_traza: list[dict]) -> Trayectoria:
    """The trajectory of one run from its spans (`laboratorio.resumen` shape, the shape the OTLP file and Langfuse carry too).
    Blocked calls never became an `execute_tool` span (the guardrails sit outside the instrumented tools), and `responder` is not a
    tool span: both are absent here by construction."""
    herramientas = sorted((s for s in spans_de_una_traza if s["name"].startswith("execute_tool ")), key=lambda s: s["inicio"])
    chats = [s for s in spans_de_una_traza if s["name"].startswith("chat ")]
    llamadas = tuple(Llamada(normalizar(s["name"][len("execute_tool "):]), s["attrs"].get("lab.tool.status") == "ok",
                             int(s["attrs"].get("lab.step") or 1), s["attrs"].get("lab.tool.args.hmac"))
                     for s in herramientas)
    return Trayectoria(llamadas, max(1, len(chats), max((c.turno for c in llamadas), default=1)))


def comparar_con_el_bucle(desde_traza: Trayectoria, lineas: list[dict]) -> list[str]:
    """Differences between the span trajectory and the loop's own lines of the same run (without `responder`, which has no span)."""
    del_bucle = AD.desde_traza_del_bucle(lineas)
    a = [(c.herramienta, c.ok, c.turno) for c in desde_traza.llamadas]
    b = [(normalizar(c.herramienta), c.ok, c.turno) for c in del_bucle.llamadas if normalizar(c.herramienta) != C.HERRAMIENTA_DE_ENTREGA]
    dif = []
    if a != b:
        dif.append("llamadas")
    if desde_traza.pasos != del_bucle.pasos:
        dif.append("pasos")
    return dif


def con_responder(t: Trayectoria, lineas: list[dict]) -> Trayectoria:
    """The span trajectory plus the `responder` calls of the loop's lines (the only tool with no span), for the graders that look at
    failures and recovery of the final answer."""
    extra = [c for c in AD.desde_traza_del_bucle(lineas).llamadas if normalizar(c.herramienta) == C.HERRAMIENTA_DE_ENTREGA]
    todas = sorted(list(t.llamadas) + extra, key=lambda c: c.turno)
    return Trayectoria(tuple(todas), t.pasos)


# ---------- Langfuse ----------

def _auth() -> str:
    import importlib.util
    spec = importlib.util.spec_from_file_location("verificar_stack_s17_t", S17 / "observabilidad" / "verificar_stack.py")
    vs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vs)
    return vs.auth_langfuse(), vs.peticion


def scores_de(traza: str, res: dict) -> list[dict]:
    out = [{"name": PREFIJO_SCORE + "puntaje", "value": res["puntaje"], "dataType": "NUMERIC"},
           {"name": PREFIJO_SCORE + "ok", "value": 1 if res["ok"] else 0, "dataType": "BOOLEAN"}]
    out += [{"name": PREFIJO_SCORE + n, "value": res["notas"][n]["puntaje"], "dataType": "NUMERIC"} for n in C.EVALUADORES_CON_REGLA]
    for s in out:      # idempotent: the same trace and score name always get the same id, so a rerun overwrites
        s.update(traceId=traza, id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{traza}/{s['name']}")), source="API")
    return out


def escribir_y_leer_scores(por_traza: dict[str, dict], espera_s: int = 180) -> dict:
    auth, peticion = _auth()
    escritos, errores = 0, Counter()
    for traza, res in por_traza.items():
        for s in scores_de(traza, res):
            codigo, _ = peticion(f"{LANGFUSE}/api/public/scores", auth, s)
            if codigo in (200, 201):
                escritos += 1
            else:
                errores[codigo] += 1
    # read back with the v3 API (cursor pagination). A v3 score carries no trace id by default, so each one is matched by its id, which is
    # derived from (trace, name): the score read for a trace is exactly the one written for it.
    ids_ok = {str(uuid.uuid5(uuid.NAMESPACE_URL, f"{t}/{PREFIJO_SCORE}ok")): (t, res["ok"]) for t, res in por_traza.items()}
    leidos, limite, codigo = {}, time.time() + espera_s, None
    while time.time() < limite:
        leidos, cursor = {}, None
        while True:
            url = f"{LANGFUSE}/api/public/v3/scores?name={PREFIJO_SCORE}ok&limit=100" + (f"&cursor={cursor}" if cursor else "")
            codigo, cuerpo = peticion(url, auth)
            if codigo != 200:
                break
            for d in cuerpo.get("data") or []:
                if d.get("id") in ids_ok:
                    leidos[d["id"]] = d.get("value")
            cursor = (cuerpo.get("meta") or {}).get("cursor")
            if not cursor or not cuerpo.get("data"):
                break
        if len(leidos) == len(ids_ok):
            break
        time.sleep(5)
    coinciden = sum(1 for i, (t, ok) in ids_ok.items() if i in leidos and bool(leidos[i]) == ok)
    esperados = sum(len(scores_de(t, res)) for t, res in por_traza.items())
    return {"escritos": escritos, "esperados": esperados, "errores_http": dict(errores), "lectura_api": "v3" if codigo == 200 else None,
            "trazas_con_score_leido": len(leidos), "valores_que_coinciden": coinciden, "trazas": len(por_traza)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirmo-gasto", action="store_true", help="real model; costs money")
    ap.add_argument("--langfuse", action="store_true", help="export the spans to the Collector and write the scores to Langfuse")
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--tareas", nargs="*")
    ap.add_argument("--salida")
    a = ap.parse_args(argv)
    real = a.confirmo_gasto
    if real and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = not real
    exp = configurar_trazas(OTLP_HTTP if a.langfuse else None)
    refs = CR.cargar()
    politica = Politica.desde_archivo()
    trabajos = cargar_tareas(a.tareas, ["es", "en"])
    reproduccion = None if real else Reproduccion()
    almacen = AlmacenGasto(Path(tempfile.mkdtemp(prefix="gasto-s17-t-")) / "gasto.sqlite")
    dir_trazas = Path(tempfile.mkdtemp(prefix="trazas-s17-t-"))
    conn0, _ = conectar()
    locales, candado, conexiones, filas = threading.local(), threading.Lock(), [conn0], []
    print(f"{len(trabajos)} runs · {'REAL model' if real else 'replay of week 13 turns'} · langfuse={'on' if a.langfuse else 'off'}", flush=True)

    def una(indice: int, t: dict):
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
            with candado:
                conexiones.append(locales.conn)
        herramientas = Herramientas(Contexto.de_usuario("analista", conexion=locales.conn, idioma=t["lang"]))
        api = api_anthropic if real else reproduccion.para(t["id"])
        lineas = dir_trazas / f"{t['id']}.jsonl"
        agente = AgenteGuardado(herramientas, api=api, tenant=TENANT, politica=politica, almacen=almacen, modelo=MODELO,
                                esfuerzo=ESFUERZO, simulado=not real, trazas=lineas)
        r = agente.resolver({**t, "rep": 0}, "analista", sesion=f"sesion-{indice // TAREAS_POR_SESION:02d}")
        v = verificar(t, r.final, locales.conn, r.estado)
        with candado:
            filas.append({"id": t["id"], "tipo": t["tipo"], "corrida": r.corrida, "estado": r.estado, "exito": v["exito"], "pasos": r.pasos,
                          "usd": round(agente.ultimo.gasto.usd, 8)})

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, i, t) for i, t in enumerate(trabajos)]):
                fut.result()
    finally:
        for c in conexiones:
            c.close()
    cerrar_trazas()
    spans = resumen(exp.get_finished_spans())
    por_traza: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        por_traza[s["trace"]].append(s)
    traza_de = {s["attrs"].get("lab.run.id"): s["trace"] for s in spans if s["name"].startswith("invoke_agent")}
    resultados, puntuados, adaptador = [], {}, Counter()
    for f in sorted(filas, key=lambda x: x["id"]):
        traza = traza_de[f["corrida"]]
        lineas = AD.por_corrida(CR.leer_jsonl(dir_trazas / f"{f['id']}.jsonl"))[f["corrida"]]
        t = desde_spans(por_traza[traza])
        dif = comparar_con_el_bucle(t, lineas)
        adaptador["igual" if not dif else "+".join(dif)] += 1
        res = evaluar(refs[f["id"]], con_responder(t, lineas))
        puntuados[traza] = res
        resultados.append({**f, "traza": traza, "trayectoria_ok": res["ok"], "puntaje": res["puntaje"], "fallan": res["fallan"],
                           "adaptador": dif})
    n = len(resultados)
    cruce = Counter(f"trayectoria_{'ok' if x['trayectoria_ok'] else 'falla'}__respuesta_{'ok' if x['exito'] else 'falla'}" for x in resultados)
    por_tipo = defaultdict(list)
    for x in resultados:
        por_tipo[x["tipo"]].append(x["trayectoria_ok"])
    informe = {
        "fecha": time.strftime("%Y-%m-%d"), "modo": "modelo real" if real else "reproduccion de la semana 13 (sin modelo)",
        "modelo": MODELO, "esfuerzo": ESFUERZO, "tareas": n, "segundos": round(time.time() - t0, 1),
        "adaptador_de_spans_contra_lineas_del_bucle": dict(adaptador),
        "trayectoria_ok": round(sum(x["trayectoria_ok"] for x in resultados) / n, 4),
        "puntaje_medio": round(sum(x["puntaje"] for x in resultados) / n, 4),
        "exito_respuesta": sum(x["exito"] for x in resultados),
        "fallas_por_evaluador": dict(Counter(e for x in resultados for e in x["fallan"]).most_common()),
        "ok_por_tipo": {k: round(sum(v) / len(v), 4) for k, v in sorted(por_tipo.items())},
        "cruce_con_la_respuesta": dict(sorted(cruce.items())),
        "costo_usd": round(sum(x["usd"] for x in resultados), 6) if real else 0.0,
        "langfuse": escribir_y_leer_scores(puntuados) if a.langfuse else None,
        "omisiones_del_esquema": dict(E.OMITIDOS),
        "por_tarea": resultados,
    }
    salida = Path(a.salida) if a.salida else S17 / "resultados" / ("trayectorias_real.json" if real else "trayectorias_reproduccion.json")
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"adapter vs loop lines {dict(adaptador)} · trajectory ok {informe['trayectoria_ok']:.1%} · answers ok {informe['exito_respuesta']}/{n} · "
          f"failing {informe['fallas_por_evaluador']} · cost ${informe['costo_usd']} · langfuse {informe['langfuse']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
