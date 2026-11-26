"""Week 19, activity 10: offline IAM linting of the synth with parliament, for CI (no AWS, no credentials).

    python semana-19/seguridad/parliament_offline.py --synth lab=<dir> --synth prod=<dir> [--salida <json>]

ValidatePolicy (activity 9, `validar_politicas.py`) needs AWS and runs from the Mac; its snapshot is
`resultados/seguridad/validate_policy.json`. This script is the CI's own check, decided by Manuel on 2026-11-23: it
needs no role and no credentials. It reads the same documents (`validar_politicas.documentos`, intrinsics resolved)
and lints every one of them with parliament 1.6.4: identity policies, trust policies, the key policy and the
bucket and endpoint policies. parliament is an identity-policy linter: on a trust policy it reports MALFORMED (no
Resource, by design), and on a key policy RESOURCE_STAR (there "*" is the key itself); those have their own rules.

parliament's IAM database is the one bundled with its release (2025-04-25), so it does not know newer services or
conditions. Every finding must match a rule of `CLASIFICACION`, each with its reason; a finding that matches none
fails the run. A new kind of finding is reviewed and given a rule, or the policy is fixed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import validar_politicas as V  # noqa: E402

SALIDA = S19 / "resultados" / "seguridad" / "parliament.json"
VERSION = "1.6.4"

BASE_VIEJA = ("parliament's bundled IAM database (release 2025-04-25) predates it; ValidatePolicy, on the live "
              "database, reports no error for it (validate_policy.json)")
ESTRELLA = ("actions without resource-level permissions, or Describe and List calls, on roles whose wildcards are "
            "suppressed one by one with a reason in cdk-nag AwsSolutions-IAM5 (supresiones.json)")
ROLES_CON_IAM5 = ("RolFlowLogs", "Limite", "EjecucionCfn", "Despliegue")

# (issue, field, pattern, reason). The field is "detalle" (the finding's text), "recurso" (the logical ID) or
# "donde" (the resource type and the policy's field, e.g. "AWS::IAM::Role.AssumeRolePolicyDocument").
CLASIFICACION = [
    ("MALFORMED", "donde", r"^AWS::IAM::Role\.AssumeRolePolicyDocument$",
     "a trust policy names principals, not resources: no Resource by design"),
    ("RESOURCE_STAR", "donde", r"^AWS::KMS::Key\.KeyPolicy$",
     "in a key policy, Resource \"*\" means the key that holds the policy"),
    ("MISMATCHED_TYPE", "detalle", r"^Type mismatch: ArnLike requires a value of type Arn but given String$",
     "ArnLike on kms:EncryptionContext:aws:logs:arn, the pattern of the CloudWatch Logs documentation for a log "
     "group's KMS key"),
    ("UNKNOWN_PREFIX", "detalle", r"Unknown prefix (s3vectors|bedrock-agentcore)$", BASE_VIEJA),
    ("UNKNOWN_CONDITION_FOR_ACTION", "detalle", r"^Unknown condition iam:PermissionsBoundary for action iam:",
     BASE_VIEJA),
    ("UNKNOWN_ACTION", "detalle", r"^Unknown action apigateway:(Tag|Untag)Resource$",
     "also ValidatePolicy's INVALID_ACTION, disproved by a live AccessDenied when it was missing (#306)"),
    ("RESOURCE_MISMATCH", "detalle", r"'required_format': '(arn:\*:bedrock|\*)",
     "parliament lists every Bedrock ARN format the action accepts that the policy does not use; each policy names "
     "on purpose the formats it needs (foundation model, inference profile, guardrail, prompt), and every stack with "
     "these policies was deployed and used in activities 7 to 9"),
    ("RESOURCE_STAR", "recurso", r"^(" + "|".join(ROLES_CON_IAM5) + r")", ESTRELLA),  # identity policies only
    ("RESOURCE_POLICY_PRIVILEGE_ESCALATION", "detalle", r"on arn:aws:s3:::semana19-eval-\* due to",
     "the CloudFormation execution role sets the policy of the judge bucket it creates; scoped to semana19-eval-* "
     "and bound by the permissions boundary (threat model, F11)"),
    ("MISMATCHED_TYPE_BUT_USABLE", "detalle", r"^Type mismatch: StringEquals requires a value of type String but "
     r"given Arn$", "iam:PermissionsBoundary compared with StringEquals, as the IAM documentation does; usable"),
]


def clasificar(h: dict) -> str | None:
    for issue, campo, patron, motivo in CLASIFICACION:
        if h["issue"] == issue and re.search(patron, h[campo]):
            return motivo
    return None


def hallazgos(docs: list[dict], analizar) -> list[dict]:
    salida = []
    for d in docs:
        for f in analizar(json.dumps(d["documento"])).findings:
            h = {"stack": d["stack"], "recurso": d["recurso"], "campo": d["campo"],
                 "donde": f'{d["tipo"]}.{d["campo"].split("[")[0]}', "issue": f.issue, "detalle": str(f.detail)}
            h["motivo"] = clasificar(h)
            salida.append(h)
    return salida


def informe(por_perfil: dict[str, list[dict]], n_docs: dict[str, int]) -> dict:
    return {"herramienta": f"parliament {VERSION}", "perfiles": {
        p: {"politicas": n_docs[p], "hallazgos": len(hs),
            "por_issue": dict(sorted(Counter(h["issue"] for h in hs).items())),
            "sin_clasificar": [h for h in hs if h["motivo"] is None]} for p, hs in por_perfil.items()},
        "reglas": [{"issue": i, "campo": c, "patron": p, "motivo": m} for i, c, p, m in CLASIFICACION]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--synth", action="append", required=True, metavar="PERFIL=DIR")
    ap.add_argument("--salida", "--output", type=Path, default=SALIDA, metavar="OUTPUT")
    a = ap.parse_args(argv)
    import warnings
    warnings.filterwarnings("ignore")
    from parliament import analyze_policy_string

    def analizar(texto):
        return analyze_policy_string(texto, ignore_private_auditors=True)

    por_perfil, n_docs = {}, {}
    for par in a.synth:
        perfil, carpeta = par.split("=", 1)
        docs = V.documentos(Path(carpeta))
        n_docs[perfil] = len(docs)
        por_perfil[perfil] = hallazgos(docs, analizar)
    r = informe(por_perfil, n_docs)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sin = sum(len(p["sin_clasificar"]) for p in r["perfiles"].values())
    for p, x in r["perfiles"].items():
        print(f"{p}: {x['politicas']} policies, {x['hallazgos']} findings, "
              f"{len(x['sin_clasificar'])} unclassified")
    return 1 if sin else 0


if __name__ == "__main__":
    raise SystemExit(main())
