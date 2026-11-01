"""Spike Google ADK (sin API): herramientas MCP del servidor de la semana 14 con token Bearer y agente con modelo guionado
(subclase de `BaseLlm`). Imprime RESULTADO {json}."""
import asyncio
import importlib.metadata as md
import json
import os
import warnings

warnings.filterwarnings("ignore")
from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models.base_llm import BaseLlm  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams  # noqa: E402
from google.genai import types  # noqa: E402

SQL = "SELECT count(*) AS n FROM artmst WHERE art_crt"
GUION = [("describir_esquema", {"tablas": ["artmst"]}), ("ejecutar_sql", {"sql": SQL}), None]


class Guionado(BaseLlm):
    paso: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        accion = GUION[min(self.paso, len(GUION) - 1)]
        self.paso += 1
        parte = (types.Part(function_call=types.FunctionCall(name=accion[0], args=accion[1])) if accion
                 else types.Part(text="Hay N SKU críticos."))
        yield LlmResponse(content=types.Content(role="model", parts=[parte]),
                          usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10,
                                                                                    candidates_token_count=5))


async def main():
    ts = McpToolset(connection_params=StreamableHTTPConnectionParams(
        url=os.environ["MCP_URL"], headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}))
    tools = await ts.get_tools()
    agente = LlmAgent(name="legado", model=Guionado(model="guionado"), instruction="x", tools=[ts])
    runner = InMemoryRunner(agent=agente, app_name="spike")
    ses = await runner.session_service.create_session(app_name="spike", user_id="u")
    respuestas = []
    async for ev in runner.run_async(user_id="u", session_id=ses.id, new_message=types.Content(
            role="user", parts=[types.Part(text="¿Cuántos SKU críticos hay?")])):
        for p in (ev.content.parts if ev.content else []):
            if p.function_response:
                respuestas.append(p.function_response)
    await ts.close()
    sql = next(r for r in reversed(respuestas) if r.name == "ejecutar_sql")
    texto = json.dumps(sql.response, ensure_ascii=False, default=str)
    import google.adk.agents as ag
    sondas = {
        "anthropic": "google.adk.models.anthropic_llm.Claude (Vertex) o google.adk.models.lite_llm.LiteLlm",
        "multiagente": {"sub_agents": True, "SequentialAgent": hasattr(ag, "SequentialAgent"),
                        "ParallelAgent": hasattr(ag, "ParallelAgent"), "LoopAgent": hasattr(ag, "LoopAgent"),
                        "AgentTool": True},
        "a2a_sdk": md.version("a2a-sdk"), "a2a": "google.adk.a2a (to_a2a, RemoteA2aAgent)",
        "sesiones": "SessionService (memoria, base de datos, Vertex)",
    }
    print("RESULTADO " + json.dumps({
        "framework": "google_adk", "version": md.version("google-adk"), "mcp_sdk": md.version("mcp"),
        "herramientas": sorted(t.name for t in tools),
        "llamada": {"herramienta": "ejecutar_sql", "ok": '\\"ok\\": true' in texto or '"ok": true' in texto,
                    "extracto": texto[:160]},
        "agente_guionado": True, "sondas": sondas}, ensure_ascii=False, default=str))


asyncio.run(main())
