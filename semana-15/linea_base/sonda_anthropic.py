"""Semana 15, actividad 1: ¿cada framework habla con Claude (Haiku 5.5) y reporta tokens y costo? Sin API ($0).

    cd semana-15 && python linea_base/sonda_anthropic.py

Levanta en 127.0.0.1 un doble de la API de Mensajes de Anthropic (POST /v1/messages, con y sin streaming) que responde
siempre lo mismo: texto, 1200 tokens de entrada y 300 de salida. Cada framework apunta ahí con su integración de Claude
(nativa o por LiteLLM) y el modelo `claude-haiku-5-5`. Se registra qué pidió cada uno (modelo, streaming, herramientas)
y qué uso y costo reporta. Ningún dato sale del equipo. Escribe resultados/sonda_anthropic.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
MODELO = "claude-haiku-5-5"
ENTRADA, SALIDA = 1200, 300
PETICIONES: list[dict] = []


class Doble(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        PETICIONES.append({"ruta": self.path, "modelo": cuerpo.get("model"), "stream": bool(cuerpo.get("stream")),
                           "herramientas": len(cuerpo.get("tools") or []), "max_tokens": cuerpo.get("max_tokens"),
                           "x_api_key": bool(self.headers.get("x-api-key")), "version": self.headers.get("anthropic-version")})
        msg = {"id": "msg_doble", "type": "message", "role": "assistant", "model": cuerpo.get("model"),
               "content": [{"type": "text", "text": "hola"}], "stop_reason": "end_turn", "stop_sequence": None,
               "usage": {"input_tokens": ENTRADA, "output_tokens": SALIDA}}
        if not cuerpo.get("stream"):
            datos = json.dumps(msg).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
            return
        ev = [("message_start", {"type": "message_start", "message": {**msg, "content": [], "stop_reason": None,
                                                                      "usage": {"input_tokens": ENTRADA, "output_tokens": 1}}}),
              ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
              ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hola"}}),
              ("content_block_stop", {"type": "content_block_stop", "index": 0}),
              ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                 "usage": {"output_tokens": SALIDA}}),
              ("message_stop", {"type": "message_stop"})]
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for nombre, d in ev:
            self.wfile.write(f"event: {nombre}\ndata: {json.dumps(d)}\n\n".encode())
        self.wfile.flush()


SONDAS = {
    "langgraph": ("lg", '''
from langchain_anthropic import ChatAnthropic
m = ChatAnthropic(model=MODELO, base_url=BASE, api_key="doble", max_tokens=256)
r = m.invoke("hola")
out = {"integracion": "langchain_anthropic.ChatAnthropic (nativa)", "uso": r.usage_metadata, "costo_usd": None}
'''),
    "strands": ("st", '''
from strands import Agent
from strands.models.anthropic import AnthropicModel
m = AnthropicModel(client_args={"api_key": "doble", "base_url": BASE}, model_id=MODELO, max_tokens=256)
a = Agent(model=m, callback_handler=None)
r = a("hola")
out = {"integracion": "strands.models.anthropic.AnthropicModel (nativa)", "uso": dict(r.metrics.accumulated_usage), "costo_usd": None}
'''),
    "openai_agents": ("oa", '''
import asyncio
from agents import Agent, Runner, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel
set_tracing_disabled(True)
a = Agent(name="x", instructions="x", model=LitellmModel(model="anthropic/" + MODELO, base_url=BASE, api_key="doble"))
r = asyncio.run(Runner.run(a, "hola"))
u = r.context_wrapper.usage
import litellm
try:
    costo = litellm.cost_per_token(model=MODELO, prompt_tokens=ENTRADA, completion_tokens=SALIDA)
    costo = round(sum(costo), 6)
except Exception as e:
    costo = f"sin precio en LiteLLM {litellm.__version__ if hasattr(litellm, '__version__') else ''}: {type(e).__name__}"
out = {"integracion": "agents.extensions.models.litellm_model.LitellmModel (LiteLLM)",
       "uso": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}, "costo_usd": costo}
'''),
    "google_adk": ("adk", '''
import asyncio, warnings
warnings.filterwarnings("ignore")
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types
agente = LlmAgent(name="x", instruction="x", model=LiteLlm(model="anthropic/" + MODELO, api_base=BASE, api_key="doble"))
async def correr():
    run = InMemoryRunner(agent=agente, app_name="s")
    ses = await run.session_service.create_session(app_name="s", user_id="u")
    uso = None
    async for ev in run.run_async(user_id="u", session_id=ses.id, new_message=types.Content(role="user", parts=[types.Part(text="hola")])):
        if ev.usage_metadata:
            uso = {"prompt_token_count": ev.usage_metadata.prompt_token_count, "candidates_token_count": ev.usage_metadata.candidates_token_count}
    return uso
uso = asyncio.run(correr())
import litellm
try:
    costo = round(sum(litellm.cost_per_token(model=MODELO, prompt_tokens=ENTRADA, completion_tokens=SALIDA)), 6)
except Exception as e:
    costo = f"sin precio en LiteLLM: {type(e).__name__}"
out = {"integracion": "google.adk.models.lite_llm.LiteLlm (LiteLLM); google.adk.models.anthropic_llm.Claude solo por Vertex AI",
       "uso": uso, "costo_usd": costo}
'''),
}


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Doble)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    resultado = {"modelo": MODELO, "entrada": ENTRADA, "salida": SALIDA, "frameworks": {}}
    for fw, (venv, codigo) in SONDAS.items():
        antes = len(PETICIONES)
        prog = (f"MODELO={MODELO!r}; BASE={base!r}; ENTRADA={ENTRADA}; SALIDA={SALIDA}\n" + codigo
                + "\nimport json; print('RESULTADO ' + json.dumps(out, default=str))")
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}   # nunca la llave real
        p = subprocess.run([str(VENVS / venv / "bin" / "python"), "-c", prog], capture_output=True, text=True, timeout=120,
                           env={**env, "ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": "doble"})
        linea = next((x for x in reversed(p.stdout.splitlines()) if x.startswith("RESULTADO ")), None)
        r = json.loads(linea[10:]) if linea else {"error": (p.stderr or p.stdout)[-800:]}
        r["peticiones"] = PETICIONES[antes:]
        resultado["frameworks"][fw] = r
        print(f"{fw:<14} {json.dumps({k: r.get(k) for k in ('uso', 'costo_usd', 'error')}, default=str)[:300]} "
              f"peticiones={[(x['modelo'], x['stream']) for x in r['peticiones']]}", flush=True)
    srv.shutdown()
    (S15 / "resultados").mkdir(exist_ok=True)
    (S15 / "resultados" / "sonda_anthropic.json").write_text(json.dumps(resultado, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
