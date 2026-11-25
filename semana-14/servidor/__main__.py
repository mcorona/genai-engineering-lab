"""The week 14 MCP server over the legacy database, over stdio or Streamable HTTP on 127.0.0.1.

    python -m servidor --transporte stdio --usuario analista
    python -m servidor --transporte http --puerto 8014 --usuario analista --trazas resultados/trazas/http.jsonl
    python -m servidor --transporte http --oauth --trazas resultados/trazas/oauth.jsonl     # activity 5

(from `semana-14/`). Database: NLQ_LEGADO_DSN, PG_ADMIN_DSN or PG_DSN (week 13's herramientas/conexion.py);
without any of them, the tools that do not need one work and the rest return `sin_base`.
The user is set by whoever starts the process, never by the model; in activity 5 the OAuth token replaces it.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from .primitivas import crear_servidor  # adds semana-13 to sys.path

from herramientas import Contexto, Herramientas  # noqa: E402


def herramientas_de(usuario: str, idioma: str):
    conn = None
    if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN", "PG_DSN")):
        from herramientas.conexion import conectar
        conn, rol = conectar()
        print(f"[server] user {usuario}, database role {rol}", file=sys.stderr)
    else:
        print(f"[server] user {usuario}, no database", file=sys.stderr)
    h = Herramientas(Contexto.de_usuario(usuario, conexion=conn, idioma=idioma))
    return lambda: h


def servidor_oauth(a):
    """The activity 5 server: the issuer's JWKS (discovery), a connection pool and database roles per profile."""
    import json
    import urllib.request

    from .oauth import PoolConexiones, VerificadorJWT, aplicar_roles_bd, fabrica_oauth
    with urllib.request.urlopen(f"{a.emisor}/.well-known/openid-configuration", timeout=10) as r:
        meta = json.load(r)
    if meta["issuer"] != a.emisor:
        raise SystemExit(f"the discovery issuer {meta['issuer']!r} is not {a.emisor!r}")
    recurso = f"http://127.0.0.1:{a.puerto}/mcp"
    pool = None
    if any(os.environ.get(v) for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN")):
        from herramientas.conexion import conectar
        conn, _ = conectar()              # creates copilot_nlq if needed and sets NLQ_LEGADO_DSN
        conn.close()
        if os.environ.get("PG_ADMIN_DSN"):
            aplicar_roles_bd(os.environ["PG_ADMIN_DSN"])
        pool = PoolConexiones(os.environ["NLQ_LEGADO_DSN"], tamano=4)
    verificador = VerificadorJWT(a.emisor, recurso, meta["jwks_uri"])
    return crear_servidor(fabrica_oauth(pool, a.idioma)), {"verificador": verificador, "emisor": a.emisor,
                                                           "recurso": recurso}


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--transporte", "--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--usuario", "--user", default=os.environ.get("MCP_USUARIO", "analista"), metavar="USER")
    p.add_argument("--idioma", "--language", choices=["es", "en"], default=os.environ.get("MCP_IDIOMA", "es"))
    p.add_argument("--puerto", "--port", type=int, default=8014, metavar="PORT")
    p.add_argument("--trazas", "--traces", type=Path, default=None, help="a JSONL file of traces per request (http only)", metavar="TRACES")
    p.add_argument("--oauth", action="store_true", help="OAuth resource server: the user and the permissions come from the token")
    p.add_argument("--emisor", "--issuer", default=os.environ.get("OAUTH_EMISOR", "http://127.0.0.1:8180/realms/legacybridge"), metavar="ISSUER")
    a = p.parse_args()
    if a.oauth and a.transporte == "http":
        servidor, extra = servidor_oauth(a)
        from .http import correr
        print(f"[server] http://127.0.0.1:{a.puerto}/mcp with OAuth (issuer {a.emisor})", file=sys.stderr)
        return correr(servidor, a.puerto, usuario="", ruta_trazas=a.trazas, **extra)
    servidor = crear_servidor(herramientas_de(a.usuario, a.idioma))
    if a.transporte == "stdio":
        from mcp.server.stdio import stdio_server

        async def _stdio():
            async with stdio_server() as (lectura, escritura):
                await servidor.run(lectura, escritura, servidor.create_initialization_options())
        asyncio.run(_stdio())
    else:
        from .http import correr
        print(f"[server] http://127.0.0.1:{a.puerto}/mcp", file=sys.stderr)
        correr(servidor, a.puerto, usuario=a.usuario, ruta_trazas=a.trazas)


if __name__ == "__main__":
    main()
