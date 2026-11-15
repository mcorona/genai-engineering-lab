"""Week 19, activity 5: the week 17 deterministic layer on the same texts as the live ApplyGuardrail check ($0, local).

Each text goes through the check that matches its channel: golden tasks and the injected note as user requests
(revisar_peticion), tool descriptions as tool definitions (revisar_definiciones). Reads the ApplyGuardrail results of
resultados/apply_guardrail.json and writes resultados/comparacion_determinista.json.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]              # semana-19
REPO = Path(__file__).resolve().parents[2]              # repository root
S17 = REPO / "semana-17"


def _cargar_nucleo():
    sys.path.insert(0, str(S17))                        # the week 17 package imports its own modules by name
    spec = importlib.util.spec_from_file_location("guardrails17", S17 / "guardrails" / "nucleo.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["guardrails17"] = modulo                # dataclasses looks the module up by name while it loads
    spec.loader.exec_module(modulo)
    return modulo


def _bloquea(decisiones) -> list[str]:
    return [f"{d.guardrail}:{d.motivo}" for d in decisiones if not d.permite]


def main() -> int:
    nucleo = _cargar_nucleo()
    base = json.loads((LAB / "resultados" / "apply_guardrail.json").read_text(encoding="utf-8"))
    tareas = {}
    for idioma in ("es", "en"):
        for linea in (REPO / "semana-13" / "golden" / f"tareas_{idioma}.jsonl").read_text(encoding="utf-8").splitlines()[:10]:
            if linea.strip():
                f = json.loads(linea)
                tareas[f["id"]] = f["tarea"]
    import ast
    fuente = (REPO / "semana-14" / "ataques" / "malicioso.py").read_text(encoding="utf-8")
    consts: dict = {}
    for nodo in ast.parse(fuente).body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id in {
                "DESC_CLIMA", "DESC_SQL_SOMBRA", "DESC_TC_INOCENTE", "DESC_TC_ENVENENADA", "NOTA_INYECTADA"}:
            consts[nodo.targets[0].id] = eval(compile(ast.Expression(nodo.value), "<c>", "eval"), dict(consts))

    filas = []
    for r in base["resultados"]:
        if r["tipo"] == "golden":
            decs = nucleo.revisar_peticion(tareas[r["id"]])
            canal = "peticion"
        elif r["id"] == "NOTA_INYECTADA":
            decs = nucleo.revisar_peticion(consts[r["id"]])
            canal = "peticion"
        else:
            _, _, decs = nucleo.revisar_definiciones([{"name": r["id"], "description": consts[r["id"]]}])
            canal = "definicion_de_herramienta"
        bloqueos = _bloquea(decs)
        filas.append({"tipo": r["tipo"], "id": r["id"], "canal": canal,
                      "guardrail_aws": r["accion"], "determinista": "BLOCK" if bloqueos else "ALLOW",
                      "motivos_deterministas": bloqueos})
    salida = {"version_guardrail": base["version"], "filas": filas}
    (LAB / "resultados" / "comparacion_determinista.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in filas:
        print(f"{f['tipo']:7} {f['id']:18} canal={f['canal']:24} aws={f['guardrail_aws']:21} det={f['determinista']:5} {f['motivos_deterministas']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
