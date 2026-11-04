# Whiteboard kit (week 18, activity 6)

The exit criterion of phase 4: **in 30 minutes, design on a whiteboard a multi-agent system with MCP, its security boundaries and how it
will be evaluated.** This kit was written and frozen before the first rehearsal. The briefs are sealed (`sellar_casos.py`, hashes in
`sellos.json`); each one is revealed only when it is used.

## Procedure (every rehearsal and the final)

1. Reveal the brief: `python3 sellar_casos.py --revelar caso-N` (it checks the brief against its seal). Start a 30-minute timer.
2. Draw the five zones below, in order. Talk while drawing: the explanation is transcribed.
3. At 30:00 stop. Photograph or export the board (whiteboard, Excalidraw or tldraw).
4. Save to `ensayo-N/` or `final/`: `brief.md` (the revealed brief), `pizarra.png` (or `.excalidraw`), `transcripcion.md`,
   `tiempo.txt` (start, end), then the score (`calificacion.json`, by the rubric).

Time budget (a guide, not a rule): zone 1, 3 min · zone 2, 7 min · zone 3, 7 min · zone 4, 7 min · zone 5, 5 min · trade-offs, 1 min.

## The board in five zones

| Zone | What must be on the board |
|---|---|
| **1. Context and goal** | the legacy system, its users, the goal in one sentence, what "done" means, the constraint that shapes everything |
| **2. Agents** | each agent, its single job, its model and why; how they coordinate (supervisor, handoff, A2A); **why multi-agent at all**, and what a single agent would lose or save (week 15: multi-agent cost 1.7× for the same success) |
| **3. MCP servers and tools** | each server, what it exposes (tools, resources, prompts), transport (Streamable HTTP or stdio), who owns it, its data; which agent may call which tool |
| **4. Security boundaries** | trust boundaries drawn as lines; the checklist below |
| **5. Evaluation** | the checklist below, with numbers where a number is possible |

## Security checklist (weeks 13, 14, 16 and 17)

- **Identity:** every agent acts with the end user's identity or a scoped service identity; OAuth 2.1 with PKCE; an **audience per MCP
  server** (RFC 8707) so a token for one server is refused by another.
- **Least privilege:** scopes per tool; a database role per scope (read-only); restricted columns behind their own scope.
- **Consequential actions:** a human approval step with a level per amount or risk; the approver is not the requester; the action is
  created in the same transaction as the approval; timeouts expire cleanly.
- **Data is not instructions:** text from tools, documents, comments and other agents is data; guardrails on input, tool calls and
  output; injected instructions never become tool calls.
- **Tool poisoning:** an allowlist of servers and tools, pinned tool definitions (hash), prefixes against name collisions, a third-party
  server isolated with fewer scopes.
- **Budgets:** per task, session and tenant per day, checked before each model call; a stop with a partial answer, no silent retries.
- **Tenant isolation:** per-tenant data scope and per-tenant observability projects; nothing crosses.
- **Secrets and traces:** no prompt, SQL, row or personal value in spans; redaction by allowlist; keys outside the repo; retention.
- **Kill switch:** how to stop one agent, one tool or the whole system, and who can.

## Evaluation checklist (weeks 10 to 17)

- **Golden set** of tasks with execution-based checks (the answer recomputed from the source), in every language used.
- **Security suites with no threshold:** writes, leaks, instructions obeyed, orders without approval, secrets in traces, spend over a cap.
- **Trajectory graders** on the trace: tools, order, redundant and failed calls, recovery, steps; scores written to the observability.
- **Thresholds** set by a rule fixed before running (week 10: the multiple of 0.05 below the first run minus max(0.03, 1/n), with
  false-alarm control), calibrated on the CI data.
- **Cost and latency** per task, p50/p95, against the budget.
- **Before go-live:** offline eval and a red-team pass. **After:** CI on every change, online monitoring of the same metrics, sampled
  human review, a dashboard and a runbook.
- **An LLM judge** only for what code cannot decide, and only after it is validated on known bad cases.

## Rubric (fixed before the first rehearsal)

0 = missing · 1 = mentioned but not designed · 2 = designed and justified · 3 = designed, justified and quantified or traded off.

| # | Item | What a 3 looks like |
|---|---|---|
| 1 | Architecture fits the goal | every component traces to the goal or the constraint; nothing decorative |
| 2 | Agent boundaries | each agent has one job and a reason; the single-agent alternative is weighed with its cost |
| 3 | MCP design | servers, tools, transports, ownership and auth are on the board; which agent calls what |
| 4 | Security boundaries | the trust lines are drawn and the checklist items that apply are placed on them |
| 5 | Evaluation plan | golden set, security suites, trajectory, thresholds by a rule, cost; before and after go-live |
| 6 | Trade-offs and cost | at least two explicit trade-offs and a rough cost per task or per month |
| 7 | Time | delivered in 30:00 or less (3 = with the five zones complete; 2 = one zone thin; 0 = over time) |

**Pass:** every item ≥ 2 and a total ≥ 16 of 21. The score is written by the reviewer with a reason per item and the list of what was
missing; the next rehearsal starts from that list.
