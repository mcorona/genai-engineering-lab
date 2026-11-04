# Activity 9: security and privacy of the observability

The Collector now runs its `redaction` processor in **allowlist mode**: only the 105 keys of the locked span shape (99 from
`instrumentacion/esquema.py` plus 6 resource keys) pass, and every other attribute is dropped whole. That closes the list gap measured in
activity 2 and any content a library captures. Measured on the live stack, $0: **0 of 9 canaries** reach Langfuse or the Collector's
file, with message content capture **off and on**. A second Langfuse project, for another tenant, has keys that cannot see or delete
the first tenant's traces, and the other way round. Retention is a job, because Langfuse OSS cannot set it per project.

Files: `seguridad_obs/` (`verificar_canarios.py`, `tenants.py`, `retencion.py`), the allowlist in `observabilidad/collector.yaml`,
`tests/test_seguridad_obs.py` (8 tests: the allowlist against the schema, the real Collector, injection payloads through the real stack,
and the evidence), and `resultados/seguridad_obs_*.json`.

## Plan versus result

| Plan bullet | Result |
|---|---|
| Canaries (DSN, OAuth token, API key, emails, phones, tax IDs) seeded in data, prompts and tool results; none in Langfuse or the Collector file, with content capture off and on; no threshold | ✅ 9 canaries (activity 2's 7 plus 2 in a list) seeded in the prompt, an SQL argument, a tool result (a note in `legado.artnot`, inserted for the run and deleted after it), the model's answer, and a span from a library that DOES capture (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, a list attribute, a `gen_ai.user.message` event, and an allowed key carrying a canary). Agent with no guardrails (the worst case), real MCP server and database, scripted model. Capture `NO_CONTENT` and `SPAN_AND_EVENT`: **0 canaries** in the file and in Langfuse (observations with their input, output and metadata) in both; the content keys never arrive; the allowed key arrives masked |
| … nor in the CI artifact | ⏳ there is no CI artifact yet: activity 10 adds it, and checks it with the same canaries |
| Langfuse projects per tenant, so one tenant's traces are invisible to another's keys | ✅ a second project (`legacybridge-tenant-b`) with its own keys: each key lists one project, a different one; a trace exported with each project's keys is visible to its own keys and returns nothing to the other's (both directions); a delete with the other project's keys removes nothing (checked 3 minutes later). ⚠️ Langfuse OSS has no API to create projects (the admin API and organization keys are Enterprise: "not available on your current plan"), so the project was created through the UI's own API, logged in as the admin, once. ⚠️ The lab's Collector still exports every trace to the first project: per-tenant export is shown with an exporter per tenant, not with routing in the Collector |
| Keys out of the repo | ✅ every key lives in `observabilidad/.secretos.env` (git-ignored, mode 600, never printed), tenant B's appended there; a test checks none of the evidence carries a key, and activity 2's tests check the compose file and the scripts |
| A retention policy configured and documented | ✅ the policy: 30 days in Langfuse, 7 days of rotated Collector files (at most 5 × 20 MB), no message content anywhere (the allowlist drops it). ⚠️ Langfuse OSS cannot enforce it ("user does not have access to entitlement: data-retention"), so it is a job, `retencion.py` (dry run by default): it lists the observations older than the cut, takes their traces and deletes them in batches. Proven on tenant B's project: a trace from 10 days ago and one from now, a 7-day cut deletes the old one only; the delete is asynchronous and took 101 s |
| Prompt injection through traces: a trace viewed by an LLM-powered tool, or a judge reading trace text, treats it as data; covered by the week 16 cases | ✅ covered structurally and tested with week 16's own payloads: as the task text, a tool name, an SQL literal, a tool result and the answer, none of them reaches any span (the schema keeps no free text, and an unknown tool becomes `execute_tool _unknown`); through the real Collector they are dropped with the keys that carried them; and the only automated reader of traces (activity 7's graders) takes a tool name, a status, a step and a hash. No LLM judge reads traces (activity 7). Week 16's cases cover the other half: an LLM agent reading injected comments and names treated them as data (0 obeyed) |
| Cost $0 | ✅ $0 |

## Findings

1. **The allowlist is the control; the patterns are the second layer.** With `allow_all_keys: false` a content key, a list or an event's text
   is dropped before any pattern runs. The seven patterns still matter for what an ALLOWED key carries: the canary put in `lab.task.id`
   arrived as `****`. A test pins the allowlist to the schema, so a new key needs both.
2. **The Collector checks keys, not the shape of their values.** An allowed key with a sentence in it would pass the Collector (unless the
   sentence matches a secret pattern). The shape of values is enforced in the instrumentation (`esquema.fijar`: identifiers, enumerations,
   numbers, hashes). A producer that does not use the lab's instrumentation is only bound by the key list.
3. **Langfuse OSS lacks the two controls the plan assumed**: projects by API and retention per project are Enterprise. Both have a
   working substitute here (the UI's API, once, and a deletion job), and both should move to the supported feature if the license changes.
4. **A delete with the wrong project's keys answers 200.** It removes nothing (measured), and it does not reveal whether the trace exists,
   but an audit of deletions cannot trust the status code: it has to check the effect, as the retention job's proof does.
5. **Deletion in Langfuse is asynchronous** (101 s here). A check made right after the call sees the trace; the first version of the
   tenant check judged too early and was corrected to wait 3 minutes.
6. **The Collector's raw file still holds older content.** The message events of the optional Strands run (activity 3) were written before
   the allowlist. The file rotates by size (20 MB), so they stay until it fills or the stack is deleted (`arrancar.sh --borrar`, which only
   the operator should run). From now on nothing like that reaches the file.

## Reproduce

```
cd semana-17                                                     # the stack up: ./observabilidad/arrancar.sh --reiniciar loads the allowlist
uv run --group semana17 python -m seguridad_obs.verificar_canarios    # canaries, capture off and on
uv run --group semana17 python -m seguridad_obs.tenants               # tenant B's project (once) and the isolation check
uv run --group semana17 python -m seguridad_obs.retencion --demostrar # the retention proof on tenant B; --dias N [--borrar] for the job
```
