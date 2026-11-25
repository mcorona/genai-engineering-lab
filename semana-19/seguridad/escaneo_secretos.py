"""Week 19, activity 9, step 1: secret scan with gitleaks over the git history and the CDK synth ($0, no AWS).

    uv run --group semana19 python semana-19/seguridad/escaneo_secretos.py --gitleaks <binary> \
        --cdk-out lab=<dir> --cdk-out prod=<dir> [--salida semana-19/resultados/seguridad/secretos.json]

Scopes:
- `historia`: every commit of the repository (`gitleaks git`, all refs). It covers every versioned file, so the
  working tree's tracked files need no separate pass. Untracked files are out of scope.
- `cdk_out_<perfil>`: a synth directory (`gitleaks dir`), templates and Lambda assets.

gitleaks writes its report to stdout and this script reads it in memory: the secret values never touch the disk and
the saved report carries no secret, no author and no email. Every finding gets one class, with its reason:

- `tercero`: third-party code kept unmodified: a path under a `vendor/` folder, or, in a synth, a file listed in a
  package's `*.dist-info/RECORD` inside the same asset (botocore's data examples, PyJWT, cryptography). Scanned and
  counted, never fixed here.
- `falso_positivo`: the value is not a credential: a CDK asset key (64 hex characters, optionally `.zip` or `.json`),
  a bare identifier with letters only, a Python keyword argument (`snake_case=`), or, in a Python file of the history,
  a Sid declared as `sid="<value>"` in the same file at the same commit.
- `prueba`: a fixture of a test or a canary, in a file listed in PRUEBAS with its reason.
- `sin_clasificar`: anything else. The script exits 1 if one exists.

The account ID in the history is a decision already taken (it is not rewritten): it is recorded as accepted.
gitleaks has no rule for it; `tests/test_sin_cuenta_en_versionados.py` keeps it out of the current tree.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
sys.path.insert(0, str(S19))
from comun.redaccion import redactar  # noqa: E402

VERSION_GITLEAKS = "8.30.1"
SALIDA = S19 / "resultados" / "seguridad" / "secretos.json"

ASSET_DE_CDK = re.compile(r"[0-9a-f]{64}(\.zip|\.json)?")
IDENTIFICADOR = re.compile(r"[A-Za-z]+")
ARGUMENTO_CON_NOMBRE = re.compile(r"[a-z]+(_[a-z]+)+=")

# Files whose findings are test fixtures or canaries. Each one is reviewed by hand; a new file needs a new entry.
PRUEBAS = {
    "semana-17/observabilidad/verificar_stack.py":
        "canaries of the week 17 log check: fake DSN, JWT and bearer values the check must find redacted",
    "semana-19/tests/test_agentes_comparar.py":
        "fake JWT that the redaction test expects to become <token>",
    "semana-19/tests/test_consultas.py":
        "a fixed question string the async worker test must never log",
}

DECISION_CUENTA = ("The account ID appears in earlier commits of the history. Decision already taken: the history is "
                   "not rewritten. The current tree is kept clean by tests/test_sin_cuenta_en_versionados.py, and "
                   "gitleaks has no rule for account IDs.")


def archivos_de_terceros(raiz_synth: Path) -> set[str]:
    """Paths, relative to the synth directory, of every file a package installed into a Lambda asset."""
    propios: set[str] = set()
    for record in raiz_synth.glob("asset.*/*.dist-info/RECORD"):
        asset = record.parent.parent
        for linea in record.read_text(encoding="utf-8", errors="replace").splitlines():
            ruta = linea.split(",", 1)[0].strip()
            if ruta and not ruta.startswith(".."):
                propios.add(str((asset / ruta).relative_to(raiz_synth)))
    return propios


def fuente_en_commit(commit: str, archivo: str) -> str:
    r = subprocess.run(["git", "show", f"{commit}:{archivo}"], cwd=RAIZ, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def clasificar(hallazgo: dict, *, terceros: set[str] = frozenset(), fuente=fuente_en_commit) -> tuple[str, str]:
    """One class and its reason. `hallazgo["File"]` is relative to the scope's root; `fuente(commit, file)` returns
    that file's text at that commit (history findings only)."""
    archivo, secreto = hallazgo["File"], hallazgo.get("Secret", "")
    if "/vendor/" in f"/{archivo}" or archivo in terceros:
        return "tercero", "third-party file kept unmodified (vendor/ folder or a package's dist-info RECORD)"
    if ASSET_DE_CDK.fullmatch(secreto):
        return "falso_positivo", "CDK asset key: the content hash of an asset, not a credential"
    if IDENTIFICADOR.fullmatch(secreto):
        return "falso_positivo", "identifier with letters only (a Sid or a property name), not a credential"
    if ARGUMENTO_CON_NOMBRE.fullmatch(secreto) and archivo.endswith(".py"):
        return "falso_positivo", "a Python keyword argument (snake_case=), not a credential"
    commit = hallazgo.get("Commit")
    if commit and archivo.endswith(".py") and f'sid="{secreto}"' in fuente(commit, archivo):
        return "falso_positivo", "a policy statement Sid, declared as sid=\"...\" in the same file at that commit"
    if archivo in PRUEBAS:
        return "prueba", PRUEBAS[archivo]
    return "sin_clasificar", "not explained: review it by hand before merging"


def correr_gitleaks(binario: str, modo: str, objetivo: Path) -> list[dict]:
    """gitleaks' JSON report from stdout. Its exit code is forced to 0: the classes decide, not the raw count."""
    r = subprocess.run([binario, modo, str(objetivo), "--no-banner", "--log-level", "error", "--exit-code", "0",
                        "--report-format", "json", "--report-path", "-"], capture_output=True, text=True, check=True)
    return json.loads(r.stdout or "[]")


def version_de(binario: str) -> str:
    return subprocess.run([binario, "version"], capture_output=True, text=True, check=True).stdout.strip()


def resumen(alcance: str, hallazgos: list[dict], *, raiz: Path, terceros: set[str] = frozenset()) -> dict:
    """Counts per class and rule, and the detail of every finding that is not third-party, without the secret."""
    filas, clases, reglas = [], Counter(), Counter()
    for h in hallazgos:
        archivo = h["File"]
        if Path(archivo).is_absolute():
            archivo = str(Path(archivo).relative_to(raiz))
        h = {**h, "File": archivo}
        clase, razon = clasificar(h, terceros=terceros)
        clases[clase] += 1
        reglas[h["RuleID"]] += 1
        if clase != "tercero":
            filas.append({"archivo": archivo, "linea": h["StartLine"], "commit": (h.get("Commit") or "")[:7] or None,
                          "regla": h["RuleID"], "clase": clase, "razon": razon})
    filas.sort(key=lambda f: (f["clase"], f["archivo"], f["linea"], f["commit"] or ""))
    return {"alcance": alcance, "hallazgos": len(hallazgos), "por_clase": dict(sorted(clases.items())),
            "por_regla": dict(sorted(reglas.items())), "detalle": filas}


def armar(alcances: list[dict], version: str) -> dict:
    sin_clasificar = sum(a["por_clase"].get("sin_clasificar", 0) for a in alcances)
    return redactar({
        "herramienta": f"gitleaks {version}", "configuracion": "default rules, no allowlist file",
        "alcances": alcances, "cuenta_en_historial": {"estado": "aceptado", "razon": DECISION_CUENTA},
        "sin_clasificar": sin_clasificar, "veredicto": "ok" if sin_clasificar == 0 else "revisar"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gitleaks", required=True, help=f"gitleaks binary, version {VERSION_GITLEAKS}")
    ap.add_argument("--cdk-out", action="append", default=[], metavar="PERFIL=DIR", help="a synth directory")
    ap.add_argument("--sin-historia", "--no-history", action="store_true", help="skip the history (a shallow checkout)")
    ap.add_argument("--salida", "--output", type=Path, default=SALIDA, metavar="OUTPUT")
    a = ap.parse_args(argv)
    version = version_de(a.gitleaks)
    if version.lstrip("v") != VERSION_GITLEAKS:
        sys.exit(f"gitleaks {VERSION_GITLEAKS} expected, found {version}")
    alcances = []
    if not a.sin_historia:
        alcances.append(resumen("historia", correr_gitleaks(a.gitleaks, "git", RAIZ), raiz=RAIZ))
    for par in a.cdk_out:
        perfil, _, carpeta = par.partition("=")
        raiz = Path(carpeta).resolve()
        alcances.append(resumen(f"cdk_out_{perfil}", correr_gitleaks(a.gitleaks, "dir", raiz), raiz=raiz,
                                terceros=archivos_de_terceros(raiz)))
    informe = armar(alcances, version)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for al in informe["alcances"]:
        print(al["alcance"], al["hallazgos"], al["por_clase"])
    print("sin_clasificar:", informe["sin_clasificar"])
    return 0 if informe["sin_clasificar"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
