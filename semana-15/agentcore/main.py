"""Semana 15, actividad 8: el agente Strands de la actividad 4, servido por AgentCore Runtime.

Es el mismo `resolver_peticion` que usa el trabajador local (arnes/puente.py): misma entrada (tarea, URL del servidor MCP,
token del usuario, límites) y misma salida (resultado con el contrato de la semana 13 y trazas comunes). Solo cambian:

- **Dónde corre:** una microVM de AgentCore por sesión (ARM64, Python 3.13, paquete CodeZip).
- **La llave de Anthropic:** no viaja en el paquete ni en variables de entorno. Se pide a AgentCore Identity
  (proveedor de llave de API) con el *workload access token* que Runtime entrega en cada invocación. Por eso la
  invocación lleva `runtimeUserId`: con autenticación IAM (SigV4), Runtime solo emite ese token para un usuario.
- **Arranque:** cada respuesta incluye cuánto lleva vivo el proceso, cuánto tardó en importar y cuántas invocaciones ha
  atendido, para separar arranque en frío de arranque en caliente.

    {"ping": true}                       → solo datos de arranque (sin modelo, sin llave)
    {"tarea": {...}, "mcp_url": ..., "token": ..., "limites": {...}}   → una corrida del agente

El token MCP del usuario llega en la carga útil (TLS hasta Runtime) y no se registra: ni este código ni el adaptador
imprimen la carga útil.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

T0 = time.time()
RAIZ = Path(__file__).resolve().parent
S15 = RAIZ / "semana-15" if (RAIZ / "semana-15").is_dir() else RAIZ.parent   # paquete CodeZip o repositorio
sys.path.insert(0, str(S15))

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402
from bedrock_agentcore.runtime.context import BedrockAgentCoreContext  # noqa: E402

from arnes.puente import resolver_peticion  # noqa: E402
import adaptadores.strands  # noqa: E402,F401  importar aquí: el costo de importación cuenta como arranque, no como tarea

IMPORTACION_S = round(time.time() - T0, 3)
PROVEEDOR = os.environ.get("PROVEEDOR_LLAVE", "semana15-anthropic")
app = BedrockAgentCoreApp()
_estado = {"invocaciones": 0, "llave": False}


def _llave_de_identity() -> None:
    """Pide la llave a AgentCore Identity una vez por proceso y la deja solo en memoria del proceso."""
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
    if not payload.get("base_url"):          # con el modelo simulado (pruebas) no hace falta la llave
        try:
            _llave_de_identity()
        except Exception as e:  # noqa: BLE001
            return {"error": f"identity: {type(e).__name__}: {e}"[:500], "arranque": arranque}
    arranque["llave_s"] = round(time.time() - t, 3)
    out = resolver_peticion("strands", payload)
    out["arranque"] = arranque
    return out


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PUERTO", "8080")))   # en AgentCore, 8080; en pruebas, un puerto libre
