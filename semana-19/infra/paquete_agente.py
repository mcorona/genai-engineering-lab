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
# Lambda layout: the code lives under app/, so every RAIZ computed from a file (parents[2]) resolves to /var/task, and the
# data of each week sits at the package root under the repository's own name (semana-13, semana-17, ...).
CODIGO = {
    "app/agente": S19 / "agente",
    "app/herramientas": S19 / "herramientas",
    "app/consultas": S19 / "consultas",
}
DATOS = {
    "semana-07": RAIZ / "semana-07",
    "semana-13": RAIZ / "semana-13",
    "semana-14": RAIZ / "semana-14",
    "semana-17/presupuestos": RAIZ / "semana-17" / "presupuestos",
    "semana-17/instrumentacion": RAIZ / "semana-17" / "instrumentacion",
    "semana-17/guardrails": RAIZ / "semana-17" / "guardrails",
    "semana-16/legacy-schema-audit": RAIZ / "semana-16" / "legacy-schema-audit",
    "semana-10/legado": RAIZ / "semana-10" / "legado",
}
# Locked in uv.lock (the lab's lock). Pure Python or manylinux wheels only.
DEPENDENCIAS = ["pydantic==2.14.1", "pydantic-core==2.50.1", "psycopg==3.3.6", "psycopg-binary==3.3.6", "sqlglot==30.26.0"]
IGNORAR = shutil.ignore_patterns("__pycache__", "tests", "*.pyc", "resultados", ".pytest_cache", "*.log")
SHIM_APP = (
    '"""Lambda layout (week 19, activity 6): this folder holds the lab\'s code so that RAIZ resolves to the package root.\n\n'
    'Importing app.<package> puts this folder on sys.path, so `from agente import ...` works inside it."""\n'
    "import sys as _sys\n"
    "from pathlib import Path as _Path\n\n"
    "_aqui = str(_Path(__file__).resolve().parent)\n"
    "if _aqui not in _sys.path:\n"
    "    _sys.path.insert(0, _aqui)\n"
)


def construir(sin_dependencias: bool = False) -> Path:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)
    for nombre, origen in {**CODIGO, **DATOS}.items():
        if not origen.is_dir():
            raise FileNotFoundError(f"falta {origen}")
        shutil.copytree(origen, DESTINO / nombre, ignore=IGNORAR)
    (DESTINO / "app" / "__init__.py").write_text(SHIM_APP, encoding="utf-8")
    if not (DESTINO / "semana-07" / "prices.json").is_file():
        raise FileNotFoundError("falta semana-07/prices.json en el paquete")
    if not sin_dependencias:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(DESTINO),
                        "--only-binary=:all:", "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
                        "--python-version", "3.13", "--implementation", "cp", *DEPENDENCIAS], check=True)
    return DESTINO


if __name__ == "__main__":
    ruta = construir(sin_dependencias="--sin-dependencias" in sys.argv)
    print(f"paquete listo: {ruta}")
