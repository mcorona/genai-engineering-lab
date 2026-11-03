"""Week 17, optional of activity 2: tail sampling measured end to end on the Mac ($0, no model call).

    ./arrancar.sh                       (the stack must be up)
    uv run --group semana17 python semana-17/observabilidad/verificar_muestreo.py [--salida resultados/muestreo.json]

It restarts the Collector with `./arrancar.sh --muestreo`, sends synthetic traces of five kinds (ok, with an ERROR span, task
abstained, limit reached, slow) with a canary in an attribute, waits for the overlay's `decision_wait`, and reads what reached
Langfuse and the JSONL file. Then it puts the stack back in its default (keep everything) and checks that a batch of ok traces
arrives whole. It never prints a secret and the report has no local path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import verificar_stack as vs  # noqa: E402

COLECTOR = "s17-observabilidad-collector-1"
CANARIO = "ana.garcia@example.com"
MEZCLA = {"ok": 40, "con_error": 4, "abstenida": 3, "limite": 2, "lenta": 2}


def args_del_colector() -> list[str]:
    p = subprocess.run(["docker", "inspect", COLECTOR, "--format", "{{json .Args}}"], capture_output=True, text=True)
    return json.loads(p.stdout or "[]")


def arrancar(*opciones: str) -> None:
    p = subprocess.run([str(vs.ARRANCAR), *opciones], capture_output=True, text=True, timeout=600)
    if p.returncode:
        raise SystemExit(f"arrancar.sh {' '.join(opciones)} failed: {p.stderr[-300:]}")


def enviar(mezcla: dict) -> dict[str, set[str]]:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.trace import Status, StatusCode
    tp = TracerProvider(resource=Resource.create({"service.name": "legacybridge-muestreo"}))
    tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=vs.OTLP_HTTP, timeout=20)))
    tr = tp.get_tracer("muestreo")
    ids = {k: set() for k in mezcla}
    ahora = time.time_ns()
    estado_de = {"ok": "respondida", "con_error": "respondida", "abstenida": "abstenida", "limite": "limite_alcanzado",
                 "lenta": "respondida"}
    for clase, n in mezcla.items():
        for _ in range(n):
            inicio = ahora - (90 * 10**9 if clase == "lenta" else 0)
            raiz = tr.start_span("invoke_agent legacybridge", start_time=inicio, attributes={
                "gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "legacybridge",
                "lab.outcome.status": estado_de[clase], "prueba.canario": CANARIO})
            ids[clase].add(format(raiz.get_span_context().trace_id, "032x"))
            with trace.use_span(raiz, end_on_exit=False):
                hijo = tr.start_span("chat claude-haiku-5-5", start_time=inicio, attributes={
                    "gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",
                    "gen_ai.request.model": "claude-haiku-5-5", "gen_ai.usage.input_tokens": 100,
                    "gen_ai.usage.output_tokens": 10})
                if clase == "con_error":
                    hijo.set_status(Status(StatusCode.ERROR, "api_error"))
                hijo.end(end_time=ahora)
            raiz.end(end_time=ahora)
    tp.force_flush()
    tp.shutdown()
    return ids


def en_langfuse(traza: str, auth: str) -> bool:
    estado, cuerpo = vs.peticion(f"{vs.LANGFUSE}/api/public/v2/observations?traceId={traza}&fields=core,basic", auth)
    return estado == 200 and len(cuerpo.get("data", [])) >= 2


def esperar_a(condicion, espera: int) -> bool:
    t0 = time.time()
    while time.time() - t0 < espera:
        if condicion():
            return True
        time.sleep(5)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(vs.S17 / "resultados" / "muestreo.json"))
    a = ap.parse_args(argv)
    if vs.peticion(f"{vs.LANGFUSE}/api/public/health")[0] != 200:
        print("[muestreo] the stack is not up: run semana-17/observabilidad/arrancar.sh first", file=sys.stderr)
        return 2
    auth = vs.auth_langfuse()
    r: dict = {"fecha": time.strftime("%Y-%m-%d"), "mezcla": MEZCLA}

    # 1. with the overlay
    arrancar("--muestreo")
    r["capa_activa"] = any(x.endswith("muestreo.yaml") and "sin_" not in x for x in args_del_colector())
    t0 = time.time()
    ids = enviar(MEZCLA)
    todas = set().union(*ids.values())
    criticas = ids["con_error"] | ids["abstenida"] | ids["limite"] | ids["lenta"]
    llegaron = esperar_a(lambda: all(en_langfuse(t, auth) for t in criticas), 240)
    r["segundos_hasta_las_criticas"] = round(time.time() - t0)
    time.sleep(20)                                   # let the sampled ok traces arrive too before counting
    en_lf = {t for t in todas if en_langfuse(t, auth)}
    archivo = vs.DATOS / "trazas.jsonl"
    texto_archivo = archivo.read_text() if archivo.exists() else ""
    en_archivo = {t for t in todas if t in texto_archivo}
    por_clase = {c: {"enviadas": len(ids[c]), "en_langfuse": len(ids[c] & en_lf), "en_archivo": len(ids[c] & en_archivo)}
                 for c in MEZCLA}
    r["con_muestreo"] = {"por_clase": por_clase, "criticas_llegaron": llegaron,
                         "langfuse_igual_al_archivo": en_lf == en_archivo,
                         "canario_en_el_archivo": CANARIO in texto_archivo}

    # 2. back to the default: everything is kept
    arrancar()
    r["capa_por_omision"] = any(x.endswith("sin_muestreo.yaml") for x in args_del_colector())
    ids2 = enviar({"ok": 10})
    llegaron2 = esperar_a(lambda: all(en_langfuse(t, auth) for t in ids2["ok"]), 120)
    r["sin_muestreo"] = {"enviadas": 10, "en_langfuse": sum(en_langfuse(t, auth) for t in ids2["ok"]), "todas": llegaron2}

    c = r["con_muestreo"]["por_clase"]
    ok = (r["capa_activa"] and r["capa_por_omision"] and r["con_muestreo"]["criticas_llegaron"]
          and all(c[k]["en_langfuse"] == c[k]["enviadas"] == c[k]["en_archivo"] for k in ("con_error", "abstenida", "limite", "lenta"))
          and 0 < c["ok"]["en_langfuse"] < c["ok"]["enviadas"] and r["con_muestreo"]["langfuse_igual_al_archivo"]
          and not r["con_muestreo"]["canario_en_el_archivo"] and r["sin_muestreo"]["todas"])
    r["ok"] = bool(ok)
    Path(a.salida).write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
