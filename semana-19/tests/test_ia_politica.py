"""Week 19, activity 5: one model value, and an agent policy that cannot call any other model or profile.

Offline and $0. The foundation-model ARNs were read with get-inference-profile on 2026-11-15.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19 / "ia"))

import config  # noqa: E402
import politica  # noqa: E402

CUENTA = "<account>"
GUARDRAIL = f"arn:aws:bedrock:us-east-1:{CUENTA}:guardrail/semana19-legacybridge"
PROMPTS = [f"arn:aws:bedrock:us-east-1:{CUENTA}:prompt/PROMPTID:1"]


def _politica():
    return politica.politica_invocar_modelo(CUENTA, GUARDRAIL, PROMPTS)


def _recursos(doc):
    for st in doc["Statement"]:
        r = st["Resource"]
        yield from (r if isinstance(r, list) else [r])


def test_el_id_del_modelo_solo_vive_en_la_configuracion():
    # Changing to another model must be a change of config.MODELO_ID and nothing else.
    raiz = S19
    hallazgos = []
    for ruta in list((raiz / "ia").rglob("*.py")) + list((raiz / "infra" / "cdk").rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        if ruta.name == "config.py" and ruta.parent.name == "ia":
            continue
        if "claude-haiku-4-5" in ruta.read_text(encoding="utf-8"):
            hallazgos.append(str(ruta.relative_to(raiz)))
    assert hallazgos == []


def test_la_politica_no_tiene_comodines_ni_bedrock_completo():
    doc = _politica()
    for st in doc["Statement"]:
        acciones = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        assert "bedrock:*" not in acciones and "*" not in acciones
    for recurso in _recursos(doc):
        assert recurso != "*", "a wildcard resource is not allowed"


def test_solo_permite_el_perfil_de_haiku_45_y_sus_modelos_subyacentes():
    doc = _politica()
    perfil = politica.arn_perfil(CUENTA)
    recursos = set(_recursos(doc))
    modelos_base = {politica.arn_modelo_base(r) for r in config.REGIONES_DEL_MODELO}
    permitidos = {perfil, GUARDRAIL, *PROMPTS} | modelos_base
    assert recursos <= permitidos
    # No other model family or geography profile sneaks in.
    assert not any(re.search(r"sonnet|opus|global\.|haiku-5|haiku-3", r) for r in recursos)


def test_los_modelos_subyacentes_solo_se_usan_via_el_perfil():
    doc = _politica()
    cond = [st for st in doc["Statement"] if st["Sid"] == "InvocarModeloSubyacenteSoloViaPerfil"][0]
    assert cond["Condition"] == {"StringEquals": {"bedrock:InferenceProfileArn": politica.arn_perfil(CUENTA)}}


def test_acciones_exactas_del_modelo_y_del_guardrail_y_prompts():
    doc = _politica()
    acciones = {a for st in doc["Statement"] for a in (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])}
    assert acciones == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                        "bedrock:ApplyGuardrail", "bedrock:GetPrompt"}


def test_cambiar_de_modelo_es_solo_cambiar_el_valor_de_configuracion(monkeypatch):
    nuevo = "us.anthropic.claude-haiku-5-5-EJEMPLO:0"
    monkeypatch.setattr(config, "MODELO_ID", nuevo)
    monkeypatch.setattr(politica, "MODELO_ID", nuevo)
    doc = politica.politica_invocar_modelo(CUENTA, GUARDRAIL, PROMPTS)
    recursos = set(_recursos(doc))
    assert politica.arn_perfil(CUENTA) in recursos
    assert not any("claude-haiku-4-5" in r for r in recursos)
