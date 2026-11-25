"""Week 19, activity 5: the Converse request the agent sends, built offline.

The request carries the model (config.MODELO_ID), the guardrail (id and version, so the guardrail runs on the
model's input and output) and the system prompt rendered from its pinned Prompt Management version. Nothing here calls
AWS: the Lambda passes the guardrail id and version, and the prompt text it read at cold start.
"""
from __future__ import annotations

import re

from ia.config import MODELO_ID

VARIABLE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def renderizar(texto: str, variables: dict[str, str]) -> str:
    """Replace each {{name}} with its value. A missing variable raises: no prompt goes out with a raw placeholder."""
    def sustituir(m: re.Match) -> str:
        nombre = m.group(1)
        if nombre not in variables:
            raise KeyError(f"a variable without a value in the prompt: {nombre}")
        return variables[nombre]
    return VARIABLE.sub(sustituir, texto)


def construir_converse(*, tarea: str, texto_sistema: str, variables: dict[str, str],
                       guardrail_id: str, guardrail_version: str) -> dict:
    """The Converse call: one user turn with the task, the rendered system prompt, and the guardrail on that call."""
    if not guardrail_id or not guardrail_version:
        raise ValueError("the guardrail is required: an id and a pinned version")
    return {
        "modelId": MODELO_ID,
        "system": [{"text": renderizar(texto_sistema, variables)}],
        "messages": [{"role": "user", "content": [{"text": tarea}]}],
        "guardrailConfig": {"guardrailIdentifier": guardrail_id, "guardrailVersion": str(guardrail_version)},
    }
