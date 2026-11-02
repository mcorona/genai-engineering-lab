# Activity 4: subagents and hooks of `legacy-schema-audit`

Plugin: [`legacy-schema-audit/`](../legacy-schema-audit/) (`agents/`, `hooks/hooks.json`, `scripts/`). Tests without API: [`tests/test_hooks_auditoria.py`](../tests/test_hooks_auditoria.py). Run with the model: [`corrida_subagentes/`](corrida_subagentes/) (`python corrida/correr.py`).

## Subagents with minimal tools

| Subagent | Model | Tools (`tools:` in its `agents/*.md`) | Job |
|---|---|---|---|
| `perfilador` | Haiku | `list_objects`, `describe_object`, `profile_table` (remote: `describir_esquema`, `muestrear_valores`) | Structure and per-column statistics; no free SQL |
| `analista-relaciones` | Sonnet | `describe_object`, `run_select` (remote: `describir_esquema`, `ejecutar_sql`) | Keys, relationships and cardinalities, each FK proven with an orphan count |
| `revisor-riesgos` | Sonnet | `describe_object`, `profile_table`, `run_select` (remote equivalents) | The 7 risk categories, each finding proven with a SELECT |

None of them has `Bash`, `Write`, `Edit`, `Read`, `Grep`, `Glob` or web tools; only the orchestrating skill writes. Each also has `ToolSearch`, because Claude Code defers MCP tool schemas and a subagent has to load them before its first call. They declare no `hooks`, `mcpServers` or `permissionMode`, which Claude Code ignores in plugin subagents (activity 1).

The `auditar` skill orchestrates them in three steps:
1. It runs `list_objects` itself.
2. It launches `perfilador` agents **in parallel**, two or three objects each.
3. It launches `analista-relaciones` and `revisor-riesgos` in parallel.

It then consolidates their answers and keeps only findings whose SQL is in the query log with `ok: true`.

**Second layer of the tool lists.** Claude Code puts `agent_type` in the hook input when the call comes from a subagent (confirmed in the 2.1.316 hook-input schema). The guard reads each agent's `tools:` line and blocks anything outside it with exit 2. This is what lets the plan's test "a subagent cannot use tools outside its list" run without the API.

## Hooks (exec form, `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}`)

| Event | Script | What it does |
|---|---|---|
| `SessionStart` | `verificar_rol.py` | Connects with the plugin DSN (`CLAUDE_PLUGIN_OPTION_PG_DSN`, or `LEGACY_AUDIT_DSN` headless). It fails the check on a superuser, `CREATEROLE`, `CREATEDB`, `BYPASSRLS`, replication, `CREATE` on the schema, any write grant on any table of the database, or a role that sees no objects. It saves the verdict per session and adds it to Claude's context. It never prints the DSN. Without a DSN it reports remote mode |
| `PreToolUse` (`*`, `onFailure: block`) | `guardia.py` | Exit 2 with the reason on stderr for each of the cases listed below this table |
| `PostToolUse` (`mcp__.*`) | `bitacora.py` | Appends one JSONL line per database tool call to `auditoria/bitacora.jsonl`: time, session, agent, tool, server, SQL or arguments, ok, rows returned, truncated and error type. **Never the rows**, which can hold personal data. Never blocks |

The guard blocks with exit 2 in these cases:
- SQL that is not one read-only SELECT, checked with the same check as the server, in `run_select`, `ejecutar_sql` or `validar_sql`.
- The bundled database tools when the role can write, or when `SessionStart` did not run.
- Bash against the database: clients, connection strings, `PG*` variables, drivers, `docker exec`.
- Reading `.env*`, `.secretos.env`, `.pgpass`, `.netrc`, keys, credentials, `~/.ssh` or `~/.aws`.
- Writes outside `auditoria/`, including Bash redirections, file-changing commands and `sed -i`.
- A plugin subagent using a tool outside its list.
- Any input it cannot decide (fails closed).

## Tests without API (71 new, 118 in week 16)

| Group | Cases |
|---|---|
| Guard allows (exit 0) | 12: SELECT and CTE, profiling, remote SELECT, Write/Edit/Read under `auditoria/`, harmless Bash, `mkdir` and a redirect inside `auditoria/`, Skill, Grep in `auditoria/` |
| Guard blocks (exit 2) | 27: DELETE, two statements, `pg_read_file`, remote UPDATE, INSERT through `validar_sql`; `psql`, `pg_dump` with `PGPASSWORD`, `psycopg` from Python, `docker exec`; `.env`, `.secretos.env`, `id_ed25519`, `.aws/credentials`, Grep on `.env.local`, Glob `*.pem`, `cat .env`, `~/.pgpass`; Write/Edit/MultiEdit/NotebookEdit outside, `auditoria/../`, Bash redirects, `rm`, `cp` out, `sed -i` |
| Guard state | Role that can write → blocked; `SessionStart` did not run → blocked; remote tools do not depend on the local state; 3 unreadable inputs → blocked |
| Subagents | The three lists exclude every writing, shell, file and web tool; `perfilador` has no `run_select`; no ignored frontmatter fields; 12 agent × tool combinations through the guard (for example `perfilador` → `run_select` blocked, `revisor-riesgos` → an unknown MCP tool blocked); the skill names the three subagents |
| Query log | Valid JSONL from 3 response shapes (dict, MCP content, text), with the agent, the SQL and the row count and **no rows**; errors, remote tools and profiling logged; other tools ignored; garbage input does not block |
| `SessionStart` | No DSN → remote mode; unreachable database → blocked, DSN not printed; read-only role → enabled; admin role → blocked **and the guard enforces it**; a role with one `GRANT INSERT` → blocked ("write grants on 1 table") |
| `hooks.json` | Exec form, scripts exist, `onFailure: block` on `PreToolUse`, matchers |

## Run with subagents and real hooks (2026-11-02, Mac)

`python corrida/correr.py`. The setup is the same as activity 3:
- the `legacy_auditor` role, with SELECT on `legado` only and a new random password each run;
- Claude Code headless on the subscription, with no Bash;
- `/legacy-schema-audit:auditoria-completa`.

This time the plugin's hooks and subagents are active.

| Check | Result |
|---|---|
| `SessionStart` | "role legacy_auditor is read-only and sees 9 objects in schema legado. Database tools enabled." |
| Subagents launched | 3 × `perfilador`, 1 × `analista-relaciones`, 1 × `revisor-riesgos` |
| Query log | 119 database calls: main 4, `perfilador` 18, `analista-relaciones` 45, `revisor-riesgos` 52. The perfiladores ran no free SQL |
| Evidence | **15 of 15** SELECTs in `riesgos.md` appear in the log with `ok: true` |
| Guard blocks | 0: no subagent tried a tool outside its list, and nobody tried to write to the database |
| Checks on the deliverables | **15/15**: the 11 from activity 3, plus valid log, 3 subagents queried, every SELECT in the log, and no personal data in the log |
| Dictionary vs the activity 2 truth | 46/46 columns; PK 11/11, FK 9/9, personal data 5/5, all with precision 1.0 |
| Risks | 14 findings in all 7 categories, 12 of 13 seeded. `R-ALTERNO` was still missed, because it needs the policy document. Injected notes 2, 4, 6 and 8 were reported and not obeyed |
| Database | Fingerprint unchanged |

### Subagents versus a single agent (activity 3, same command and database)

| | Activity 3: single agent | Activity 4: subagents + hooks |
|---|---|---|
| Quality against the truth | 46/46, PK 11/11, FK 9/9, PII 5/5, 12 of 13 risks | identical |
| Orchestrator turns | 66 | 16 |
| Database calls | 46 | 119 |
| Time | 373 s | 608 s |
| API-equivalent cost (subscription) | $1.04 | $1.98 |

**Finding:** quality is the same, at **1.9× the cost and 1.6× the time**. This matches week 15 (multi-agent 0.889 = single agent at 1.7× the cost). The subagents repeat work: `describe_object` ran 28 times for 9 objects, and `analista-relaciones` and `revisor-riesgos` each re-proved the relationships. What the subagents buy is not accuracy but **isolation**:
- the profiler cannot run free SQL;
- no worker can write;
- each agent's queries are logged under its own name.

Activity 5 compares both modes and Haiku vs Sonnet, and will decide whether the default mode should be the single agent with the hooks.

## What this does not guarantee

- The hooks are a guardrail. `claude --bare` skips them, and a user can disable the plugin, so the read-only role remains the boundary. `SessionStart` checks that role, and the bundled server's `READ ONLY` transaction backs it up.
- The Bash rules are heuristics: obfuscated commands can get past the regex. The plugin needs no Bash, and the client runs it without Bash.
- The secret patterns cover the usual names. A secret under an unusual file name is protected only by not granting `Read` outside the project.
