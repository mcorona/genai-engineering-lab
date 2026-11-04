"""Week 17, activity 3 (optional): the same task through Strands, with its own OpenTelemetry. Runs in the `st` venv of week 15.

It is not meant to be run by hand: `comparar_frameworks.py` starts it with a scripted model (`LAB_GUION`, a JSON file), the URL
of the lab's MCP server (`LAB_MCP_URL`) and the user's token (`LAB_TOKEN`, an environment variable: never an argument, so it
is not in `ps`). Strands calls the real server through its own `MCPClient`; the model is scripted, so it costs $0.

Nothing is configured for tracing except the global TracerProvider (in-memory, plus OTLP HTTP when `LAB_OTLP_HTTP` is set):
what Strands emits by itself is exactly what is measured. The spans go to `LAB_SALIDA` as JSON, with the checks that need the
secrets (is a canary, the token or a returned row in any span?) already done here, so the parent never has to re-read them.
"""
import asyncio
import json
import os
import re
import sys
import time
import warnings
from importlib.metadata import version
from pathlib import Path

warnings.filterwarnings("ignore")

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

GUION = json.loads(Path(os.environ["LAB_GUION"]).read_text(encoding="utf-8"))
URL, TOKEN, SALIDA = os.environ["LAB_MCP_URL"], os.environ["LAB_TOKEN"], os.environ["LAB_SALIDA"]
OTLP = os.environ.get("LAB_OTLP_HTTP")

memoria = InMemorySpanExporter()
proveedor = TracerProvider(resource=Resource.create({"service.name": "strands-lab"}))
proveedor.add_span_processor(SimpleSpanProcessor(memoria))
if OTLP:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    proveedor.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP)))
trace.set_tracer_provider(proveedor)

from strands import Agent  # noqa: E402
from strands.hooks import AfterToolCallEvent  # noqa: E402
from strands.models.model import Model  # noqa: E402
from strands.tools.mcp import MCPClient  # noqa: E402


class Guionado(Model):
    """Plays the lab's scripted turns as Strands stream events: tool uses with their input, then a plain text turn."""

    def __init__(self, turnos):
        self.turnos, self.n = turnos, 0
        self.config = {"model_id": GUION["modelo"]}      # the providers keep their model id here; Strands reads it from there

    def update_config(self, **kw):
        pass

    def get_config(self):
        return self.config

    async def structured_output(self, *a, **kw):
        raise NotImplementedError

    async def stream(self, *a, **kw):
        turno = self.turnos[self.n]
        self.n += 1
        await asyncio.sleep(turno.get("latencia_s", 0))
        u = turno["usage"]
        yield {"messageStart": {"role": "assistant"}}
        if "herramientas" in turno:
            for k, (nombre, entrada) in enumerate(turno["herramientas"]):
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"toolu_scripted_{self.n:02d}_{k + 1}",
                                                                    "name": nombre}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(entrada)}}}}
                yield {"contentBlockStop": {}}
            parada = "tool_use"
        else:
            yield {"contentBlockDelta": {"delta": {"text": turno["final"]["respuesta"]}}}
            yield {"contentBlockStop": {}}
            parada = "end_turn"
        yield {"messageStop": {"stopReason": parada}}
        # Strands' Anthropic provider reports the API's own numbers: input_tokens is the UNCACHED part
        uso = {"inputTokens": u["input_tokens"], "outputTokens": u["output_tokens"],
               "totalTokens": u["input_tokens"] + u["output_tokens"]
               + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)}
        if "cache_read_input_tokens" in u:
            uso["cacheReadInputTokens"] = u["cache_read_input_tokens"]
        if "cache_creation_input_tokens" in u:
            uso["cacheWriteInputTokens"] = u["cache_creation_input_tokens"]
        yield {"metadata": {"usage": uso, "metrics": {"latencyMs": int(1000 * turno.get("latencia_s", 0))}}}


def valor(v):
    return list(v) if isinstance(v, (list, tuple)) else v


def volcar(s):
    return {"name": s.name, "kind": s.kind.name, "trace": format(s.context.trace_id, "032x"),
            "span": format(s.context.span_id, "016x"), "parent": format(s.parent.span_id, "016x") if s.parent else None,
            "estado": s.status.status_code.name, "alcance": s.instrumentation_scope.name if s.instrumentation_scope else "",
            "inicio": s.start_time, "fin": s.end_time,
            "attrs": {k: valor(v) for k, v in (s.attributes or {}).items()},
            "eventos": [{"name": e.name, "attrs": {k: valor(v) for k, v in (e.attributes or {}).items()}} for e in s.events]}


def main():
    salidas = []                                  # text of every tool result, to look for returned rows in the spans
    t0 = time.time()
    with MCPClient(url=URL, headers={"Authorization": f"Bearer {TOKEN}"}) as cliente:
        herramientas = cliente.list_tools_sync()
        agente = Agent(model=Guionado(GUION["turnos"]), tools=herramientas, callback_handler=None,
                       system_prompt="You answer questions about a legacy inventory database.")

        def guardar(ev):
            r = ev.result if isinstance(ev.result, dict) else {}
            for b in r.get("content", []):
                salidas.append(b["text"] if "text" in b else json.dumps(b.get("json"), ensure_ascii=False))
        agente.hooks.add_callback(AfterToolCallEvent, guardar)
        res = agente(GUION["tarea"])
    proveedor.force_flush()
    spans = [volcar(s) for s in memoria.get_finished_spans()]
    blob = json.dumps(spans, ensure_ascii=False, default=str)
    filas = sorted({m for t in salidas for m in re.findall(r"SKU-\d{4}", t)})
    uso = getattr(res.metrics, "accumulated_usage", None)
    informe = {
        "framework": "strands", "versiones": {"strands-agents": version("strands-agents"), "mcp": version("mcp")},
        "segundos": round(time.time() - t0, 2), "parada": res.stop_reason,
        "herramientas": sorted(t.tool_name for t in herramientas), "spans": spans,
        "uso_acumulado": dict(uso) if uso else None,
        "resultados_de_herramientas": len(salidas), "con_filas": bool(filas),
        "fugas": {**{k: (v in blob) for k, v in GUION["canarios"].items()},
                  "sql_completo": GUION["sql"] in blob, "token": TOKEN in blob, "tarea": GUION["tarea"] in blob,
                  "filas_devueltas": (any(f in blob for f in filas) if filas else None)},
    }
    Path(SALIDA).write_text(json.dumps(informe, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
