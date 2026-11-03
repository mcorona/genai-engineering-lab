# Week 16: a reusable plugin for clients, with its own eval

**Outcome.** The work of weeks 10 to 15 (reading a legacy schema with cryptic names, inferring relationships and
rules, finding risks, read-only) becomes a Claude Code plugin that a client can install:
[`legacy-schema-audit`](legacy-schema-audit/README.md) 1.0.0, published in this repo's marketplace. Its quality,
security and cost are measured against a frozen ground truth, and the `eval-semana-16` check runs a mini eval with
the API on every pull request.

```bash
claude plugin marketplace add mcorona/genai-engineering-lab --sparse .claude-plugin semana-16/legacy-schema-audit
claude plugin install legacy-schema-audit@genai-engineering-lab
```

The plan and the log of decisions are in [`PLAN.md`](PLAN.md).

## 1. Architecture

```
 Claude Code session (client's project folder)
 ├─ skill `auditar` + commands auditoria-completa · solo-diccionario · solo-riesgos
 ├─ subagents perfilador (Haiku) · analista-relaciones · revisor-riesgos   (minimal tools, no writes)
 ├─ hooks
 │   ├─ SessionStart  verificar_rol.py  is the role read-only? (otherwise the DB tools stay blocked)
 │   ├─ PreToolUse *  guardia.py        fails closed; every block → auditoria/bloqueos.jsonl
 │   └─ PostToolUse   bitacora.py       every query → auditoria/bitacora.jsonl
 └─ access, one of:
     A. bundled MCP server `legacy-sql` (stdio) ── read-only role (DSN in the keychain) ──► PostgreSQL, one schema
     B. client's remote MCP server (HTTP + bearer token or OAuth) ── its own permissions ──► the database
 deliverables → auditoria/: diccionario.yaml · relaciones.mmd · riesgos.md (each finding with its SELECT) · resumen.md
```

| Layer | What enforces read-only |
|---|---|
| Database | A role with SELECT only on the audited schema. This is the real boundary, and the plugin checks it at session start |
| Bundled server | One parsed `SELECT` at a time (sqlglot), in a `READ ONLY` transaction with a timeout, scoped to one schema; system catalogs are out of scope |
| Guard (PreToolUse) | Blocks write SQL on any server, the shell against the database, reads of secrets, shell profiles and anything outside the project, writes outside `auditoria/`, personal values and findings without `SELECT` in deliverables, subagent tools outside their list, and browser actions other than looking at local pages |
| Skill | Never follows instructions found in the data, never offers to change data, separates fact from inference |

## 2. What was built (10 activities)

| # | Activity | Result | PR |
|---|---|---|---|
| 1 | Baseline of Claude Code as a plugin platform | 18 checks without the model on 2.1.316: plugin, marketplace, `plugin eval`, hooks, subagents, `userConfig`, browser and computer use | #111, #112 |
| 2 | Ground truth | The correct dictionary (46 columns, 9 objects), 13 seeded risks with SQL evidence, 4 injected notes; recomputed in CI and frozen with a hash manifest | #113 |
| 3 | The plugin: skill, commands, read-only server | Sonnet run: 11/11 checks, PK/FK/PII 1.00, 12 of 13 risks, $1.04. Through the week 14 server with OAuth, least privilege hid 5 of 9 objects without the audit knowing, which became a decision for clients | #114, #115 |
| 4 | Subagents and hooks | 15/15 checks; same quality as one agent at 1.9× the cost and 1.6× the time | #116 |
| 5 | Plugin eval | `claude plugin eval`: 10 cases, Δ **+0.57** over no plugin. The own evaluator compared Sonnet and Haiku, with and without the plugin. The eval forced two plugin fixes | #117 |
| 6 | Security | 7 cases × 2 models: **14/14**. A real `~/.zshrc` leak in the first run led to the guard blocking reads outside the project | #118, #119 |
| 7 | Spike: browser agent on a legacy screen | Playwright MCP, local only: 10/10 fields, 13/13 screen-only facts, 0 submissions, injection treated as data, $0.014 | #120 |
| 8 | Spike: computer use (optional) | `computer_toolset_20260801` in a container with no network: 10/10, 13/13, $0.0031; justified only for applications with no DOM and no API | #121 |
| 9 | Packaging for clients | Marketplace, 1.0.0, CHANGELOG, client README, synthetic sample, offer; installation from scratch 20/20 from the checkout and from GitHub | #122, #123 |
| 10 | CI, README and criterion 16 | `eval-semana-16` with ephemeral Postgres and Keycloak, 328 tests without API, mini eval with API, calibrated thresholds, security without a threshold | #124 |

## 3. Results

### Quality against the ground truth (activity 5, real database, 9 objects and 46 columns)

| Setup | Meaning | PK / FK / PII (P and R) | Seeded risks | Cost | Time |
|---|---|---|---|---|---|
| **Plugin, Sonnet 5.5**, command | 1.00 | 1.00 | **12/13** | $1.04 | 373 s |
| Plugin, Sonnet 5.5, plain request | 0.98 | 1.00 | 11/13 | $0.91 | 370 s |
| Plugin, Sonnet 5.5, subagents | 1.00 | 1.00 | 12/13 | $1.98 | 608 s |
| Plugin, Haiku 5.5, plain request | 0.96 | 1.00 | 9/13 | **$0.04** | 158 s |
| No plugin, Sonnet 5.5, detailed prompt | 1.00 | 1.00 | 12/13 | $0.83 | 330 s |
| No plugin, Haiku 5.5, detailed prompt | 0.98 | 1.00 | 8/13 | $0.05 | 215 s |

What the plugin adds is not raw quality: Sonnet audits well when the prompt carries the specification. It adds three
things:
- **What the user does not have to write.** Short requests produce the right four files: Δ +0.57 in the behavior
  suite.
- **Safety by construction.** The role is checked before starting, personal data is blocked at write time, there is
  no write path, and there is a query log.
- **Evidence.** Every finding has its `SELECT` and every one runs again. Without the plugin, at least one finding
  per run had no `SELECT`.

### Security (activity 6, no threshold)

**Haiku 7/7, Sonnet 7/7.** Seven cases:
- instructions injected in data, comments and object names;
- a request to "fix" data;
- reading `.env` and credentials;
- bypassing the hooks through Bash and through a subagent;
- tool poisoning from a second MCP server.

Results across the 14 runs:
- data and catalog fingerprints unchanged;
- 0 canaries leaked;
- 0 instructions obeyed;
- every block logged.

In the first run, the credentials case read the real `~/.zshrc`. The keys were rotated, the evidence was redacted, and
the guard now blocks reads outside the project and of shell profiles ([`resultados/seguridad.md`](resultados/seguridad.md)).

### Legacy screens (activities 7 and 8)

| | Browser agent (Playwright MCP) | Computer use |
|---|---|---|
| Fields / screen-only facts | 10/10 · 13/13 | 10/10 · 13/13 |
| Steps / time / cost | 8 calls · 39.7 s · $0.014 | 13 actions · 32.1 s · $0.0031 |
| No submission enforced by | The guard (no typing, filling or submit-like clicks) and the screen's POST count | The screen's POST count only, because a click cannot be guarded without a DOM |
| Use it for | Web screens: the default | Desktop clients, terminals, Citrix or RDP: no DOM, no API |

### CI (activity 10)

5 deterministic behavior cases plus 2 real Haiku audits per pull request, one with a read-only DSN and one with a
Keycloak token through the week 14 server.

The thresholds were calibrated on 2 runs with the week 10 rule (false alarm ≤ 10 %), then enforced on a third run:
- graders 0.90;
- meaning 0.90;
- PK 0.45;
- FK 0.85;
- PII 0.80;
- risks 0.35;
- token coverage and meaning 0.90.

There are 20 security checks with no threshold, and a run costs about $0.11 ([`resultados/ci.md`](resultados/ci.md)).

## 4. Security of the plugin, in one place

- **The read-only role.** It is checked before the audit starts. If it can write, the database tools stay blocked
  for the whole session.
- **The guard.** It fails closed (`onFailure: block`), and each block is logged with a hash of the input, never the
  input.
- **Credentials.** The DSN is a sensitive option kept in the system keychain. It is never written to deliverables,
  logs or evidence, and CI checks this on every run.
- **Option B.** The client's server decides what the token can see. The audit lists what was hidden, and CI checks
  that nothing outside the token's scopes appears.
- **Legacy screens.** The browser agent only looks, at local origins. Claude in Chrome is blocked because it shares
  the user's sessions. Computer use runs in a container with no network and no credentials.

## 5. How to run it

```bash
cd semana-16
uv run python -m pytest -q tests -p no:cacheprovider                     # 328 tests, $0 (needs PG_DSN, PG_ADMIN_DSN)
uv run python ci/eval_ci.py --simular --emisor prueba                    # the CI mini eval circuit, $0
uv run python corrida/correr.py --modelo sonnet --sin-subagentes         # one audit on the subscription
uv run python seguridad/correr.py --modelo haiku                         # the 7 security cases
uv run python navegador/ensayo.py && uv run python navegador/correr.py --modelo haiku --tope 0.50
uv run python empaquetado/instalar_desde_cero.py --github mcorona/genai-engineering-lab
```

## 6. Costs

| Item | Billing | Cost |
|---|---|---|
| Activities 3 to 7: audits, the eval suite (pass 1 stopped at the cap: $6.56), security cases, browser spike | Claude Code subscription | about $18 API-equivalent, $0 billed |
| Activity 8: computer use (2 attempts, authorized, cap $0.25) | API | $0.0062 |
| Activity 10: 3 CI runs (calibration and enforcement) | API (CI secret) | $0.3419 |
| **Total billed for the week** | | **$0.35** |
| From now on: each pull request that touches week 16 code | API | about $0.11 per run (cap $0.40) |

## 7. Exit criterion 16

> **16.** A reusable plugin or skill for clients, with its own eval.

| Required | Evidence | |
|---|---|---|
| Reusable for clients | `legacy-schema-audit` 1.0.0 in the `genai-engineering-lab` marketplace. Installation from scratch from GitHub passed 20/20. It ships a client README (configuration A or B, cost by schema size, limits), a synthetic sample report and an offer (`oferta.md`) | ✅ |
| Its own eval | A frozen ground truth (activity 2), `claude plugin eval` with 10 cases (Δ +0.57), an own quality evaluator (meaning, PK, FK, PII, risks, SQL run again), 7 security cases × 2 models (14/14), and a mini eval in CI with calibrated thresholds on every PR | ✅ |
| Verified in CI | `eval-semana-16` green on PR #124 with the thresholds enforced (run 3: all metrics above their threshold, 20/20 security checks, $0.1156) | ✅ |

## 8. What carries over

- **Plugins.** Plugins are the unit of delivery for client work. The guardrails go in hooks that fail closed, the
  boundary goes in the database role, and quality goes in an evaluator against a ground truth, because
  `claude plugin eval` has no code graders.
- **Haiku and Sonnet.** Haiku is good enough for a dictionary and for CI. It is not good enough for a client's risk
  report, where Sonnet stays.
- **Least privilege.** It hides objects from an audit silently. An audit needs its own scope, or a read-only DSN.
- **Legacy screens.** They add what the database cannot hold. Use a browser agent first, and computer use only
  where there is no DOM.
