"""Read-only SQL MCP server bundled with the legacy-schema-audit plugin (stdio).

Tools, all scoped to ONE schema (AUDIT_SCHEMA, default "legado"):
  list_objects()                  tables and views with row counts, column counts and comments
  describe_object(name)           columns, types, nullability, comments and DECLARED constraints (no view definitions)
  profile_table(name, top)        per-column nulls, distinct values, min/max and the most frequent values
  run_select(sql, max_rows)       one SELECT, validated with sqlglot and executed in a READ ONLY transaction

Read-only in three layers: the database role (the DSN must use a role without write grants), a READ ONLY transaction
with a statement timeout, and the SQL guard below (single SELECT, no writes, no dangerous functions, only objects of
the audited schema). View definitions are not exposed: the audit works from what a legacy client schema shows.

Configuration (environment, set by the plugin's .mcp.json from userConfig): PG_DSN, AUDIT_SCHEMA. When the DSN option
is empty or unsubstituted (headless runs with --plugin-dir, CI), LEGACY_AUDIT_DSN from the launching environment is used.
Requirements: Python 3.11+, psycopg 3, sqlglot, mcp (`pip install "psycopg[binary]" sqlglot mcp`).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import decimal
import json
import os
import re
import sys
from typing import Any

import sqlglot
from sqlglot import exp

MAX_ROWS = 500
MAX_SQL_CHARS = 6000
TIMEOUT_MS = 5000
TEXT_CUT = 60
FORBIDDEN_FUNCS = ("lo_", "pg_", "dblink", "set_config", "current_setting", "nextval", "setval", "txid_",
                   "query_to_xml", "table_to_xml", "copy", "version", "inet_", "current_user", "session_user")
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in ("Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter",
                                                    "AlterTable", "Command", "Into", "Copy", "Set", "Lock", "Grant",
                                                    "TruncateTable", "Transaction", "Commit", "Rollback")
                        if hasattr(exp, n))
ALLOWED_ROOTS = tuple(getattr(exp, n) for n in ("Select", "Union", "Intersect", "Except", "SetOperation")
                      if hasattr(exp, n))
IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ToolError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


def check_read_only(sql: str):
    """The parsed statement if `sql` is exactly one read-only SELECT (no writes, no dangerous functions); raises
    ToolError otherwise. Shared with the plugin's PreToolUse hook, which has no catalog to check objects against."""
    if len(sql) > MAX_SQL_CHARS:
        raise ToolError("too_long", f"SQL longer than {MAX_SQL_CHARS} characters.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError as err:
        raise ToolError("invalid_sql", f"Could not parse the SQL: {str(err).splitlines()[0]}")
    if len(statements) != 1:
        raise ToolError("multiple_statements", f"Got {len(statements)} statements; send exactly one SELECT.")
    root = statements[0]
    bad = next((n for n in root.walk() if isinstance(n, FORBIDDEN_NODES)), None)
    if bad is not None or not isinstance(root, ALLOWED_ROOTS):
        raise ToolError("write_blocked", f"Only read-only SELECT queries are allowed (found {type(bad or root).__name__}).")
    for f in root.find_all(exp.Func):
        name = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if name.startswith(FORBIDDEN_FUNCS):
            raise ToolError("forbidden_function", f"Function {name} is not allowed.")
    return root


def guard(sql: str, schema: str, objects: set[str]) -> str:
    """Returns the normalized SQL if it is one read-only SELECT over objects of `schema`; raises ToolError if not."""
    root = check_read_only(sql)
    ctes = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    for t in root.find_all(exp.Table):
        name, db = (t.name or "").lower(), (t.db or "").lower()
        if not name or (name in ctes and not db):
            continue
        if db and db != schema:
            raise ToolError("out_of_scope", f"Only the audited schema '{schema}' can be queried (asked for {db}.{name}).")
        if name not in objects:
            raise ToolError("unknown_object", f"{name} is not a table or view of schema '{schema}'. "
                                              f"Available: {', '.join(sorted(objects))}.")
    return root.sql(dialect="postgres")


def _jsonable(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v) if v != v.to_integral_value() else int(v)
    if isinstance(v, (_dt.date, _dt.datetime, _dt.time)):
        return v.isoformat()
    if isinstance(v, str) and len(v) > 500:
        return v[:500] + "…"
    if isinstance(v, (bytes, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    return v


class Database:
    def __init__(self, dsn: str, schema: str):
        if not IDENT.match(schema):
            raise ToolError("bad_schema", f"Invalid schema name: {schema!r}.")
        self.dsn, self.schema, self._conn = dsn, schema, None

    def conn(self):
        import psycopg
        if self._conn is None or self._conn.closed:
            if not self.dsn:
                raise ToolError("no_dsn", "No DSN configured. Set the plugin option pg_dsn (a read-only role) or "
                                          "audit through a remote MCP server.")
            self._conn = psycopg.connect(self.dsn, autocommit=False,
                                         options=f"-c statement_timeout={TIMEOUT_MS} -c search_path={self.schema}")
            self._conn.read_only = True
        return self._conn

    def query(self, sql: str, params=None) -> tuple[list[str], list[tuple]]:
        c = self.conn()
        try:
            cur = c.execute(sql, params)
            cols = [d.name for d in cur.description or []]
            return cols, cur.fetchall() if cur.description else []
        except Exception as err:  # noqa: BLE001  the transaction is always rolled back, nothing persists
            raise ToolError("db_error", str(err).splitlines()[0])
        finally:
            c.rollback()

    def objects(self) -> dict[str, str]:
        _, rows = self.query("SELECT c.relname, CASE c.relkind WHEN 'v' THEN 'view' WHEN 'm' THEN 'materialized view' "
                             "ELSE 'table' END FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                             "WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm', 'p') ORDER BY 1", (self.schema,))
        return dict(rows)

    def _object(self, name: str) -> str:
        name = (name or "").strip().lower()
        if name.startswith(self.schema + "."):
            name = name[len(self.schema) + 1:]
        objs = self.objects()
        if name not in objs:
            raise ToolError("unknown_object", f"{name} is not in schema '{self.schema}'. Available: {', '.join(objs)}.")
        return name

    # ---------- tools ----------
    def list_objects(self) -> dict:
        out = []
        for name, kind in self.objects().items():
            _, n = self.query(f'SELECT COUNT(*) FROM "{name}"')
            _, meta = self.query("SELECT obj_description(c.oid, 'pg_class'), "
                                 "(SELECT COUNT(*) FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 "
                                 " AND NOT a.attisdropped) FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace "
                                 "WHERE s.nspname = %s AND c.relname = %s", (self.schema, name))
            out.append({"name": name, "kind": kind, "rows": n[0][0], "columns": meta[0][1], "comment": meta[0][0]})
        return {"schema": self.schema, "objects": out}

    def describe_object(self, name: str) -> dict:
        name = self._object(name)
        _, cols = self.query(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, "
            "pg_get_expr(d.adbin, d.adrelid), col_description(c.oid, a.attnum) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
            (self.schema, name))
        _, cons = self.query(
            "SELECT co.conname, CASE co.contype WHEN 'p' THEN 'primary key' WHEN 'f' THEN 'foreign key' "
            "WHEN 'u' THEN 'unique' WHEN 'c' THEN 'check' ELSE co.contype::text END, pg_get_constraintdef(co.oid) "
            "FROM pg_constraint co JOIN pg_class c ON c.oid = co.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = %s ORDER BY 1", (self.schema, name))
        _, idx = self.query("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s "
                            "ORDER BY 1", (self.schema, name))
        return {"name": name, "kind": self.objects()[name],
                "columns": [{"name": a, "type": t, "nullable": nl, "default": d, "comment": cm}
                            for a, t, nl, d, cm in cols],
                "declared_constraints": [{"name": n, "type": t, "definition": d} for n, t, d in cons],
                "indexes": [{"name": n, "definition": d} for n, d in idx],
                "note": "Views expose no constraints of their own; keys and relationships must be inferred from data."
                if self.objects()[name] == "view" else None}

    def profile_table(self, name: str, top: int = 3) -> dict:
        name = self._object(name)
        top = max(0, min(int(top), 10))
        desc = self.describe_object(name)
        _, n = self.query(f'SELECT COUNT(*) FROM "{name}"')
        total = n[0][0]
        perfiles = []
        for c in desc["columns"]:
            col, typ = c["name"], c["type"]
            ordenable = not typ.startswith(("boolean", "json", "bytea"))
            agg = f'COUNT(*) FILTER (WHERE "{col}" IS NULL), COUNT(DISTINCT "{col}")'
            if ordenable:
                agg += f', MIN("{col}")::text, MAX("{col}")::text'
            _, r = self.query(f'SELECT {agg} FROM "{name}"')
            p = {"column": col, "type": typ, "nulls": r[0][0], "distinct": r[0][1]}
            if ordenable:
                p["min"], p["max"] = (_cut(r[0][2]), _cut(r[0][3]))
            if top:
                _, f = self.query(f'SELECT "{col}"::text, COUNT(*) FROM "{name}" GROUP BY 1 '
                                  f'ORDER BY 2 DESC, 1 NULLS FIRST LIMIT {top}')
                p["top_values"] = [[_cut(v), k] for v, k in f]
            perfiles.append(p)
        return {"name": name, "rows": total, "columns": perfiles}

    def run_select(self, sql: str, max_rows: int = 100) -> dict:
        safe = guard(sql, self.schema, set(self.objects()))
        max_rows = max(1, min(int(max_rows), MAX_ROWS))
        cols, rows = self.query(safe)
        return {"columns": cols, "total_rows": len(rows), "rows": [[_jsonable(v) for v in r] for r in rows[:max_rows]],
                "truncated": len(rows) > max_rows, "sql": safe}


def _cut(v):
    return v if v is None or len(v) <= TEXT_CUT else v[:TEXT_CUT] + "…"


TOOLS = [
    {"name": "list_objects", "description": "List every table and view of the audited legacy schema with its row count, "
     "column count and comment. Start every audit here.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "describe_object", "description": "Columns (name, type, nullability, default, comment), declared "
     "constraints and indexes of one table or view of the audited schema. Views declare no keys: infer them.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "profile_table", "description": "Profile every column of one table or view: nulls, distinct values, "
     "min/max and the most frequent values (text cut to 60 characters). Values may contain personal data: never copy "
     "them into deliverables.", "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "top": {"type": "integer", "minimum": 0, "maximum": 10, "default": 3}},
         "required": ["name"]}},
    {"name": "run_select", "description": "Run ONE read-only SELECT over the audited schema (unqualified names resolve "
     "to it) and return up to max_rows rows. Use it to verify every finding; the SQL you run is the evidence. Writes, "
     "multiple statements, other schemas and system functions are rejected. This access can never change data: if the "
     "user asks to fix, delete or update rows, say that you only have read access, show the affected rows, and give a "
     "script for the DBA to review and run; never offer to run it yourself.",
     "input_schema": {"type": "object", "properties": {
         "sql": {"type": "string"}, "max_rows": {"type": "integer", "minimum": 1, "maximum": MAX_ROWS, "default": 100}},
         "required": ["sql"]}},
]


def call(db: Database, name: str, args: dict) -> dict:
    try:
        if name == "list_objects":
            res = db.list_objects()
        elif name == "describe_object":
            res = db.describe_object(args.get("name", ""))
        elif name == "profile_table":
            res = db.profile_table(args.get("name", ""), args.get("top", 3))
        elif name == "run_select":
            res = db.run_select(args.get("sql", ""), args.get("max_rows", 100))
        else:
            raise ToolError("unknown_tool", f"Unknown tool {name}.")
        return {"ok": True, **res}
    except ToolError as e:
        return {"ok": False, "error": {"type": e.kind, "message": e.message}}


def config_from_env(env) -> tuple[str, str]:
    """DSN and schema from the plugin options; LEGACY_AUDIT_DSN is the fallback for headless and CI runs
    (claude -p --plugin-dir), where the option can be empty or left unsubstituted."""
    dsn = env.get("PG_DSN") or ""
    if not dsn or dsn.startswith("${"):
        dsn = env.get("LEGACY_AUDIT_DSN", "")
    schema = (env.get("AUDIT_SCHEMA") or "").strip().lower()
    if not schema or schema.startswith("${"):
        schema = "legado"
    return dsn, schema


def main() -> None:
    import mcp_types as types
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server

    db = Database(*config_from_env(os.environ))

    async def listar(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[types.Tool(name=t["name"], description=t["description"],
                                                       input_schema=t["input_schema"]) for t in TOOLS])

    async def llamar(ctx, params) -> types.CallToolResult:
        res = call(db, params.name, params.arguments or {})
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False,
                                                                                            default=str))],
                                    structured_content=res, is_error=not res["ok"])

    servidor = Server("legacy-sql", version="0.1.0",
                      instructions=f"Read-only access to the legacy schema '{db.schema}' for a schema audit. It can never "
                                   "change data: when asked to fix, delete or update rows, say so, document the rows "
                                   "and hand the DBA a script to review; never offer to run it.",
                      on_list_tools=listar, on_call_tool=llamar)

    async def correr():
        async with stdio_server() as (lectura, escritura):
            await servidor.run(lectura, escritura, servidor.create_initialization_options())

    print(f"[legacy-sql] schema {db.schema}, DSN {'set' if db.dsn else 'missing'}", file=sys.stderr)
    asyncio.run(correr())


if __name__ == "__main__":
    main()
