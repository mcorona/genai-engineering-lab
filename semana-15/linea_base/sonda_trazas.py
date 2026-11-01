"""Semana 15, actividad 1: ¿qué trazas emite cada framework sin configuración extra? Sin API ($0).

    cd semana-15 && python linea_base/sonda_trazas.py

Cada framework corre un agente con modelo guionado (una respuesta de texto) con un TracerProvider de OpenTelemetry en
memoria. Se cuentan los spans y los atributos `gen_ai.*` (convenciones semánticas GenAI de OpenTelemetry), que es lo que
se reutiliza en la semana 17. Para OpenAI Agents SDK se mide además su tracing propio con un procesador local (el
exportador por defecto, que envía a OpenAI, se reemplaza). Escribe resultados/sonda_trazas.json.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))

OTEL = '''
import json, warnings
warnings.filterwarnings("ignore")
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
exp = InMemorySpanExporter()
tp = TracerProvider(); tp.add_span_processor(SimpleSpanProcessor(exp)); trace.set_tracer_provider(tp)
def informe(extra=None):
    spans = exp.get_finished_spans()
    attrs = sorted({k for s in spans for k in (s.attributes or {}) if k.startswith("gen_ai.")})
    print("RESULTADO " + json.dumps({"spans_otel": len(spans), "nombres": sorted({s.name for s in spans})[:12],
                                     "atributos_gen_ai": attrs, **(extra or {})}, ensure_ascii=False))
'''

PROGS = {
    "langgraph": ("lg", OTEL + '''
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent
a = create_react_agent(GenericFakeChatModel(messages=iter([AIMessage(content="ok")])), [])
a.invoke({"messages": [("user", "hola")]})
informe({"nativo": "LangSmith (LANGSMITH_TRACING); OTel requiere instrumentación externa"})
'''),
    "strands": ("st", OTEL + '''
from strands import Agent
from strands.models.model import Model
class G(Model):
    def update_config(self, **kw): pass
    def get_config(self): return {}
    async def structured_output(self, *a, **kw): raise NotImplementedError
    async def stream(self, *a, **kw):
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"delta": {"text": "ok"}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}, "metrics": {"latencyMs": 1}}}
Agent(model=G(), callback_handler=None)("hola")
informe({"nativo": "OpenTelemetry (StrandsTelemetry)"})
'''),
    "openai_agents": ("oa", OTEL + '''
import asyncio
from agents import Agent, Runner, set_trace_processors
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.tracing.processor_interface import TracingProcessor
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
propios = []
class Local(TracingProcessor):
    def on_trace_start(self, t): pass
    def on_trace_end(self, t): pass
    def on_span_start(self, s): pass
    def on_span_end(self, s): propios.append(type(s.span_data).__name__)
    def shutdown(self): pass
    def force_flush(self): pass
set_trace_processors([Local()])
class G(Model):
    async def get_response(self, *a, **kw):
        return ModelResponse(output=[ResponseOutputMessage(type="message", id="m", role="assistant", status="completed",
            content=[ResponseOutputText(type="output_text", text="ok", annotations=[])])], usage=Usage(requests=1), response_id=None)
    def stream_response(self, *a, **kw): raise NotImplementedError
asyncio.run(Runner.run(Agent(name="x", instructions="x", model=G()), "hola"))
informe({"nativo": "tracing propio (exporta a OpenAI por defecto)", "spans_propios": propios})
'''),
    "google_adk": ("adk", OTEL + '''
import asyncio
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
class G(BaseLlm):
    async def generate_content_async(self, req, stream=False):
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="ok")]),
                          usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=7, candidates_token_count=3))
async def correr():
    r = InMemoryRunner(agent=LlmAgent(name="x", instruction="x", model=G(model="g")), app_name="s")
    ses = await r.session_service.create_session(app_name="s", user_id="u")
    async for _ in r.run_async(user_id="u", session_id=ses.id, new_message=types.Content(role="user", parts=[types.Part(text="hola")])):
        pass
asyncio.run(correr())
informe({"nativo": "OpenTelemetry"})
'''),
}


def main():
    res = {}
    for fw, (venv, prog) in PROGS.items():
        p = subprocess.run([str(VENVS / venv / "bin" / "python"), "-c", prog], capture_output=True, text=True, timeout=120,
                           env={**{k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}, "OPENAI_API_KEY": ""})
        linea = next((x for x in reversed(p.stdout.splitlines()) if x.startswith("RESULTADO ")), None)
        res[fw] = json.loads(linea[10:]) if linea else {"error": (p.stderr or p.stdout)[-1200:]}
        print(fw, json.dumps(res[fw], ensure_ascii=False)[:600], flush=True)
    (S15 / "resultados" / "sonda_trazas.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
