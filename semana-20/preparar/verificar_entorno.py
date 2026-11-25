"""Week 20, preparation: readiness check that costs $0 and prints no secret.

    uv run --group semana20 python semana-20/preparar/verificar_entorno.py --ci
    uv run --group semana20 python semana-20/preparar/verificar_entorno.py --operador semana19-lectura --python-cdk <python with aws-cdk-lib>

Checks:
- the pins of the semana20 group, installed;
- the week 19 baseline (`semana-19/resultados/eval_aws_detalle.jsonl`): present, one JSON object per line, with the
  fields week 20 reads (activity 1 recomputes its figures);
- the week 19 hand-off the plan builds on: `modelo.invocar`, the quote model, the model config, the span exporter;
- the CI paths: `semana-20/**` in the required `regresion` check, and `eval-semana-20` without AWS;
- Mac only: the week 19 stacks synthesize (lab and prod, COMPUTO=1) with the tags proyecto, perfil and componente,
  and the profiles have an active session (STS, account masked as <account>).

The status of the cost allocation tags is not read here: `ce:ListCostAllocationTags` is a Cost Explorer API call, and
every Cost Explorer call needs Manuel's OK. Manuel reads it in the Billing console when he activates `componente`.

It writes nothing outside stdout and a temporary folder, and exits with 1 if a required check fails.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S20 = AQUI.parent
RAIZ = S20.parent
S19 = RAIZ / "semana-19"
V = json.loads((AQUI / "versiones.json").read_text(encoding="utf-8"))
FECHA = date.today().isoformat()
LINEA_BASE = S19 / "resultados" / "eval_aws_detalle.jsonl"
CAMPOS_LINEA_BASE = ("id", "idioma", "fase", "exito", "estado", "latencia_s", "pasos", "tokens_entrada",
                     "tokens_salida", "tokens_cache_lectura", "tokens_cache_escritura", "costo_usd", "trayectoria_ok")
TRASPASO = {
    "modelo.invocar": (S19 / "agente" / "modelo.py", r"^def invocar\("),
    "modelo de cotización": (S19 / "costos" / "modelo.py", None),
    "MODELO_ID en ia/config.py": (S19 / "ia" / "config.py", r"^MODELO_ID = "),
    "exportador de spans": (S19 / "agente" / "exportador.py", None),
    "etiquetas de las pilas": (S19 / "infra" / "cdk" / "app.py", r"^def etiquetas\("),
}
PILAS = ("semana19-control", "semana19-base", "semana19-datos", "semana19-ia", "semana19-computo", "semana19-gateway",
         "semana19-agentes-comparacion", "semana19-eval")


def _semana19():
    """Week 19's readiness module, for its STS helper (it masks the account)."""
    spec = importlib.util.spec_from_file_location("verificar_entorno_s19", S19 / "preparar" / "verificar_entorno.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def paquetes_python() -> dict:
    salida = {}
    for paquete, esperado in V["python"].items():
        try:
            version = md.version(paquete)
        except md.PackageNotFoundError:
            version = None
        salida[paquete] = {"esperado": esperado, "instalado": version, "ok": version == esperado}
    return salida


def linea_base(ruta: Path = LINEA_BASE) -> dict:
    if not ruta.exists():
        return {"ok": False, "motivo": "no existe"}
    filas, malas = [], []
    for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            malas.append(n)
            continue
        if not isinstance(fila, dict) or any(c not in fila for c in CAMPOS_LINEA_BASE):
            malas.append(n)
        filas.append(fila)
    return {"ok": bool(filas) and not malas, "filas": len(filas), "lineas_malas": malas,
            "con_costo": sum(1 for f in filas if f.get("costo_usd"))}


def traspaso() -> dict:
    salida = {}
    for nombre, (ruta, patron) in TRASPASO.items():
        ok = ruta.exists() and (patron is None or re.search(patron, ruta.read_text(encoding="utf-8"), re.M) is not None)
        salida[nombre] = ok
    return salida


def rutas_ci() -> dict:
    regresion = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    eval20 = RAIZ / ".github" / "workflows" / "eval-semana-20.yml"
    return {
        "semana-20 en regresion": '"semana-20/**"' in regresion.split("jobs:", 1)[0],
        "eval-semana-20.yml existe": eval20.exists(),
        "eval-semana-20 sin AWS": eval20.exists() and not re.search(
            r"aws-actions|AWS_|aws configure|aws sts|aws login|boto3\.client", eval20.read_text(encoding="utf-8")),
    }


def sintesis(python_cdk: str) -> dict:
    """The week 19 stacks synthesize in lab and prod, each with its three tags. No AWS call: CDK only reads files."""
    subprocess.run([python_cdk, str(S19 / "infra" / "paquete_agente.py"), "--sin-dependencias"], check=True,
                   capture_output=True, text=True, timeout=300)
    salida = {}
    for perfil in ("lab", "prod"):
        carpeta = Path(tempfile.mkdtemp(prefix=f"s20-synth-{perfil}-"))
        entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(carpeta), "COMPUTO": "1",
                   "S19_SIN_DEPENDENCIAS": "1", "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"}
        r = subprocess.run([python_cdk, str(S19 / "infra" / "cdk" / "app.py")], env=entorno, capture_output=True,
                           text=True, timeout=600)
        if r.returncode:
            salida[perfil] = {"ok": False, "motivo": r.stderr.strip().splitlines()[-1][:200] if r.stderr else "rc"}
            continue
        artefactos = json.loads((carpeta / "manifest.json").read_text(encoding="utf-8"))["artifacts"]
        etiquetas = {k: a["properties"].get("tags") for k, a in artefactos.items()
                     if a.get("type") == "aws:cloudformation:stack"}
        bien = {k: t == {"proyecto": "semana19", "perfil": perfil, "componente": k.removeprefix("semana19-")}
                for k, t in etiquetas.items()}
        salida[perfil] = {"ok": set(etiquetas) == set(PILAS) and all(bien.values()), "pilas": len(etiquetas),
                          "sin_etiquetas": sorted(k for k, ok in bien.items() if not ok)}
    return salida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ci", action="store_true", help="CI mode: no AWS, no CDK")
    ap.add_argument("--operador", "--operator", help="read-only profile for the session (for example semana19-lectura)", metavar="OPERATOR")
    ap.add_argument("--admin", help="admin profile: only Manuel runs it")
    ap.add_argument("--python-cdk", help="the python with aws-cdk-lib to synthesize (Mac mode)")
    a = ap.parse_args(argv)

    informe = {"fecha": FECHA, "modo": "ci" if a.ci else "mac", "python": platform.python_version(),
               "paquetes_python": paquetes_python(), "linea_base_semana19": linea_base(), "traspaso": traspaso(),
               "rutas_ci": rutas_ci()}
    requeridos = [all(p["ok"] for p in informe["paquetes_python"].values()), informe["linea_base_semana19"]["ok"],
                  all(informe["traspaso"].values()), all(informe["rutas_ci"].values())]
    if not a.ci:
        if a.python_cdk:
            informe["sintesis_semana19"] = sintesis(a.python_cdk)
            requeridos.append(all(p["ok"] for p in informe["sintesis_semana19"].values()))
        else:
            informe["sintesis_semana19"] = {"ok": None, "motivo": "pasar --python-cdk"}
            requeridos.append(False)
        s19 = _semana19()
        sesiones = []
        for rol, perfil in (("operador", a.operador), ("admin", a.admin)):
            if perfil:
                sesiones.append({"rol": rol, **s19.sesion(perfil)})
            elif rol == "operador":
                sesiones.append({"rol": rol, "sesion": None, "motivo": "pasar --operador"})
        informe["sesiones"] = sesiones
        requeridos.append(all(s.get("sesion") is True for s in sesiones))
    informe["ok"] = all(requeridos)
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
