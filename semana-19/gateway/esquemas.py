"""Week 19, activity 7: the gateway target's tool schemas, projected from the loop's own definitions (one source).

The source is agente/capa_determinista.definiciones_semana19(): the schemas the loop gives the model. A gateway
target's schema accepts only type, description, properties, required and items for each property
(bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html, read 2026-11-18), so the projection drops the
rest (pattern, minimum, maximum, minLength, maxLength, additionalProperties). Those checks do not disappear: the
deterministic layer validates the full schema before the call leaves the agent, and the tools Lambda validates the
proposal again (agente/escritor_orden.validar_propuesta).

One declared difference: proponer_orden_compra gains `solicitante`, required. The agent Lambda sets it to the
token's subject, never the model, and the gateway's Cedar policy allows the call only when it equals the caller's
`sub` (gateway/politicas/proponer.cedar).

`python -m gateway.esquemas` (from semana-19/) rewrites gateway/herramientas.json, the file the CDK synth reads
(the CDK environment does not load the agent's dependencies). A test compares that file with this projection.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
ARCHIVO = Path(__file__).resolve().parent / "herramientas.json"
CLAVES = ("type", "description", "properties", "required", "items")
DESCRIPCION_SOLICITANTE = ("Requester: the subject (sub) of the verified token, set by the agent Lambda, never by the "
                           "model. The gateway's policy allows the call only when it is the caller's own sub.")


def proyectar(esquema: dict) -> dict:
    """The supported keys only. An optional field written as anyOf [X, null] (pydantic's form for `X | None`) becomes X:
    being optional is already said by its absence from `required`. Any other anyOf has no projection and fails."""
    if "anyOf" in esquema and "type" not in esquema:
        ramas = [r for r in esquema["anyOf"] if r.get("type") != "null"]
        if len(ramas) != 1:
            raise ValueError("anyOf sin una única rama no nula: no hay proyección para el gateway")
        esquema = {**ramas[0], **{k: v for k, v in esquema.items() if k == "description"}}
    salida = {}
    for clave in CLAVES:
        if clave not in esquema:
            continue
        valor = esquema[clave]
        if clave == "properties":
            valor = {n: proyectar(p) for n, p in valor.items()}
        elif clave == "items":
            valor = proyectar(valor)
        salida[clave] = valor
    return salida


def definiciones_gateway(definiciones: list[dict]) -> list[dict]:
    salida = []
    for d in definiciones:
        entrada = proyectar(d["input_schema"])
        if d["name"] == "proponer_orden_compra":
            entrada["properties"]["solicitante"] = {"type": "string", "description": DESCRIPCION_SOLICITANTE}
            entrada["required"] = [*entrada.get("required", []), "solicitante"]
        salida.append({"name": d["name"], "description": d["description"], "inputSchema": entrada})
    return salida


def desde_el_bucle() -> list[dict]:
    if str(S19) not in sys.path:
        sys.path.insert(0, str(S19))
    from agente import capa_determinista as C
    return definiciones_gateway(C.definiciones_semana19())


def escribir() -> None:
    ARCHIVO.write_text(json.dumps(desde_el_bucle(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def leer() -> list[dict]:
    return json.loads(ARCHIVO.read_text(encoding="utf-8"))


if __name__ == "__main__":
    escribir()
    print(f"{ARCHIVO.name}: {[d['name'] for d in leer()]}")
