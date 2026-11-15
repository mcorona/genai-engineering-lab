"""An MCP gateway with week 14's client defenses, for any framework.

The defenses (an allowlist, hash pinning against `legado://manifiesto`, a per-server prefix, results wrapped in
`untrusted_data`) live in `ClienteSeguro`, which is a Python MCP client. So that LangGraph and Strands use them without
reimplementing them, the gateway publishes `ClienteSeguro`'s already filtered and prefixed catalog as an MCP server over
Streamable HTTP on 127.0.0.1, and each call goes through `ClienteSeguro.llamar`. The framework only sees the gateway: a
blocked server (a rug pull, outside the allowlist) does not exist for it, and every result arrives as untrusted data.
It is the *MCP gateway* pattern; here it runs in the same process as the orchestrator, which thus keeps the call log
that the week 14 eval needs to judge each case.
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
    """An HTTP server on a free port of 127.0.0.1 (no OAuth: loopback only and only for this run)."""
    return ServidorHTTP(crear_pasarela(cliente), usuario="pasarela")
