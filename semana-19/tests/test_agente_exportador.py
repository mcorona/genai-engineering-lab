"""Week 19, activity 6: the agent's span exporter, offline ($0, no AWS, no model)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import exportador as X  # noqa: E402
from agente.exportador import ExportadorSpans  # noqa: E402
from instrumentacion import esquema  # noqa: E402

CHAT_OK = {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.request.model": "claude-haiku-4-5-20251001",
    "gen_ai.request.max_tokens": 900,
    "gen_ai.usage.input_tokens": 1200,
    "gen_ai.usage.output_tokens": 300,
    "gen_ai.response.finish_reasons": ["tool_use"],
}


@pytest.fixture(autouse=True)
def limpiar():
    X.OMITIDOS.clear()
    yield
    X.OMITIDOS.clear()


def _exportar(spans, estricto=False, monkeypatch=None):
    salida = []
    if monkeypatch is not None:
        monkeypatch.setattr(esquema, "ESTRICTO", estricto)
    e = ExportadorSpans(escribir=salida.append)
    e.exportar(spans)
    return [json.loads(l) for l in salida]


def test_span_de_modelo_valido_sale_completo_y_sin_omitidos():
    (linea,) = _exportar([{"name": "chat claude-haiku-4-5-20251001", "tipo": "chat", "attrs": CHAT_OK}])
    assert linea["attrs"] == CHAT_OK and linea["omitidos"] == []
    assert linea["schema"] == esquema.SCHEMA_VERSION and linea["tipo"] == "chat"


def test_atributo_de_texto_libre_se_omite_y_se_cuenta(monkeypatch):
    attrs = dict(CHAT_OK, **{"lab.error": "postgresql://user:clave@host/db"})
    (linea,) = _exportar([{"name": "chat x", "tipo": "chat", "attrs": attrs}], monkeypatch=monkeypatch)
    assert "lab.error" not in linea["attrs"]
    assert linea["omitidos"] == ["lab.error"]
    assert X.OMITIDOS["chat:lab.error"] == 1
    assert "clave" not in json.dumps(linea)


def test_valor_de_tipo_incorrecto_se_omite(monkeypatch):
    attrs = dict(CHAT_OK, **{"gen_ai.usage.input_tokens": "1200 tokens"})
    (linea,) = _exportar([{"name": "chat x", "tipo": "chat", "attrs": attrs}], monkeypatch=monkeypatch)
    assert "gen_ai.usage.input_tokens" not in linea["attrs"]


def test_modo_estricto_levanta_ante_un_atributo_no_declarado(monkeypatch):
    attrs = dict(CHAT_OK, **{"usuario.nombre": "Ana"})
    with pytest.raises(esquema.ErrorEsquema):
        _exportar([{"name": "chat x", "tipo": "chat", "attrs": attrs}], estricto=True, monkeypatch=monkeypatch)


def test_tipo_de_span_desconocido_no_se_exporta(monkeypatch):
    with pytest.raises(esquema.ErrorEsquema):
        _exportar([{"name": "x", "tipo": "volcado_completo", "attrs": {}}], monkeypatch=monkeypatch)


def test_cada_span_es_una_linea_json_y_no_se_filtra_el_token_de_tarea(monkeypatch):
    token = "AQAAAOzTOKENSECRETO123456789"
    attrs = dict(CHAT_OK, **{"lab.task_token": token})
    salida = []
    monkeypatch.setattr(esquema, "ESTRICTO", False)
    e = ExportadorSpans(escribir=salida.append)
    assert e.exportar([{"name": "chat a", "tipo": "chat", "attrs": attrs},
                       {"name": "chat b", "tipo": "chat", "attrs": CHAT_OK}]) == 2
    assert len(salida) == 2 and all(json.loads(l) for l in salida)
    assert token not in "".join(salida)
