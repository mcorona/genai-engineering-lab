"""Week 19, activity 6b: POST /consultas and GET /consultas/{id}, behind the HTTP API's JWT authorizer.

The authorizer has already checked the token and its scope. The question is stored with a hash of the subject (never the
token or the subject), the agent starts asynchronously, and the answer is 202. Only the owner reads the answer: another
subject gets the same 404 as a missing id, so ids cannot be probed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from typing import Any, Callable

MAX_PREGUNTA = 1000
VIGENCIA_SEGUNDOS = 7 * 24 * 3600
CAMPOS_PUBLICOS = ("id", "estado", "respuesta")


def dueno_de(claims: dict) -> str:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise PermissionError("el token no trae sujeto")
    return hashlib.sha256(sub.encode("utf-8")).hexdigest()


def _respuesta(status: int, cuerpo: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(cuerpo, ensure_ascii=False)}


def _claims(event: dict) -> dict:
    return event["requestContext"]["authorizer"]["jwt"]["claims"]


def _cuerpo(event: dict) -> Any:
    crudo = event.get("body") or ""
    if event.get("isBase64Encoded"):
        crudo = base64.b64decode(crudo).decode("utf-8")
    return json.loads(crudo)


def crear(event: dict, *, guardar: Callable, invocar: Callable, actualizar: Callable,
          ahora: Callable = time.time, nuevo_id: Callable = lambda: str(uuid.uuid4())) -> dict:
    try:
        claims = _claims(event)
        dueno = dueno_de(claims)
    except (KeyError, TypeError, PermissionError):
        return _respuesta(401, {"error": "no_autorizado"})
    try:
        cuerpo = _cuerpo(event)
    except (ValueError, UnicodeDecodeError):
        return _respuesta(400, {"error": "cuerpo_invalido"})
    pregunta = cuerpo.get("pregunta") if isinstance(cuerpo, dict) else None
    if not isinstance(pregunta, str) or not 1 <= len(pregunta.strip()) <= MAX_PREGUNTA:
        return _respuesta(400, {"error": "pregunta_invalida"})
    id_consulta = nuevo_id()
    marca = int(ahora())
    guardar({"id": id_consulta, "dueno": dueno, "estado": "en_curso", "creada": marca, "expira": marca + VIGENCIA_SEGUNDOS})
    try:
        invocar({"id": id_consulta, "claims": claims, "pregunta": pregunta.strip()})
    except Exception:  # noqa: BLE001 — the start failed: the question ends as 'error', with no detail stored
        actualizar(id_consulta, "error")
        return _respuesta(503, {"error": "no_disponible"})
    return _respuesta(202, {"id": id_consulta, "estado": "en_curso"})


def leer(event: dict, *, obtener: Callable) -> dict:
    try:
        dueno = dueno_de(_claims(event))
    except (KeyError, TypeError, PermissionError):
        return _respuesta(401, {"error": "no_autorizado"})
    id_consulta = (event.get("pathParameters") or {}).get("id") or ""
    item = obtener(id_consulta) if id_consulta else None
    if not item or item.get("dueno") != dueno:
        return _respuesta(404, {"error": "no_encontrada"})
    publico = {k: item[k] for k in CAMPOS_PUBLICOS if k in item}
    publico["decisiones"] = json.loads(item.get("decisiones_json") or "[]")
    return _respuesta(200, publico)


def manejar(event: dict, *, guardar: Callable, obtener: Callable, invocar: Callable, actualizar: Callable,
            ahora: Callable = time.time, nuevo_id: Callable = lambda: str(uuid.uuid4())) -> dict:
    ruta = event.get("routeKey")
    if ruta == "POST /consultas":
        return crear(event, guardar=guardar, invocar=invocar, actualizar=actualizar, ahora=ahora, nuevo_id=nuevo_id)
    if ruta == "GET /consultas/{id}":
        return leer(event, obtener=obtener)
    return _respuesta(404, {"error": "ruta_desconocida"})


def handler_lambda(event: dict, context: Any) -> dict:
    import boto3

    tabla = boto3.resource("dynamodb").Table(os.environ["TABLA_CONSULTAS"])
    lam = boto3.client("lambda")
    agente = os.environ["FUNCION_AGENTE"]

    def guardar(item: dict) -> None:
        tabla.put_item(Item=item)

    def obtener(id_consulta: str):
        return tabla.get_item(Key={"id": id_consulta}).get("Item")

    def invocar(payload: dict) -> None:
        lam.invoke(FunctionName=agente, InvocationType="Event", Payload=json.dumps(payload).encode("utf-8"))

    def actualizar(id_consulta: str, estado: str) -> None:
        tabla.update_item(Key={"id": id_consulta}, UpdateExpression="SET estado = :e",
                          ExpressionAttributeValues={":e": estado})

    return manejar(event, guardar=guardar, obtener=obtener, invocar=invocar, actualizar=actualizar)
