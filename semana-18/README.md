# Unit 18: LegacyBridge v1 and the close of Phase 4

**Status: in progress.** Activities 1, 2 and 6 are merged. The release gate, the demo, the video, the whiteboard rehearsals, the final whiteboard design and CCAR-P (activities 3 to 5 and 7 to 10) are pending, so exit criterion 18 is not verified yet ([exit criteria](../docs/exit-criteria.md#phase-4-exit-criteria)).

Units 13 to 17 built the pieces of LegacyBridge and measured each one. A client buys the whole: one thing that installs, runs, is safe by construction, and can be shown in three minutes and drawn on a whiteboard in thirty. LegacyBridge v1 adds no new capabilities. It puts the measured pieces behind **one bring-up** and **one entry point**, freezes a version, and proves it with **one gate**.

## What is merged

| Activity | Result | Files | PR |
|---|---|---|---|
| 1. Scope and baseline | An inventory of how each piece starts today (five start procedures, three secret files), the four gaps to an integrated v1, and what is in and out of v1, with the reasons | [`ALCANCE.md`](ALCANCE.md) | #142 |
| 2. One bring-up and one entry point | `legacybridge/arrancar.sh` starts or confirms the database, Keycloak with the approver roles and the observability stack, with health checks and secrets generated per machine. `python -m legacybridge` asks questions, lists and approves proposals, exports the dashboard and runs the runbook, in two modes that share the unit 17 layers (budgets, guardrails, approvals, tracing): `simple` (the unit 13 loop) and `multiagente` (a supervisor that delegates purchasing over A2A to the unit 15 specialist, which holds no credentials) | [`legacybridge/`](legacybridge/), [`tests/test_v1.py`](tests/test_v1.py) | #143 |
| 6. Whiteboard kit | Sealed design briefs (their hashes are committed before they are revealed), a five-zone board template, security and evaluation checklists, and a rubric fixed before the first rehearsal | [`pizarra/`](pizarra/) | #141 |

## Usage

```bash
semana-18/legacybridge/arrancar.sh             # start or confirm every service, then print the state
cd semana-18
python -m legacybridge preguntar "Which critical SKUs are below their reorder point?" --lang en
python -m legacybridge preguntar "..." --modo multiagente
python -m legacybridge pendientes              # proposals waiting for approval
python -m legacybridge aprobar <id> --como gerente
```

Real model calls need `ANTHROPIC_API_KEY`, and each answer prints its cost. The command never prints a token, a password or a DSN.

The tests run without the API, against the quickstart database (see the [root README](../README.md#quickstart)), with `PG_ADMIN_DSN` and `PG_DSN` set: `uv run python -m pytest -q semana-18/tests` (13 tests). They cover approval and resumption in both modes, the specialist's answer treated as data, a single trace across agents, and the absence of secrets in the repository and in the bring-up output.

## Plan

The full plan, with every activity, its time and its cost, is in [`Fas4Sema18.md`](Fas4Sema18.md).
