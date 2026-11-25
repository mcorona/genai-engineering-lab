"""Week 19, activity 7: the gateway's Cedar policies, versioned as files (gateway/politicas/*.cedar).

Each file is one policy of the policy engine (one AWS::BedrockAgentCore::Policy each). A policy that names specific
actions must name the gateway with `resource ==` (bedrock-agentcore/latest/devguide/example-policies-principal.html,
read 2026-11-18), so the files carry the placeholder {{GATEWAY_ARN}}: the stack puts the gateway's ARN there and the
tests a fixed one. Default deny: a tool no policy permits is denied, the approval included (it is not a tool).
"""
from __future__ import annotations

from pathlib import Path

CARPETA = Path(__file__).resolve().parent / "politicas"
MARCADOR = "{{GATEWAY_ARN}}"


def politicas() -> dict[str, str]:
    """{policy name: Cedar text with the placeholder}, by file name."""
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(CARPETA.glob("*.cedar"))}


def con_gateway(texto: str, arn_gateway: str) -> str:
    if texto.count(MARCADOR) != 1:
        raise ValueError("each policy names the gateway exactly once")
    return texto.replace(MARCADOR, arn_gateway)
