"""Spike Strands Agents (sin API): herramientas MCP del servidor de la semana 14 con token Bearer y agente con modelo
guionado (implementa la interfaz `Model` de Strands). Imprime RESULTADO {json}."""
import importlib.metadata as md
import json
import os

from strands import Agent
from strands.models.model import Model
from strands.tools.mcp import MCPClient

SQL = "SELECT count(*) AS n FROM artmst WHERE art_crt"
GUION = [("describir_esquema", {"tablas": ["artmst"]}), ("ejecutar_sql", {"sql": SQL}), None]


class Guionado(Model):
    def __init__(self):
        self.paso = 0
        self.config = {}

    def update_config(self, **kw):
        self.config.update(kw)

    def get_config(self):
        return self.config

    async def structured_output(self, *a, **kw):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
        accion = GUION[min(self.paso, len(GUION) - 1)]
        self.paso += 1
        yield {"messageStart": {"role": "assistant"}}
        if accion:
            nombre, args = accion
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{self.paso}", "name": nombre}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": "Hay N SKU críticos."}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}, "metrics": {"latencyMs": 1}}}


cli = MCPClient(url=os.environ["MCP_URL"], headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"})
with cli:
    tools = cli.list_tools_sync()
    agente = Agent(model=Guionado(), tools=tools, callback_handler=None)
    r = agente("¿Cuántos SKU críticos hay?")
    resultados = [b["toolResult"] for m in agente.messages for b in m["content"] if "toolResult" in b]
    sql = resultados[-1]
    texto = json.dumps(sql, ensure_ascii=False, default=str)

from strands.multiagent import graph, swarm  # noqa: E402
import strands.interrupt  # noqa: E402,F401
sondas = {
    "anthropic_nativo": "strands.models.anthropic.AnthropicModel",
    "uso_reportado": dict(r.metrics.accumulated_usage),
    "multiagente": {"graph": hasattr(graph, "GraphBuilder"), "swarm": hasattr(swarm, "Swarm"), "agentes_como_herramienta": True},
    "a2a_servidor": "strands.multiagent.a2a.A2AServer", "a2a_sdk": md.version("a2a-sdk"),
    "interrupciones": "strands.interrupt.Interrupt", "otel": "strands.telemetry.StrandsTelemetry",
}
print("RESULTADO " + json.dumps({
    "framework": "strands", "version": md.version("strands-agents"), "mcp_sdk": md.version("mcp"),
    "herramientas": sorted(t.tool_name for t in tools),
    "llamada": {"herramienta": "ejecutar_sql", "ok": sql.get("status") == "success" and '\\"ok\\": true' in texto,
                "extracto": texto[:160]},
    "agente_guionado": True, "sondas": sondas}, ensure_ascii=False, default=str))
