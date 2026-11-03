"""Week 17, activity 1: baseline of the observability capabilities, checked by running code (no model, $0).

Each probe runs in its own subprocess, with its own OpenTelemetry TracerProvider, and prints one JSON line.

| Probe | What it measures | Where |
|---|---|---|
| paquetes | the `semana17` group installed at the pins of preparar/versiones.json | Mac, container, CI |
| semconv | GenAI attribute names and operation values in opentelemetry-semantic-conventions; `gen_ai.system` deprecated | Mac, container, CI |
| util_genai | the spans of opentelemetry-util-genai (the chosen instrumentation) for an agent, a model call and a tool; content capture off by default and on with OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT | Mac, container, CI |
| collector | otelcol-contrib version, config validation, OTLP in → redaction → JSON file, with 6 canaries | Mac (Docker), container (binary) |
| mcp | W3C trace context from the MCP client to the week 14 server over Streamable HTTP (SEP-414 `_meta`), and whether the agent's span reaches it through the week 14 threaded client | Mac, container, CI (database) |
| agent_sdk | the installed claude-agent-sdk passes the active trace (TRACEPARENT) to the Claude Code CLI | Mac, container |
| frameworks | LangGraph and Strands spans (week 15 probe, rerun with --frameworks if its venvs exist) | Mac |
| langfuse | --langfuse: a throwaway Langfuse v4 (images by digest) behind the Collector: health, OTLP auth, gen_ai.* → observation types and usage, canaries, scores, metrics and dashboards APIs, which v1 read APIs are off in v4 | Mac (Docker) |
| claude_code | --con-modelo: Claude Code telemetry (metrics, events, beta traces) to a local OTLP receiver, prompt not exported. One tiny `claude -p` on the subscription, no API key | Mac |
| repo | semana-17/** in the paths of the required regresion check | everywhere |

    uv run --group semana17 python semana-17/linea_base/verificar.py                          # container, CI
    uv run --group semana17 python semana-17/linea_base/verificar.py --langfuse --frameworks   # Mac, $0
    uv run --group semana17 python semana-17/linea_base/verificar.py --con-modelo             # Mac, subscription

The report goes to resultados/linea_base_<where>.json, with no secret: DSNs, tokens and keys are never printed.
"""
from __future__ import annotations

import argparse
import base64
import http.server
import importlib.metadata as md
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S17 = AQUI.parent
RAIZ = S17.parent
V = json.loads((S17 / "preparar" / "versiones.json").read_text(encoding="utf-8"))
CANARIOS = {"dsn": "postgresql://legacy_auditor:canario-dsn-1234@db:5432/inventory",
            "bearer": "Bearer canariotoken1234567890abc", "email": "juan.perez@correo.example",
            "telefono": "33 0000 1201", "rfc": "PEJU800101AB1", "clave": "sk-ant-canario1234567890"}


def imagen(nombre: str) -> str:
    """repo@sha256 from versiones.json (the tag is dropped: the digest is what is pinned)."""
    repo = V["imagenes"][nombre].rsplit(":", 1)[0]
    return f"{repo}@{V['digests'][nombre]}"


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def proveedor_en_memoria():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    exp = InMemorySpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exp))
    trace.set_tracer_provider(tp)
    return exp


def resumen_spans(spans) -> list[dict]:
    return [{"name": s.name, "kind": s.kind.name, "trace": format(s.context.trace_id, "032x"),
             "span": format(s.context.span_id, "016x"),
             "parent": format(s.parent.span_id, "016x") if s.parent else None,
             "attrs": {k: v for k, v in (s.attributes or {}).items()}} for s in spans]


# ---------- probes (each runs in a subprocess: python verificar.py --sonda NAME) ----------

def sonda_paquetes() -> dict:
    instalado = {}
    for p in V["python"]:
        try:
            instalado[p] = md.version(p)
        except md.PackageNotFoundError:
            instalado[p] = None
    return {"esperado": V["python"], "instalado": instalado, "ok": instalado == V["python"]}


def sonda_semconv() -> dict:
    import inspect

    from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as g
    nombres = {n: getattr(g, n) for n in (
        "GEN_AI_OPERATION_NAME", "GEN_AI_PROVIDER_NAME", "GEN_AI_REQUEST_MODEL", "GEN_AI_RESPONSE_MODEL",
        "GEN_AI_USAGE_INPUT_TOKENS", "GEN_AI_USAGE_OUTPUT_TOKENS", "GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS",
        "GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS", "GEN_AI_USAGE_REASONING_OUTPUT_TOKENS", "GEN_AI_AGENT_NAME",
        "GEN_AI_TOOL_NAME", "GEN_AI_TOOL_CALL_ID", "GEN_AI_TOOL_TYPE", "GEN_AI_CONVERSATION_ID",
        "GEN_AI_INPUT_MESSAGES", "GEN_AI_OUTPUT_MESSAGES") if hasattr(g, n)}
    fuente = inspect.getsource(g)
    i = fuente.find("GEN_AI_SYSTEM: Final")
    deprecado = "Deprecated: Replaced by `gen_ai.provider.name`" in fuente[i:i + 400]
    operaciones = [v.value for v in g.GenAiOperationNameValues]
    return {"atributos": nombres, "operaciones": operaciones, "gen_ai_system_deprecado": deprecado,
            "ok": len(nombres) == 16 and {"chat", "invoke_agent", "execute_tool"} <= set(operaciones) and deprecado}


def sonda_util_genai() -> dict:
    resultado = {}
    for modo in ("", "SPAN_ONLY"):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = modo
        codigo = f'''
import json, os, sys
sys.path.insert(0, {str(AQUI)!r})
import verificar
exp = verificar.proveedor_en_memoria()
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import InputMessage, OutputMessage, Text
h = get_telemetry_handler()
with h.invoke_local_agent(agent_name="legacybridge", request_model="claude-haiku-5-5"):
    with h.inference("anthropic", request_model="claude-haiku-5-5") as inf:
        inf.input_tokens = 1020; inf.output_tokens = 30; inf.cache_read_input_tokens = 900
        try:
            inf.input_messages = [InputMessage(role="user", parts=[Text(content="pregunta-canario")])]
            inf.output_messages = [OutputMessage(role="assistant", parts=[Text(content="respuesta-canario")],
                                                 finish_reason="stop")]
        except Exception as e:
            print("NOTA", repr(e), file=sys.stderr)
    with h.tool("describir_esquema", tool_type="function") as t:
        t.tool_call_id = "toolu_1"
print(json.dumps(verificar.resumen_spans(exp.get_finished_spans()), default=str))
'''
        p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60,
                           env={**os.environ, "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": modo})
        spans = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else []
        resultado[modo or "por_omision"] = {"spans": [{"name": s["name"], "attrs": sorted(s["attrs"])} for s in spans],
                                            "contenido": "pregunta-canario" in p.stdout, "error": p.stderr[-300:]}
    nombres = [s["name"] for s in resultado["por_omision"]["spans"]]
    chat = next((s for s in resultado["por_omision"]["spans"] if s["name"].startswith("chat ")), {"attrs": []})
    ok = (sorted(nombres) == ["chat claude-haiku-5-5", "execute_tool describir_esquema", "invoke_agent legacybridge"]
          and {"gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.provider.name"} <= set(chat["attrs"])
          and not resultado["por_omision"]["contenido"] and resultado["SPAN_ONLY"]["contenido"])
    return {**resultado, "ok": ok}


def sonda_collector() -> dict:
    binario = os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")
    salida = Path(tempfile.mkdtemp(prefix="otel-"))
    os.chmod(salida, 0o777)
    puerto = puerto_libre()
    config = AQUI / "collector_prueba.yaml"
    if binario:
        version = subprocess.run([binario, "--version"], capture_output=True, text=True).stdout.strip()
        env = {**os.environ, "OTLP_HTTP_ENDPOINT": f"127.0.0.1:{puerto}", "OTLP_ARCHIVO": str(salida / "t.jsonl")}
        valido = subprocess.run([binario, "validate", f"--config={config}"], env=env, capture_output=True).returncode == 0
        proc = subprocess.Popen([binario, f"--config={config}"], env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        parar = proc.terminate
        donde = "binary"
    elif shutil.which("docker"):
        img = imagen("otel-collector")
        version = subprocess.run(["docker", "run", "--rm", img, "--version"], capture_output=True, text=True).stdout.strip()
        base = ["-e", "OTLP_HTTP_ENDPOINT=0.0.0.0:4318", "-e", "OTLP_ARCHIVO=/salida/t.jsonl",
                "-v", f"{config}:/etc/otelcol/config.yaml:ro", "-v", f"{salida}:/salida"]
        valido = subprocess.run(["docker", "run", "--rm", *base, img, "validate", "--config=/etc/otelcol/config.yaml"],
                                capture_output=True).returncode == 0
        cid = subprocess.run(["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{puerto}:4318", *base, img,
                              "--config=/etc/otelcol/config.yaml"], capture_output=True, text=True).stdout.strip()
        parar = lambda: subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
        donde = "docker"
    else:
        return {"ok": False, "detalle": "no otelcol-contrib binary and no Docker"}
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        tp = TracerProvider()
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://127.0.0.1:{puerto}/v1/traces")))
        with tp.get_tracer("linea_base").start_as_current_span("execute_tool ejecutar_sql") as s:
            s.set_attribute("gen_ai.tool.name", "ejecutar_sql")
            for k, v in CANARIOS.items():
                s.set_attribute(f"prueba.{k}", f"valor {v} fin")
        tp.force_flush()
        tp.shutdown()
        texto = ""
        for _ in range(50):
            f = salida / "t.jsonl"
            if f.exists() and f.stat().st_size:
                texto = f.read_text()
                break
            time.sleep(0.2)
    finally:
        parar()
    filtrados = [k for k, v in CANARIOS.items() if v in texto]
    return {"donde": donde, "version": version, "config_valida": valido, "exportado": bool(texto),
            "canarios_filtrados": filtrados, "enmascarado": "****" in texto,
            "ok": valido and bool(texto) and not filtrados and V["imagenes"]["otel-collector"].endswith(
                version.split()[-1]) if version else False}


def sonda_mcp() -> dict:
    if not (os.environ.get("NLQ_LEGADO_DSN") or os.environ.get("PG_ADMIN_DSN")):
        return {"ok": False, "detalle": "NLQ_LEGADO_DSN or PG_ADMIN_DSN not set"}
    if not os.environ.get("NLQ_LEGADO_DSN"):   # same read-only role as weeks 13 and 14
        sys.path.insert(0, str(RAIZ / "semana-13"))
        from herramientas.conexion import conectar
        conectar()[0].close()
    exp = proveedor_en_memoria()
    import importlib.util

    from opentelemetry import trace
    s14 = RAIZ / "semana-14"
    sys.path.insert(0, str(s14))
    spec = importlib.util.spec_from_file_location("seguridad14_lb17", s14 / "seguridad" / "correr.py")
    seg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seg)
    from cliente.seguro import ClienteSeguro, ServidorMCP
    ent = seg.Entorno("prueba", con_base=True)
    try:
        srv = ent.servidores["normal"]
        with ClienteSeguro([ServidorMCP("legado", srv.url, ent.token("analista"))], defensas=False) as c:
            c.definiciones()
            herramienta = next(k for k in c._mapa if k.endswith("describir_esquema"))
            with trace.get_tracer("legacybridge").start_as_current_span("invoke_agent legacybridge"):
                ok_llamada = bool(c.llamar(herramienta, {}).get("ok"))
    finally:
        ent.cerrar()
    spans = resumen_spans(exp.get_finished_spans())
    cliente = next(s for s in spans if s["name"] == "MCP send tools/call describir_esquema")
    servidor = next(s for s in spans if s["name"] == "tools/call describir_esquema")
    agente = next(s for s in spans if s["name"] == "invoke_agent legacybridge")
    cliente_a_servidor = servidor["trace"] == cliente["trace"] and servidor["parent"] == cliente["span"]
    agente_a_cliente = cliente["trace"] == agente["trace"]
    return {"llamada_ok": ok_llamada, "spans": [{k: s[k] for k in ("name", "kind", "parent")} | {
            "mismo_trace_que_el_agente": s["trace"] == agente["trace"]} for s in spans],
            "atributos_servidor": servidor["attrs"], "cliente_a_servidor": cliente_a_servidor,
            "agente_a_cliente": agente_a_cliente,
            # Expected today: the context crosses MCP but not the week 14 client's thread. Activity 3 fixes the thread.
            "ok": ok_llamada and cliente_a_servidor and not agente_a_cliente
            and servidor["attrs"].get("gen_ai.operation.name") == "execute_tool"}


def sonda_agent_sdk() -> dict:
    try:
        import claude_agent_sdk
        version = md.version("claude-agent-sdk")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detalle": f"claude-agent-sdk not importable ({type(e).__name__})"}
    fuente = (Path(claude_agent_sdk.__file__).parent / "_internal" / "transport" / "subprocess_cli.py").read_text()
    propaga = "from opentelemetry import propagate" in fuente and '"TRACEPARENT", "TRACESTATE"' in fuente
    cli = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
    cli_version = subprocess.run([str(cli), "--version"], capture_output=True, text=True,
                                 timeout=30).stdout.strip() if cli.exists() else None
    return {"version": version, "propaga_traceparent": propaga, "cli_empaquetado": cli_version,
            "ok": propaga}


def sonda_frameworks(rerun: bool) -> dict:
    archivo = RAIZ / "semana-15" / "resultados" / "sonda_trazas.json"
    if rerun and (RAIZ / "semana-15" / ".venvs").exists():
        subprocess.run([sys.executable, str(RAIZ / "semana-15" / "linea_base" / "sonda_trazas.py")],
                       cwd=RAIZ / "semana-15", capture_output=True, timeout=600)
    d = json.loads(archivo.read_text(encoding="utf-8"))
    return {"langgraph": {k: d["langgraph"][k] for k in ("spans_otel", "nativo")},
            "strands": {"spans_otel": d["strands"]["spans_otel"], "nombres": d["strands"]["nombres"],
                        "atributos_gen_ai": d["strands"]["atributos_gen_ai"]},
            "reejecutado": rerun, "ok": d["langgraph"]["spans_otel"] == 0 and d["strands"]["spans_otel"] >= 3}


def peticion(url: str, auth: str | None = None, cuerpo: dict | None = None, metodo: str | None = None):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 method=metodo or ("POST" if cuerpo is not None else "GET"),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Basic {auth}"} if auth else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": type(e).__name__}


def sonda_langfuse() -> dict:
    if not shutil.which("docker"):
        return {"ok": False, "detalle": "Docker not available"}
    tmp = Path(tempfile.mkdtemp(prefix="lf17-"))
    salida = tmp / "salida"
    salida.mkdir()
    os.chmod(salida, 0o777)
    shutil.copy(AQUI / "langfuse_prueba.compose.yml", tmp / "compose.yml")
    shutil.copy(AQUI / "collector_langfuse.yaml", tmp / "collector_langfuse.yaml")
    pk, sk = f"pk-lf-{secrets.token_hex(8)}", f"sk-lf-{secrets.token_hex(16)}"
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    env = {"POSTGRES_PASSWORD": secrets.token_hex(12), "SALT": secrets.token_hex(16),
           "ENCRYPTION_KEY": secrets.token_hex(32), "CLICKHOUSE_PASSWORD": secrets.token_hex(12),
           "MINIO_ROOT_PASSWORD": secrets.token_hex(12), "REDIS_AUTH": secrets.token_hex(12),
           "NEXTAUTH_SECRET": secrets.token_hex(16), "LANGFUSE_PUBLIC_KEY": pk, "LANGFUSE_SECRET_KEY": sk,
           "LANGFUSE_USER_PASSWORD": secrets.token_urlsafe(12), "LANGFUSE_AUTH": auth, "SALIDA": str(salida),
           "IMG_LANGFUSE_WEB": imagen("langfuse-web"), "IMG_LANGFUSE_WORKER": imagen("langfuse-worker"),
           "IMG_CLICKHOUSE": imagen("clickhouse"), "IMG_MINIO": imagen("minio"), "IMG_REDIS": imagen("redis"),
           "IMG_POSTGRES": imagen("postgres"), "IMG_COLLECTOR": imagen("otel-collector")}
    (tmp / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    os.chmod(tmp / ".env", 0o600)
    dc = ["docker", "compose", "-f", str(tmp / "compose.yml"), "--env-file", str(tmp / ".env")]
    r: dict = {}
    base = "http://127.0.0.1:3100"
    t0 = time.time()
    try:
        p = subprocess.run([*dc, "up", "-d"], capture_output=True, text=True, timeout=600)
        r["compose_up"] = p.returncode == 0
        if p.returncode:
            r["detalle"] = p.stderr[-400:]
            return {**r, "ok": False}
        estado = 0
        while time.time() - t0 < 300:
            estado, cuerpo = peticion(f"{base}/api/public/health")
            if estado == 200:
                break
            time.sleep(3)
        r["salud"] = {"estado": estado, "segundos_hasta_listo": round(time.time() - t0)}
        version = peticion(f"{base}/api/public/health")[1].get("version")
        r["version"] = version
        # OTLP auth on Langfuse's own endpoint: without and with Basic auth.
        sin_auth = peticion(f"{base}/api/public/otel/v1/traces", cuerpo={"resourceSpans": []})[0]
        con_auth = peticion(f"{base}/api/public/otel/v1/traces", auth=auth, cuerpo={"resourceSpans": []})[0]
        r["otlp_auth"] = {"sin_auth": sin_auth, "con_auth": con_auth}
        # A LegacyBridge-shaped trace through the Collector (redaction on the way).
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        tp = TracerProvider(resource=Resource.create({"service.name": "legacybridge-linea-base"}))
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://127.0.0.1:4318/v1/traces")))
        tr = tp.get_tracer("legacybridge")
        with tr.start_as_current_span("invoke_agent legacybridge", attributes={
                "gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "legacybridge",
                "prueba.email": CANARIOS["email"]}) as raiz:
            traza = format(raiz.get_span_context().trace_id, "032x")
            with tr.start_as_current_span("chat claude-haiku-5-5", attributes={
                    "gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",
                    # semconv: input_tokens includes the cached ones (Anthropic's API reports them apart).
                    "gen_ai.request.model": "claude-haiku-5-5", "gen_ai.usage.input_tokens": 1020,
                    "gen_ai.usage.output_tokens": 30, "gen_ai.usage.cache_read.input_tokens": 900,
                    "prueba.dsn": CANARIOS["dsn"]}):
                pass
            with tr.start_as_current_span("execute_tool describir_esquema", attributes={
                    "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "describir_esquema",
                    "gen_ai.tool.call.id": "toolu_1", "prueba.bearer": CANARIOS["bearer"]}):
                pass
        tp.force_flush()
        tp.shutdown()
        obs: list = []
        while time.time() - t0 < 480:
            estado, cuerpo = peticion(f"{base}/api/public/v2/observations?traceId={traza}"
                                      "&fields=core,basic,model,usage,metadata", auth=auth)
            obs = cuerpo.get("data", []) if estado == 200 else []
            if len(obs) >= 3:
                break
            time.sleep(3)
        r["observaciones_v2"] = {"estado": estado, "n": len(obs), "tipos": sorted(o.get("type") for o in obs)}
        gen = next((o for o in obs if o.get("type") == "GENERATION"), {})
        r["generacion"] = {"modelo": gen.get("providedModelName") or gen.get("model"),
                           "usage": gen.get("usageDetails")}
        texto = json.dumps(obs, ensure_ascii=False)
        r["canarios_en_langfuse"] = [k for k, v in CANARIOS.items() if v in texto]
        # Scores: write (v1 POST) and read (v3 GET).
        e_score, _ = peticion(f"{base}/api/public/scores", auth=auth, cuerpo={
            "traceId": traza, "name": "trayectoria", "value": 0.9, "dataType": "NUMERIC"})
        leido = []
        while time.time() - t0 < 540:
            e3, c3 = peticion(f"{base}/api/public/v3/scores?traceId={traza}", auth=auth)
            leido = [s for s in c3.get("data", []) if s.get("name") == "trayectoria"] if e3 == 200 else []
            if leido:
                break
            time.sleep(3)
        r["scores"] = {"post_v1": e_score, "get_v3": e3, "leido": bool(leido)}
        # Read APIs in v4: which v1 routes are off in the default events_only mode, and the newer ones.
        consulta = json.dumps({"view": "observations", "metrics": [{"measure": "count", "aggregation": "count"}],
                               "dimensions": [], "filters": [], "fromTimestamp": "2026-01-01T00:00:00Z",
                               "toTimestamp": "2027-01-01T00:00:00Z"})
        q = urllib.request.quote(consulta)
        r["apis"] = {
            "GET /api/public/traces/{id}": peticion(f"{base}/api/public/traces/{traza}", auth=auth)[0],
            "GET /api/public/scores": peticion(f"{base}/api/public/scores?limit=1", auth=auth)[0],
            "GET /api/public/metrics": peticion(f"{base}/api/public/metrics?query={q}", auth=auth)[0],
            "GET /api/public/v2/metrics": peticion(f"{base}/api/public/v2/metrics?query={q}", auth=auth)[0],
            "GET /api/public/v2/observations": estado,
            "GET /api/public/v3/scores": e3,
            "GET /api/public/unstable/dashboards": peticion(f"{base}/api/public/unstable/dashboards", auth=auth)[0],
        }
        coleccion = salida / "trazas.jsonl"
        r["collector_archivo"] = coleccion.exists() and coleccion.stat().st_size > 0
        r["canarios_en_archivo"] = [k for k, v in CANARIOS.items()
                                    if coleccion.exists() and v in coleccion.read_text()]
    finally:
        subprocess.run([*dc, "down", "-v"], capture_output=True, timeout=300)
        r["borrado"] = subprocess.run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=s17-linea-base"],
                                      capture_output=True, text=True).stdout.strip() == ""
        shutil.rmtree(tmp, ignore_errors=True)
    r["ok"] = (r.get("salud", {}).get("estado") == 200 and r.get("otlp_auth", {}).get("sin_auth") == 401
               and r.get("otlp_auth", {}).get("con_auth") in (200, 201, 207)
               and r.get("observaciones_v2", {}).get("tipos") == ["AGENT", "GENERATION", "TOOL"]
               and (r.get("generacion", {}).get("usage") or {}).get("input") == 120          # 1020 - 900 cached
               and (r.get("generacion", {}).get("usage") or {}).get("input_cached_tokens") == 900
               and r.get("canarios_en_langfuse") == [] and r.get("scores", {}).get("leido") is True
               and r.get("borrado") is True)
    return r


class _Receptor(http.server.BaseHTTPRequestHandler):
    cuerpos: list = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.cuerpos.append((self.path, self.rfile.read(n).decode("utf-8", "replace")))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def sonda_claude_code() -> dict:
    """One tiny `claude -p` on the subscription (ANTHROPIC_API_KEY removed), telemetry to a local OTLP receiver."""
    puerto = puerto_libre()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), _Receptor)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    canario = f"canario-prompt-{secrets.token_hex(4)}"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY" and not k.startswith("OTEL_")}
    env.update({"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
                "OTEL_METRICS_EXPORTER": "otlp", "OTEL_LOGS_EXPORTER": "otlp", "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json", "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{puerto}",
                "OTEL_METRIC_EXPORT_INTERVAL": "1000", "OTEL_LOGS_EXPORT_INTERVAL": "500",
                "OTEL_TRACES_EXPORT_INTERVAL": "500"})
    t = time.time()
    import claude_agent_sdk  # the CLI on PATH, else the one bundled with the pinned SDK
    cli = shutil.which("claude") or str(Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude")
    p = subprocess.run([cli, "-p", "--model", "haiku", "--max-turns", "1"],
                       input=f"Responde solo con la palabra ok. ({canario})", capture_output=True, text=True,
                       env=env, timeout=180, cwd=tempfile.mkdtemp())
    time.sleep(4)
    srv.shutdown()
    cuerpos = _Receptor.cuerpos
    texto = "\n".join(c for _, c in cuerpos)
    nombres = sorted(set(re.findall(r'"name":"(claude_code\.[a-z_.]+)"', texto)))
    eventos = sorted(set(re.findall(r'"event\.name","value":\{"stringValue":"([a-z_]+)"', texto)))
    gen_ai = sorted(set(re.findall(r'"key":"(gen_ai\.[a-z_.]+)"', texto)))
    tokens = sorted(set(re.findall(r'"key":"((?:input|output|cache_read|cache_creation)_tokens)"', texto)))
    version = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    return {"cli": version, "exit": p.returncode, "segundos": round(time.time() - t),
            "rutas": sorted({r for r, _ in cuerpos}), "metricas_y_spans": nombres, "eventos": eventos,
            "atributos_gen_ai": gen_ai, "atributos_de_tokens_no_estandar": tokens,
            "prompt_exportado": canario in texto,
            "ok": p.returncode == 0 and {"claude_code.interaction", "claude_code.llm_request",
                                         "claude_code.session.count"} <= set(nombres) and canario not in texto}


def sonda_repo() -> dict:
    regresion = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    return {"ok": '"semana-17/**"' in regresion}


SONDAS = {"paquetes": sonda_paquetes, "semconv": sonda_semconv, "util_genai": sonda_util_genai,
          "collector": sonda_collector, "mcp": sonda_mcp, "agent_sdk": sonda_agent_sdk,
          "langfuse": sonda_langfuse, "claude_code": sonda_claude_code, "repo": sonda_repo}


def correr_sonda(nombre: str, extra: list[str] | None = None, timeout: int = 900) -> dict:
    p = subprocess.run([sys.executable, str(Path(__file__)), "--sonda", nombre, *(extra or [])], capture_output=True,
                       text=True, timeout=timeout, env=os.environ)
    linea = next((x for x in reversed(p.stdout.splitlines()) if x.startswith("{")), None)
    if not linea:
        return {"ok": False, "detalle": (p.stderr or p.stdout)[-500:]}
    return json.loads(linea)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--langfuse", action="store_true", help="throwaway Langfuse v4 in Docker (Mac)")
    ap.add_argument("--frameworks", action="store_true", help="rerun the week 15 LangGraph/Strands probe")
    ap.add_argument("--con-modelo", action="store_true", help="Claude Code telemetry, one call on the subscription")
    ap.add_argument("--solo", help="comma-separated probes to run")
    ap.add_argument("--sonda", help=argparse.SUPPRESS)
    ap.add_argument("--salida", type=Path)
    a = ap.parse_args(argv)
    if a.sonda:
        r = sonda_frameworks(a.frameworks) if a.sonda == "frameworks" else SONDAS[a.sonda]()
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0
    nombres = ["paquetes", "semconv", "util_genai", "collector", "mcp", "agent_sdk", "frameworks", "repo"]
    if a.langfuse:
        nombres.append("langfuse")
    if a.con_modelo:
        nombres.append("claude_code")
    if a.solo:
        nombres = [n for n in nombres if n in a.solo.split(",")]
    resultados = {}
    for n in nombres:
        t = time.time()
        resultados[n] = correr_sonda(n, ["--frameworks"] if n == "frameworks" and a.frameworks else None)
        print(f"  {'OK' if resultados[n].get('ok') else 'FALLA'}  {n}  ({round(time.time() - t)} s)", flush=True)
    donde = "mac" if platform.system() == "Darwin" else ("ci" if os.environ.get("GITHUB_ACTIONS") else "contenedor")
    salida = a.salida or S17 / "resultados" / f"linea_base_{donde}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps({"donde": donde, "fecha": time.strftime("%Y-%m-%d"), "python": platform.python_version(),
                        "sondas": resultados}, ensure_ascii=False, indent=1, default=str)
    texto = texto.replace(str(Path.home()), "~")
    salida.write_text(texto + "\n", encoding="utf-8")
    fallas = [n for n, r in resultados.items() if not r.get("ok")]
    print(f"\n{len(nombres) - len(fallas)}/{len(nombres)} sondas OK" + (f"; fallan: {', '.join(fallas)}" if fallas else ""))
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
