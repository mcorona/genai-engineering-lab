"""Week 15, activity 8: the activity 4 Strands agent, served by AgentCore Runtime.

It is the same `resolver_peticion` the local worker uses (arnes/puente.py): the same input (task, MCP server URL,
user token, limits) and the same output (a result with the week 13 contract and common traces). Only these change:

- **Where it runs:** one AgentCore microVM per session (ARM64, Python 3.13, a CodeZip package).
- **The Anthropic key:** it travels neither in the package nor in environment variables. It is requested from AgentCore Identity
  (an API key provider) with the *workload access token* that Runtime delivers on each invocation. That is why the
  invocation carries `runtimeUserId`: with IAM authentication (SigV4), Runtime only issues that token for a user.
- **Start-up:** each response includes how long the process has been alive, how long it took to import and how many invocations it has
  served, to separate cold starts from warm starts.

    {"ping": true}                       → start-up data only (no model, no key)
    {"tarea": {...}, "mcp_url": ..., "token": ..., "limites": {...}}   → one agent run

The user's MCP token arrives in the payload (TLS up to Runtime) and is not logged: neither this code nor the adapter
prints the payload.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

T0 = time.time()
RAIZ = Path(__file__).resolve().parent
S15 = RAIZ / "semana-15" if (RAIZ / "semana-15").is_dir() else RAIZ.parent   # CodeZip package or repository
sys.path.insert(0, str(S15))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402
from bedrock_agentcore.runtime.context import BedrockAgentCoreContext  # noqa: E402

from arnes.puente import resolver_peticion  # noqa: E402
import adaptadores.strands  # noqa: E402,F401  import here: the import cost counts as start-up, not as the task

IMPORTACION_S = round(time.time() - T0, 3)
PROVEEDOR = os.environ.get("PROVEEDOR_LLAVE", "semana15-anthropic")
app = BedrockAgentCoreApp()
_estado = {"invocaciones": 0, "llave": False}


def _llave_de_identity() -> None:
    """Requests the key from AgentCore Identity once per process and keeps it only in the process's memory."""
    if _estado["llave"]:
        return
    import boto3
    token = BedrockAgentCoreContext.get_workload_access_token()
    if not token:
        raise RuntimeError("sin workload access token: invoca con runtimeUserId (autenticación IAM)")
    cliente = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    os.environ["ANTHROPIC_API_KEY"] = cliente.get_resource_api_key(
        workloadIdentityToken=token, resourceCredentialProviderName=PROVEEDOR)["apiKey"]
    _estado["llave"] = True


@app.entrypoint
def invocar(payload: dict, context=None) -> dict:
    _estado["invocaciones"] += 1
    arranque = {"proceso_s": round(time.time() - T0, 3), "importacion_s": IMPORTACION_S,
                "invocacion": _estado["invocaciones"], "pid": os.getpid()}
    if payload.get("ping"):
        return {"ping": True, "arranque": arranque}
    t = time.time()
    if not payload.get("base_url"):          # with the simulated model (tests) the key is not needed
        try:
            _llave_de_identity()
        except Exception as e:  # noqa: BLE001
            return {"error": f"identity: {type(e).__name__}: {e}"[:500], "arranque": arranque}
    arranque["llave_s"] = round(time.time() - t, 3)
    out = resolver_peticion("strands", payload)
    out["arranque"] = arranque
    return out


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PUERTO", "8080")))   # 8080 in AgentCore; a free port in tests
