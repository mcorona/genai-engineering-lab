"""Puente entre procesos: cada framework corre en su propio entorno virtual (fijan versiones incompatibles de `mcp`,
`a2a-sdk` y `litellm`), y el orquestador, la base y el verificador en el entorno principal.

Protocolo por líneas JSON: el orquestador escribe {"tarea", "mcp_url", "token", "modelo", "esfuerzo", "base_url"} en la
entrada estándar del trabajador; el trabajador responde {"resultado": {...}, "eventos": [...]} o {"error": "..."}.

    python -m arnes.puente trabajador <framework>      # dentro del entorno del framework
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
ADAPTADORES = {"propio": "arnes.adaptador:AdaptadorPropio",
               "langgraph": "adaptadores.langgraph:AdaptadorLangGraph",
               "strands": "adaptadores.strands:AdaptadorStrands"}
VENV = {"langgraph": "lg", "strands": "st", "openai_agents": "oa", "google_adk": "adk"}


def cargar(framework: str):
    mod, clase = ADAPTADORES[framework].split(":")
    return getattr(importlib.import_module(mod), clase)


def trabajador(framework: str):
    from .contrato import resultado_a_dict
    clase = cargar(framework)
    for linea in sys.stdin:
        if not linea.strip():
            continue
        pet = json.loads(linea)
        try:
            a = clase(pet["mcp_url"], pet["token"], pet.get("modelo", "claude-haiku-5-5"), pet.get("esfuerzo", "low"),
                      base_url=pet.get("base_url"))
            r = a.resolver(pet["tarea"])
            out = {"resultado": resultado_a_dict(r), "eventos": getattr(a, "ultimas_trazas", [])}
        except Exception as e:  # noqa: BLE001  el orquestador decide; el trabajador no muere
            out = {"error": f"{type(e).__name__}: {e}"[:2000]}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()


class Puente:
    """Del lado del orquestador: un proceso trabajador por framework, reutilizado entre tareas."""

    def __init__(self, framework: str, python: str | None = None):
        venvs = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
        py = python or (str(venvs / VENV[framework] / "bin" / "python") if framework in VENV else sys.executable)
        self.p = subprocess.Popen([py, "-m", "arnes.puente", "trabajador", framework], cwd=S15, text=True,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1,
                                  env={**os.environ, "PYTHONPATH": str(S15)})

    def resolver(self, **peticion) -> dict:
        self.p.stdin.write(json.dumps(peticion, ensure_ascii=False, default=str) + "\n")
        self.p.stdin.flush()
        linea = self.p.stdout.readline()
        if not linea:
            raise RuntimeError("el trabajador terminó: " + self.p.stderr.read()[-1500:])
        return json.loads(linea)

    def cerrar(self):
        self.p.stdin.close()
        self.p.wait(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "trabajador":
    trabajador(sys.argv[2])
