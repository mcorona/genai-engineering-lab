"""Puente entre procesos: cada framework corre en su propio entorno virtual (fijan versiones incompatibles de `mcp`,
`a2a-sdk` y `litellm`), y el orquestador, la base y el verificador en el entorno principal.

Protocolo por líneas JSON: el orquestador escribe {"tarea", "mcp_url", "token", "modelo", "esfuerzo", "base_url",
"limites", "opciones"} en la
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
               "strands": "adaptadores.strands:AdaptadorStrands",
               "openai_agents": "adaptadores.openai_agents:AdaptadorOpenAIAgents",
               "google_adk": "adaptadores.google_adk:AdaptadorGoogleADK"}
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
            from .contrato import semana13
            lim = semana13().Limites(**pet["limites"]) if pet.get("limites") else None
            a = clase(pet["mcp_url"], pet["token"], pet.get("modelo", "claude-haiku-5-5"), pet.get("esfuerzo", "low"),
                      limites=lim, base_url=pet.get("base_url"), **(pet.get("opciones") or {}))
            r = a.resolver(pet["tarea"])
            out = {"resultado": resultado_a_dict(r), "eventos": getattr(a, "ultimas_trazas", []),
                   "extra": {k: getattr(a, k) for k in ("pausas", "decisiones", "checkpoints") if hasattr(a, k)}}
        except Exception as e:  # noqa: BLE001  el orquestador decide; el trabajador no muere
            out = {"error": f"{type(e).__name__}: {e}"[:2000]}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()


class Puente:
    """Del lado del orquestador: un proceso trabajador por framework, reutilizado entre tareas."""

    def __init__(self, framework: str, python: str | None = None, timeout_s: float = 600):
        venvs = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
        self.framework, self.timeout_s = framework, timeout_s
        self.cmd = [python or (str(venvs / VENV[framework] / "bin" / "python") if framework in VENV else sys.executable),
                    "-m", "arnes.puente", "trabajador", framework]
        self._arrancar()

    def _arrancar(self):
        # stderr a /dev/null: un trabajador que escribe mucho en stderr no debe bloquearse con el buffer lleno
        self.p = subprocess.Popen(self.cmd, cwd=S15, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=1, env={**os.environ, "PYTHONPATH": str(S15)})

    def resolver(self, **peticion) -> dict:
        """Una tarea. Si el trabajador no responde en `timeout_s`, se mata y se reinicia, y se devuelve un error."""
        import select
        self.p.stdin.write(json.dumps(peticion, ensure_ascii=False, default=str) + "\n")
        self.p.stdin.flush()
        listos, _, _ = select.select([self.p.stdout], [], [], self.timeout_s)
        if not listos:
            self.p.kill()
            self.p.wait()
            self._arrancar()
            return {"error": f"timeout_trabajador: sin respuesta en {self.timeout_s:.0f} s"}
        linea = self.p.stdout.readline()
        if not linea:
            self._arrancar()
            return {"error": "el trabajador terminó sin responder"}
        return json.loads(linea)

    def cerrar(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()


if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "trabajador":
    trabajador(sys.argv[2])
