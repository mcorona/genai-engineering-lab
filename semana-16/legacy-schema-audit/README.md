# legacy-schema-audit

Read-only audit of a legacy database schema for Claude Code. It produces four versionable files under `auditoria/`:

| File | For |
|---|---|
| `diccionario.yaml` | Data dictionary: meaning, type, keys, unit and personal-data flag of every column, with confidence and evidence |
| `relaciones.mmd` | ER diagram in Mermaid (declared vs inferred relationships) |
| `riesgos.md` | Findings with the `SELECT` that proves each one |
| `resumen.md` | One page for a non-technical buyer |

## Install

```bash
claude plugin marketplace add mcorona/genai-engineering-lab
claude plugin install legacy-schema-audit@genai-engineering-lab
```

Until the marketplace entry is published (week 16, activity 9), load it from a checkout with `claude --plugin-dir semana-16/legacy-schema-audit`.

Requirements: Python 3.11+ with `pip install "psycopg[binary]" sqlglot mcp`, and either a read-only PostgreSQL role (plugin option `pg_dsn`, stored in the system keychain) or a remote MCP server for the database.

## Use

`/legacy-schema-audit:auditoria-completa`, `/legacy-schema-audit:solo-diccionario`, `/legacy-schema-audit:solo-riesgos`, or just ask Claude to audit the legacy schema.

## What it never does

It never writes to the database. The bundled server only runs one validated `SELECT` at a time, in a read-only transaction, over the configured schema. It never follows instructions found in the data, and it never copies personal data into the deliverables.
