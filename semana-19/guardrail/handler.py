"""Week 19, activity 5: custom resource that creates the Guardrail with its tier.

CloudFormation's AWS::Bedrock::Guardrail has no tierConfig, so the Guardrail is created here through the Bedrock
control plane (public endpoint, so this function runs outside the VPC). ResourceProperties are the definition of
definicion.py in the Bedrock API's own names, plus the name and the KMS key ARN. Output: GuardrailId and Version.
No secrets are logged or returned.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request

# boto3 and botocore are vendored at the version the tests validate against (the runtime's own boto3 is older and
# does not accept tierConfig on contextual grounding).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor"))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402

SIN_GUARDRAIL = "sin-id"  # physical id when the create failed before a guardrail existed


def _convertir_umbrales(valor):
    """CloudFormation passes every custom-resource value as text: thresholds go back to numbers."""
    if isinstance(valor, dict):
        return {k: (float(v) if k == "threshold" else _convertir_umbrales(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_convertir_umbrales(v) for v in valor]
    return valor


def _parametros(props: dict) -> dict:
    cuerpo = {k: v for k, v in props.items() if k != "ServiceToken"}
    return _convertir_umbrales(cuerpo)


def _responder(event, context, estado: str, datos: dict, id_fisico: str, motivo: str = "") -> None:
    registro = getattr(context, "log_stream_name", "sin-registro")
    cuerpo = json.dumps({
        "Status": estado,
        "Reason": motivo or f"Ver los logs de la función: {registro}",
        "PhysicalResourceId": id_fisico,
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "NoEcho": False,
        "Data": datos,
    }).encode("utf-8")
    peticion = urllib.request.Request(event["ResponseURL"], data=cuerpo, method="PUT",
                                      headers={"content-type": "", "content-length": str(len(cuerpo))})
    urllib.request.urlopen(peticion, timeout=30)  # noqa: S310 - the presigned CloudFormation URL


def handler(event, context):
    tipo = event["RequestType"]
    props = event.get("ResourceProperties", {})
    cliente = boto3.client("bedrock", config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}))
    id_previo = event.get("PhysicalResourceId", "sin-id")
    try:
        if tipo == "Create":
            gid = cliente.create_guardrail(**_parametros(props))["guardrailId"]
        elif tipo == "Update":
            gid = id_previo
            cliente.update_guardrail(guardrailIdentifier=gid, **_parametros(props))
        else:  # Delete
            if id_previo != SIN_GUARDRAIL and not id_previo.startswith("fallido"):
                try:
                    cliente.delete_guardrail(guardrailIdentifier=id_previo)
                except cliente.exceptions.ResourceNotFoundException:
                    pass
            _responder(event, context, "SUCCESS", {}, id_previo)
            return
        version = cliente.create_guardrail_version(guardrailIdentifier=gid, description="Version of the activity 5 stack")["version"]
        _responder(event, context, "SUCCESS", {"GuardrailId": gid, "Version": version}, gid)
    except Exception as error:  # noqa: BLE001 - every failure must answer CloudFormation or the stack hangs
        _responder(event, context, "FAILED", {}, id_previo, motivo=str(error)[:500])
