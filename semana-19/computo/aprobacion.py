"""Week 19, activity 6: the approval step's Lambdas (the task token never reaches a log or a response, ADR 0011).

registrar: receives the task token from Step Functions (waitForTaskToken) after the pending order was written, and
  stores it in DynamoDB (encrypted with the stack key, with a TTL) with what the decision is checked against: the
  order id, its required level (computed by the database) and the requester. It returns only the request id.
aprobar: the approver's call (POST /aprobaciones/{id}, body {"decision": "aprobar"|"rechazar", "motivo": str}).
  The approver's identity and level come from the token claims the authorizer verified, never from the body:
    - the requester cannot decide their own order (separation of duties);
    - approving needs a level at least the order's required level (the database checks it again);
    - rejecting needs a reason (the policy records it); any approval level may reject.
  The decision goes to Step Functions with SendTaskSuccess (approval and rejection alike: the workflow's next state
  writes it), then the row is deleted. Clients are injected; the deployed ones are built in the handler.
"""
from __future__ import annotations

import json
import os
import time

TTL_SEGUNDOS = 24 * 3600      # the wait of the state machine is shorter than this (see the stack)
RANGO = {"comprador": 1, "gerente": 2, "director": 3}   # computo/tokens.py and po_level_rank in the database
CLAIM_NIVEL = "nivel_aprobacion"
# Step Functions errors for a token that was already used or whose wait ended (botocore names the exception classes so).
TOKEN_YA_USADO = frozenset({"TaskTimedOut", "TaskDoesNotExist", "InvalidToken"})


def registrar(evento: dict, tabla, ahora=time.time) -> dict:
    """evento = {"id", "token", "orden": {"po_id", "nivel_requerido", ...}, "solicitud": {"solicitante", ...}}.
    Returns {"id": ...}; the token is not returned."""
    if not isinstance(evento.get("id"), str) or not evento.get("token"):
        raise ValueError("falta el id o el token de tarea")
    orden, solicitud = evento.get("orden") or {}, evento.get("solicitud") or {}
    if not isinstance(orden.get("po_id"), int) or orden.get("nivel_requerido") not in RANGO \
            or not isinstance(solicitud.get("solicitante"), str) or not solicitud["solicitante"]:
        raise ValueError("faltan la orden pendiente o quien la pidió")
    tabla.put_item(Item={"id": evento["id"], "token": evento["token"], "expira": int(ahora()) + TTL_SEGUNDOS,
                         "estado": "pendiente", "po_id": orden["po_id"], "nivel_requerido": orden["nivel_requerido"],
                         "solicitante": solicitud["solicitante"]})
    return {"id": evento["id"]}


def aprobar(id_solicitud: str, decision: str, tabla, sfn, *, aprobador: str, nivel: str | None, motivo=None,
            ahora=time.time) -> dict:
    """aprobador and nivel come from the verified token. Returns {"estado": ...}; a refusal sends nothing."""
    if decision not in ("aprobar", "rechazar"):
        raise ValueError("decision debe ser aprobar o rechazar")
    if decision == "rechazar" and not (isinstance(motivo, str) and 1 <= len(motivo.strip()) <= 200):
        raise ValueError("rechazar requiere un motivo de 1 a 200 caracteres")
    if not aprobador or nivel not in RANGO:
        return {"estado": "sin_nivel_de_aprobacion"}
    fila = tabla.get_item(Key={"id": id_solicitud}).get("Item")
    if not fila or int(fila.get("expira", 0)) < int(ahora()):
        return {"estado": "no_encontrada"}
    if fila.get("solicitante") == aprobador:
        return {"estado": "misma_persona"}
    if decision == "aprobar" and RANGO[nivel] < RANGO.get(fila.get("nivel_requerido"), 99):
        return {"estado": "nivel_insuficiente", "nivel_requerido": fila.get("nivel_requerido")}
    salida = {"decision": decision, "decidido_por": aprobador, "nivel": nivel}
    if decision == "rechazar":
        salida["nota"] = motivo.strip()
    try:
        sfn.send_task_success(taskToken=fila["token"], output=json.dumps(salida, sort_keys=True))
    except Exception as error:  # noqa: BLE001 - only the "token no longer valid" errors are answered, the rest raise
        if type(error).__name__ not in TOKEN_YA_USADO:
            raise
        tabla.delete_item(Key={"id": id_solicitud})   # decided by someone else, or the wait ended
        return {"estado": "no_encontrada"}
    tabla.delete_item(Key={"id": id_solicitud})
    return {"estado": "aprobada" if decision == "aprobar" else "rechazada"}


ESTADO_HTTP = {"aprobada": 200, "rechazada": 200, "no_encontrada": 404, "sin_nivel_de_aprobacion": 403,
               "misma_persona": 403, "nivel_insuficiente": 403}


def handler_registrar(event, context):
    import boto3  # provided by the Lambda runtime
    tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_TOKENS"])
    return registrar(event, tabla)


def _claims(event) -> dict:
    return (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}


def handler_aprobar(event, context, *, tabla=None, sfn=None):
    if tabla is None or sfn is None:
        import boto3
        tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_TOKENS"])
        sfn = boto3.client("stepfunctions")
    try:
        cuerpo = json.loads(event.get("body") or "{}")
    except ValueError:
        return {"statusCode": 400, "body": json.dumps({"error": "cuerpo_invalido"})}
    cuerpo = cuerpo if isinstance(cuerpo, dict) else {}
    claims = _claims(event)
    id_solicitud = (event.get("pathParameters") or {}).get("id", "")
    try:
        res = aprobar(id_solicitud, cuerpo.get("decision", ""), tabla, sfn, aprobador=str(claims.get("sub") or ""),
                      nivel=claims.get(CLAIM_NIVEL), motivo=cuerpo.get("motivo"))
    except ValueError:
        return {"statusCode": 400, "body": json.dumps({"error": "decision_invalida"})}
    return {"statusCode": ESTADO_HTTP[res["estado"]], "body": json.dumps(res)}
