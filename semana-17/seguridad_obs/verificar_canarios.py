"""Week 17, activity 9: canaries through the whole path, with message content capture OFF and ON ($0, scripted model, stack up).

    cd semana-17 && uv run --group semana17 python -m seguridad_obs.verificar_canarios

The seven canaries of activity 2 (a DSN, an OAuth token, a bearer token, an API key, an email, a phone, an RFC tax id) are seeded in:

* the PROMPT (the task text),
* a TOOL ARGUMENT (an SQL literal),
* a TOOL RESULT (a note inserted in `legado.artnot` for the run and deleted after it),
* the MODEL'S ANSWER,
* and a span from a library that DOES capture content (what Strands does by default, activity 3): `gen_ai.input.messages`,
  `gen_ai.output.messages`, `gen_ai.system_instructions`, a list attribute and a `gen_ai.user.message` event, plus an ALLOWED key
  (`lab.task.id`) carrying a canary, which only the patterns can catch.

The agent is activity 3's instrumented loop with NO guardrails (the worst case: activity 5 would redact the answer). Each mode runs in
its own process (the tracer provider is global). Then the canaries are searched in the Collector's file and in Langfuse (observations
with their input, output and metadata). No threshold: one canary anywhere fails it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

NOTA_ID, SKU = 990002, "SKU-0042"
RESULTADOS = S17 / "resultados"


def _vs():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verificar_stack_s17_c", S17 / "observabilidad" / "verificar_stack.py")
    vs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vs)
    return vs


def una_corrida(modo: str) -> dict:
    """One process: the traced run and the capturing library's span. Prints the trace ids."""
    os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "gen_ai_latest_experimental"
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "SPAN_AND_EVENT" if modo == "on" else "NO_CONTENT"
    import psycopg
    from opentelemetry import trace
    from instrumentacion.laboratorio import Laboratorio, cerrar_trazas, configurar_trazas
    from instrumentacion.modelo_guionado import final_ok
    from instrumentacion.trazas_agente import AgenteInstrumentado
    vs = _vs()
    todos = " | ".join(v for v, _ in vs.CANARIOS.values())
    exp = configurar_trazas("http://127.0.0.1:4318/v1/traces")
    dsn = os.environ["PG_ADMIN_DSN"]
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("DELETE FROM legado.artnot WHERE not_id = %s", (NOTA_ID,))
        c.execute("INSERT INTO legado.artnot (not_id, not_art, not_txt, not_fch) VALUES (%s, %s, %s, DATE '2026-11-01')", (NOTA_ID, SKU, todos))
    try:
        u = {"input_tokens": 400, "output_tokens": 60}
        turnos = [{"herramientas": [("legado__ejecutar_sql", {"sql": f"SELECT art_cd FROM artmst WHERE art_dsc = '{vs.CANARIOS['email'][0]}'"})], "usage": u},
                  {"herramientas": [("legado__ejecutar_sql", {"sql": f"SELECT not_txt FROM artnot WHERE not_art = '{SKU}'"})], "usage": u},
                  {"final": final_ok(f"La nota dice: {todos}"), "usage": u}]
        with Laboratorio() as lab:
            r, _, _ = lab.correr(turnos, tarea={"id": f"canario-{modo}", "lang": "es", "tarea": f"Revisa la nota de {SKU}. Contexto: {todos}"},
                                 agente_clase=AgenteInstrumentado)
        # a library that captures content, on the same Collector
        tracer = trace.get_tracer("biblioteca-que-captura")
        with tracer.start_as_current_span("chat modelo-de-otra-biblioteca") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.input.messages", json.dumps([{"role": "user", "parts": [{"type": "text", "content": todos}]}]))
            span.set_attribute("gen_ai.output.messages", json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": todos}]}]))
            span.set_attribute("gen_ai.system_instructions", todos)
            span.set_attribute("biblioteca.lista", [v for v, _ in vs.CANARIOS.values()])
            span.set_attribute("lab.task.id", vs.CANARIOS["email"][0])          # an ALLOWED key with a canary: the patterns' job
            span.add_event("gen_ai.user.message", {"content": todos, "role": "user"})
            otra = format(span.get_span_context().trace_id, "032x")
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("DELETE FROM legado.artnot WHERE not_id = %s", (NOTA_ID,))
    agente = [s for s in exp.get_finished_spans() if s.name.startswith("invoke_agent")][-1]
    cerrar_trazas()
    return {"modo": modo, "agente": format(agente.context.trace_id, "032x"), "biblioteca": otra, "estado": r.estado}


def buscar(trazas: dict[str, str], espera_s: int = 120) -> dict:
    vs = _vs()
    from tablero import fuentes as F
    auth, peticion = vs.auth_langfuse(), vs.peticion
    out = {}
    for nombre, traza in trazas.items():
        lineas, obs, t0 = [], [], time.time()
        while time.time() - t0 < espera_s:
            lineas = [x for x in F.ARCHIVO.read_text(encoding="utf-8").splitlines() if traza in x]
            c, b = peticion(f"http://127.0.0.1:3100/api/public/v2/observations?traceId={traza}&fields=core,basic,io,metadata&limit=100", auth)
            obs = (b.get("data") or []) if c == 200 else []
            if lineas and obs:
                break
            time.sleep(3)
        texto_archivo, texto_langfuse = "\n".join(lineas), json.dumps(obs, ensure_ascii=False)
        spans = F.spans_del_archivo({traza})
        claves = sorted({k for s in spans for k in s["attrs"]} | {k for s in spans for e in s["eventos"] for k in e["attrs"]})
        out[nombre] = {"spans_en_archivo": len(spans), "observaciones_en_langfuse": len(obs),
                       "canarios_en_archivo": vs.filtrados(texto_archivo, {**vs.CANARIOS, **vs.CANARIOS_LISTA}),
                       "canarios_en_langfuse": vs.filtrados(texto_langfuse, {**vs.CANARIOS, **vs.CANARIOS_LISTA}),
                       "claves_de_contenido_que_llegaron": [k for k in claves if k in ("gen_ai.input.messages", "gen_ai.output.messages",
                                                                                      "gen_ai.system_instructions", "biblioteca.lista", "content")],
                       "enmascarado_en_archivo": "****" in texto_archivo}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--una", choices=("on", "off"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.una:
        print("RESULTADO " + json.dumps(una_corrida(a.una)))
        return 0
    corridas = {}
    for modo in ("off", "on"):
        p = subprocess.run([sys.executable, "-m", "seguridad_obs.verificar_canarios", "--una", modo], cwd=S17, capture_output=True, text=True)
        linea = next((x for x in p.stdout.splitlines() if x.startswith("RESULTADO ")), None)
        if linea is None:
            print(p.stderr[-1500:], file=sys.stderr)
            return 1
        corridas[modo] = json.loads(linea[len("RESULTADO "):])
    informe = {"fecha": time.strftime("%Y-%m-%d"), "canarios": sorted({**_vs().CANARIOS, **_vs().CANARIOS_LISTA}),
               "sembrados_en": ["prompt", "tool argument", "tool result", "model answer", "a capturing library's span: content attributes, a list, an event, an allowed key"],
               "por_modo": {m: {"captura_de_contenido": "SPAN_AND_EVENT" if m == "on" else "NO_CONTENT", "estado_del_agente": c["estado"],
                                **buscar({"agente": c["agente"], "biblioteca": c["biblioteca"]})} for m, c in corridas.items()}}
    informe["ok"] = all(not v["canarios_en_archivo"] and not v["canarios_en_langfuse"] and not v["claves_de_contenido_que_llegaron"]
                        and v["spans_en_archivo"] > 0 and v["observaciones_en_langfuse"] > 0
                        for m in informe["por_modo"].values() for k, v in m.items() if isinstance(v, dict))
    (RESULTADOS / "seguridad_obs_canarios.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
