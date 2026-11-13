# ADR 0004: Lambda agent, AgentCore Runtime or Bedrock Agents

## Context

The LegacyBridge agent runs a loop of model calls and tool calls. Week 15 measured the same Strands agent on AgentCore Runtime (`semana-15/resultados/agentcore.md`): same success (1.000 on the 20-task mini eval) and same model cost per task ($0.0031 vs $0.0029).

## Alternatives

- **Lambda.** Function outside the VPC, called from API Gateway. Warm starts are fast; a cold start loads the Python imports.
- **AgentCore Runtime.** Per-session microVM, deploy in about 35 s (READY), per-second billing with I/O wait free.
- **Bedrock Agents.** Managed agent with action groups; not used by the agent code of the course.

### Measured data (week 15)

- Cold start on AgentCore Runtime: **5.7–5.9 s** on every new session (3.7 s of it is Python imports).
- Warm: **263–288 ms**.
- Deploy to READY: **about 35 s**.
- Total cost of the week 15 run: **$0.062 model and $0.024 AWS**.

## Decision

**Lambda for the lab agent.** The agent runs outside the VPC, calls Bedrock directly (Converse with Guardrail and Prompt Management) and needs no session isolation for a single demo user. Its cold start is the cost of the demo, and the measured figures let us say so.

**AgentCore Runtime is the prod option** if per-session isolation is needed; the cold start of 5.7–5.9 s is the number to explain to the user. Bedrock Agents is not used.

## Consequences

- The Lambda agent is outside the VPC; only the tools Lambda is inside it.
- The 5.7–5.9 s cold start appears in the demo's first request after an idle period.

## Costs (from `precios.json`)

- Lambda arm64, per GB-second: **0.0000106667 USD** (M, `Lambda-GB-Second-ARM`). One query at 512 MB × 3 s = 1.5 GB-s = 0.000016 USD (model assumption, declared).
- Lambda per request, x86: **0.0000002 USD** (M, usagetype `Request`, SKU `GU2ZS9HVP6QTQ7KE`, Price List, 2026-11-13). Included in the lab total.
- AgentCore Runtime, c5.large, per hour: **0.0102 USD** (M, `Runtime:Instance-based:c5.large:Management-Hours`, 2026-11-12), the instance-based price from linea_base.md.
- Bedrock Agents: **N**. Not measured.
