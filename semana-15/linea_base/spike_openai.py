"""Spike OpenAI Agents SDK (sin API): herramientas MCP del servidor de la semana 14 con token Bearer y agente con modelo
guionado (interfaz `Model` del SDK). El tracing hacia OpenAI se desactiva: no sale nada del equipo. Imprime RESULTADO {json}."""
import asyncio
import importlib.metadata as md
import json
import os

from agents import Agent, Runner, set_tracing_disabled
from agents.items import ModelResponse
from agents.mcp import MCPServerStreamableHttp
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

set_tracing_disabled(True)
SQL = "SELECT count(*) AS n FROM artmst WHERE art_crt"
GUION = [("describir_esquema", {"tablas": ["artmst"]}), ("ejecutar_sql", {"sql": SQL}), None]


class Guionado(Model):
    def __init__(self):
        self.paso = 0

    async def get_response(self, *a, **kw):
        accion = GUION[min(self.paso, len(GUION) - 1)]
        self.paso += 1
        if accion:
            item = ResponseFunctionToolCall(type="function_call", id=f"fc{self.paso}", call_id=f"c{self.paso}",
                                            name=accion[0], arguments=json.dumps(accion[1]), status="completed")
        else:
            item = ResponseOutputMessage(type="message", id="m1", role="assistant", status="completed", content=[
                ResponseOutputText(type="output_text", text="Hay N SKU críticos.", annotations=[])])
        return ModelResponse(output=[item], usage=Usage(requests=1, input_tokens=10, output_tokens=5, total_tokens=15),
                             response_id=None)

    def stream_response(self, *a, **kw):
        raise NotImplementedError


async def main():
    async with MCPServerStreamableHttp(params={"url": os.environ["MCP_URL"],
                                               "headers": {"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}},
                                       name="legado", cache_tools_list=True) as srv:
        tools = await srv.list_tools()
        agente = Agent(name="legado", instructions="x", model=Guionado(), mcp_servers=[srv])
        r = await Runner.run(agente, "¿Cuántos SKU críticos hay?", max_turns=6)
    salidas = [it for it in r.new_items if it.type == "tool_call_output_item"]
    texto = str(salidas[-1].output)
    import agents
    sondas = {
        "anthropic": "agents.extensions.models.litellm_model.LitellmModel (LiteLLM " + md.version("litellm") + ")",
        "uso_reportado": {"requests": r.context_wrapper.usage.requests, "input_tokens": r.context_wrapper.usage.input_tokens},
        "limite_pasos": "Runner.run(max_turns=...)",
        "multiagente": {"handoffs": hasattr(agents, "Handoff"), "agent_as_tool": hasattr(Agent, "as_tool")},
        "hitl": {"aprobacion_mcp": hasattr(agents, "MCPToolApprovalRequest"), "tool_approval_item": hasattr(agents, "ToolApprovalItem")},
        "guardrails": hasattr(agents, "InputGuardrail"),
        "sesiones": hasattr(agents, "SessionABC"),
        "tracing": "propio (exporta a OpenAI por defecto; add_trace_processor para otros destinos)",
    }
    print("RESULTADO " + json.dumps({
        "framework": "openai_agents", "version": md.version("openai-agents"), "mcp_sdk": md.version("mcp"),
        "herramientas": sorted(t.name for t in tools),
        "llamada": {"herramienta": "ejecutar_sql", "ok": '"ok": true' in texto, "extracto": texto[:160]},
        "agente_guionado": True, "salida_final": r.final_output, "sondas": sondas}, ensure_ascii=False, default=str))


asyncio.run(main())
