# Phase 4 · Week 18: LegacyBridge v1 and the close of the phase

Repo: `mcorona/genai-engineering-lab`. Folder: `semana-18/`. Each activity closes with a PR, green checks and a merge before moving on to
the next. Documentation goes in separate PRs.

- **Topic:** closing phase 4 (weeks 13 to 18: agents, MCP and orchestration over legacy systems).
- **Deliverable:** **LegacyBridge v1**, one release that a client can run, with a **3-minute demo video in English**.
- **Exit criterion of the phase (root README, criterion 18):** a whiteboard design, done in **30 minutes**, of a **multi-agent system with
  MCP**, its **security boundaries** and **how it will be evaluated**, versioned in the repo; CCAR-P presented.
- **Why it matters for clients:** weeks 13 to 17 built the pieces and measured each one. A client buys the whole: one thing that installs,
  runs, is safe by construction, and can be shown in three minutes and drawn on a whiteboard in thirty. The video and the whiteboard
  design are the two artifacts used in a first client meeting.

## What v1 is made of (weeks 13 to 17, all merged)

| Week | Piece | Where |
|---|---|---|
| 13 | The agent loop and its golden set (84 tasks, execution-based checks), security suite | `semana-13/` |
| 14 | Remote MCP server, Streamable HTTP, Keycloak OAuth (PKCE, RFC 8707), least privilege, tool-poisoning defenses | `semana-14/` |
| 15 | Multi-agent over A2A (supervisor + specialist), the same agent in other frameworks, AgentCore, decision matrix | `semana-15/` |
| 16 | `legacy-schema-audit` plugin for clients, its eval, marketplace | `semana-16/` |
| 17 | Tracing (OTel GenAI + Langfuse), budgets, guardrails, human approval, trajectory eval, dashboard, CI mini eval | `semana-17/` |

v1 does not add capabilities. It integrates them behind one entry point and one bring-up, freezes a version, and proves it with one gate.

## Default decisions

- **v1 topology:** the week 15 multi-agent shape (a supervisor that plans, specialists that act) with every specialist behind week 14's MCP
  server and week 17's layers (instrumentation, budgets, guardrails, approval). A single-agent mode stays available: week 15 measured the
  multi-agent version at 1.7× the cost for the same success, and v1 must show the client both and why one is the default.
- **One bring-up:** `semana-18/legacybridge/arrancar.sh` starts PostgreSQL (CI data), Keycloak, the MCP server, the Collector and Langfuse,
  checks health, and prints the URLs. `--detener` and `--borrar` as in week 17.
- **One entry point:** `python -m legacybridge` (`preguntar`, `proponer`, `aprobar`, `tablero`, `demo`) over the existing modules.
- **Version:** `v1.0.0` git tag and GitHub release, with notes generated from the per-activity reports; the release gate is the week 17 CI
  plus the full v1 eval (activity 3).
- **The video:** English, 3:00 ± 0:10, screen recording with voice-over recorded by Manuel; Claude writes the script, the storyboard, the
  deterministic demo scenario and the captions. Nothing is published without approval; the video goes to the release as an asset or as an
  unlisted link.
- **The whiteboard:** the briefs are written BEFORE the rehearsals and kept out of sight until each one is used; the final brief is new. A
  rubric fixed before the first rehearsal scores each design. Timer, photo or export, and a written transcript go to the repo.
- **Cost:** the v1 eval and the demo's live take use the API (estimated and authorized first, with a cap); rehearsal reviews are done in
  the Claude Code session ($0 extra).

## Activities

### 1. v1 scope and baseline
- Inventory of what v1 uses from each week and how it is started today (commands, ports, secrets, data).
- The gaps to an integrated v1: what is started by hand, what only runs in tests, what has two versions.
- Freeze the v1 scope in `semana-18/ALCANCE.md` (in, out, and why), and the demo storyline (activity 4) in one paragraph.
- **Time:** ~1 h. **Cost:** $0.

### 2. LegacyBridge v1: one bring-up and one entry point
- `legacybridge/arrancar.sh`: every service, pinned images, secrets generated per machine, health checks, idempotent.
- `python -m legacybridge`: the subcommands above over the week 13 to 17 modules (no copies).
- Multi-agent mode: the week 15 supervisor + specialists, each specialist an MCP client with its own audience and scopes, all spans in one
  trace, budgets per task across agents, guardrails on every agent's input and output, the approval step only on the consequential tool.
- Single-agent mode, same commands, `--modo simple`.
- Tests without API: bring-up check, the entry point with a scripted model, one trace across agents, the security layers active in both
  modes.
- **Time:** ~3 h. **Cost:** $0.

### 3. v1 eval and release gate
- The 84 golden tasks in both modes (success, trajectory, cost, latency), the 38 attacks and the week 13 security cases against the
  multi-agent mode, the 7 approval scenarios.
- Thresholds: the week 17 CI thresholds as the floor; security with no threshold (0 writes, 0 leaks, 0 obeyed, 0 orders without approval,
  0 secrets in traces, 0 spend over a cap).
- The comparison table single vs multi-agent, with confidence intervals (week 13's bootstrap), and the recommendation for clients.
- `v1.0.0`: tag, GitHub release, release notes, the results JSON attached.
- **Time:** ~2 h. **Cost:** ~$0.60 (84 tasks × 2 modes + attacks; authorized first, with a cap).

### 4. The demo scenario
- A storyline that fits 3 minutes and shows what a client must see: a business question answered from a cryptic legacy schema with
  the SQL behind it; an injected instruction blocked; a purchase-order proposal paused and approved by a manager in Keycloak; the trace
  and the cost of the whole thing in the dashboard.
- `python -m legacybridge demo`: deterministic steps, a scripted model for rehearsals ($0) and the real model for the take, the same
  data every time, a reset between takes, and a timer per step.
- Rehearse at $0 until it fits the time with margin.
- **Time:** ~1.5 h. **Cost:** $0 rehearsals; ~$0.05 for the live take.

### 5. The video (3 minutes, English)
- Script (about 400 words at ~140 words per minute) with timecodes, a storyboard (shot, screen, action, line), and a recording
  checklist (resolution, font size, hidden secrets and paths, notifications off).
- Manuel records the screen and the voice-over; Claude reviews the take against the script and the checklist (no secret, DSN, home path
  or personal value on screen).
- English captions (`.srt`) checked against the final cut; a thumbnail and a 2-line description.
- Publish only with approval: release asset or unlisted link, referenced from the root README.
- **Time:** ~2 h (most of it Manuel's recording). **Cost:** $0.

### 6. Whiteboard kit
- **Briefs:** 6 short client scenarios (a legacy system, a goal, constraints), written now and sealed: 3 for rehearsals, 1 for the final,
  2 spare. Each one needs more than one agent and at least one MCP server.
- **Template** (the board in five zones, in this order): context and goal; agents and their responsibilities; MCP servers, tools and
  data; security boundaries; evaluation.
- **Security checklist** from weeks 14, 16 and 17: identity and OAuth audiences per server, least-privilege scopes and DB roles,
  consequential actions behind human approval, data-is-not-instructions guardrails, tool poisoning and allowlists, budgets, secrets and
  redaction in traces, tenant isolation, kill switch.
- **Evaluation checklist** from weeks 10 to 17: golden set with execution-based checks, security suites with no threshold, trajectory
  graders, thresholds by the week 10 rule, cost and latency, online monitoring.
- **Rubric** (fixed before the first rehearsal, 0 to 3 per item): architecture fits the goal; agent boundaries justified (or why not
  multi-agent); MCP design (servers, tools, auth); security boundaries complete; evaluation plan measurable; trade-offs and cost stated;
  delivered in 30 minutes. Pass: every item ≥ 2 and a total ≥ 16 of 21.
- **Time:** ~1 h. **Cost:** $0.

### 7. Rehearsals (3 × 30 minutes)
- Manuel opens a sealed brief, sets a 30-minute timer, draws (whiteboard photo, Excalidraw or tldraw export).
- Claude scores it with the rubric, lists what is missing, and the next rehearsal starts from that list.
- Each rehearsal goes to `semana-18/pizarra/ensayo-N/` (brief, image, transcript of the explanation, score).
- **Time:** ~2.5 h. **Cost:** $0.

### 8. The final whiteboard (the exit criterion)
- An unseen brief, 30 minutes on a timer, the explanation recorded or transcribed.
- Scored with the same rubric; the image, the transcript, the time and the score versioned in `semana-18/pizarra/final/`.
- If it does not pass, one more attempt with a spare brief after reviewing the gaps (both attempts kept).
- **Time:** ~1 h. **Cost:** $0.

### 9. CCAR-P
- Map the exam's domains to the phase 4 work (which week covers what, what to review).
- Presentation of the certification: registration and the exam are Manuel's actions; the repo keeps only the evidence that it was
  presented, with no personal data.
- **Time:** depends on the exam. **Cost:** the exam fee, outside this plan.

### 10. CI, README and the close of phase 4
- `eval-semana-18` workflow: v1 bring-up check, the entry point tests without API, and a v1 mini eval with API on both modes (thresholds
  by the week 10 rule, security with no threshold), evidence as an artifact.
- `semana-18/README.md`: v1 architecture, the single vs multi-agent table, the video, the whiteboard design and its score.
- Root README: criterion 18 `[x]` with its evidence, phase 4 complete, the link to the video and the v1 release.
- Phase 4 retrospective (what each week proved, what a client gets, what moves to phase 5).
- **Time:** ~2 h. **Cost:** ~$0.10 to $0.20 per CI run (calibration ~$0.40). Documentation in a separate PR, $0.

## Summary

| | |
|---|---|
| Estimated total time | ~17 h (about 6 of them Manuel's: recording, rehearsals, final whiteboard, exam) |
| Estimated API cost | ~$1.00 to $1.30 (v1 eval ~$0.60, demo take ~$0.05, CI calibration ~$0.40); each paid run authorized first, with a cap |
| Cloud | None. Everything runs on the Mac and in CI |
| Risks | the video runs long (rehearse with a timer, cut lines, not steps); secrets on screen (checklist and review before publishing); the multi-agent mode costs more for the same success (show it, recommend single-agent where it fits); the whiteboard briefs leak into the practice (seal them, keep the final unseen) |

## Dependencies

```
1 scope ──► 2 bring-up + entry point ──► 3 v1 eval + release ──► 4 demo ──► 5 video ─────────────┐
                                                                                                 ├──► 10 CI, README, close
6 whiteboard kit ──► 7 rehearsals ──► 8 final whiteboard ─────────────────────────────────────────┤
9 CCAR-P (in parallel, Manuel) ───────────────────────────────────────────────────────────────────┘
```

Activities 6 to 8 do not depend on the code and can start on day one, in parallel with 1 to 3.

## Log

- 2026-11-04: plan created after week 17 closed (criterion 17 verified, PRs #132 to #139).
