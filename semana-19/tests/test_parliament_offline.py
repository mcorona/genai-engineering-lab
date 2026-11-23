"""Week 19, activity 10: the offline parliament check's classification, with a fake analyzer (no parliament needed)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("parliament_offline", S19 / "seguridad" / "parliament_offline.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def _h(issue, detalle, recurso="X", stack="semana19-control", donde="AWS::IAM::Policy.PolicyDocument"):
    return {"issue": issue, "detalle": detalle, "recurso": recurso, "stack": stack, "donde": donde}


def test_lo_explicado_tiene_motivo():
    assert P.clasificar(_h("UNKNOWN_PREFIX", "Unknown prefix s3vectors"))
    assert P.clasificar(_h("UNKNOWN_PREFIX", "Unknown prefix bedrock-agentcore"))
    assert P.clasificar(_h("UNKNOWN_ACTION", "Unknown action apigateway:TagResource"))
    assert P.clasificar(_h("RESOURCE_STAR", "['kms:DescribeKey']", recurso="EjecucionCfnDatos4EF77136"))
    assert P.clasificar(_h("RESOURCE_POLICY_PRIVILEGE_ESCALATION",
                           "Possible resource policy privilege escalation on arn:aws:s3:::semana19-eval-* due to x"))


def test_confianza_y_llave_tienen_su_regla_solo_donde_aplica():
    sin_recurso = "Statement contains neither Resource nor NotResource"
    assert P.clasificar(_h("MALFORMED", sin_recurso, donde="AWS::IAM::Role.AssumeRolePolicyDocument"))
    assert P.clasificar(_h("MALFORMED", sin_recurso)) is None
    assert P.clasificar(_h("RESOURCE_STAR", "['kms:Decrypt']", recurso="Llave0AEC6D4F", donde="AWS::KMS::Key.KeyPolicy"))
    assert P.clasificar(_h("RESOURCE_STAR", "['kms:Decrypt']", recurso="Llave0AEC6D4F")) is None


def test_lo_nuevo_no_tiene_motivo():
    assert P.clasificar(_h("UNKNOWN_PREFIX", "Unknown prefix bedrockk")) is None
    assert P.clasificar(_h("UNKNOWN_ACTION", "Unknown action s3:GetObjekt")) is None
    assert P.clasificar(_h("RESOURCE_STAR", "['s3:GetObject']", recurso="FuncionAgenteServiceRoleDefaultPolicy")) is None
    assert P.clasificar(_h("RESOURCE_POLICY_PRIVILEGE_ESCALATION",
                           "Possible resource policy privilege escalation on arn:aws:s3:::otro-* due to x")) is None
    assert P.clasificar(_h("PRIVILEGE_ESCALATION", "iam:PassRole")) is None


def test_todas_las_politicas_y_cuenta_lo_sin_clasificar():
    docs = [{"stack": "s", "recurso": "R", "tipo": "AWS::IAM::Policy", "campo": "PolicyDocument",
             "policyType": "IDENTITY_POLICY", "documento": {}},
            {"stack": "s", "recurso": "T", "tipo": "AWS::IAM::Role", "campo": "AssumeRolePolicyDocument",
             "policyType": "RESOURCE_POLICY", "documento": {}}]
    vistos = []

    def analizar(texto):
        vistos.append(texto)
        return SimpleNamespace(findings=[SimpleNamespace(issue="UNKNOWN_PREFIX", detail="Unknown prefix s3vectors"),
                                         SimpleNamespace(issue="RESOURCE_STAR", detail="['s3:*']")])
    hs = P.hallazgos(docs, analizar)
    assert len(vistos) == 2 and len(hs) == 4
    r = P.informe({"lab": hs}, {"lab": 2})
    assert r["perfiles"]["lab"]["hallazgos"] == 4
    assert [h["issue"] for h in r["perfiles"]["lab"]["sin_clasificar"]] == ["RESOURCE_STAR", "RESOURCE_STAR"]


def test_el_resultado_guardado_no_tiene_nada_sin_clasificar():
    r = json.loads((S19 / "resultados" / "seguridad" / "parliament.json").read_text(encoding="utf-8"))
    assert r["herramienta"] == f"parliament {P.VERSION}"
    assert set(r["perfiles"]) == {"lab", "prod"}
    for p in r["perfiles"].values():
        assert p["politicas"] > 0 and p["sin_clasificar"] == []
