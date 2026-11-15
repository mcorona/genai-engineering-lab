"""Builds the agent's CodeZip package for AgentCore Runtime (ARM64, Python 3.13) in `build/agente.zip`.

    python agentcore/empaquetar.py            # from semana-15; needs uv and access to PyPI ($0)

Contents: `main.py` at the root, the week 15 code the agent uses (arnes and the Strands adapter), the
week 13 contract (agente/loop.py and agente/respuesta.py) and the dependencies installed for linux/aarch64.
It includes no keys, no `.env`, no tests and none of the rest of the repository: `--revisar` lists the contents and fails if
anything that looks like a secret appears.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S15 = AQUI.parent
S13 = S15.parent / "semana-13"
BUILD = AQUI / "build"
ZIP = BUILD / "agente.zip"
CODIGO = [  # (source, destination inside the zip)
    (AQUI / "main.py", "main.py"),
    (S15 / "arnes" / "__init__.py", "semana-15/arnes/__init__.py"),
    (S15 / "arnes" / "adaptador.py", "semana-15/arnes/adaptador.py"),
    (S15 / "arnes" / "contrato.py", "semana-15/arnes/contrato.py"),
    (S15 / "arnes" / "puente.py", "semana-15/arnes/puente.py"),
    (S15 / "arnes" / "trazas.py", "semana-15/arnes/trazas.py"),
    (S15 / "adaptadores" / "__init__.py", "semana-15/adaptadores/__init__.py"),
    (S15 / "adaptadores" / "strands.py", "semana-15/adaptadores/strands.py"),
    (S13 / "agente" / "__init__.py", "semana-13/agente/__init__.py"),
    (S13 / "agente" / "loop.py", "semana-13/agente/loop.py"),
    (S13 / "agente" / "respuesta.py", "semana-13/agente/respuesta.py"),
    (S15.parent / "semana-07" / "prices.json", "semana-07/prices.json"),   # the price table that loop.py reads
]
PROHIBIDOS = (".env", "secretos", ".pem", "credentials", "id_rsa")


def dependencias(destino: Path) -> None:
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(destino), "--python-version", "3.13",
                    "--python-platform", "aarch64-manylinux_2_28", "--only-binary", ":all:",
                    "-r", str(AQUI / "requisitos_runtime.txt")], check=True)


def armar(sin_dependencias: bool = False) -> Path:
    shutil.rmtree(BUILD, ignore_errors=True)
    deps = BUILD / "deps"
    deps.mkdir(parents=True)
    if not sin_dependencias:
        dependencias(deps)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for origen, destino in CODIGO:
            z.write(origen, destino)
        for f in sorted(deps.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(deps).as_posix())
    return ZIP


def revisar(ruta: Path = ZIP) -> list[str]:
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
    malos = [n for n in nombres if any(p in n.lower() for p in PROHIBIDOS) and not n.endswith(".py")
             and "dist-info" not in n and not n.endswith("cacert.pem")]   # cacert.pem: public CA certificates
    for origen, destino in CODIGO:
        if destino not in nombres:
            malos.append(f"falta {destino}")
    return malos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-dependencias", action="store_true", help="only the in-house code (tests)")
    a = ap.parse_args(argv)
    ruta = armar(a.sin_dependencias)
    malos = revisar(ruta)
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    print(f"{ruta}  {ruta.stat().st_size / 1e6:.1f} MB  sha256 {sha[:16]}…  own files {len(CODIGO)}")
    if malos:
        print("REVISAR:", *malos, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
