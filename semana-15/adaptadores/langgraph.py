"""Semana 15, actividad 3: el agente de la semana 13 en LangGraph.

Grafo explícito, sin el agente prefabricado (`create_react_agent`), para que cada regla de la semana 13 sea visible:

    START → modelo ─┬─(pide herramientas)→ herramientas ─┬─(sigue)→ modelo
                    │                                    └─(responder válido, límite o 3 errores seguidos)→ END
                    └─(sin herramientas: un recordatorio; la segunda vez, límite)→ END

- **Modelo:** `ChatAnthropic` con el prompt de sistema, el modelo, el esfuerzo (`output_config`) y los tokens de salida
  de la semana 13, más las herramientas del servidor MCP y `responder`.
- **Herramientas:** el adaptador MCP de LangChain (`langchain-mcp-adapters`) con el token del usuario en una sola
  sesión por tarea (la actividad 1 mostró que sin sesión abre una por llamada). `responder` se valida con el mismo
  código que la semana 13 (`arnes.Registro`).
- **Límites:** los de la semana 13 (pasos, herramientas, tokens totales, que acotan el costo, y tiempo), revisados en el
  grafo antes de cada llamada; el `recursion_limit` de LangGraph queda como red de seguridad, no como límite real.
- **Checkpoints en memoria** (`InMemorySaver`), un hilo por corrida.
- **Human-in-the-loop:** antes de `proponer_orden_compra` el grafo se detiene con `interrupt()` y espera la decisión
  (`Command(resume="aprobar" | "rechazar")`). En la eval decide la política `aprobacion`; en la semana 17 la decide una
  persona. Una propuesta rechazada no llega al servidor y el modelo recibe el rechazo como error de herramienta.
"""
from __future__ import annotations

import asyncio
import json
import operator
import time
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from arnes.adaptador import Adaptador, Registro
from arnes.contrato import semana13

HERRAMIENTA_HITL = "proponer_orden_compra"


class Estado(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    recordatorio: bool
    errores_seguidos: int
    parada: dict | None
    decisiones: Annotated[list, operator.add]


def _texto_salida(contenido) -> str:
    """El adaptador devuelve el resultado MCP como texto o como bloques; el JSON de la herramienta va en el texto."""
    if isinstance(contenido, (list, tuple)):
        if len(contenido) == 2 and not isinstance(contenido[0], dict):   # (contenido, artefacto)
            contenido = contenido[0]
        partes = [c.get("text", "") if isinstance(c, dict) else str(c) for c in contenido]
        return "".join(partes)
    return str(contenido)


def construir_grafo(modelo_lc, herramientas_mcp: dict, reg: Registro, aprobacion: str | None):
    l13 = semana13()

    async def nodo_modelo(st: Estado):
        if motivo := reg.excedido():
            return {"parada": {"estado": "limite_alcanzado", "motivo": motivo}}
        t = time.perf_counter()
        try:
            ai: AIMessage = await modelo_lc.ainvoke([SystemMessage(reg.sistema())] + st["messages"])
        except Exception as e:  # noqa: BLE001  como la semana 13: un error de la API termina la tarea
            return {"parada": {"estado": "error", "motivo": f"api: {e}"[:300]}}
        pedidas = [c["name"] for c in ai.tool_calls]
        reg.modelo(ai.usage_metadata, 1000 * (time.perf_counter() - t), pedidas)
        if pedidas:
            return {"messages": [ai]}
        if (ai.response_metadata or {}).get("stop_reason") == "max_tokens":
            return {"messages": [ai], "parada": {"estado": "limite_alcanzado", "motivo": "max_tokens_salida"}}
        if st.get("recordatorio"):
            return {"messages": [ai], "parada": {"estado": "limite_alcanzado", "motivo": "sin_responder"}}
        return {"messages": [ai, HumanMessage("Deliver your final answer by calling the responder tool.")],
                "recordatorio": True}

    async def nodo_herramientas(st: Estado):
        ai: AIMessage = st["messages"][-1]
        llamadas = ai.tool_calls
        salidas, errores, decisiones = [], st.get("errores_seguidos", 0), []
        for c in llamadas:
            if reg.herramientas_agotadas():
                return {"messages": salidas, "parada": {"estado": "limite_alcanzado", "motivo": "max_herramientas"}}
            t = time.perf_counter()
            if c["name"] == "responder":
                if len(llamadas) > 1:
                    salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje":
                              "responder must be called alone, after the other tools have returned.",
                              "sugerencia": "Corrige los campos y llama responder de nuevo."}}
                    reg.herramienta("responder", 1000 * (time.perf_counter() - t), salida)
                else:
                    salida = reg.responder(c["args"])
                texto = json.dumps(salida, ensure_ascii=False, default=str)
            elif c["name"] == HERRAMIENTA_HITL and aprobacion is not None and c["name"] in herramientas_mcp:
                decision = interrupt({"herramienta": c["name"], "argumentos": c["args"], "corrida": reg.r.corrida})
                decisiones.append({"herramienta": c["name"], "decision": decision})
                if decision == "aprobar":
                    texto = _texto_salida(await herramientas_mcp[c["name"]].ainvoke(c["args"]))
                    salida = json.loads(texto)
                else:
                    salida = {"ok": False, "error": {"tipo": "rechazada_por_humano", "mensaje":
                              "A person rejected this purchase proposal.", "sugerencia": "Do not propose it again."}}
                    texto = json.dumps(salida, ensure_ascii=False)
                reg.herramienta(c["name"], 1000 * (time.perf_counter() - t), salida)
            elif c["name"] in herramientas_mcp:
                try:
                    texto = _texto_salida(await herramientas_mcp[c["name"]].ainvoke(c["args"]))
                    salida = json.loads(texto)
                except Exception as e:  # noqa: BLE001
                    # el adaptador convierte isError=true en ToolException con el texto de la herramienta: es el error
                    # estructurado del servidor (permiso_denegado, sql_invalido...), no un fallo del protocolo
                    try:
                        salida = json.loads(str(e))
                    except json.JSONDecodeError:
                        salida = {"ok": False, "error": {"tipo": "error_mcp", "mensaje": str(e)[:300]}}
                    texto = json.dumps(salida, ensure_ascii=False)
                reg.herramienta(c["name"], 1000 * (time.perf_counter() - t), salida)
            else:
                salida = {"ok": False, "error": {"tipo": "herramienta_desconocida", "mensaje": c["name"]}}
                texto = json.dumps(salida, ensure_ascii=False)
                reg.herramienta(c["name"], 0, salida)
            errores = 0 if salida.get("ok") else errores + 1
            salidas.append(ToolMessage(texto, tool_call_id=c["id"], name=c["name"], status="success" if salida.get("ok") else "error"))
        cambio = {"messages": salidas, "errores_seguidos": errores, "decisiones": decisiones}
        if reg.final is None and errores >= l13.MAX_ERRORES_SEGUIDOS:
            cambio["parada"] = {"estado": "limite_alcanzado", "motivo": "errores_herramienta"}
        return cambio

    def tras_modelo(st: Estado):
        return END if st.get("parada") else ("herramientas" if st["messages"][-1].type == "ai" else "modelo")

    def tras_herramientas(st: Estado):
        return END if st.get("parada") or reg.final is not None else "modelo"

    g = StateGraph(Estado)
    g.add_node("modelo", nodo_modelo)
    g.add_node("herramientas", nodo_herramientas)
    g.add_edge(START, "modelo")
    g.add_conditional_edges("modelo", tras_modelo, ["herramientas", "modelo", END])
    g.add_conditional_edges("herramientas", tras_herramientas, ["modelo", END])
    return g.compile(checkpointer=InMemorySaver())


class AdaptadorLangGraph(Adaptador):
    framework = "langgraph"

    def __init__(self, *a, aprobacion: str | None = "aprobar", **kw):
        """`aprobacion`: política del human-in-the-loop en corridas sin persona ("aprobar", "rechazar"), o None para no
        interrumpir. `decidir`: función (pausa) -> decisión; si existe, tiene prioridad (la semana 17 pone ahí a la persona)."""
        self.decidir = kw.pop("decidir", None)
        super().__init__(*a, **kw)
        self.aprobacion = aprobacion
        self.pausas: list[dict] = []
        self.checkpoints = 0

    def _modelo(self, herramientas: list):
        l13 = semana13()
        lim = self.limites or l13.Limites()
        m = ChatAnthropic(model=self.modelo, max_tokens=lim.max_tokens_salida, output_config={"effort": self.esfuerzo},
                          max_retries=3, **({"base_url": self.base_url, "api_key": "doble"} if self.base_url else {}))
        return m.bind_tools(herramientas + [Registro.herramienta_responder()])

    async def _resolver(self, tarea: dict):
        reg = self.registro(tarea)
        cliente = MultiServerMCPClient({"legado": {"transport": "streamable_http", "url": self.mcp_url,
                                                   "headers": {"Authorization": f"Bearer {self.token}"}}})
        async with cliente.session("legado") as sesion:
            tools = await load_mcp_tools(sesion)
            grafo = construir_grafo(self._modelo(tools), {t.name: t for t in tools}, reg, self.aprobacion)
            cfg = {"configurable": {"thread_id": reg.r.corrida}, "recursion_limit": 4 * reg.lim.max_pasos + 10}
            entrada = {"messages": [HumanMessage(reg.mensaje())], "recordatorio": False, "errores_seguidos": 0,
                       "parada": None, "decisiones": []}
            estado = await grafo.ainvoke(entrada, cfg)
            while "__interrupt__" in estado:                       # human-in-the-loop
                pausa = estado["__interrupt__"][0].value
                self.pausas.append(pausa)
                decision = self.decidir(pausa) if self.decidir else self.aprobacion
                estado = await grafo.ainvoke(Command(resume=decision), cfg)
            self.checkpoints = len([x async for x in grafo.aget_state_history(cfg)])
        parada = estado.get("parada") or {}
        self.decisiones = estado.get("decisiones", [])
        r = reg.parar(parada.get("estado"), parada.get("motivo", ""))
        self.ultimas_trazas = reg.traza.eventos
        return r

    def resolver(self, tarea: dict):
        return asyncio.run(self._resolver(tarea))
