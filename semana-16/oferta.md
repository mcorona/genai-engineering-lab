# Offer: the plugin inside the "AI Opportunity & Risk Assessment" service

The `legacy-schema-audit` plugin is the technical basis of this fixed-scope consulting service. The plugin does the
read-only deciphering of the legacy database in minutes. The consultant validates it with the client and turns it
into decisions: which data can carry AI use cases, what must be fixed first, and what it would cost.

## Who it is for

- A company that wants AI on top of a legacy system (an ERP, inventory, billing or CRM database with cryptic names
  and no documentation) and does not know whether its data can support it.
- A buyer, investor or new owner evaluating that system: what it holds, how reliable it is, and what personal data
  comes with it.

## Scope

| Included | Not included |
|---|---|
| One database, one schema, through a read-only role or MCP server that the client's DBA creates (the role script is provided) | Any change to the client's data or systems, which stays with the client's DBA |
| An automated audit with the plugin, re-run as needed | Building the AI solutions (a separate project) |
| Validation of the inferred meanings with one or two client subject-matter experts (one 1-hour session) | Legal advice on personal data (the report flags it for counsel) |
| An AI opportunity map: 3 to 5 use cases ranked by value and data readiness | More schemas or databases (quoted per schema) |
| A remediation backlog ordered by risk | Legacy screens without a DOM or API (optional add-on, see below) |
| A 1-hour executive readout | |

Remote engagement in English or Spanish. Typical duration: 2 weeks from access to readout.

## Deliverables

1. **Data dictionary** (`diccionario.yaml`): validated with the client, with the unconfirmed inferences marked.
2. **ER diagram** (`relaciones.mmd`): declared and inferred relationships, and the orphans.
3. **Risk report** (`riesgos.md`): every finding with the `SELECT` that proves it, so the client's team can run it
   again.
4. **Executive summary** (`resumen.md`): one page for the buyer or the steering committee.
5. **AI opportunity map:** use cases such as natural-language queries over the database, document search (RAG) or
   agents for recurring tasks. For each one: expected value, the data it needs, the risks above that block it, a
   cost estimate, and how its success would be measured.
6. **Remediation backlog:** ordered by risk and by which opportunities each fix unlocks. Changes are written as
   scripts for the client's DBA to review and run.
7. **Evidence pack:** the query log (`bitacora.jsonl`) and the guardrail log (`bloqueos.jsonl`), showing that the
   access was read-only and that no personal values left the database.

A complete sample of deliverables 1 to 4, on synthetic data, is in
[`legacy-schema-audit/ejemplo/`](legacy-schema-audit/ejemplo/).

## How the plugin is used in the engagement

| Step | Who | Time |
|---|---|---|
| 1. Kick-off and access: the client's DBA creates the read-only role from the script; the plugin's start-up check confirms that it cannot write | Consultant and DBA | 1–2 h |
| 2. Automated audit: `/legacy-schema-audit:auditoria-completa` with Sonnet (Haiku for quick re-runs of the dictionary) | Plugin | minutes; model cost $1–2 per run on the reference schema |
| 3. Review: the consultant checks every high-severity finding, runs its `SELECT` again and discards false positives | Consultant | 3–6 h |
| 4. Validation session: the inferred meanings and units, the open questions in the summary | Consultant and client experts | 1 h |
| 5. Opportunity map and backlog | Consultant | 4–8 h |
| 6. Readout | Consultant and sponsor | 1 h |

The measured quality of step 2 is in [`resultados/eval_plugin.md`](resultados/eval_plugin.md). On the reference
schema, keys, foreign keys and personal-data flags were 1.00, and 11–12 of 13 seeded risks were found. The plugin
gives a strong first pass, and step 3 is what makes it a paid deliverable.

## Reference price

The program's reference price, set on 2026-11-02 for the first engagements. It is derived from the consulting target
rate of USD 150–200 per hour and the hours in the table above: about 6 to 10 hours for a Snapshot (steps 1 to 4 and
the readout) and 10 to 18 for an Assessment.

| Package | Schema | Price (fixed fee, USD) |
|---|---|---|
| **Snapshot** | up to ~10 objects: dictionary, ER diagram, risk report and summary, plus one validation session; no opportunity map | 1,500 |
| **Assessment** | up to ~50 objects: all 7 deliverables | 3,500 |
| **Assessment+** | 50+ objects, or several schemas | quoted after a measured pilot run on a sample of the schema |
| Add-on: legacy screen review | a browser agent (or computer use for screens without a DOM) walks the data-entry screens and adds what the user sees to the dictionary | 500 per application |

Model costs are included in the fee: measured at about $1 per audit run on a small schema, and $0.003 to $0.014 per
screen for the add-on (activities 5, 7 and 8 of week 16). Medium and large schemas have not been measured yet, which
is why the large package is quoted after a pilot.

## Guarantees written into the proposal

- Read-only access: the client creates the role, and the plugin checks it before starting.
- No personal values in any deliverable; personal data is reported by column and count.
- Every finding is reproducible: the client's team can run the `SELECT` and get the same result.
- Instructions planted in the data are reported, never followed.
- The deliverables are plain text files (YAML, Markdown, Mermaid) that belong to the client and can be versioned.
