"""Week 19, activity 6: the approval step's Lambdas (the task token never reaches a log or a response, ADR 0011).

registrar: receives the task token from Step Functions (waitForTaskToken) and stores it in DynamoDB, encrypted with the
  stack key, with a TTL. It returns only the request id.
aprobar: the approver's call (POST /aprobaciones/{id}). It reads the token, sends the decision to Step Functions with
  SendTaskSuccess (or SendTaskFailure on rejection) and deletes the row. Clients are injected; the deployed ones are
  built in the handler from the environment.
"""
from __future__ import annotations

import os
import time

TTL_SEGUNDOS = 24 * 3600      # the wait of the state machine is shorter than this (see the stack)


def registrar(evento: dict, tabla, ahora=time.time) -> dict:
    """evento = {"id": str, "token": str, "solicitud": {...}}. Returns {"id": ...}; the token is not returned."""
    if not isinstance(evento.get("id"), str) or not evento.get("token"):
        raise ValueError("falta el id o el token de tarea")
    tabla.put_item(Item={"id": evento["id"], "token": evento["token"], "expira": int(ahora()) + TTL_SEGUNDOS,
                           "estado": "pendiente"})
    return {"id": evento["id"]}


def aprobar(id_solicitud: str, decision: str, tabla, sfn, ahora=time.time) -> dict:
    """decision is 'aprobar' or 'rechazar'. A row that is missing or expired is not an error to reveal details about."""
    if decision not in ("aprobar", "rechazar"):
        raise ValueError("decision debe ser aprobar o rechazar")
    fila = tabla.get_item(Key={"id": id_solicitud}).get("Item")
    if not fila or int(fila.get("expira", 0)) < int(ahora()):
        return {"estado": "no_encontrada"}
    if decision == "aprobar":
        sfn.send_task_success(taskToken=fila["token"], output='{"decision": "aprobada"}')
    else:
        sfn.send_task_failure(taskToken=fila["token"], error="RechazadaPorAprobador", cause="rechazada")
    tabla.delete_item(Key={"id": id_solicitud})
    return {"estado": "aprobada" if decision == "aprobar" else "rechazada"}


def handler_registrar(event, context):
    import boto3  # provided by the Lambda runtime
    tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_TOKENS"])
    return registrar(event, tabla)


def handler_aprobar(event, context):
    import json

    import boto3
    tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_TOKENS"])
    sfn = boto3.client("stepfunctions")
    cuerpo = json.loads(event.get("body") or "{}")
    id_solicitud = (event.get("pathParameters") or {}).get("id", "")
    res = aprobar(id_solicitud, cuerpo.get("decision", ""), tabla, sfn)
    return {"statusCode": 200, "body": json.dumps(res)}
