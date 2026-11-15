"""Week 19, activity 5: the Converse request, offline ($0, no AWS, no model).

Checks that every agent call carries the model from config, the guardrail id and its pinned version, and the system
prompt rendered from the pinned text with its variable filled in. A missing guardrail or variable fails.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from ia.config import MODELO_ID  # noqa: E402
from ia.peticion import construir_converse, renderizar  # noqa: E402


def _cargar_prompts():
    spec = importlib.util.spec_from_file_location("prompts_sistema", S19 / "ia" / "prompts_sistema.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.PROMPTS


PROMPTS = _cargar_prompts()
VARIABLES = {"nombre_empresa": "Distribuidora Ejemplo"}


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_converse_lleva_modelo_guardrail_y_version_fijada(idioma):
    req = construir_converse(tarea="¿Cuál es el inventario de la sucursal 1?", texto_sistema=PROMPTS[idioma],
                             variables=VARIABLES, guardrail_id="teps1un80k04", guardrail_version="3")
    assert req["modelId"] == MODELO_ID
    assert req["guardrailConfig"] == {"guardrailIdentifier": "teps1un80k04", "guardrailVersion": "3"}
    assert req["messages"] == [{"role": "user", "content": [{"text": "¿Cuál es el inventario de la sucursal 1?"}]}]


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_system_es_el_prompt_fijado_con_la_variable_llena(idioma):
    req = construir_converse(tarea="x", texto_sistema=PROMPTS[idioma], variables=VARIABLES,
                             guardrail_id="g", guardrail_version="1")
    texto = req["system"][0]["text"]
    assert "Distribuidora Ejemplo" in texto
    assert "{{" not in texto and "}}" not in texto
    assert texto == renderizar(PROMPTS[idioma], VARIABLES)


def test_sin_guardrail_no_hay_peticion():
    with pytest.raises(ValueError):
        construir_converse(tarea="x", texto_sistema=PROMPTS["en"], variables=VARIABLES,
                           guardrail_id="", guardrail_version="3")
    with pytest.raises(ValueError):
        construir_converse(tarea="x", texto_sistema=PROMPTS["en"], variables=VARIABLES,
                           guardrail_id="g", guardrail_version="")


def test_variable_sin_valor_falla_en_vez_de_mandar_la_llave():
    with pytest.raises(KeyError):
        renderizar(PROMPTS["en"], {})


def test_renderizar_no_toca_texto_sin_variables():
    assert renderizar("sin variables", {"nombre_empresa": "X"}) == "sin variables"
