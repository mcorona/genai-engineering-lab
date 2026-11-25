"""Week 19, activity 9, step 1: every cdk-nag suppression and checkov skip of the synth, with its reason, and whether
it is still needed ($0, no AWS).

    uv run --group semana19 python semana-19/seguridad/supresiones.py --checkov <binary> \
        --synth lab=<dir> --synth prod=<dir> [--salida semana-19/resultados/seguridad/supresiones.json]

The synth must include every stack (COMPUTO=1). For each profile:

- cdk-nag: the suppressions are read from each resource's metadata (`cdk_nag.rules_to_suppress`) and matched with the
  stack's NagReport. A suppression the report never used (no `Suppressed` row for that resource and rule) is not
  needed. For AwsSolutions-IAM5, whose reason lists Sids (`Sid: reason | Sid: reason`), each Sid is checked against
  the resource's policy documents: a Sid that is gone, or whose statement has no `*` in its actions or resources,
  is listed as not needed.
- checkov: the skips are read from `checkov.skip` and matched with checkov's own `skipped_checks`. A skip checkov
  never applied is not needed. A skip without a comment fails.
- Unsuppressed findings: NagReport rows `Non-Compliant` and checkov `failed_checks`. Both must be zero.

The script exits 1 if any finding is unsuppressed, any skip has no reason, or any suppression is not needed.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))
from comun.redaccion import redactar  # noqa: E402

VERSION_CHECKOV = "3.4.4"
SALIDA = S19 / "resultados" / "seguridad" / "supresiones.json"
IAM5 = "AwsSolutions-IAM5"


def _lista(x) -> list:
    return x if isinstance(x, list) else [x]


def _tiene_comodin(valores) -> bool:
    """A `*` anywhere in the value, Fn::Join and Fn::Sub included."""
    return "*" in json.dumps(valores)


def documentos_de(recurso: dict) -> list[dict]:
    """The policy documents a resource carries: a policy, a managed policy, or a role's inline policies."""
    p = recurso.get("Properties", {})
    docs = [p["PolicyDocument"]] if isinstance(p.get("PolicyDocument"), dict) else []
    politicas = p.get("Policies") if isinstance(p.get("Policies"), list) else []
    docs += [x["PolicyDocument"] for x in politicas if isinstance(x, dict) and isinstance(x.get("PolicyDocument"), dict)]
    return docs


def estado_del_sid(sid: str, docs: list[dict]) -> str:
    for doc in docs:
        for st in _lista(doc.get("Statement", [])):
            if st.get("Sid") == sid:
                comodin = (_tiene_comodin(st.get("Action", [])) or _tiene_comodin(st.get("Resource", []))
                           or "NotAction" in st or "NotResource" in st)
                return "con_comodin" if comodin else "sin_comodin"
    return "ausente"


def sids_de_la_razon(razon: str) -> list[str]:
    sids = []
    for parte in razon.split(" | "):
        cabeza, sep, _ = parte.partition(": ")
        if sep and cabeza.isidentifier():
            sids.append(cabeza)
    return sids


def leer_nag(carpeta: Path) -> tuple[set[tuple[str, str]], list[dict]]:
    """(stack, logical ID, rule) triples the reports suppressed, and the unsuppressed rows."""
    logicos = logicos_por_ruta(carpeta)
    usadas, malas = set(), []
    for f in sorted(carpeta.glob("*NagReport.csv")):
        for r in csv.DictReader(f.open(encoding="utf-8")):
            if r["Compliance"] == "Suppressed":
                ruta = r["Resource ID"]
                usadas.add((ruta.split("/", 1)[0], logicos.get(ruta, ruta), r["Rule ID"]))
            elif r["Compliance"] == "Non-Compliant":
                malas.append({"regla": r["Rule ID"], "recurso": r["Resource ID"]})
    return usadas, malas


def logicos_por_ruta(carpeta: Path) -> dict[str, str]:
    """`stack/construct/path` -> logical ID, from each stack's `<stack>.metadata.json` (or the manifest of an older
    CDK). The templates carry no aws:cdk:path."""
    fuentes = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(carpeta.glob("*.metadata.json"))]
    manifiesto = carpeta / "manifest.json"
    if manifiesto.exists():
        fuentes += [a.get("metadata") or {} for a in json.loads(manifiesto.read_text(encoding="utf-8"))
                    .get("artifacts", {}).values()]
    mapa = {}
    for fuente in fuentes:
        for ruta, entradas in fuente.items():
            for e in entradas:
                if isinstance(e, dict) and e.get("type") == "aws:cdk:logicalId":
                    mapa[ruta.lstrip("/")] = e["data"]
    return mapa


def correr_checkov(binario: str, carpeta: Path) -> dict:
    r = subprocess.run([binario, "-d", str(carpeta), "--framework", "cloudformation", "--compact", "-o", "json"], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    d = d[0] if isinstance(d, list) else d
    return d.get("results", {"passed_checks": [], "failed_checks": [], "skipped_checks": []})


def revisar(carpeta: Path, checkov: dict) -> dict:
    plantillas, informes = list(carpeta.glob("*.template.json")), list(carpeta.glob("*NagReport.csv"))
    if not plantillas or len(informes) != len(plantillas):
        raise SystemExit(f"{carpeta}: {len(plantillas)} templates and {len(informes)} NagReports; synthesize every "
                         "stack with COMPUTO=1 first")
    usadas_nag, sin_suprimir_nag = leer_nag(carpeta)
    aplicadas_checkov = {(c["resource"], c["check_id"]) for c in checkov.get("skipped_checks", [])}
    filas = []
    for plantilla in sorted(carpeta.glob("*.template.json")):
        stack = plantilla.name.removesuffix(".template.json")
        recursos = json.loads(plantilla.read_text(encoding="utf-8")).get("Resources", {})
        for logico, recurso in recursos.items():
            md = recurso.get("Metadata", {})
            for s in md.get("cdk_nag", {}).get("rules_to_suppress", []):
                fila = {"perfil_stack": stack, "recurso": logico, "herramienta": "cdk-nag", "regla": s["id"],
                        "razon": s.get("reason", ""), "usada": (stack, logico, s["id"]) in usadas_nag}
                if s["id"] == IAM5:
                    # apply_to_children puts the suppression on the role and on its default policy: look for the Sid
                    # in every policy document of the stack.
                    docs = [d for r in recursos.values() for d in documentos_de(r)]
                    fila["sids"] = {sid: estado_del_sid(sid, docs) for sid in sids_de_la_razon(fila["razon"])}
                filas.append(fila)
            for s in md.get("checkov", {}).get("skip", []):
                filas.append({"perfil_stack": stack, "recurso": logico, "herramienta": "checkov", "regla": s["id"],
                              "razon": s.get("comment", ""),
                              "usada": (f"{recurso['Type']}.{logico}", s["id"]) in aplicadas_checkov})
    # One suppression call with apply_to_children copies the same (rule, reason) to a role and to its default policy;
    # only one of them triggers the rule. A suppression is not needed when no copy in the stack was used.
    grupos: dict[tuple, list[dict]] = {}
    for f in filas:
        grupos.setdefault((f["perfil_stack"], f["herramienta"], f["regla"], f["razon"]), []).append(f)
    sobran = []
    for (stack, _, regla, _), copias in grupos.items():
        recursos_del_grupo = sorted(f["recurso"] for f in copias)
        if not any(f["usada"] for f in copias):
            sobran.append({"stack": stack, "recursos": recursos_del_grupo, "regla": regla,
                           "motivo": "the tool never applied it"})
        for sid, estado in copias[0].get("sids", {}).items():
            if estado != "con_comodin":
                sobran.append({"stack": stack, "recursos": recursos_del_grupo, "regla": f"{IAM5} ({sid})",
                               "motivo": f"Sid {estado}"})
    for f in filas:
        f["usada_en_su_grupo"] = any(c["usada"] for c in grupos[(f["perfil_stack"], f["herramienta"], f["regla"],
                                                                   f["razon"])])
    sin_razon = [{"recurso": f["recurso"], "regla": f["regla"]} for f in filas if not f["razon"].strip()]
    fallidos = [{"regla": c["check_id"], "recurso": c["resource"]} for c in checkov.get("failed_checks", [])]
    return {
        "conteos": {"nag_suprimidas": sum(f["herramienta"] == "cdk-nag" for f in filas),
                    "nag_sin_suprimir": len(sin_suprimir_nag),
                    "checkov_aprobados": len(checkov.get("passed_checks", [])),
                    "checkov_omitidos": sum(f["herramienta"] == "checkov" for f in filas),
                    "checkov_fallidos": len(fallidos),
                    "por_regla": dict(sorted(Counter(f["regla"] for f in filas).items()))},
        "sin_suprimir": {"cdk_nag": sin_suprimir_nag, "checkov": fallidos},
        "sin_razon": sin_razon, "sobran": sobran, "supresiones": filas}


def veredicto(perfiles: dict) -> str:
    malo = any(p["sin_suprimir"]["cdk_nag"] or p["sin_suprimir"]["checkov"] or p["sin_razon"] or p["sobran"]
               for p in perfiles.values())
    return "revisar" if malo else "ok"


def version_de(binario: str) -> str:
    return subprocess.run([binario, "--version"], capture_output=True, text=True, check=True).stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--checkov", required=True, help=f"checkov binary, version {VERSION_CHECKOV}")
    ap.add_argument("--synth", action="append", required=True, metavar="PERFIL=DIR")
    ap.add_argument("--salida", "--output", type=Path, default=SALIDA, metavar="OUTPUT")
    a = ap.parse_args(argv)
    version = version_de(a.checkov)
    if version != VERSION_CHECKOV:
        sys.exit(f"checkov {VERSION_CHECKOV} expected, found {version}")
    perfiles = {}
    for par in a.synth:
        perfil, _, carpeta = par.partition("=")
        carpeta = Path(carpeta)
        perfiles[perfil] = revisar(carpeta, correr_checkov(a.checkov, carpeta))
    informe = redactar({"herramientas": {"cdk-nag": "AwsSolutions (cdk-nag of the semana19 group)",
                                         "checkov": f"checkov {version}"},
                        "perfiles": perfiles, "veredicto": veredicto(perfiles)})
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for perfil, p in informe["perfiles"].items():
        print(perfil, p["conteos"] | {"por_regla": None}, "sobran:", len(p["sobran"]), "sin razón:", len(p["sin_razon"]))
    print("veredicto:", informe["veredicto"])
    return 0 if informe["veredicto"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
