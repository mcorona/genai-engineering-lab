"""Week 19, activity 5: the guardrail custom resource, offline ($0). A fake Bedrock client; parameters are checked
against the Bedrock service model that botocore ships (the same validation the API applies to its shapes)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import botocore.session
from botocore.validate import ParamValidator

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19 / "guardrail"))


def _cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


H = _cargar("handler_guardrail", S19 / "guardrail" / "handler.py")
D = _cargar("definicion_guardrail", S19 / "guardrail" / "definicion.py")

MODELO = botocore.session.get_session().get_service_model("bedrock")
LLAVE = "arn:aws:kms:us-east-1:<account>:key/EJEMPLO"


def _props():
    # What CloudFormation sends: every value as text (thresholds included).
    como_texto = json.loads(json.dumps(D.definicion_guardrail("semana19-legacybridge")),
                            parse_float=str, parse_int=str)
    como_texto["kmsKeyId"] = LLAVE
    como_texto["ServiceToken"] = "arn:aws:lambda:us-east-1:<account>:function:x"
    return como_texto


def test_los_parametros_de_creacion_son_validos_para_la_api_de_bedrock():
    params = H._parametros(_props())
    forma = MODELO.operation_model("CreateGuardrail").input_shape
    errores = ParamValidator().validate(params, forma)
    assert not errores.has_errors(), errores.generate_report()
    assert "ServiceToken" not in params
    # Update takes the same definition minus the KMS key (checked against its own shape).
    sin_llave = {k: v for k, v in params.items() if k != "kmsKeyId"}
    forma_upd = MODELO.operation_model("UpdateGuardrail").input_shape
    assert not ParamValidator().validate({"guardrailIdentifier": "x", **sin_llave}, forma_upd).has_errors()
    umbrales = [f["threshold"] for f in params["contextualGroundingPolicyConfig"]["filtersConfig"]]
    assert umbrales and all(isinstance(u, float) for u in umbrales)


class _Excepciones:
    class ResourceNotFoundException(Exception):
        pass


class _Cliente:
    exceptions = _Excepciones

    def __init__(self):
        self.llamadas = []

    def create_guardrail(self, **kw):
        self.llamadas.append(("create_guardrail", kw))
        return {"guardrailId": "gid123"}

    def create_guardrail_version(self, **kw):
        self.llamadas.append(("create_guardrail_version", kw))
        return {"version": "1"}

    def delete_guardrail(self, **kw):
        self.llamadas.append(("delete_guardrail", kw))
        raise _Excepciones.ResourceNotFoundException()


class _Contexto:
    log_stream_name = "stream-de-prueba"


def _evento(tipo, **extra):
    return {"RequestType": tipo, "ResourceProperties": _props() if tipo != "Delete" else {},
            "ResponseURL": "https://cfn.example/presigned", "StackId": "stack", "RequestId": "req",
            "LogicalResourceId": "Guardrail", **extra}


def _capturar(monkeypatch):
    enviado = {}

    def fake_urlopen(peticion, timeout=None):
        enviado["cuerpo"] = json.loads(peticion.data.decode("utf-8"))

    monkeypatch.setattr(H.urllib.request, "urlopen", fake_urlopen)
    return enviado


def test_create_crea_el_guardrail_publica_una_version_y_responde_success(monkeypatch):
    cliente = _Cliente()
    monkeypatch.setattr(H.boto3, "client", lambda *a, **k: cliente)
    enviado = _capturar(monkeypatch)
    H.handler(_evento("Create"), _Contexto())
    nombres = [n for n, _ in cliente.llamadas]
    assert nombres == ["create_guardrail", "create_guardrail_version"]
    assert cliente.llamadas[1][1]["guardrailIdentifier"] == "gid123"
    assert enviado["cuerpo"]["Status"] == "SUCCESS"
    assert enviado["cuerpo"]["Data"] == {"GuardrailId": "gid123", "Version": "1"}


def test_delete_tolera_el_guardrail_ya_borrado_y_responde_success(monkeypatch):
    cliente = _Cliente()
    monkeypatch.setattr(H.boto3, "client", lambda *a, **k: cliente)
    enviado = _capturar(monkeypatch)
    H.handler(_evento("Delete", PhysicalResourceId="gid123"), _Contexto())
    assert enviado["cuerpo"]["Status"] == "SUCCESS"
    assert enviado["cuerpo"]["PhysicalResourceId"] == "gid123"


def test_un_fallo_responde_failed_para_que_cloudformation_no_se_quede_colgado(monkeypatch):
    class Roto(_Cliente):
        def create_guardrail(self, **kw):
            raise ValueError("boom")

    monkeypatch.setattr(H.boto3, "client", lambda *a, **k: Roto())
    enviado = _capturar(monkeypatch)
    H.handler(_evento("Create"), _Contexto())
    assert enviado["cuerpo"]["Status"] == "FAILED"
    assert "boom" in enviado["cuerpo"]["Reason"]
