"""Week 17, activity 3 (optional): the same task through LangGraph, with whatever tracing it brings. Runs in the `lg` venv of week 15.

`comparar_frameworks.py` starts it with the scripted model (`LAB_GUION`), the lab server's URL and the user's token (the token
is an environment variable, never an argument). It first tries to reach the real MCP server through `langchain-mcp-adapters`;
if that fails, the tools are plain Python functions with canned results, and the report says which of the two happened and why
(the exception class only). The model is scripted: $0.

Two things are measured, with nothing configured beyond a global OpenTelemetry TracerProvider (in memory) and, for the second,
a local callback:
  1. how many OpenTelemetry spans LangGraph and LangChain emit by themselves;
  2. the shape of the run tree they do produce (the LangSmith format, captured here without sending it anywhere) and what it
     contains: whether the prompt, the SQL or the returned rows are in it.
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
os.environ.pop("LANGSMITH_API_KEY", None)
os.environ["LANGSMITH_TRACING"] = "false"          # no network: the run tree is captured by a local callback

from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

GUION = json.loads(Path(os.environ["LAB_GUION"]).read_text(encoding="utf-8"))
URL, TOKEN, SALIDA = os.environ["LAB_MCP_URL"], os.environ["LAB_TOKEN"], os.environ["LAB_SALIDA"]

memoria = InMemorySpanExporter()
proveedor = TracerProvider()
proveedor.add_span_processor(SimpleSpanProcessor(memoria))
trace.set_tracer_provider(proveedor)

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_core.tracers.base import BaseTracer  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402


class Guionado(GenericFakeChatModel):
    """The scripted turns as AIMessages with `usage_metadata` (LangChain's `input_tokens` is the TOTAL, cache included)."""

    def bind_tools(self, tools, **kw):
        return self


def mensajes(turnos):
    salida = []
    for n, t in enumerate(turnos, 1):
        u = t["usage"]
        leidos, escritos = u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0)
        uso = {"input_tokens": u["input_tokens"] + leidos + escritos, "output_tokens": u["output_tokens"],
               "total_tokens": u["input_tokens"] + leidos + escritos + u["output_tokens"],
               "input_token_details": {"cache_read": leidos, "cache_creation": escritos}}
        if "herramientas" in t:
            llamadas = [{"name": nombre, "args": entrada, "id": f"toolu_scripted_{n:02d}_{k + 1}", "type": "tool_call"}
                        for k, (nombre, entrada) in enumerate(t["herramientas"])]
            salida.append(AIMessage(content="", tool_calls=llamadas, usage_metadata=uso))
        else:
            salida.append(AIMessage(content=t["final"]["respuesta"], usage_metadata=uso))
    return salida


@tool
def describir_esquema(tablas: list[str]) -> str:
    """Describe tables of the legacy schema (canned result)."""
    return json.dumps({"tablas": {"artmst": ["art_cd", "art_ptr"], "exidet": ["exi_art", "exi_qty"]}})


@tool
def ejecutar_sql(sql: str) -> str:
    """Run a SELECT on the legacy schema (canned result)."""
    return json.dumps({"columnas": ["art_cd"], "filas": [["SKU-0003"], ["SKU-0009"]]})


class Rastro(BaseTracer):
    """Collects the run tree LangChain builds for every invocation (what LangSmith would receive)."""

    def __init__(self):
        super().__init__()
        self.raices = []

    def _persist_run(self, run):
        self.raices.append(run)


def arbol(run):
    return {"name": run.name, "run_type": run.run_type, "hijos": [arbol(h) for h in run.child_runs]}


def contar(nodo):
    return 1 + sum(contar(h) for h in nodo["hijos"])


async def herramientas_reales():
    from langchain_mcp_adapters.client import MultiServerMCPClient
    cliente = MultiServerMCPClient({"legado": {"transport": "streamable_http", "url": URL,
                                               "headers": {"Authorization": f"Bearer {TOKEN}"}}})
    return await asyncio.wait_for(cliente.get_tools(), 30)


async def correr():
    servidor_real, motivo = True, None
    try:
        herramientas = await herramientas_reales()
        if not herramientas:
            raise RuntimeError("no tools")
    except BaseException as e:   # noqa: BLE001  (an ExceptionGroup from the transport is the usual shape)
        servidor_real, motivo = False, type(e).__name__
        herramientas = [describir_esquema, ejecutar_sql]
    agente = create_react_agent(Guionado(messages=iter(mensajes(GUION["turnos"]))), herramientas)
    rastro = Rastro()
    t0 = time.time()
    salida = await agente.ainvoke({"messages": [("user", GUION["tarea"])]}, config={"callbacks": [rastro]})
    return servidor_real, motivo, salida, rastro, time.time() - t0


def main():
    servidor_real, motivo, salida, rastro, segundos = asyncio.run(correr())
    spans = memoria.get_finished_spans()
    arboles = [arbol(r) for r in rastro.raices]
    todas = []

    def recoger(r):
        todas.append(r)
        for h in r.child_runs:
            recoger(h)
    for r in rastro.raices:
        recoger(r)
    contenido = json.dumps([{"in": r.inputs, "out": r.outputs} for r in todas], ensure_ascii=False, default=str)
    filas = sorted(set(re.findall(r"SKU-\d{4}", contenido)))
    informe = {
        "framework": "langgraph", "segundos": round(segundos, 2), "servidor_real": servidor_real,
        "versiones": {n: version(n) for n in ("langgraph", "langchain-core", "langchain-mcp-adapters", "mcp")},
        "motivo_sin_servidor": motivo, "mensajes": len(salida["messages"]),
        "spans_otel": len(spans), "nombres_otel": sorted({s.name for s in spans}),
        "atributos_gen_ai_otel": sorted({k for s in spans for k in (s.attributes or {}) if k.startswith("gen_ai.")}),
        "arboles": arboles, "runs": sum(contar(a) for a in arboles),
        "tipos": sorted({r.run_type for r in todas}),
        "usage_en_el_rastro": "usage_metadata" in contenido,
        "fugas": {**{k: (v in contenido) for k, v in GUION["canarios"].items()},
                  "sql_completo": GUION["sql"] in contenido, "token": TOKEN in contenido, "tarea": GUION["tarea"] in contenido,
                  "filas_devueltas": bool(filas)},
    }
    Path(SALIDA).write_text(json.dumps(informe, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
