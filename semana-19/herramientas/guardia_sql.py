"""Week 19, activity 6: the read-only guard for the tools Lambda's ejecutar_sql.

The guard is the week 16 module (servidor/sql_lectura.py: sqlglot, one read-only SELECT, no dangerous functions,
objects of the audited schema). It is loaded by path, not copied. The tools Lambda calls it BEFORE it opens a
connection; a rejected statement never reaches the database.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
_MODULO = RAIZ / "semana-16" / "legacy-schema-audit" / "servidor" / "sql_lectura.py"

_spec = importlib.util.spec_from_file_location("sql_lectura_s16", _MODULO)
sql_lectura = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sql_lectura)

ToolError = sql_lectura.ToolError
guard = sql_lectura.guard
