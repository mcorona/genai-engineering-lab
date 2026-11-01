"""Semana 15, actividad 4: el agente de la semana 13 en Strands Agents.

Strands es un loop dirigido por el modelo (no hay grafo que dibujar): se le dan el modelo, el prompt y las herramientas, y
las reglas de la semana 13 entran por **hooks**, el mecanismo de extensión del framework:

| Hook                    | Qué hace                                                                                |
|-------------------------|-----------------------------------------------------------------------------------------|
| `BeforeModelCallEvent`  | Límites antes de cada llamada (3 errores seguidos, pasos, tokens totales, tiempo): `cancel` |
| `AfterModelCallEvent`   | Cuenta el paso, los tokens, el costo y las herramientas pedidas; traza `modelo`          |
| `BeforeToolCallEvent`   | `max_herramientas`; `responder` solo en su turno; **interrupción** antes de proponer       |
| `AfterToolCallEvent`    | Resultado de cada herramienta (error estructurado del servidor incluido); traza `herramienta` |

- **Modelo:** `AnthropicModel` directo (no Bedrock), con el modelo, los tokens de salida y el esfuerzo de la semana 13.
  El uso de tokens de cada llamada se toma del evento `metadata` del stream, porque las métricas del agente se
  actualizan después de `AfterModelCallEvent`.
- **Herramientas:** `MCPClient` de Strands con el token del usuario (protocolo 2026-07-28), ejecución secuencial como
  la semana 13 y sin recorte de la conversación; `responder` con el JSON Schema y la validación de la semana 13.
- **Fin:** un `responder` válido llama `agent.cancel(after_current_tools=True)`. Sin herramientas, un recordatorio (una
  segunda invocación con el mismo texto que la semana 13) y luego `sin_responder`.
- **Human-in-the-loop:** `event.interrupt()` antes de `proponer_orden_compra`; el agente vuelve con
  `stop_reason="interrupt"` y se reanuda con `interruptResponse`. Mismas políticas que LangGraph.
"""
from __future__ import annotations

import json
import time

from strands import Agent
from strands.agent.conversation_manager import NullConversationManager
from strands.hooks import (AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent, BeforeToolCallEvent,
                           HookProvider, HookRegistry)
from strands.models.anthropic import AnthropicModel
from strands.tools.executors import SequentialToolExecutor
from strands.tools.mcp import MCPClient
from strands.tools.tools import PythonAgentTool

from arnes.adaptador import Adaptador, Registro
from arnes.contrato import semana13

HERRAMIENTA_HITL = "proponer_orden_compra"
RECORDATORIO = "Deliver your final answer by calling the responder tool."


class ModeloContado(AnthropicModel):
    """AnthropicModel que deja a la vista el uso de la última llamada (evento `metadata` del stream)."""
    ultimo_uso: dict | None = None

    async def stream(self, *a, **kw):
        self.ultimo_uso = None
        async for ev in super().stream(*a, **kw):
            if "metadata" in ev:
                self.ultimo_uso = ev["metadata"].get("usage")
            yield ev


def _salida_de(resultado: dict | None) -> dict:
    texto = "".join(c.get("text", "") for c in (resultado or {}).get("content", []) if isinstance(c, dict))
    try:
        salida = json.loads(texto)
        return salida if isinstance(salida, dict) else {"ok": False, "error": {"tipo": "salida_no_json"}}
    except json.JSONDecodeError:
        return {"ok": False, "error": {"tipo": "error_mcp", "mensaje": texto[:300]}}


class ReglasSemana13(HookProvider):
    def __init__(self, reg: Registro, modelo: ModeloContado, conocidas: set[str], aprobacion: str | None):
        self.reg, self.modelo, self.conocidas, self.aprobacion = reg, modelo, conocidas, aprobacion
        self.parada: dict | None = None
        self.errores_seguidos = 0
        self.t_modelo = 0.0
        self.ya_registradas: set[str] = set()
        self.pausas, self.decisiones = [], []

    def register_hooks(self, registry: HookRegistry, **kw):
        registry.add_callback(BeforeModelCallEvent, self.antes_modelo)
        registry.add_callback(AfterModelCallEvent, self.despues_modelo)
        registry.add_callback(BeforeToolCallEvent, self.antes_herramienta)
        registry.add_callback(AfterToolCallEvent, self.despues_herramienta)

    def _parar(self, estado: str, motivo: str):
        if self.parada is None:
            self.parada = {"estado": estado, "motivo": motivo}

    def antes_modelo(self, ev: BeforeModelCallEvent):
        if self.parada:
            ev.cancel = "stopped"
            return
        if self.reg.final is None and self.errores_seguidos >= semana13().MAX_ERRORES_SEGUIDOS:
            self._parar("limite_alcanzado", "errores_herramienta")
        elif motivo := self.reg.excedido():
            self._parar("limite_alcanzado", motivo)
        if self.parada:
            ev.cancel = "stopped"
        self.t_modelo = time.perf_counter()

    def despues_modelo(self, ev: AfterModelCallEvent):
        if self.parada or ev.stop_response is None:      # llamada cancelada por un límite: no es un paso
            if ev.exception is not None and not self.parada:
                self._parar("error", f"api: {ev.exception}"[:300])
            return
        pedidas = [b["toolUse"]["name"] for b in ev.stop_response.message["content"] if "toolUse" in b]
        self.reg.modelo(self.modelo.ultimo_uso, 1000 * (time.perf_counter() - self.t_modelo), pedidas)
        if not pedidas and ev.stop_response.stop_reason == "max_tokens":
            self._parar("limite_alcanzado", "max_tokens_salida")

    def antes_herramienta(self, ev: BeforeToolCallEvent):
        nombre, uid = ev.tool_use["name"], ev.tool_use["toolUseId"]
        if self.parada:
            ev.cancel_tool = "stopped"
            return
        if self.reg.herramientas_agotadas():
            self._parar("limite_alcanzado", "max_herramientas")
            ev.cancel_tool = "stopped"
            ev.agent.cancel()
            return
        if nombre == "responder":
            ultimo = ev.agent.messages[-1]["content"]
            if sum(1 for b in ultimo if "toolUse" in b) > 1:
                salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje":
                          "responder must be called alone, after the other tools have returned.",
                          "sugerencia": "Corrige los campos y llama responder de nuevo."}}
                self.reg.herramienta("responder", 0, salida)
                self.errores_seguidos += 1
                self.ya_registradas.add(uid)
                ev.cancel_tool = json.dumps(salida, ensure_ascii=False)
            return
        if nombre == HERRAMIENTA_HITL and self.aprobacion is not None and nombre in self.conocidas:
            pausa = {"herramienta": nombre, "argumentos": ev.tool_use["input"], "corrida": self.reg.r.corrida}
            decision = ev.interrupt("aprobacion_" + nombre, reason=pausa)     # la primera vez detiene el agente
            self.decisiones.append({"herramienta": nombre, "decision": decision})
            if decision != "aprobar":
                ev.cancel_tool = json.dumps({"ok": False, "error": {"tipo": "rechazada_por_humano", "mensaje":
                                             "A person rejected this purchase proposal.",
                                             "sugerencia": "Do not propose it again."}}, ensure_ascii=False)

    def despues_herramienta(self, ev: AfterToolCallEvent):
        nombre, uid = ev.tool_use["name"], ev.tool_use["toolUseId"]
        if nombre == "responder" or uid in self.ya_registradas or (self.parada and ev.result is None):
            if nombre == "responder" and uid not in self.ya_registradas:
                self.errores_seguidos = 0 if self.reg.final else self.errores_seguidos + 1
            return
        if ev.selected_tool is None and nombre not in self.conocidas:
            salida = {"ok": False, "error": {"tipo": "herramienta_desconocida", "mensaje": nombre}}
        elif self.parada and (ev.result or {}).get("status") == "error" and "stopped" in json.dumps(ev.result):
            return
        else:
            salida = _salida_de(ev.result)
        self.reg.herramienta(nombre, 1000 * (ev.duration or 0) if isinstance(ev.duration, (int, float)) else 0, salida)
        self.errores_seguidos = 0 if salida.get("ok") else self.errores_seguidos + 1


class AdaptadorStrands(Adaptador):
    framework = "strands"

    def __init__(self, *a, aprobacion: str | None = "aprobar", **kw):
        self.decidir = kw.pop("decidir", None)
        super().__init__(*a, **kw)
        self.aprobacion = aprobacion
        self.pausas: list[dict] = []
        self.decisiones: list[dict] = []

    def _herramienta_responder(self, reg: Registro) -> PythonAgentTool:
        spec = Registro.herramienta_responder()

        def responder(tool_use, **_):
            salida = reg.responder(tool_use["input"])
            if reg.final is not None:
                _["agent"].cancel(after_current_tools=True)
            return {"toolUseId": tool_use["toolUseId"], "status": "success" if salida.get("ok") else "error",
                    "content": [{"text": json.dumps(salida, ensure_ascii=False)}]}
        responder.__name__ = "responder"
        return PythonAgentTool("responder", {"name": "responder", "description": spec["description"],
                                             "inputSchema": {"json": spec["input_schema"]}}, responder)

    def resolver(self, tarea: dict):
        lim = self.limites or semana13().Limites()
        reg = self.registro(tarea)
        modelo = ModeloContado(client_args={"api_key": "doble", "base_url": self.base_url} if self.base_url else {},
                               model_id=self.modelo, max_tokens=lim.max_tokens_salida,
                               params={"output_config": {"effort": self.esfuerzo}})
        cliente = MCPClient(url=self.mcp_url, headers={"Authorization": f"Bearer {self.token}"})
        with cliente:
            tools = cliente.list_tools_sync()
            reglas = ReglasSemana13(reg, modelo, {t.tool_name for t in tools} | {"responder"}, self.aprobacion)
            agente = Agent(model=modelo, system_prompt=reg.sistema(), tools=tools + [self._herramienta_responder(reg)],
                           hooks=[reglas], tool_executor=SequentialToolExecutor(), callback_handler=None,
                           conversation_manager=NullConversationManager())
            prompt, recordatorio = reg.mensaje(), False
            while True:
                try:
                    res = agente(prompt)
                except Exception as e:  # noqa: BLE001
                    reglas._parar("error", f"api: {e}"[:300])
                    break
                if res.stop_reason == "interrupt":                    # human-in-the-loop
                    respuestas = []
                    for i in res.interrupts:
                        self.pausas.append(i.reason)
                        decision = self.decidir(i.reason) if self.decidir else self.aprobacion
                        respuestas.append({"interruptResponse": {"interruptId": i.id, "response": decision}})
                    prompt = respuestas
                    continue
                if reg.final is not None or reglas.parada:
                    break
                if recordatorio:
                    reglas._parar("limite_alcanzado", "sin_responder")
                    break
                recordatorio, prompt = True, RECORDATORIO
        self.decisiones = reglas.decisiones
        parada = reglas.parada or {}
        r = reg.parar(None if reg.final else parada.get("estado"), parada.get("motivo", ""))
        self.ultimas_trazas = reg.traza.eventos
        return r
