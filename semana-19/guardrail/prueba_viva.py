"""Week 19, activity 5: live ApplyGuardrail check (no model generation).

Inputs: the first 10 Spanish and 10 English golden tasks (the CI subset) as legitimate inputs, and the malicious
description and note texts of the week 14 payload module as attack inputs. Prints the estimate first and aborts if it
exceeds the USD cap; then calls ApplyGuardrail once per text on the pinned version. Writes no account id.

Usage: prueba_viva.py [--si]   (default: estimate only, no AWS calls)
"""
from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]          # semana-19
REPO = Path(__file__).resolve().parents[2]         # repository root (semana-13 and semana-14 live here)
GUARDRAIL_ID = "teps1un80k04"                       # from the stack output IdGuardrail
VERSION = "3"                                       # from the stack output VersionGuardrail
PERFIL = "manuel-admin"
REGION = "us-east-1"
TOPE_USD = 5.0
PRECIO_UNIDAD_MAX = 0.00015                         # per 1000-char text unit per policy (upper bound from the Price List)
POLITICAS = 3                                       # content, topic, PII: upper bound for the estimate


def _golden(ruta: Path, n: int) -> list[tuple[str, str]]:
    filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(f["id"], f["tarea"]) for f in filas[:n]]


def _ataques() -> list[tuple[str, str]]:
    fuente = (REPO / "semana-14" / "ataques" / "malicioso.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    constantes = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id in {
                "DESC_CLIMA", "DESC_SQL_SOMBRA", "DESC_TC_INOCENTE", "DESC_TC_ENVENENADA", "NOTA_INYECTADA"}:
            constantes[nodo.targets[0].id] = eval(compile(ast.Expression(nodo.value), "<const>", "eval"), dict(constantes))
    return [(k, constantes[k]) for k in ("DESC_CLIMA", "DESC_SQL_SOMBRA", "DESC_TC_ENVENENADA", "NOTA_INYECTADA")]


def main(argv: list[str]) -> int:
    si = "--si" in argv
    golden = (_golden(REPO / "semana-13" / "golden" / "tareas_es.jsonl", 10)
              + _golden(REPO / "semana-13" / "golden" / "tareas_en.jsonl", 10))
    ataques = _ataques()
    entradas = [("golden", i, t) for i, t in golden] + [("ataque", i, t) for i, t in ataques]
    unidades = sum(math.ceil(len(t) / 1000) for _, _, t in entradas)
    estimado = unidades * POLITICAS * PRECIO_UNIDAD_MAX
    print(f"textos: {len(entradas)} (golden {len(golden)}, ataques {len(ataques)}); unidades: {unidades}")
    print(f"estimado (tope superior): {estimado:.5f} USD; tope: {TOPE_USD} USD")
    if estimado > TOPE_USD:
        print("ABORTA: la estimación supera el tope.", file=sys.stderr)
        return 2
    if not si:
        print("Solo estimación. Para llamar a ApplyGuardrail: --si")
        return 0
    import boto3
    cliente = boto3.Session(profile_name=PERFIL, region_name=REGION).client("bedrock-runtime")
    resultados = []
    for tipo, id_, texto in entradas:
        r = cliente.apply_guardrail(guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=VERSION, source="INPUT",
                                    content=[{"text": {"text": texto}}])
        resultados.append({"tipo": tipo, "id": id_, "accion": r["action"],
                           "evaluacion": r.get("assessments", []), "unidades": r.get("usage", {})})
        print(f"{tipo:7} {id_:18} {r['action']}")
    salida = LAB / "resultados" / "apply_guardrail.json"
    salida.write_text(json.dumps({"guardrail": GUARDRAIL_ID, "version": VERSION, "resultados": resultados},
                                 ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"guardado: {salida.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
