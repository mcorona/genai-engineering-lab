"""A bridge between processes: each framework runs in its own virtual environment (they pin incompatible versions of `mcp`,
`a2a-sdk` and `litellm`), and the orchestrator, the database and the verifier run in the main environment.

A JSON-lines protocol: the orchestrator writes {"tarea", "mcp_url", "token", "modelo", "esfuerzo", "base_url",
"limites", "opciones"} to the
worker's standard input; the worker answers {"resultado": {...}, "eventos": [...]} or {"error": "..."}.

    python -m arnes.puente trabajador <framework>      # inside the framework's environment
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
               "google_adk": "adaptadores.google_adk:AdaptadorGoogleADK",
               "multiagente": "adaptadores.multiagente:AdaptadorMultiagente"}
VENV = {"langgraph": "lg", "strands": "st", "openai_agents": "oa", "google_adk": "adk", "multiagente": "lg"}


def cargar(framework: str):
    mod, clase = ADAPTADORES[framework].split(":")
    return getattr(importlib.import_module(mod), clase)


def resolver_peticion(framework: str, pet: dict) -> dict:
    """A protocol request resolved in this process. Used by the worker and by the agent deployed on AgentCore
    (activity 8), so the input and output contract is the same locally and in the cloud."""
    from .contrato import resultado_a_dict, semana13
    try:
        lim = semana13().Limites(**pet["limites"]) if pet.get("limites") else None
        a = cargar(framework)(pet["mcp_url"], pet["token"], pet.get("modelo", "claude-haiku-5-5"), pet.get("esfuerzo", "low"),
                              limites=lim, base_url=pet.get("base_url"), **(pet.get("opciones") or {}))
        r = a.resolver(pet["tarea"])
        return {"resultado": resultado_a_dict(r), "eventos": getattr(a, "ultimas_trazas", []),
                "extra": {k: getattr(a, k) for k in ("pausas", "decisiones", "checkpoints", "propuestas", "especialistas")
                          if hasattr(a, k)}}
    except Exception as e:  # noqa: BLE001  the orchestrator decides; the worker does not die
        return {"error": f"{type(e).__name__}: {e}"[:2000]}


def trabajador(framework: str):
    cargar(framework)
    for linea in sys.stdin:
        if not linea.strip():
            continue
        out = resolver_peticion(framework, json.loads(linea))
        sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()


class Puente:
    """On the orchestrator's side: one worker process per framework, reused across tasks."""

    def __init__(self, framework: str, python: str | None = None, timeout_s: float = 600):
        venvs = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
        self.framework, self.timeout_s = framework, timeout_s
        self.cmd = [python or (str(venvs / VENV[framework] / "bin" / "python") if framework in VENV else sys.executable),
                    "-m", "arnes.puente", "trabajador", framework]
        self._arrancar()

    def _arrancar(self):
        # stderr to /dev/null: a worker that writes a lot to stderr must not block on a full buffer
        self.p = subprocess.Popen(self.cmd, cwd=S15, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=1, env={**os.environ, "PYTHONPATH": str(S15)})

    def resolver(self, **peticion) -> dict:
        """One task. If the worker does not answer within `timeout_s`, it is killed and restarted, and an error is returned."""
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
