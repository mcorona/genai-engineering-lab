"""Week 17, activity 4: where do the budget decisions end up? ($0, scripted model). Mac only (needs the activity 2 stack).

    ./semana-17/observabilidad/arrancar.sh
    cd semana-17 && uv run --group semana17 python -m presupuestos.verificar_langfuse [--salida resultados/presupuestos_langfuse.json]

Four scripted tasks run through the real loop, MCP client, OAuth-protected server and PostgreSQL, with the budget on, and their
spans go to the Collector (redaction, then Langfuse and the JSONL file):

  * `permite`      room to spare: three `allow` decisions;
  * `degrada`      the policy names a cheaper model: the first decision is `degrade`;
  * `para_tarea`   the task budget is spent: `allow`, then `stop` with a partial answer;
  * `para_sesion`  two tasks of one session: the second one stops before any model call.

For each one it compares three places: the span events the lab recorded, the same events in the Collector's output file, and
what Langfuse stored (observations, types, level, the outcome of the agent, the model and cost of each generation). The report
has numbers and ids only: no prompt, SQL, answer or secret.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import sys
import tempfile
import time
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion import verificar_langfuse as VL  # noqa: E402
from instrumentacion.laboratorio import Laboratorio, cerrar_trazas, configurar_trazas, resumen  # noqa: E402
from instrumentacion.modelo_guionado import turnos_principal  # noqa: E402
from presupuestos.agente_presupuestado import AgentePresupuestado  # noqa: E402
from presupuestos.almacen import AlmacenGasto  # noqa: E402
from presupuestos.politica import Limite, Politica  # noqa: E402

vs = VL.vs
M, S = "claude-haiku-5-5", "claude-sonnet-5-5"
TOPE_DE_LA_TAREA = Limite(0.0011, 10**6)        # call 1 fits (about $0.0005); call 2 would need about $0.00075 and $0.0006 is left
CLAVES_DE_COMPARACION = ("lab.budget.decision", "lab.budget.scope", "lab.budget.reason", "lab.budget.step", "lab.budget.spent_usd",
                         "lab.budget.limit_usd", "lab.budget.max_tokens", "gen_ai.request.model")


def turnos(usos=((3000, 400), (3600, 500), (4200, 300))):
    ts = turnos_principal()
    for t, (i, o) in zip(ts, usos):
        t["usage"] = {"input_tokens": i, "output_tokens": o}
    return ts


def _valor(v: dict):
    return next(iter(v.values())) if len(v) == 1 else v


def spans_del_archivo(traza: str, espera: int = 90) -> list[dict]:
    """The spans of one trace as the Collector wrote them (OTLP JSON, one request per line; the file holds every earlier run too,
    and a request can mix traces, so the spans are picked one by one)."""
    archivo, t0 = vs.DATOS / "trazas.jsonl", time.time()
    while True:
        encontrados = []
        for linea in (archivo.read_text() if archivo.exists() else "").splitlines():
            if traza not in linea:
                continue
            for rs in json.loads(linea).get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []):
                    encontrados += [sp for sp in ss.get("spans", []) if sp.get("traceId") == traza]
        if encontrados or time.time() - t0 > espera:
            return encontrados
        time.sleep(3)


def eventos_de(spans: list[dict]) -> list[dict]:
    return sorted(({"t": int(e["timeUnixNano"]), "nombre": e["name"], "attrs": {a["key"]: _valor(a["value"]) for a in e.get("attributes", [])}}
                   for sp in spans for e in sp.get("events", [])), key=lambda e: e["t"])


def _numero(x):
    return float(x) if isinstance(x, (int, float, str)) and str(x).replace(".", "", 1).replace("-", "", 1).isdigit() else x


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(S17 / "resultados" / "presupuestos_langfuse.json"))
    a = ap.parse_args(argv)
    if vs.peticion("http://127.0.0.1:3100/api/public/health")[0] != 200 or vs.peticion("http://127.0.0.1:13133/")[0] != 200:
        print("[verificar] the stack is not up: run semana-17/observabilidad/arrancar.sh first", file=sys.stderr)
        return 2
    auth = vs.auth_langfuse()
    os.environ["LAB_OBS_SALT"] = secrets.token_hex(16)
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
    E.ESTRICTO = True
    exp = configurar_trazas(otlp_http=VL.OTLP)
    almacen = AlmacenGasto(Path(tempfile.mkdtemp(prefix="gasto-s17-")) / "gasto.sqlite")
    canario = VL.CANARIOS["prompt"]
    tarea = {**VL.TAREA, "tarea": f"{VL.TAREA['tarea']} {canario}"}

    corridas: dict[str, dict] = {}
    with Laboratorio(tenant="lab") as lab:
        def correr(nombre, politica, **kw):
            exp.clear()
            r, modelo, _ = lab.correr(turnos(), agente_clase=AgentePresupuestado, politica=politica, almacen=almacen, tarea=tarea, **kw)
            VL.estable(exp)
            spans = resumen(exp.get_finished_spans())
            raiz = next(s for s in spans if s["name"].startswith("invoke_agent"))
            propios = [s for s in spans if s["trace"] == raiz["trace"]]
            corridas[nombre] = {"r": r, "modelo": modelo, "spans": propios, "raiz": raiz,
                                "eventos": [e for s in propios for e in s["eventos"] if e["name"] == E.EVENTO_PRESUPUESTO]}
            print(f"[verificar] {nombre}: {r.estado}/{r.motivo}, {len(propios)} spans, {len(corridas[nombre]['eventos'])} decisions")

        correr("permite", Politica(Limite(0.01, 150_000), min_salida=500))
        correr("degrada", Politica(Limite(0.01, 10**6), min_salida=500, degradar={S: M}), modelo=S)
        correr("para_tarea", Politica(TOPE_DE_LA_TAREA, min_salida=500))
        sesion = Politica(Limite(0.01, 10**6), sesion=Limite(0.0012, 10**6), min_salida=500)
        correr("para_sesion_1", sesion, sesion="s-verificar")
        correr("para_sesion_2", sesion, sesion="s-verificar")
        tokens = list(lab.entorno._tokens.values())
    cerrar_trazas()

    informe = {"fecha": time.strftime("%Y-%m-%d"), "plataforma": platform.platform(terse=True), "modelo": "guionado (sin API, $0)",
               "escenarios": {}}
    todo_ok, textos, textos_archivo = True, [], []
    for nombre, c in corridas.items():
        spans, r, ev = c["spans"], c["r"], c["eventos"]
        traza = c["raiz"]["trace"]
        spans_archivo = spans_del_archivo(traza)
        textos_archivo.append(json.dumps(spans_archivo))
        en_archivo = [e for e in eventos_de(spans_archivo) if e["nombre"] == E.EVENTO_PRESUPUESTO]
        obs = VL.leer_langfuse(traza, auth, len(spans))
        por_id = {o["id"]: o for o in obs}
        textos.append(json.dumps(obs, default=str))
        ids_ok = len(obs) == len(spans) and all(s["span"] in por_id for s in spans)
        tipos_ok = ids_ok and all(por_id[s["span"]]["type"] == VL.tipo_esperado(s) for s in spans)
        raiz_lf = por_id[c["raiz"]["span"]] if ids_ok else {}
        meta = raiz_lf.get("metadata") or {}
        # the events in the file are the events the lab recorded: same order, same values, all 13 keys
        archivo_igual = (len(en_archivo) == len(ev) and all(
            set(f["attrs"]) == set(e["attrs"]) and all(_numero(f["attrs"][k]) == _numero(e["attrs"][k]) for k in CLAVES_DE_COMPARACION)
            for f, e in zip(en_archivo, ev)))
        # Langfuse: the outcome of the agent and the model and cost of each generation
        resultado_ok = (ids_ok and meta.get("attributes.lab.outcome.status") == c["raiz"]["attrs"]["lab.outcome.status"]
                        and meta.get("attributes.lab.outcome.reason") == c["raiz"]["attrs"]["lab.outcome.reason"]
                        and (raiz_lf.get("level") == "ERROR") == (c["raiz"]["estado"] == "ERROR"))
        generaciones = [por_id[s["span"]] for s in spans if s["name"].startswith("chat ") and ids_ok and s["estado"] != "ERROR"]
        modelos_lf = [g["model"] for g in generaciones]
        modelos_lab = [s["attrs"]["gen_ai.request.model"] for s in spans if s["name"].startswith("chat ")]
        costo_lf = sum(g["costDetails"]["total"] for g in generaciones)
        costo_ok = ids_ok and abs(costo_lf - c["raiz"]["attrs"]["lab.run.cost_usd"]) < 1e-7
        modelos_ok = ids_ok and sorted(modelos_lf) == sorted(modelos_lab)
        en_langfuse = any(E.EVENTO_PRESUPUESTO in json.dumps(o, default=str) for o in obs)
        ok = all([ids_ok, tipos_ok, archivo_igual, resultado_ok, costo_ok, modelos_ok, len(ev) >= 1])
        informe["escenarios"][nombre] = {
            "estado_agente": r.estado, "motivo": r.motivo, "spans": len(spans), "observaciones_en_langfuse": len(obs),
            "decisiones": [e["attrs"]["lab.budget.decision"] for e in ev],
            "alcances": sorted({e["attrs"]["lab.budget.scope"] for e in ev}), "motivos": [e["attrs"]["lab.budget.reason"] for e in ev],
            "eventos_en_el_archivo_del_collector": len(en_archivo), "eventos_del_archivo_iguales_a_los_del_laboratorio": archivo_igual,
            "claves_por_evento": sorted({len(e["attrs"]) for e in en_archivo}),
            "eventos_en_langfuse": en_langfuse, "tipos_correctos": tipos_ok, "resultado_del_agente_en_langfuse_igual": resultado_ok,
            "modelos_de_las_generaciones_en_langfuse_iguales": modelos_ok, "modelos": modelos_lab,
            "costo_en_langfuse_igual_al_del_agente": costo_ok, "ok": bool(ok)}
        todo_ok = todo_ok and bool(ok)
        print(f"[verificar] {nombre}: file {len(en_archivo)}/{len(ev)} events, Langfuse events={en_langfuse}, ok={ok}")

    trazas = {c["raiz"]["trace"] for c in corridas.values()}
    texto_archivo = "\n".join(textos_archivo)           # only the spans of this run's traces: the file also holds earlier runs
    privados = {"canario": [canario], "token": tokens}
    fugas = sorted(f"{k} en {donde}" for k, vs_ in privados.items() for v in vs_ if v
                   for donde, texto in (("langfuse", "\n".join(textos)), ("archivo", texto_archivo)) if v in texto)
    informe["canarios"] = {"revisados": len(privados["canario"]) + len(tokens), "fugas": fugas}
    informe["trazas_revisadas"] = len(trazas)
    informe["los_eventos_llegan_a_langfuse"] = any(e["eventos_en_langfuse"] for e in informe["escenarios"].values())
    informe["ok"] = bool(todo_ok and not fugas)
    Path(a.salida).write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[verificar] ok={informe['ok']} · events in Langfuse: {informe['los_eventos_llegan_a_langfuse']} · leaks: {len(fugas)}")
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
