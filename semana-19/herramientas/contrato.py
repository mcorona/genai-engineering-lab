"""Week 19, activity 7: the one contract between the callers of the tools Lambda and its handler.

`entrada_de_herramienta` is the internal call the handler runs (it moved here from agente/construccion.py so the tools
Lambda's adapters build the same call without importing the agent). Three formats reach the function and each has
its adapter (herramientas/adaptadores.py): the agent Lambda's lambda.invoke (direct), the AgentCore Gateway (MCP
target) and Bedrock Agents (action group). All three end in this same dictionary.
"""
from __future__ import annotations

HERRAMIENTAS = ("describir_esquema", "ejecutar_sql", "proponer_orden_compra")
TARGET = "herramientas"     # the gateway target's name: the gateway calls tools as `herramientas___<tool>`
SEPARADOR = "___"           # bedrock-agentcore/latest/devguide/gateway-tool-naming.html
SOLICITANTE = "solicitante"  # the requester of a proposal: the token's subject, never the model's choice


def entrada_de_herramienta(nombre: str, args: dict, solicitante: str | None = None) -> dict:
    if nombre == "describir_esquema":
        return {"herramienta": nombre}
    if nombre == "ejecutar_sql":
        return {"herramienta": nombre, "sql": args["sql"]}
    if nombre == "proponer_orden_compra":
        # The requester is the token's subject (agente/handler.py), outside the model's arguments.
        return {"herramienta": nombre, "entrada": args, "solicitante": solicitante}
    raise ValueError(f"herramienta sin binding: {nombre}")


def nombre_en_gateway(nombre: str) -> str:
    return f"{TARGET}{SEPARADOR}{nombre}"


def nombre_local(nombre_gateway: str) -> str:
    """`herramientas___ejecutar_sql` -> `ejecutar_sql`. Another target's prefix or an unknown tool is refused."""
    prefijo = TARGET + SEPARADOR
    if not isinstance(nombre_gateway, str) or not nombre_gateway.startswith(prefijo):
        raise ValueError("herramienta de otro target")
    nombre = nombre_gateway[len(prefijo):]
    if nombre not in HERRAMIENTAS:
        raise ValueError("herramienta desconocida")
    return nombre
