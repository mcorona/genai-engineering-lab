#!/usr/bin/env python3
"""Week 19, activity 6b: builds the asset of the agent Lambda in semana-19/.build/agente (git-ignored).

The agent reuses the week 13 loop (semana-13/agente, with its own `herramientas`) and the week 17 budget and
instrumentation. Two packages named `agente` and `herramientas` cannot share a folder, so the week 13 copy goes under
s13/ and construccion.py finds it through S19_RUTA_SEMANA13. Dependencies are Linux wheels (the Lambda runtime).

Usage:
  python3 infra/paquete_agente.py                 # full asset, for cdk deploy (needs pip and network)
  python3 infra/paquete_agente.py --sin-dependencias   # layout only (offline tests; not deployable)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
DESTINO = S19 / ".build" / "agente"
COPIAS = {
    "agente": S19 / "agente",
    "herramientas": S19 / "herramientas",
    "consultas": S19 / "consultas",
    "presupuestos": RAIZ / "semana-17" / "presupuestos",
    "instrumentacion": RAIZ / "semana-17" / "instrumentacion",
    "s13/agente": RAIZ / "semana-13" / "agente",
    "s13/herramientas": RAIZ / "semana-13" / "herramientas",
}
# Locked in uv.lock (the lab's lock). Pure Python or manylinux wheels only.
DEPENDENCIAS = ["pydantic==2.14.1", "pydantic-core==2.50.1", "psycopg==3.3.6", "psycopg-binary==3.3.6", "sqlglot==30.26.0"]
IGNORAR = shutil.ignore_patterns("__pycache__", "tests", "*.pyc", "resultados")


def construir(sin_dependencias: bool = False) -> Path:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)
    for nombre, origen in COPIAS.items():
        if not origen.is_dir():
            raise FileNotFoundError(f"falta el paquete {origen}")
        shutil.copytree(origen, DESTINO / nombre, ignore=IGNORAR)
    if not sin_dependencias:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(DESTINO),
                        "--only-binary=:all:", "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
                        "--python-version", "3.13", "--implementation", "cp", *DEPENDENCIAS], check=True)
    return DESTINO


if __name__ == "__main__":
    ruta = construir(sin_dependencias="--sin-dependencias" in sys.argv)
    print(f"paquete listo: {ruta}")
