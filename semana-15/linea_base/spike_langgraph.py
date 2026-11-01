"""Spike LangGraph (sin API): herramientas MCP del servidor de la semana 14 con token Bearer, agente con modelo guionado,
checkpoint e interrupción. Imprime RESULTADO {json}."""
import asyncio
import importlib.metadata as md
import json
import os

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command, interrupt

SQL = "SELECT count(*) AS n FROM artmst WHERE art_crt"


class Guionado(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


def guion():
    return iter([
        AIMessage(content="", tool_calls=[{"name": "describir_esquema", "args": {"tablas": ["artmst"]}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "ejecutar_sql", "args": {"sql": SQL}, "id": "c2"}]),
        AIMessage(content="Hay N SKU críticos."),
    ])


async def main():
    cli = MultiServerMCPClient({"legado": {"transport": "streamable_http", "url": os.environ["MCP_URL"],
                                           "headers": {"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}}})
    tools = await cli.get_tools()
    agente = create_react_agent(Guionado(messages=guion()), tools, checkpointer=InMemorySaver())
    estado = await agente.ainvoke({"messages": [("user", "¿Cuántos SKU críticos hay?")]},
                                  {"configurable": {"thread_id": "t1"}})
    msgs = estado["messages"]
    tool_msgs = [m for m in msgs if m.type == "tool"]
    sql_msg = next(m for m in tool_msgs if m.name == "ejecutar_sql")
    ok = '"ok": true' in str(sql_msg.content).replace("'ok': True", '"ok": true') or '"ok":true' in str(sql_msg.content)

    # checkpoint + human-in-the-loop: interrupción antes de una acción, reanudación con Command(resume=...)
    from langgraph.graph import StateGraph, START, END
    from typing_extensions import TypedDict

    class S(TypedDict):
        aprobado: bool

    def pedir(s):
        return {"aprobado": interrupt({"accion": "proponer_orden_compra", "sku": "SKU-0001"}) == "sí"}

    g = StateGraph(S)
    g.add_node("pedir", pedir)
    g.add_edge(START, "pedir")
    g.add_edge("pedir", END)
    app = g.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "h1"}}
    r1 = app.invoke({"aprobado": False}, cfg)
    pausado = "__interrupt__" in r1
    r2 = app.invoke(Command(resume="sí"), cfg)

    try:
        import langgraph_supervisor  # noqa: F401
        supervisor = md.version("langgraph-supervisor")
    except ImportError:
        supervisor = None
    from langchain_anthropic import ChatAnthropic
    sondas = {
        "checkpoint_interrupcion": pausado and r2.get("aprobado") is True,
        "checkpoints_en_estado": len(list(app.get_state_history(cfg))),
        "anthropic_nativo": ChatAnthropic.__module__,
        "usage_metadata": "usage_metadata" in AIMessage.model_fields,
        "limite_pasos": "recursion_limit (config)",
        "multiagente": {"langgraph_supervisor": supervisor, "subgrafos": True, "handoffs": "langgraph_supervisor / Command(goto)"},
        "a2a_en_libreria": False,   # A2A lo ofrece el Agent Server alojado de LangGraph, no la librería
    }
    print("RESULTADO " + json.dumps({
        "framework": "langgraph", "version": md.version("langgraph"), "adaptador_mcp": md.version("langchain-mcp-adapters"),
        "mcp_sdk": md.version("mcp"), "herramientas": sorted(t.name for t in tools),
        "llamada": {"herramienta": "ejecutar_sql", "ok": ok, "extracto": str(sql_msg.content)[:160]},
        "agente_guionado": True, "mensajes": len(msgs), "sondas": sondas}, ensure_ascii=False, default=str))


asyncio.run(main())
