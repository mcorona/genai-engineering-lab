"""Pasarela MCP con las defensas del cliente de la semana 14, para cualquier framework.

Las defensas (allowlist, pinning por hash contra `legado://manifiesto`, prefijo por servidor, resultados envueltos en
`untrusted_data`) viven en `ClienteSeguro`, que es un cliente MCP de Python. Para que LangGraph y Strands las usen sin
reimplementarlas, la pasarela publica el catálogo ya filtrado y prefijado del `ClienteSeguro` como un servidor MCP por
Streamable HTTP en 127.0.0.1, y cada llamada pasa por `ClienteSeguro.llamar`. El framework solo ve la pasarela: un
servidor bloqueado (rug pull, fuera de la allowlist) no existe para él, y todo resultado llega como dato no confiable.
Es el patrón de *MCP gateway*; aquí corre en el mismo proceso que el orquestador, que así conserva el registro de
llamadas que la eval de la semana 14 necesita para juzgar cada caso.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server

S14 = Path(__file__).resolve().parents[2] / "semana-14"
if str(S14) not in sys.path:
    sys.path.insert(0, str(S14))
from servidor.lab import ServidorHTTP  # noqa: E402


def crear_pasarela(cliente) -> Server:
    async def listar(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[types.Tool(name=d["name"], description=d.get("description", ""),
                                                       input_schema=d["input_schema"]) for d in cliente.definiciones()])

    async def llamar(ctx, params) -> types.CallToolResult:
        res = await anyio.to_thread.run_sync(cliente.llamar, params.name, params.arguments or {})
        texto = json.dumps(res, ensure_ascii=False, default=str)
        return types.CallToolResult(content=[types.TextContent(type="text", text=texto)],
                                    structured_content=json.loads(texto), is_error=not res.get("ok"))

    return Server("pasarela-segura", version="0.1.0", on_list_tools=listar, on_call_tool=llamar)


def abrir_pasarela(cliente) -> ServidorHTTP:
    """Servidor HTTP en un puerto libre de 127.0.0.1 (sin OAuth: solo loopback y solo para esta corrida)."""
    return ServidorHTTP(crear_pasarela(cliente), usuario="pasarela")
