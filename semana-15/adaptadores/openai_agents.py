"""Week 15, activity 6 (spike): the week 13 agent in the OpenAI Agents SDK, with Claude through LiteLLM.

- **Model:** `LitellmModel("anthropic/claude-haiku-5-5")` with week 13's `max_tokens` and effort in
  `ModelSettings.extra_args` (with `extra_body`, LiteLLM 1.83 sends the literal key `extra_body` inside the JSON, which the
  Anthropic API would reject; with `reasoning_effort` it translates it to `thinking` with a 1024-token budget).
- **Tools:** `MCPServerStreamableHttp` with the user's token (protocol 2026-07-28); `responder` is a
  `FunctionTool` with week 13's JSON Schema and validation; `tool_use_behavior` ends the run only when
  the final answer is valid.
- **Week 13 rules:** `RunHooks` (before and after each model call and each tool). A limit
  reached raises `Parada` from the hook, and the run ends with that state.
- **Tracing:** disabled; the default exporter sends the traces to OpenAI (activity 1).
- No human-in-the-loop in the spike (the SDK offers it with approvals of MCP tools).
"""
from __future__ import annotations

import asyncio
import json
import time

from agents import (Agent, FunctionTool, ModelSettings, RunHooks, Runner, ToolsToFinalOutputResult,
                    set_tracing_disabled)
from agents.extensions.models.litellm_model import LitellmModel
from agents.mcp import MCPServerStreamableHttp

from arnes.adaptador import Adaptador, Registro
from arnes.contrato import semana13

set_tracing_disabled(True)
RECORDATORIO = "Deliver your final answer by calling the responder tool."


class Parada(Exception):
    pass


def _salida(texto) -> dict:
    """The SDK delivers the MCP result as a dict or a list of blocks ({"type": "text", "text": ...}), or as its text."""
    if isinstance(texto, list):
        return _salida("".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in texto))
    if isinstance(texto, dict):
        return _salida(texto["text"]) if texto.get("type") == "text" and "text" in texto else texto
    if isinstance(texto, str) and texto.startswith(("{'", "[{'")):
        import ast
        try:
            return _salida(ast.literal_eval(texto))
        except (ValueError, SyntaxError):
            pass
    try:
        s = json.loads(str(texto))
        if isinstance(s, dict):
            return _salida(s) if s.get("type") == "text" and "text" in s else s
        if isinstance(s, list):                       # MCP content blocks
            return _salida(s)
    except json.JSONDecodeError:
        pass
    return {"ok": False, "error": {"tipo": "error_mcp", "mensaje": str(texto)[:300]}}


class Reglas(RunHooks):
    def __init__(self, reg: Registro):
        self.reg, self.errores, self.parada, self.t, self.turno = reg, 0, None, 0.0, []

    def _parar(self, estado, motivo):
        self.parada = self.parada or {"estado": estado, "motivo": motivo}
        raise Parada(motivo)

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        if self.reg.final is None and self.errores >= semana13().MAX_ERRORES_SEGUIDOS:
            self._parar("limite_alcanzado", "errores_herramienta")
        if motivo := self.reg.excedido():
            self._parar("limite_alcanzado", motivo)
        self.t = time.perf_counter()

    async def on_llm_end(self, context, agent, response):
        self.turno = [getattr(x, "name", None) for x in response.output if getattr(x, "type", "") == "function_call"]
        self.reg.modelo(response.usage, 1000 * (time.perf_counter() - self.t), self.turno)

    async def on_tool_start(self, context, agent, tool):
        if self.reg.herramientas_agotadas():
            self._parar("limite_alcanzado", "max_herramientas")
        self._t_tool = time.perf_counter()

    async def on_tool_end(self, context, agent, tool, result):
        if tool.name == "responder":
            self.errores = 0 if self.reg.final else self.errores + 1
            return
        salida = _salida(result)
        self.reg.herramienta(tool.name, 1000 * (time.perf_counter() - self._t_tool), salida)
        self.errores = 0 if salida.get("ok") else self.errores + 1


class AdaptadorOpenAIAgents(Adaptador):
    framework = "openai_agents"

    def __init__(self, *a, aprobacion=None, **kw):
        kw.pop("decidir", None)
        super().__init__(*a, **kw)

    def _responder(self, reg: Registro, reglas: Reglas) -> FunctionTool:
        spec = Registro.herramienta_responder()

        async def invocar(ctx, args_json: str) -> str:
            if len(reglas.turno) > 1:
                salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje":
                          "responder must be called alone, after the other tools have returned.",
                          "sugerencia": "Corrige los campos y llama responder de nuevo."}}
                reg.herramienta("responder", 0, salida)
            else:
                try:
                    entrada = json.loads(args_json or "{}")
                except json.JSONDecodeError:
                    entrada = {}
                salida = reg.responder(entrada)
            return json.dumps(salida, ensure_ascii=False)
        return FunctionTool(name="responder", description=spec["description"], params_json_schema=spec["input_schema"],
                            on_invoke_tool=invocar, strict_json_schema=False)

    async def _resolver(self, tarea: dict):
        lim = self.limites or semana13().Limites()
        reg = self.registro(tarea)
        reglas = Reglas(reg)
        modelo = LitellmModel(model="anthropic/" + self.modelo, base_url=self.base_url,
                              api_key="doble" if self.base_url else None)
        ajustes = ModelSettings(max_tokens=lim.max_tokens_salida, extra_args={"output_config": {"effort": self.esfuerzo},
                                                                             "timeout": 120})

        def fin(ctx, resultados):
            return ToolsToFinalOutputResult(is_final_output=reg.final is not None, final_output="responder")

        async with MCPServerStreamableHttp(params={"url": self.mcp_url, "headers": {"Authorization": f"Bearer {self.token}"},
                                                   "timeout": 30}, name="legado", cache_tools_list=True,
                                           client_session_timeout_seconds=60) as mcp:
            agente = Agent(name="legado", instructions=reg.sistema(), model=modelo, model_settings=ajustes,
                           mcp_servers=[mcp], tools=[self._responder(reg, reglas)], tool_use_behavior=fin)
            entrada, recordatorio = reg.mensaje(), False
            while True:
                try:
                    res = await Runner.run(agente, entrada, hooks=reglas, max_turns=4 * lim.max_pasos + 10)
                except Parada:
                    break
                except Exception as e:  # noqa: BLE001
                    reglas.parada = reglas.parada or {"estado": "error", "motivo": f"{type(e).__name__}: {e}"[:300]}
                    break
                if reg.final is not None:
                    break
                if recordatorio:
                    reglas.parada = {"estado": "limite_alcanzado", "motivo": "sin_responder"}
                    break
                recordatorio = True
                entrada = res.to_input_list() + [{"role": "user", "content": RECORDATORIO}]
        parada = reglas.parada or {}
        r = reg.parar(None if reg.final else parada.get("estado"), parada.get("motivo", ""))
        self.ultimas_trazas = reg.traza.eventos
        return r

    def resolver(self, tarea: dict):
        return asyncio.run(self._resolver(tarea))
