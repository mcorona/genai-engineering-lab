"""Week 19, activity 6: the tools Lambda binds its real collaborators from the environment, offline ($0, no AWS).

The connection and the state machine client are fakes. Missing environment fails before any client exists; the
database user is copilot_ro only; the starter sends the proposed order as the workflow input with a fresh request id.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from herramientas import construccion as C  # noqa: E402

ENTORNO = {"HOST_BD": "bd.ejemplo.internal", "ARN_APROBACION": "arn:aws:states:us-east-1:111111111111:stateMachine:x",
           "AWS_REGION": "us-east-1"}


def test_falta_entorno_falla_antes_de_crear_clientes(monkeypatch):
    creados = []
    monkeypatch.setattr(C, "conectar_real", lambda *a, **k: creados.append("conexion"))
    with pytest.raises(RuntimeError, match="ARN_APROBACION"):
        C.construir({"HOST_BD": "h", "AWS_REGION": "us-east-1"})
    assert creados == []


def test_entorno_completo_construye_los_dos_colaboradores():
    deps = C.construir(ENTORNO)
    assert set(deps) == {"conectar", "iniciar"} and callable(deps["conectar"]) and callable(deps["iniciar"])


def test_conexion_usa_solo_copilot_ro_con_token_iam_y_tls(monkeypatch):
    capturado = {}

    class Conexion:
        def __init__(self, usuario, **kw):
            capturado.update(usuario=usuario, **kw)

    falso = types.SimpleNamespace(Connection=Conexion)
    monkeypatch.setitem(sys.modules, "pg8000", types.SimpleNamespace(native=falso))
    monkeypatch.setitem(sys.modules, "pg8000.native", falso)
    generar = lambda **kw: "token-de-prueba"  # noqa: E731
    C.conectar_real("bd.ejemplo.internal", "us-east-1", generar=generar)
    assert capturado["usuario"] == "copilot_ro"
    assert capturado["password"] == "token-de-prueba"
    assert capturado["ssl_context"] is not None
    assert "token" not in json.dumps({k: v for k, v in capturado.items() if k in ("usuario", "host", "port")})


def test_iniciar_envia_la_orden_como_entrada_del_flujo():
    enviados = []

    class Cliente:
        def start_execution(self, **kw):
            enviados.append(kw)

    iniciar = C.iniciar_real(ENTORNO["ARN_APROBACION"], cliente=Cliente())
    id_solicitud = iniciar(json.dumps({"sku": "SKU-0001", "cantidad": 3, "motivo": "reposicion"}))
    (llamada,) = enviados
    assert llamada["name"] == id_solicitud
    entrada = json.loads(llamada["input"])
    assert entrada["id"] == id_solicitud
    assert entrada["solicitud"] == {"sku": "SKU-0001", "cantidad": 3, "motivo": "reposicion"}
