# Activity 9. Packaging for clients

`legacy-schema-audit` 1.0.0 is published in the `genai-engineering-lab` marketplace. It installs from scratch in a
clean Claude Code configuration, ships a client README and a synthetic sample report, and is offered inside the
"AI Opportunity & Risk Assessment" service. Everything was checked without the model: **$0**.

## What was added

| Item | Where |
|---|---|
| Marketplace with the plugin entry | [`/.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json): name `genai-engineering-lab`, source `./semana-16/legacy-schema-audit` |
| Semantic version | `1.0.0` in `plugin.json`, in the marketplace entry and in the marketplace metadata (0.1.0 was the unpublished lab version) |
| Changelog | [`legacy-schema-audit/CHANGELOG.md`](../legacy-schema-audit/CHANGELOG.md), in Keep a Changelog format. A change to what the deliverables contain, or to what the plugin may do, is a major version |
| Client README | [`legacy-schema-audit/README.md`](../legacy-schema-audit/README.md) |
| Sample report | [`legacy-schema-audit/ejemplo/`](../legacy-schema-audit/ejemplo/): the four deliverables of the measured Sonnet run on the synthetic `legado` schema (activity 5), byte for byte |
| Offer | [`oferta.md`](../oferta.md) |
| Install check | [`empaquetado/instalar_desde_cero.py`](../empaquetado/instalar_desde_cero.py), evidence in [`empaquetado/instalacion_checkout.json`](empaquetado/instalacion_checkout.json) |

## Installation from scratch

`instalar_desde_cero.py` stands in for a client machine. It uses a new, empty `CLAUDE_CONFIG_DIR` and an empty
project folder, with no `ANTHROPIC_*` or `CLAUDE_*` variables. It then adds the marketplace, installs the plugin,
checks it and removes it. It passed **20/20** in the cloud container, with Claude Code 2.1.317 and the CI database:

| Check | ✅ |
|---|---|
| Versions match: plugin.json, the marketplace entry, the marketplace metadata, the top CHANGELOG entry; semver | ✅ |
| The configuration was empty at the start | ✅ |
| `claude plugin validate --strict` passes on the marketplace, and also with `--profile directory` on the plugin (the checks of the plugin directory catalog) | ✅ |
| `claude plugin marketplace add` and `claude plugin install legacy-schema-audit@genai-engineering-lab` succeed | ✅ |
| Installed version 1.0.0, enabled, copied into the plugin cache (outside the checkout) | ✅ |
| `claude plugin details`: 4 skills, 3 agents, 3 hooks, 1 MCP server; about 474 tokens always on | ✅ |
| README, CHANGELOG and the 4 sample files are in the installed copy | ✅ |
| The **installed** guard blocks `DELETE` and `psql` through Bash, and allows a `SELECT` | ✅ |
| The **installed** SessionStart check flags the admin role as unsafe and the read-only role as safe, and never prints the DSN | ✅ |
| Uninstalling and removing the marketplace leave no trace | ✅ |

The same check runs in CI (`tests/test_empaquetado.py`) on every PR that touches week 16 or `.claude-plugin/`.
After the merge it is repeated from GitHub, the way a client installs it:
`python empaquetado/instalar_desde_cero.py --github mcorona/genai-engineering-lab`. That run uses the sparse
checkout from the README: only `.claude-plugin` and the plugin, not the whole lab repository.

## Client README: what it covers

| Required by the plan | Section |
|---|---|
| What it does and what it never does (read-only) | "What it does and what it never does": it never writes, never follows instructions in the data, never copies personal data, never offers to change data, never reads outside the project. The real boundary is the read-only role |
| Requirements and configuration (MCP token or read-only DSN) | "Requirements" (pinned Python packages) and "Configure". Option A: the DBA's `CREATE ROLE` script and `/plugin configure`, with the DSN in the keychain and kept off the command line. Option B: a remote MCP server with a bearer token (`claude mcp add --header "Authorization: Bearer ..."`) or OAuth |
| A sample report with synthetic data | "Sample report", pointing to `ejemplo/` with an excerpt. No real person or company appears in it |
| Expected cost by schema size, with the activity 5 numbers | "Expected cost and time". Small schema, Sonnet: $0.91–1.04 and about 6 min. Haiku for the dictionary: $0.04–0.10. Subagents: $1.98. Medium and large are marked *extrapolated* |
| Known limits | "Known limits": PostgreSQL only; one schema; views and triggers opaque; meanings are inferences; risk recall 11–12 of 13 (Sonnet) or 9–12 (Haiku); unmeasured sizes; guardrails are heuristics; Haiku sometimes quotes injected text |

## Offer

[`oferta.md`](../oferta.md) explains how the plugin is used inside the "AI Opportunity & Risk Assessment" service:

- **Scope:** one database and one schema through a read-only role, with included and excluded items listed side by
  side.
- **Deliverables:** the 4 plugin files after the consultant's validation, an AI opportunity map with 3 to 5 ranked
  use cases, a remediation backlog, and the evidence pack.
- **Steps:** the steps with their owners and hours.
- **Guarantees:** the ones that go into the proposal.

The program's reference price was set on 2026-11-02, derived from the USD 150–200 target rate and the hours per
step:

| Package | Price (fixed fee, USD) |
|---|---|
| Snapshot (up to ~10 objects) | 1,500 |
| Assessment (up to ~50 objects, all 7 deliverables) | 3,500 |
| Assessment+ (50+ objects, or several schemas) | quoted after a measured pilot |
| Add-on: legacy screen review (activities 7 and 8) | 500 per application |

Model costs, measured in activities 5, 7 and 8 at about $1 per audit and under $0.02 per screen, are included in the
fee.

## Tests

`tests/test_empaquetado.py` adds 21 tests with no API:
- the marketplace source and the four matching versions;
- the changelog order;
- every README section;
- the README costs against `eval_plugin.md`;
- the "never" list;
- the sample equal to the measured run, with no personal data, 14 findings each with its `SELECT`, and valid YAML
  with 9 objects and 46 columns;
- the offer sections and prices;
- `validate --strict`;
- the whole installation from scratch.

Week 16 now has **317 passed**.
