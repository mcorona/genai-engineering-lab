"""Semana 15, actividad 1: A2A en los frameworks que lo traen (Strands y Google ADK). Sin API ($0).

    cd semana-15 && python linea_base/sonda_a2a.py

Cada framework publica un agente con modelo guionado como servidor A2A (en memoria, con el cliente de pruebas de
Starlette). Se comprueba: Agent Card en /.well-known/agent-card.json y sus campos (versión de protocolo, interfaces,
esquemas de seguridad), una llamada con el método de la versión que declara, y si el servidor exige autenticación
cuando la tarjeta la declara. Escribe resultados/sonda_a2a.json.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))

COMUN = '''
import json, uuid, warnings
warnings.filterwarnings("ignore")
from starlette.testclient import TestClient

def probar(app):
    c = TestClient(app)
    card = c.get("/.well-known/agent-card.json").json()
    ver = card.get("protocolVersion") or [i.get("protocolVersion") for i in card.get("supportedInterfaces", [])]
    msg = {"role": "user", "parts": [{"kind": "text", "text": "hola"}], "messageId": str(uuid.uuid4())}
    msg1 = {"role": "ROLE_USER", "parts": [{"text": "hola"}], "messageId": str(uuid.uuid4())}
    intentos = []
    for metodo, m, hdr in (("SendMessage", msg1, {"A2A-Version": "1.0"}), ("message/send", msg, {})):
        rpc = card.get("url") or next((i.get("url") for i in card.get("supportedInterfaces", [])), "/")
        ruta = "/" + rpc.split("/", 3)[3] if rpc.count("/") >= 3 else "/"
        r = c.post(ruta, json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": {"message": m}}, headers=hdr)
        cuerpo = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        intentos.append({"metodo": metodo, "http": r.status_code, "error": (cuerpo.get("error") or {}).get("message"),
                         "texto": json.dumps(cuerpo.get("result"), ensure_ascii=False)[:120] if cuerpo.get("result") else None})
    return {"card_campos": sorted(card), "version_protocolo": ver,
            "seguridad_declarada": sorted((card.get("securitySchemes") or {}).keys()),
            "llamadas_sin_token": intentos}
'''

STRANDS = COMUN + '''
from strands import Agent
from strands.models.model import Model
from strands.multiagent.a2a import A2AServer
import importlib.metadata as md

class Guionado(Model):
    def __init__(self): self.config = {}
    def update_config(self, **kw): pass
    def get_config(self): return {}
    async def structured_output(self, *a, **kw): raise NotImplementedError
    async def stream(self, *a, **kw):
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockDelta": {"delta": {"text": "respuesta guionada"}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}

a = Agent(model=Guionado(), name="compras", description="Especialista de compras (propone, no ejecuta)", callback_handler=None)
srv = A2AServer(agent=a, http_url="http://127.0.0.1:9000/")
out = probar(srv.to_starlette_app())
out |= {"a2a_sdk": md.version("a2a-sdk"), "auth_en_servidor": "no hay parámetro: se agrega middleware a la app Starlette/FastAPI"}
print("RESULTADO " + json.dumps(out, ensure_ascii=False, default=str))
'''

ADK = COMUN + '''
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.genai import types
import importlib.metadata as md

class Guionado(BaseLlm):
    async def generate_content_async(self, req, stream=False):
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="respuesta guionada")]))

ag = LlmAgent(name="compras", description="Especialista de compras (propone, no ejecuta)", model=Guionado(model="g"), instruction="x")
esquemas = None
try:
    from a2a.types import SecurityScheme, OAuth2SecurityScheme, OAuthFlows, AuthorizationCodeOAuthFlow
    esquemas = {"keycloak": SecurityScheme(oauth2_security_scheme=OAuth2SecurityScheme(flows=OAuthFlows(
        authorization_code=AuthorizationCodeOAuthFlow(authorization_url="http://127.0.0.1:8180/a", token_url="http://127.0.0.1:8180/t",
                                                     scopes={"legado:compras:proponer": "proponer"}))))}
except Exception as e:
    nota = f"no se pudo construir SecurityScheme: {type(e).__name__}: {e}"
app = to_a2a(ag, host="127.0.0.1", port=8001, security_schemes=esquemas)
with TestClient(app) as _:
    pass
out = probar(app)
out |= {"a2a_sdk": md.version("a2a-sdk"), "esquema_construido": esquemas is not None}
print("RESULTADO " + json.dumps(out, ensure_ascii=False, default=str))
'''


def main():
    res = {}
    for fw, venv, prog in (("strands", "st", STRANDS), ("google_adk", "adk", ADK)):
        p = subprocess.run([str(VENVS / venv / "bin" / "python"), "-c", prog], capture_output=True, text=True, timeout=120)
        linea = next((x for x in reversed(p.stdout.splitlines()) if x.startswith("RESULTADO ")), None)
        res[fw] = json.loads(linea[10:]) if linea else {"error": (p.stderr or p.stdout)[-1500:]}
        print(fw, json.dumps(res[fw], ensure_ascii=False)[:900], flush=True)
    (S15 / "resultados" / "sonda_a2a.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
