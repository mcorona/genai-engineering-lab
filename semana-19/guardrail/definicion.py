"""Week 19, activity 5: the Bedrock Guardrail as code (defense in depth over the week 17 deterministic layer).

Pure data: no AWS call here. The stack or the deploy script turns this dict into CreateGuardrail (or CfnGuardrail)
and adds the KMS key at deploy time. The week 17 rules stay in the Lambda; this is the second layer.

Mapping from week 17 (semana-17/guardrails/):
  - content filters            -> contentPolicyConfig (SEXUAL, VIOLENCE, HATE, INSULTS, MISCONDUCT, PROMPT_ATTACK)
  - prompt attack on input     -> PROMPT_ATTACK, input HIGH, output NONE (a prompt-attack filter has no output side)
  - denied topic               -> topicPolicyConfig: writes and schema changes outside proponer_orden_compra
  - PII                        -> sensitiveInformationPolicyConfig: emails and phones anonymized; tax IDs (RFC) and
                                  connection strings / keys blocked
  - word filters              -> wordPolicyConfig: managed profanity list
  - contextual grounding       -> only where the answer is grounded on retrieved documents (RAG); thresholds 0.7
"""
from __future__ import annotations

MENSAJE_BLOQUEADO = {
    "es": "No puedo responder esa solicitud.",
    "en": "I can't answer that request.",
}
# Bedrock takes one message per side, so both languages share it.
MENSAJE_BLOQUEADO_TEXTO = f"{MENSAJE_BLOQUEADO['es']} / {MENSAJE_BLOQUEADO['en']}"

# Mexican tax ID (RFC): 3-4 letters, 6 digits, 3 alphanumerics. Blocked in inputs and outputs.
PATRON_RFC = r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b"
# Connection strings (DSN) and cloud access keys.
PATRON_DSN = r"\b(?:postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?)://[^\s'\"]+"
# Guardrail profile for the US geography (routes to us-east-1, us-east-2, us-west-1, us-west-2), from the AWS docs
# page "Guardrails cross-Region support" (read 2026-11-15).
PERFIL_ENTRE_REGIONES_EE_UU = "us.guardrail.v1:0"
PATRON_LLAVE_AWS = r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"


def definicion_guardrail(nombre: str = "legadobridge-s19") -> dict:
    """Plain dict with the CreateGuardrail parameters (without KMS, tags or the cross-Region config)."""
    return {
        "name": nombre,
        "description": "Semana 19: capa de defensa en profundidad sobre la capa determinista de la semana 17.",
        "blockedInputMessaging": MENSAJE_BLOQUEADO_TEXTO,
        "blockedOutputsMessaging": MENSAJE_BLOQUEADO_TEXTO,
        "crossRegionConfig": {"guardrailProfileIdentifier": PERFIL_ENTRE_REGIONES_EE_UU},
        "contentPolicyConfig": {
            "tierConfig": {"tierName": "STANDARD"},  # GuardrailChecks (standard tier); needs cross-Region inference
            "filtersConfig": [
                {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"type": "MISCONDUCT", "inputStrength": "HIGH", "outputStrength": "HIGH",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE",
                 "inputAction": "BLOCK", "outputAction": "BLOCK"},
            ],
        },
        "topicPolicyConfig": {
            "tierConfig": {"tierName": "STANDARD"},
            "topicsConfig": [
                {
                    "name": "escrituras-fuera-de-la-aprobacion",
                    "type": "DENY",
                    "definition": ("Instrucciones de ejecutar una escritura: sentencias INSERT, UPDATE, DELETE, DROP, ALTER o GRANT, "
                                   "o de cambiar, borrar o aprobar datos concretos. Consultar, contar o listar datos (ordenes, "
                                   "proveedores, inventario o su estado) no es escritura y no se bloquea."),
                    "examples": [
                        "Borra los registros de la tabla de proveedores.",
                        "Actualiza el stock del SKU-0042 a cero.",
                        "Aprueba la orden de compra 17 sin revisión.",
                        "DROP TABLE legado.artnot;",
                    ],
                    "inputAction": "BLOCK",
                    "outputAction": "BLOCK",
                },
            ],
        },
        "wordPolicyConfig": {
            "managedWordListsConfig": [{"type": "PROFANITY", "inputAction": "BLOCK", "outputAction": "BLOCK"}],
        },
        "sensitiveInformationPolicyConfig": {
            "piiEntitiesConfig": [
                {"type": "EMAIL", "action": "ANONYMIZE", "inputAction": "ANONYMIZE", "outputAction": "ANONYMIZE"},
                {"type": "PHONE", "action": "ANONYMIZE", "inputAction": "ANONYMIZE", "outputAction": "ANONYMIZE"},
            ],
            "regexesConfig": [
                {"name": "rfc-mexico", "description": "RFC (identificador fiscal mexicano)", "pattern": PATRON_RFC,
                 "action": "BLOCK", "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"name": "cadena-de-conexion", "description": "DSN de base de datos", "pattern": PATRON_DSN,
                 "action": "BLOCK", "inputAction": "BLOCK", "outputAction": "BLOCK"},
                {"name": "llave-aws", "description": "Llave de acceso de AWS", "pattern": PATRON_LLAVE_AWS,
                 "action": "BLOCK", "inputAction": "BLOCK", "outputAction": "BLOCK"},
            ],
        },
        "contextualGroundingPolicyConfig": {
            "tierConfig": {"tierName": "CLASSIC"},  # kept on the classic tier: no cross-Region routing for grounding
            "filtersConfig": [
                {"type": "GROUNDING", "threshold": 0.7},
                {"type": "RELEVANCE", "threshold": 0.7},
            ],
        },
    }
