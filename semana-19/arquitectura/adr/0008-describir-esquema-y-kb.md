# ADR 0008: the tools Lambda serves the schema catalog; the agent Lambda retrieves from the Knowledge Base

## Context

Activity 4 found that `bedrock-agent` has no usable private DNS in the VPC, and ADR 0005 does not include
`bedrock-agent-runtime`.

## Alternatives

- **(a)** The tools Lambda (in the VPC) returns the database catalog. The agent Lambda (outside the VPC) calls `Retrieve`
  on the Knowledge Base and merges the results.
- **(b)** An interface endpoint for `bedrock-agent-runtime`, if it resolves.

## Decision

**(a).** The agent Lambda stays outside the VPC (ADR 0004), and the Knowledge Base is reached over the public API with
the agent's role. No new endpoint is added.

## Consequences

- The agent role gets `bedrock:Retrieve` on the Knowledge Base ARN only.
- ADR 0005 stays as it is.
- Costs: (a) adds no endpoint. Retrieval is billed by the Knowledge Base, **not quoted** here.
