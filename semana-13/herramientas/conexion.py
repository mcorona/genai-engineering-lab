"""A read-only connection for the week 13 tools.

Order of preference:
1. NLQ_LEGADO_DSN: the copilot_nlq role, already created (only SELECT on the legacy views, read-only by default).
2. PG_ADMIN_DSN: (re)creates copilot_nlq with a random password for the session, like week 10's hardened NLQ, and
   connects with it. The password is not stored anywhere.
3. PG_DSN: the copilot_ro role, with search_path = legado. The guard and the READ ONLY transaction still apply.
"""
import os
import secrets

import psycopg
from psycopg import sql as pgsql
from psycopg.conninfo import make_conninfo


def crear_rol_nlq() -> str:
    clave = secrets.token_urlsafe(24)
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'copilot_nlq'").fetchone():
            conn.execute("CREATE ROLE copilot_nlq LOGIN")
        conn.execute(pgsql.SQL("ALTER ROLE copilot_nlq WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                               "PASSWORD {}").format(pgsql.Literal(clave)))
        conn.execute("ALTER ROLE copilot_nlq SET default_transaction_read_only = on")
        conn.execute("ALTER ROLE copilot_nlq SET search_path = legado")
        conn.execute("GRANT USAGE ON SCHEMA legado TO copilot_nlq")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA legado TO copilot_nlq")
    return make_conninfo(os.environ.get("PG_DSN") or os.environ["PG_ADMIN_DSN"], user="copilot_nlq", password=clave)


def conectar() -> tuple[psycopg.Connection, str]:
    """Returns (an autocommit connection, the role name)."""
    if os.environ.get("NLQ_LEGADO_DSN"):
        dsn = os.environ["NLQ_LEGADO_DSN"]
    elif os.environ.get("PG_ADMIN_DSN"):
        dsn = crear_rol_nlq()
        # The process's next connections (threads, the child MCP server) reuse this password instead of rotating it.
        os.environ["NLQ_LEGADO_DSN"] = dsn
    else:
        dsn = os.environ["PG_DSN"]
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("SET search_path = legado")
    rol = conn.execute("SELECT current_user").fetchone()[0]
    return conn, rol
