"""Week 19, preparation: readiness check that costs $0 and prints no secret.

Checks the tools and their versions, the AWS profiles (admin and operator) with an active session, the account and
region through STS (the account is printed masked as <account>), the week 13 data that the week 19 evals reuse, and
the CI paths that make the required check `regresion` run this week.

    uv run --group semana19 python semana-19/preparar/verificar_entorno.py --admin <perfil> --operador <perfil>   # Mac
    uv run --group semana19 python semana-19/preparar/verificar_entorno.py --ci                                  # CI, no AWS

Modes:
- Mac (default): tools, profiles, STS, data and CI paths. Requires --admin and --operador to check the sessions.
- --ci: no AWS and no tools beyond Python. It checks the data, the pins installed for the group and the CI paths.

It writes nothing outside stdout and exits with 1 if a required check fails. Profile names are printed; keys, tokens
and the account ID never are.
"""
from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib.metadata as md
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S19 = AQUI.parent
RAIZ = S19.parent
V = json.loads((AQUI / "versiones.json").read_text(encoding="utf-8"))
REGION = "us-east-1"
FECHA = date.today().isoformat()


def correr(args: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)[:200]
    return r.returncode, (r.stdout + r.stderr).strip()


def version_de(herramienta: str, args: list[str], patron: str) -> dict:
    ruta = shutil.which(herramienta)
    if not ruta:
        return {"instalada": None, "ruta": None, "fecha": FECHA}
    _, salida = correr([herramienta, *args])
    m = re.search(patron, salida)
    # The path is reported relative to ~ so the home directory never appears in a result.
    return {"instalada": m.group(1) if m else salida.splitlines()[0][:80] if salida else None,
            "ruta": ruta.replace(str(Path.home()), "~"), "fecha": FECHA}


def paquetes_python() -> dict:
    instalado = {}
    for paquete, esperado in V["python"].items():
        try:
            version = md.version(paquete)
        except md.PackageNotFoundError:
            version = None
        instalado[paquete] = {"esperado": esperado, "instalado": version, "ok": version == esperado}
    return instalado


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def datos_semana13() -> dict:
    manifiesto = RAIZ / "semana-13" / "golden" / "manifiesto.json"
    resultado = {}
    for nombre in ("semana-07/ci/preparar_base.py", "semana-10/legado/legado.sql",
                   "semana-13/seguridad/artnot.sql", "semana-13/golden/manifiesto.json",
                   "semana-13/golden/tareas_es.jsonl", "semana-13/golden/tareas_en.jsonl"):
        resultado[nombre] = (RAIZ / nombre).exists()
    if manifiesto.exists():
        datos = json.loads(manifiesto.read_text(encoding="utf-8"))
        hashes = datos.get("sha256", {})
        for archivo in ("tareas_es.jsonl", "tareas_en.jsonl"):
            ruta = RAIZ / "semana-13" / "golden" / archivo
            clave = f"sha256_{archivo}"
            resultado[clave] = bool(ruta.exists() and hashes.get(archivo) == sha256(ruta))
    else:
        resultado["sha256_tareas"] = False
    return {"archivos": resultado, "ok": all(resultado.values())}


def rutas_ci() -> dict:
    flujo = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    eval19 = RAIZ / ".github" / "workflows" / "eval-semana-19.yml"
    return {
        "semana-19 en regresion": '"semana-19/**"' in flujo,
        "job regresion presente": re.search(r"^  regresion:", flujo, re.M) is not None,
        "eval-semana-19.yml existe": eval19.exists(),
        "eval-semana-19 sin AWS": eval19.exists() and not re.search(
            r"aws-actions|AWS_|aws configure|aws sts|aws login|boto3\.client", eval19.read_text(encoding="utf-8")),
    }


def perfiles_configurados() -> list[str]:
    cfg = configparser.ConfigParser()
    cfg.read([Path.home() / ".aws" / "config", Path.home() / ".aws" / "credentials"])
    # In ~/.aws/config the sections are "[profile X]" (and "[default]"); in ~/.aws/credentials they are "[X]".
    nombres = {s.removeprefix("profile ").strip() for s in cfg.sections()}
    return sorted(n for n in nombres if n)


def sesion(perfil: str) -> dict:
    code, salida = correr(["aws", "sts", "get-caller-identity", "--profile", perfil,
                           "--region", REGION, "--output", "json"], timeout=60)
    if code:
        # Only the first words of the error are kept: they say whether the session expired or never existed.
        return {"perfil": perfil, "sesion": False, "motivo": salida.split("\n")[0][:120], "fecha": FECHA}
    datos = json.loads(salida)
    arn = datos.get("Arn", "")
    rol = arn.split("/")[-2] if arn.count("/") >= 2 else arn.split("/")[-1]
    return {"perfil": perfil, "sesion": True, "cuenta": "<account>", "tipo": arn.split(":")[5].split("/")[0] if ":" in arn else None,
            "rol": rol, "region": REGION, "fecha": FECHA}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ci", action="store_true", help="modo CI: sin AWS ni herramientas")
    ap.add_argument("--admin", help="perfil admin (crear y destruir), por ejemplo el del presupuesto")
    ap.add_argument("--operador", help="perfil operador (desplegar y consultar)")
    a = ap.parse_args()

    informe = {"fecha": FECHA, "modo": "ci" if a.ci else "mac", "python": platform.python_version(),
               "paquetes_python": paquetes_python(), "datos_semana13": datos_semana13(), "rutas_ci": rutas_ci()}
    requeridos = [all(v["ok"] for v in informe["paquetes_python"].values()), informe["datos_semana13"]["ok"]]
    if not a.ci:
        informe["herramientas"] = {
            "aws": version_de("aws", ["--version"], r"aws-cli/(\S+)"),
            "node": version_de("node", ["--version"], r"v(\S+)"),
            "npm": version_de("npm", ["--version"], r"(\S+)"),
            "uv": version_de("uv", ["--version"], r"uv (\S+)"),
            "cdk": version_de("cdk", ["--version"], r"(\S+)"),
            "terraform": version_de("terraform", ["version"], r"Terraform v(\S+)"),
            "checkov": version_de("checkov", ["--version"], r"(\S+)"),
        }
        informe["perfiles_configurados"] = perfiles_configurados()
        sesiones = []
        for rol, perfil in (("admin", a.admin), ("operador", a.operador)):
            if perfil:
                sesiones.append({"rol": rol, **sesion(perfil)})
            else:
                sesiones.append({"rol": rol, "sesion": None, "motivo": "perfil no asignado (pasar --" + rol + ")"})
        informe["sesiones"] = sesiones
        requeridos.append(all(s.get("sesion") is True for s in sesiones))

    requeridos.append(all(informe["rutas_ci"].values()))
    informe["ok"] = all(requeridos)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
