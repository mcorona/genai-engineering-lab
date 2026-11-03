# Legacy Schema Audit

A Claude Code plugin that audits a legacy database schema **read-only** and writes four versionable files for the
client under `auditoria/`:

| File | What it holds |
|---|---|
| `diccionario.yaml` | Data dictionary: meaning, type, keys, unit and personal-data flag of every column, with confidence and evidence |
| `relaciones.mmd` | ER diagram in Mermaid, with declared and inferred relationships kept apart, and orphan counts |
| `riesgos.md` | Findings (orphans, null keys, duplicates, inconsistent units, rules missing from the database, personal data, instructions planted in the data), each with the `SELECT` that proves it and what it returned |
| `resumen.md` | One page for a non-technical buyer: what was reviewed, the risks that matter, what is healthy, next steps, scope and limits |

Version 1.0.0 · [Changelog](CHANGELOG.md) · MIT license · Author: Manuel Corona

## What it does and what it never does

**It does:**
- read the structure and the data of **one** schema through a read-only role;
- profile every table and view;
- infer keys, relationships, meanings and units, marked as inferences with a confidence level;
- prove every finding with a `SELECT`;
- log every query in `auditoria/bitacora.jsonl`.

**It never:**
- **writes to the database.** The bundled server runs one validated `SELECT` at a time, in a read-only transaction,
  over the configured schema. Before the audit starts, the plugin checks that the role cannot write: it blocks its
  own database tools if the role is a superuser, can create objects, or holds INSERT, UPDATE, DELETE or TRUNCATE on
  any table.
- **follows instructions found in the data.** Notes, comments and object names that address the AI are reported as a
  finding, not obeyed.
- **copies personal data into the deliverables.** It names the columns and gives counts and row ids. A deliverable
  that contains an email, a phone number or a tax ID is blocked before it is written.
- **offers to change data.** Asked to fix or delete rows, it lists the affected ids and leaves the change to the DBA.
- **reads outside the project.** It does not read `.env` files, keys, credentials or shell profiles, it does not
  write outside `auditoria/`, and it does not reach the database through the shell. Each attempt is blocked and
  logged in `auditoria/bloqueos.jsonl`.

The guardrails are hooks that fail closed. The real boundary is the read-only role: give the plugin a role that
cannot write, and the audit cannot write either.

## Requirements

- Claude Code (tested with 2.1.316 and later) with a Claude subscription or an API key.
- Python 3.11 or later on `PATH` as `python3`, with the server's packages:
  ```bash
  python3 -m pip install "psycopg[binary]==3.3.6" "sqlglot==30.26.0" "mcp==2.3.0" "pyyaml==6.0.2"
  ```
  `pyyaml` is optional. Without it, the check that the dictionary YAML parses is skipped.
- PostgreSQL (tested with 16) and a read-only role (option A), or a remote MCP server in front of the database
  (option B).

## Install

```bash
claude plugin marketplace add mcorona/genai-engineering-lab --sparse .claude-plugin semana-16/legacy-schema-audit
claude plugin install legacy-schema-audit@genai-engineering-lab
```

`--sparse` checks out only the marketplace file and this plugin, not the whole lab repository. To try it from a
checkout without installing, run `claude --plugin-dir semana-16/legacy-schema-audit`.

## Configure

### Option A: a read-only PostgreSQL role (bundled server)

1. The DBA creates a role that can only read the schema to audit:
   ```sql
   CREATE ROLE legacy_auditor LOGIN PASSWORD '<a strong password>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
   GRANT CONNECT ON DATABASE <database> TO legacy_auditor;
   GRANT USAGE ON SCHEMA <schema> TO legacy_auditor;
   GRANT SELECT ON ALL TABLES IN SCHEMA <schema> TO legacy_auditor;
   ```
2. In Claude Code, run `/plugin configure legacy-schema-audit@genai-engineering-lab` and set:
   - `pg_dsn`: `postgresql://legacy_auditor:<password>@<host>:5432/<database>`. It is stored in the system keychain
     and never written to the deliverables or the logs. Avoid `--config pg_dsn=...` on the command line, which
     leaves the password in your shell history.
   - `audit_schema`: the schema to audit (default `legado`). The server reads nothing else, and system catalogs are
     out of scope.

At the start of every session the plugin checks the role and adds the result to Claude's context. If the role can
write, the plugin's database tools stay blocked for that session.

### Option B: a remote MCP server (token or OAuth)

Leave `pg_dsn` empty and register the client's database server, for example one with the tools `describir_esquema`,
`muestrear_valores`, `validar_sql` and `ejecutar_sql`:

```bash
claude mcp add --transport http legado-remoto https://<host>/mcp --header "Authorization: Bearer $LEGACY_MCP_TOKEN"
```

For a server that uses OAuth, leave out `--header` and sign in with `/mcp`. The guard applies the same read-only
check to that server's SQL. That server's own permissions decide what the audit can see, and anything they hide is
listed under "Scope and limits" in the summary.

## Use

| Command | Writes |
|---|---|
| `/legacy-schema-audit:auditoria-completa` | all four files |
| `/legacy-schema-audit:solo-diccionario` | `diccionario.yaml` and `relaciones.mmd` |
| `/legacy-schema-audit:solo-riesgos` | `riesgos.md` and `resumen.md` |

You can also ask in plain words, in English or Spanish ("document this legacy database", "¿qué riesgos tiene este
esquema?"). The `auditar` skill picks the request up. Run it from an empty project folder: the deliverables go to
its `auditoria/` folder.

## Sample report

[`ejemplo/`](ejemplo/) holds a complete audit of the lab's synthetic `legado` schema: 9 objects and 46 columns of an
inventory and purchasing system, with personal data and defects that were seeded on purpose. It was produced by
Sonnet 5.5 with this plugin from a plain request. No real person or company appears in it.

- [`resumen.md`](ejemplo/resumen.md): the one-page summary for the buyer. Excerpt:
  > **The database does not protect itself.** It has no rules that stop bad entries, such as a movement for a product
  > that does not exist. As a result, **13 of the 44 stock movements (about 3 in 10) have a problem** [...]
- [`riesgos.md`](ejemplo/riesgos.md): 14 findings, each with its `SELECT` and the result.
- [`relaciones.mmd`](ejemplo/relaciones.mmd): the ER diagram. No foreign key is declared, so every relationship is
  inferred, and the orphans are listed.
- [`diccionario.yaml`](ejemplo/diccionario.yaml): all 46 columns.

On that schema, the audit found 11 of the 13 risks that had been seeded. Keys, foreign keys and personal-data flags
were all right (precision and recall 1.00). Every `SELECT` in the report runs again with the same result.

## Expected cost and time

Measured in the lab (week 16, activity 5) on the synthetic schema of 9 objects and 46 columns. Costs are
API-equivalent. On a Claude subscription they come out of the plan's usage instead.

| Schema size | Recommended setup | Cost per audit | Time | Basis |
|---|---|---|---|---|
| Small (up to ~10 objects, ~50 columns) | Sonnet 5.5, single agent, for a deliverable the client receives | **$0.91–1.04** | ~6 min | Measured: risk recall 11–12 of 13; PK, FK and personal-data flags 1.00 |
| Small, dictionary and ER diagram only | Haiku 5.5 | **$0.04–0.10** | ~3 min | Measured: the dictionary matched Sonnet's (PK, FK, PII 1.00); risk recall varied from 9 to 12 of 13, too unstable for a paid risk report |
| Small, with subagents | Sonnet 5.5 plus the 3 subagents | $1.98 | ~10 min | Measured: same quality as a single agent at 1.9× the cost; use it only for isolation |
| Medium (10–50 objects) | Sonnet 5.5, single agent | grows with about 2 profiling calls per object plus the evidence queries | — | *Extrapolated, not measured* |
| Large (50+ objects) | Sonnet orchestrator with `perfilador` subagents on Haiku, by batch | — | — | *Extrapolated*: measure it on a schema of that size before quoting it |

The plugin itself adds about 470 tokens to every session (`claude plugin details legacy-schema-audit`). The audit
skill loads about 2.9k more when it fires.

## Known limits

- **PostgreSQL only.** The bundled server speaks PostgreSQL. Other engines need a remote MCP server (option B).
- **One schema per run.** Cross-schema relationships are not inferred.
- **Views are opaque.** The definitions of views and the triggers are not read, so rules enforced there are not seen.
- **Meanings are inferences.** Abbreviations, units and business rules are educated guesses with a confidence level.
  The client must confirm them.
- **Risk recall is high, not total.** On the reference schema it was 11–12 of 13 with Sonnet and 9–12 with Haiku.
  Treat the report as a strong first pass for a person to review, not as a certification.
- **Sizes beyond the reference schema are extrapolated.** Cost and time for medium and large schemas have not been
  measured.
- **The guardrails are heuristics.** They are hooks that fail closed, and they were tested against injected data,
  requests to change data, credential reads and attempts to bypass them through Bash, a subagent or another MCP
  server. They are not a sandbox. The read-only role is what guarantees that nothing is written.
- **Quoting.** When it reports an instruction planted in the data, Haiku sometimes quotes part of it instead of
  describing it.
- **Optional browser rules.** If a Playwright MCP server is present, the plugin only lets it look at local pages.
  The plugin does not drive the user's own browser.

## Privacy

The deliverables, the query log and the block log stay in the client's project folder. The plugin sends nothing
anywhere except what Claude Code itself sends to the model. Personal values seen while profiling are not written to
the deliverables.
