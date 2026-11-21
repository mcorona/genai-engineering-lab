"""Week 19, activity 9: the suppression inventory, offline (a hand-made synth folder, no checkov binary, no AWS)."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("supresiones", S19 / "seguridad" / "supresiones.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

IAM5 = "AwsSolutions-IAM5"


def _politica(*declaraciones):
    return {"Type": "AWS::IAM::Policy", "Properties": {"PolicyDocument": {"Statement": list(declaraciones)}}}


def synth(tmp_path: Path, recursos: dict, filas_nag: list[tuple[str, str, str]]) -> Path:
    """A synth folder with one stack `pila`: its template, its metadata (path -> logical ID) and its NagReport."""
    (tmp_path / "pila.template.json").write_text(json.dumps({"Resources": recursos}))
    (tmp_path / "pila.metadata.json").write_text(json.dumps(
        {f"/pila/{k}/Resource": [{"type": "aws:cdk:logicalId", "data": k}] for k in recursos}))
    with (tmp_path / "AwsSolutions--pila-NagReport.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Rule ID", "Resource ID", "Compliance", "Exception Reason", "Rule Level", "Rule Info"])
        for regla, logico, estado in filas_nag:
            w.writerow([regla, f"pila/{logico}/Resource", estado, "-", "Error", "-"])
    return tmp_path


def _nag(*supresiones):
    return {"cdk_nag": {"rules_to_suppress": [{"id": i, "reason": r} for i, r in supresiones]}}


SIN_CHECKOV = {"passed_checks": [], "failed_checks": [], "skipped_checks": []}


def test_supresion_usada_no_sobra(tmp_path):
    rec = {"Pol": {**_politica({"Sid": "Leer", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::b/*"}),
                   "Metadata": _nag((IAM5, "Leer: prefix of the bucket"))}}
    r = S.revisar(synth(tmp_path, rec, [(IAM5, "Pol", "Suppressed")]), SIN_CHECKOV)
    assert r["sobran"] == [] and r["supresiones"][0]["sids"] == {"Leer": "con_comodin"}


def test_supresion_que_la_herramienta_nunca_aplico(tmp_path):
    rec = {"Pol": {**_politica({"Sid": "Leer", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::b/k"}),
                   "Metadata": _nag(("AwsSolutions-S1", "no access logs"))}}
    r = S.revisar(synth(tmp_path, rec, []), SIN_CHECKOV)
    assert [s["motivo"] for s in r["sobran"]] == ["the tool never applied it"]


def test_copias_de_apply_to_children_cuentan_como_una(tmp_path):
    razon = "Leer: prefix of the bucket"
    rec = {"Rol": {"Type": "AWS::IAM::Role", "Properties": {}, "Metadata": _nag((IAM5, razon))},
           "RolPol": {**_politica({"Sid": "Leer", "Action": "s3:GetObject", "Resource": {"Fn::Join": ["", ["a", "/*"]]}}),
                      "Metadata": _nag((IAM5, razon))}}
    r = S.revisar(synth(tmp_path, rec, [(IAM5, "RolPol", "Suppressed")]), SIN_CHECKOV)
    assert r["sobran"] == []
    assert all(f["usada_en_su_grupo"] for f in r["supresiones"])


@pytest.mark.parametrize("declaracion,estado", [
    ({"Sid": "Otro", "Action": "s3:*", "Resource": "*"}, "ausente"),
    ({"Sid": "Leer", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::b/k"}, "sin_comodin"),
])
def test_sid_de_la_razon_ausente_o_sin_comodin(tmp_path, declaracion, estado):
    rec = {"Pol": {**_politica(declaracion, {"Sid": "Otro2", "Action": "s3:*", "Resource": "*"}),
                   "Metadata": _nag((IAM5, "Leer: old reason"))}}
    r = S.revisar(synth(tmp_path, rec, [(IAM5, "Pol", "Suppressed")]), SIN_CHECKOV)
    assert r["sobran"] == [{"stack": "pila", "recursos": ["Pol"], "regla": f"{IAM5} (Leer)", "motivo": f"Sid {estado}"}]


def test_sin_suprimir_y_skip_sin_razon(tmp_path):
    rec = {"Fn": {"Type": "AWS::Lambda::Function", "Properties": {},
                  "Metadata": {"checkov": {"skip": [{"id": "CKV_AWS_116", "comment": " "}]}}}}
    checkov = {"passed_checks": [{}], "skipped_checks": [{"resource": "AWS::Lambda::Function.Fn", "check_id": "CKV_AWS_116"}],
               "failed_checks": [{"resource": "AWS::Lambda::Function.Fn", "check_id": "CKV_AWS_115"}]}
    r = S.revisar(synth(tmp_path, rec, [("AwsSolutions-L1", "Fn", "Non-Compliant")]), checkov)
    assert r["sin_suprimir"] == {"cdk_nag": [{"regla": "AwsSolutions-L1", "recurso": "pila/Fn/Resource"}],
                                 "checkov": [{"regla": "CKV_AWS_115", "recurso": "AWS::Lambda::Function.Fn"}]}
    assert r["sin_razon"] == [{"recurso": "Fn", "regla": "CKV_AWS_116"}]
    assert r["sobran"] == []  # the skip was applied
    assert S.veredicto({"lab": r}) == "revisar"


def test_skip_de_checkov_no_aplicado_sobra(tmp_path):
    rec = {"Fn": {"Type": "AWS::Lambda::Function", "Properties": {},
                  "Metadata": {"checkov": {"skip": [{"id": "CKV_AWS_117", "comment": "outside the VPC"}]}}}}
    r = S.revisar(synth(tmp_path, rec, []), SIN_CHECKOV)
    assert r["sobran"][0]["regla"] == "CKV_AWS_117"


def test_synth_vacio_o_incompleto_falla(tmp_path):
    with pytest.raises(SystemExit):
        S.revisar(tmp_path, SIN_CHECKOV)
    (tmp_path / "x.template.json").write_text("{}")
    with pytest.raises(SystemExit):
        S.revisar(tmp_path, SIN_CHECKOV)


def test_comodin_dentro_de_join():
    assert S._tiene_comodin({"Fn::Join": ["", ["arn:aws:logs:", {"Ref": "AWS::Region"}, ":*"]]})
    assert not S._tiene_comodin(["arn:aws:s3:::b/k"])


def test_informe_versionado_en_cero():
    informe = json.loads((S19 / "resultados" / "seguridad" / "supresiones.json").read_text(encoding="utf-8"))
    assert informe["veredicto"] == "ok" and set(informe["perfiles"]) == {"lab", "prod"}
    for p in informe["perfiles"].values():
        assert p["sin_suprimir"] == {"cdk_nag": [], "checkov": []}
        assert p["sobran"] == [] and p["sin_razon"] == []
        assert p["conteos"]["checkov_fallidos"] == 0 and p["conteos"]["nag_sin_suprimir"] == 0
