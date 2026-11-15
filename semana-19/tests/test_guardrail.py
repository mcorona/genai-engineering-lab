"""Week 19, activity 5: the Guardrail definition is valid for the Bedrock API and covers the week 17 layer.

Offline and $0: the shape is checked against the botocore service model (no AWS call).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import botocore.session
from botocore.validate import validate_parameters

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from guardrail.definicion import (  # noqa: E402
    PATRON_DSN,
    PATRON_LLAVE_AWS,
    PATRON_RFC,
    definicion_guardrail,
)

D = definicion_guardrail()


def _modelo_create_guardrail():
    servicio = botocore.session.get_session().get_service_model("bedrock")
    return servicio.operation_model("CreateGuardrail").input_shape


def test_forma_valida_para_createguardrail():
    # botocore raises ParamValidationError on unknown keys, wrong types or enum values.
    validate_parameters(D, _modelo_create_guardrail())


def test_prompt_attack_solo_en_la_entrada():
    filtro = next(f for f in D["contentPolicyConfig"]["filtersConfig"] if f["type"] == "PROMPT_ATTACK")
    assert filtro["inputStrength"] == "HIGH" and filtro["outputStrength"] == "NONE"


def test_categorias_de_contenido_de_la_semana_17():
    tipos = {f["type"] for f in D["contentPolicyConfig"]["filtersConfig"]}
    assert {"SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT", "PROMPT_ATTACK"} <= tipos


def test_tema_denegado_cubre_escrituras_fuera_de_la_aprobacion():
    tema = D["topicPolicyConfig"]["topicsConfig"][0]
    assert tema["type"] == "DENY"
    assert any("DROP" in ejemplo for ejemplo in tema["examples"])
    assert any("Aprueba" in ejemplo for ejemplo in tema["examples"])


def test_pii_correo_y_telefono_se_anonimizan_y_rfc_se_bloquea():
    pii = {p["type"]: p["action"] for p in D["sensitiveInformationPolicyConfig"]["piiEntitiesConfig"]}
    assert pii == {"EMAIL": "ANONYMIZE", "PHONE": "ANONYMIZE"}
    rfc = next(r for r in D["sensitiveInformationPolicyConfig"]["regexesConfig"] if r["name"] == "rfc-mexico")
    assert rfc["action"] == "BLOCK"


def test_patrones_detectan_lo_que_deben_y_no_lo_normal():
    assert re.search(PATRON_RFC, "RFC: GODE561231GR8")
    assert not re.search(PATRON_RFC, "SKU-0042 con 12 unidades")
    assert re.search(PATRON_DSN, "postgresql://usuario:clave@host:5432/postgres")
    assert not re.search(PATRON_DSN, "la conexión es estable")
    assert re.search(PATRON_LLAVE_AWS, "AKIAIOSFODNN7EXAMPLE")
    assert not re.search(PATRON_LLAVE_AWS, "AKIA corto")


def test_grounding_y_relevancia_con_umbral():
    filtros = {f["type"]: f["threshold"] for f in D["contextualGroundingPolicyConfig"]["filtersConfig"]}
    assert filtros == {"GROUNDING": 0.7, "RELEVANCE": 0.7}


def test_mensajes_bloqueados_en_espanol_e_ingles():
    assert "/" in D["blockedInputMessaging"]
    assert D["blockedInputMessaging"] == D["blockedOutputsMessaging"]


def test_sin_cuenta_ni_correos_reales_en_la_definicion():
    texto = repr(D)
    assert not re.search(r"\b\d{12}\b", texto), "no account ids in the definition"
    assert "@" not in texto
