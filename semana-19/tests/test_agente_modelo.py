"""Week 20, preparation: `modelo.invocar` is the week 19 model path, unchanged (offline, $0)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from agente import modelo  # noqa: E402
from agente.converse_adaptador import api_converse  # noqa: E402
from ia import config  # noqa: E402

GUARD = {"guardrailIdentifier": "gid", "guardrailVersion": "3"}
CUERPO = {"model": "x", "max_tokens": 900, "system": "SISTEMA", "output_config": {"effort": "low"},
          "tools": [{"name": "describir_esquema", "description": "d", "input_schema": {"type": "object"}}],
          "messages": [{"role": "user", "content": "pregunta"}]}
RESP = {"output": {"message": {"role": "assistant", "content": [{"text": "hola"}]}}, "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 2}}


class Llamada:
    def __init__(self):
        self.pedidos = []

    def __call__(self, req):
        self.pedidos.append(copy.deepcopy(req))
        return RESP


def test_invocar_es_igual_al_camino_de_la_semana_19():
    a, b = Llamada(), Llamada()
    cfg = modelo.ConfigModelo(modelo_id=config.MODELO_ID, guardrail=GUARD)
    nuevo = modelo.invocar(a, CUERPO, config=cfg)
    viejo = api_converse(b, modelo_id=config.MODELO_ID, guardrail=GUARD)(CUERPO)
    assert nuevo == viejo
    assert a.pedidos == b.pedidos and len(a.pedidos) == 1


def test_sin_cache_ni_ruteo_todavia():
    a = Llamada()
    modelo.api(a, config=modelo.ConfigModelo(modelo_id=config.MODELO_ID, guardrail=GUARD))(CUERPO)
    req = a.pedidos[0]
    assert req["modelId"] == config.MODELO_ID and req["guardrailConfig"] == GUARD
    assert "cachePoint" not in repr(req)


def test_el_modelo_del_agente_es_el_de_la_configuracion():
    assert K.MODELO_ID == config.MODELO_ID


def test_construccion_usa_modelo_invocar():
    texto = (S19 / "agente" / "construccion.py").read_text(encoding="utf-8")
    assert "modelo.api(" in texto and "api_converse" not in texto
