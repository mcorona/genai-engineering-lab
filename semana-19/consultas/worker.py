"""Week 19, activity 6b: the agent Lambda's entry point. Runs the agent (agente.handler) for one question and stores the
answer in the table of consultas. A failure stores only the state 'error' in the table. For operators, the log gets the exception type and the trace
positions (file, line, function) only: never the exception message, the prompt or the answer.
"""
from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any, Callable

log = logging.getLogger(__name__)


def procesar(event: dict, *, correr: Callable, actualizar: Callable) -> dict:
    id_consulta = event["id"]
    try:
        res = correr({"claims": event["claims"], "pregunta": event["pregunta"], "token": event.get("token")})
        campos = {"estado": str(res["estado"]), "respuesta": str(res.get("respuesta") or ""),
                  "decisiones_json": json.dumps(res.get("decisiones") or [], ensure_ascii=False, default=str)}
    except Exception as error:  # noqa: BLE001 — every failure ends as 'error'
        campos = {"estado": "error", "respuesta": "", "decisiones_json": "[]"}
        posiciones = [f"{f.filename}:{f.lineno}:{f.name}" for f in traceback.extract_tb(error.__traceback__)]
        log.error("consulta %s fallida: %s en %s", id_consulta, type(error).__name__, " > ".join(posiciones[-6:]))
    actualizar(id_consulta, campos)
    return {"id": id_consulta, "estado": campos["estado"]}


def handler_lambda(event: dict, context: Any) -> dict:
    import boto3

    from agente import handler as agente_handler

    tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_CONSULTAS"])

    def actualizar(id_consulta: str, campos: dict) -> None:
        tabla.update_item(
            Key={"id": id_consulta},
            UpdateExpression="SET estado = :e, respuesta = :r, decisiones_json = :d",
            ExpressionAttributeValues={":e": campos["estado"], ":r": campos["respuesta"], ":d": campos["decisiones_json"]})

    return procesar(event, correr=lambda ev: agente_handler.handler(ev, context), actualizar=actualizar)
