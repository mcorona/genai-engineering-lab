"""Semana 15, actividad 6 (spike): el agente de la semana 13 en Google ADK, con Claude por LiteLLM.

- **Modelo:** `LiteLlm("anthropic/claude-haiku-5-5")` con `max_tokens` y `output_config` de la semana 13. El `Claude`
  nativo de ADK solo funciona por Vertex AI.
- **Prompt:** la instrucción va como función (`InstructionProvider`) para que ADK no interprete llaves como variables de
  estado. ADK agrega siempre una línea de identidad al prompt de sistema ("You are an agent. Your internal name is
  ..."), así que el prompt no es idéntico al de la semana 13: es el de la semana 13 más esa línea.
- **Herramientas:** `McpToolset` con el token del usuario (ADK negocia el protocolo 2025-11-25, actividad 1);
  `responder` es un `BaseTool` con el JSON Schema de la semana 13; una respuesta válida activa `skip_summarization`
  para que ADK no vuelva a llamar al modelo.
- **Reglas de la semana 13:** callbacks del agente (`before_model`, `after_model`, `before_tool`, `after_tool`). Un límite
  alcanzado en `before_model` devuelve una respuesta sin llamar al modelo y la corrida termina con ese estado.
- Sin human-in-the-loop en el spike (ADK lo ofrece con `require_confirmation`).
"""
from __future__ import annotations

import asyncio
import json
import time
import warnings

warnings.filterwarnings("ignore")
from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.adk.tools.base_tool import BaseTool  # noqa: E402
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams  # noqa: E402
from google.genai import types  # noqa: E402

from arnes.adaptador import Adaptador, Registro  # noqa: E402
from arnes.contrato import semana13  # noqa: E402

RECORDATORIO = "Deliver your final answer by calling the responder tool."


def _salida(resp) -> dict:
    if isinstance(resp, dict) and "ok" in resp:
        return resp
    if isinstance(resp, dict):
        sc = resp.get("structuredContent") or resp.get("structured_content")
        if isinstance(sc, dict) and "ok" in sc:
            return sc
        texto = "".join(c.get("text", "") for c in resp.get("content", []) if isinstance(c, dict))
    else:
        texto = str(resp)
    try:
        s = json.loads(texto)
        return s if isinstance(s, dict) else {"ok": False, "error": {"tipo": "salida_no_json"}}
    except json.JSONDecodeError:
        return {"ok": False, "error": {"tipo": "error_mcp", "mensaje": texto[:300]}}


class Responder(BaseTool):
    def __init__(self, reg: Registro, estado: dict):
        spec = Registro.herramienta_responder()
        super().__init__(name="responder", description=spec["description"])
        self.reg, self.estado, self.esquema = reg, estado, spec["input_schema"]

    def _get_declaration(self):
        return types.FunctionDeclaration(name=self.name, description=self.description,
                                         parameters_json_schema=self.esquema)

    async def run_async(self, *, args, tool_context):
        if len(self.estado["turno"]) > 1:
            salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje":
                      "responder must be called alone, after the other tools have returned.",
                      "sugerencia": "Corrige los campos y llama responder de nuevo."}}
            self.reg.herramienta("responder", 0, salida)
        else:
            salida = self.reg.responder(args)
        self.estado["errores"] = 0 if self.reg.final else self.estado["errores"] + 1
        if self.reg.final is not None:
            tool_context.actions.skip_summarization = True
        return salida


class AdaptadorGoogleADK(Adaptador):
    framework = "google_adk"

    def __init__(self, *a, aprobacion=None, **kw):
        kw.pop("decidir", None)
        super().__init__(*a, **kw)

    async def _resolver(self, tarea: dict):
        lim = self.limites or semana13().Limites()
        reg = self.registro(tarea)
        est = {"errores": 0, "parada": None, "t": 0.0, "turno": [], "t_tool": 0.0}

        def parar(estado, motivo):
            est["parada"] = est["parada"] or {"estado": estado, "motivo": motivo}
            return LlmResponse(content=types.Content(role="model", parts=[types.Part(text="stopped")]))

        def antes_modelo(callback_context, llm_request):
            if est["parada"]:
                return parar(**est["parada"])
            if reg.final is None and est["errores"] >= semana13().MAX_ERRORES_SEGUIDOS:
                return parar("limite_alcanzado", "errores_herramienta")
            if motivo := reg.excedido():
                return parar("limite_alcanzado", motivo)
            est["t"] = time.perf_counter()
            return None

        def despues_modelo(callback_context, llm_response):
            if est["parada"] or llm_response.partial:
                return None
            partes = (llm_response.content.parts if llm_response.content else None) or []
            est["turno"] = [p.function_call.name for p in partes if p.function_call]
            u = llm_response.usage_metadata
            reg.modelo({"prompt_token_count": (u.prompt_token_count or 0) if u else 0,
                        "candidates_token_count": (u.candidates_token_count or 0) if u else 0},
                       1000 * (time.perf_counter() - est["t"]), est["turno"])
            return None

        def antes_herramienta(tool, args, tool_context):
            if est["parada"]:
                return {"ok": False, "error": {"tipo": "detenida"}}
            if reg.herramientas_agotadas():
                parar("limite_alcanzado", "max_herramientas")
                return {"ok": False, "error": {"tipo": "detenida"}}
            est["t_tool"] = time.perf_counter()
            return None

        def despues_herramienta(tool, args, tool_context, tool_response):
            if tool.name == "responder" or est["parada"]:
                return None
            salida = _salida(tool_response)
            reg.herramienta(tool.name, 1000 * (time.perf_counter() - est["t_tool"]), salida)
            est["errores"] = 0 if salida.get("ok") else est["errores"] + 1
            return None

        extra = {"api_base": self.base_url, "api_key": "doble"} if self.base_url else {}
        modelo = LiteLlm(model="anthropic/" + self.modelo, max_tokens=lim.max_tokens_salida,
                         output_config={"effort": self.esfuerzo}, timeout=120, **extra)
        mcp = McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=self.mcp_url, headers={"Authorization": f"Bearer {self.token}"}, timeout=30))
        sistema = reg.sistema()
        agente = LlmAgent(name="legado", model=modelo, instruction=lambda ctx: sistema,
                          tools=[mcp, Responder(reg, est)], before_model_callback=antes_modelo,
                          after_model_callback=despues_modelo, before_tool_callback=antes_herramienta,
                          after_tool_callback=despues_herramienta)
        runner = InMemoryRunner(agent=agente, app_name="legado")
        ses = await runner.session_service.create_session(app_name="legado", user_id="u")
        mensaje, recordatorio = reg.mensaje(), False
        try:
            while True:
                try:
                    async for _ in runner.run_async(user_id="u", session_id=ses.id, new_message=types.Content(
                            role="user", parts=[types.Part(text=mensaje)])):
                        pass
                except Exception as e:  # noqa: BLE001
                    est["parada"] = est["parada"] or {"estado": "error", "motivo": f"{type(e).__name__}: {e}"[:300]}
                    break
                if reg.final is not None or est["parada"]:
                    break
                if recordatorio:
                    est["parada"] = {"estado": "limite_alcanzado", "motivo": "sin_responder"}
                    break
                recordatorio, mensaje = True, RECORDATORIO
        finally:
            await mcp.close()
        parada = est["parada"] or {}
        r = reg.parar(None if reg.final else parada.get("estado"), parada.get("motivo", ""))
        self.ultimas_trazas = reg.traza.eventos
        return r

    def resolver(self, tarea: dict):
        return asyncio.run(self._resolver(tarea))
