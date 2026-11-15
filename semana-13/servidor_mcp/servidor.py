"""Week 13, activity 4: an MCP server (stdio) with the same tool catalog.

It exposes the five activity 2 tools with the same names, descriptions and JSON Schemas
(`herramientas.definiciones()`), and runs each call with the same implementation (`Herramientas.llamar`). That way the
server duplicates no logic: the guard, permissions, limits and structured errors are the same.

Permissions: the user is set by whoever registers the server (the host: Claude Code, the agent or the inspector) with the
MCP_USUARIO variable (analista by default), never by the model. The tools' arguments admit no roles or user.

Database (herramientas/conexion.py): NLQ_LEGADO_DSN, or PG_ADMIN_DSN to recreate copilot_nlq, or PG_DSN
(copilot_ro). Without any of them, the tools that need no database work and the others return `sin_base`.

    MCP_USUARIO=analista python semana-13/servidor_mcp/servidor.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mcp_types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from herramientas import Contexto, Herramientas, definiciones  # noqa: E402

USUARIO = os.environ.get("MCP_USUARIO", "analista")
IDIOMA = os.environ.get("MCP_IDIOMA", "es")
_h: Herramientas | None = None


def herramientas() -> Herramientas:
    global _h
    if _h is None:
        conn = None
        if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN", "PG_DSN")):
            from herramientas.conexion import conectar
            conn, rol = conectar()
            print(f"[MCP server] user {USUARIO}, database role {rol}", file=sys.stderr)
        else:
            print(f"[MCP server] user {USUARIO}, no database", file=sys.stderr)
        _h = Herramientas(Contexto.de_usuario(USUARIO, conexion=conn, idioma=IDIOMA))
    return _h


async def listar(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[types.Tool(name=d["name"], description=d["description"], input_schema=d["input_schema"])
                                        for d in definiciones()])


async def llamar(ctx, params) -> types.CallToolResult:
    h = herramientas()
    res = h.llamar(params.name, params.arguments or {})
    del h.ctx.llamadas[:-200]  # the process's call log does not grow without bound
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False, default=str))],
                                structured_content=res, is_error=not res["ok"])


servidor = Server("legado-semana13", version="0.1.0",
                  instructions="Read-only tools over a legacy inventory schema: describe the schema, look up business "
                               "rules, sample values, validate and run SELECT queries.",
                  on_list_tools=listar, on_call_tool=llamar)


async def main():
    async with stdio_server() as (lectura, escritura):
        await servidor.run(lectura, escritura, servidor.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
