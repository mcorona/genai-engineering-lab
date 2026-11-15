"""Week 19, activity 5: the managed policy for the agent Lambda (activity 6).

Allows only: invoking the one inference profile in MODELO_ID (and its underlying foundation models, conditioned on
that profile), ApplyGuardrail on the guardrail, and GetPrompt on the pinned prompt versions. No bedrock:*.
ARNs take the account and the guardrail/prompt ARNs as tokens or values, so the repo never holds the account id.
"""
from __future__ import annotations

from config import MODELO_ID, REGIONES_DEL_MODELO

# The actions the Converse API uses for the model call (Converse maps to InvokeModel and its stream variant).
ACCIONES_MODELO = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]


def arn_perfil(cuenta: str, region: str = "us-east-1") -> str:
    return f"arn:aws:bedrock:{region}:{cuenta}:inference-profile/{MODELO_ID}"


def arn_modelo_base(region: str) -> str:
    # The profile id is the geography prefix ("us.") plus the foundation model id, which keeps its version suffix.
    return f"arn:aws:bedrock:{region}::foundation-model/{MODELO_ID.removeprefix('us.')}"


def politica_invocar_modelo(cuenta: str, arn_guardrail: str, arns_prompts: list[str]) -> dict:
    perfil = arn_perfil(cuenta)
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvocarPerfilDeModelo",
                "Effect": "Allow",
                "Action": ACCIONES_MODELO,
                "Resource": perfil,
            },
            {
                "Sid": "InvocarModeloSubyacenteSoloViaPerfil",
                "Effect": "Allow",
                "Action": ACCIONES_MODELO,
                "Resource": [arn_modelo_base(r) for r in REGIONES_DEL_MODELO],
                "Condition": {"StringEquals": {"bedrock:InferenceProfileArn": perfil}},
            },
            {
                "Sid": "AplicarGuardrail",
                "Effect": "Allow",
                "Action": ["bedrock:ApplyGuardrail"],
                "Resource": arn_guardrail,
            },
            {
                "Sid": "LeerVersionesFijadasDePrompts",
                "Effect": "Allow",
                "Action": ["bedrock:GetPrompt"],
                "Resource": arns_prompts,
            },
        ],
    }
