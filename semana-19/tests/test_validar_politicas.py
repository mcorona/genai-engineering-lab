"""Week 19, activity 9: ValidatePolicy over the synth, offline (resolver, extraction, Stubber, snapshot; no AWS)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validar_politicas", S19 / "seguridad" / "validar_politicas.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)

SNAPSHOT = S19 / "resultados" / "seguridad" / "validate_policy.json"

BASE = {
    "Resources": {
        "Llave": {"Type": "AWS::KMS::Key", "Properties": {"KeyPolicy": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"AWS": {"Fn::Join": ["", ["arn:", {"Ref": "AWS::Partition"}, ":iam::",
                                                                         {"Ref": "AWS::AccountId"}, ":root"]]}},
             "Action": "kms:*", "Resource": "*"}]}}},
    },
    "Outputs": {"ExportLlave": {"Value": {"Fn::GetAtt": ["Llave", "Arn"]}, "Export": {"Name": "base:Llave"}}},
}
COMPUTO = {
    "Resources": {
        "Tabla": {"Type": "AWS::DynamoDB::Table", "Properties": {"TableName": "semana19-tokens"}},
        "Rol": {"Type": "AWS::IAM::Role", "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
            "Policies": [{"PolicyName": "p", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": "logs:CreateLogStream", "Resource": "*"}]}}]}},
        "Pol": {"Type": "AWS::IAM::Policy", "Properties": {"PolicyName": "x", "Roles": [{"Ref": "Rol"}],
            "PolicyDocument": {"Version": "2012-10-17", "Statement": [
                {"Effect": "Allow", "Action": "dynamodb:PutItem", "Resource": {"Fn::GetAtt": ["Tabla", "Arn"]}},
                {"Effect": "Allow", "Action": "kms:Decrypt", "Resource": {"Fn::ImportValue": "base:Llave"}},
                {"Effect": "Allow", "Action": "logs:PutLogEvents",
                 "Resource": {"Fn::Sub": "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/semana19/*"}}]}}},
        "Ep": {"Type": "AWS::EC2::VPCEndpoint", "Properties": {"PolicyDocument": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "*",
             "Condition": {"StringEquals": {"aws:PrincipalAccount": {"Ref": "AWS::AccountId"}}}}]}}},
    },
}


@pytest.fixture
def synth(tmp_path):
    (tmp_path / "semana19-base.template.json").write_text(json.dumps(BASE))
    (tmp_path / "semana19-computo.template.json").write_text(json.dumps(COMPUTO))
    return tmp_path


def test_extrae_cada_documento_con_su_tipo(synth):
    docs = V.documentos(synth)
    tipos = sorted((d["recurso"], d["campo"], d["policyType"], d["validatePolicyResourceType"]) for d in docs)
    assert tipos == [
        ("Ep", "PolicyDocument", "RESOURCE_POLICY", None),
        ("Llave", "KeyPolicy", "RESOURCE_POLICY", None),
        ("Pol", "PolicyDocument", "IDENTITY_POLICY", None),
        ("Rol", "AssumeRolePolicyDocument", "RESOURCE_POLICY", "AWS::IAM::AssumeRolePolicyDocument"),
        ("Rol", "Policies[0]", "IDENTITY_POLICY", None),
    ]


def test_resuelve_intrinsecas_e_importaciones(synth):
    pol = next(d for d in V.documentos(synth) if d["recurso"] == "Pol")["documento"]["Statement"]
    assert pol[0]["Resource"] == "arn:aws:dynamodb:us-east-1:111122223333:table/semana19-tokens"
    assert pol[1]["Resource"] == f"arn:aws:kms:us-east-1:111122223333:key/{V.LLAVE_EJEMPLO}"
    assert pol[2]["Resource"] == "arn:aws:logs:us-east-1:111122223333:log-group:/semana19/*"
    llave = next(d for d in V.documentos(synth) if d["recurso"] == "Llave")["documento"]
    assert llave["Statement"][0]["Principal"]["AWS"] == "arn:aws:iam::111122223333:root"


def test_la_huella_es_del_documento_sin_resolver(synth):
    d = next(d for d in V.documentos(synth) if d["recurso"] == "Pol")
    assert d["huella"] == V.huella(COMPUTO["Resources"]["Pol"]["Properties"]["PolicyDocument"])


@pytest.mark.parametrize("x", [{"Fn::Base64": "x"}, {"Fn::ImportValue": "nadie:exporta"},
                               {"Fn::GetAtt": ["Tabla", "StreamArn"]}])
def test_intrinseca_desconocida_detiene_la_corrida(synth, x):
    plantillas = {"semana19-computo": COMPUTO, "semana19-base": BASE}
    with pytest.raises(V.SinResolver):
        V.Resolutor(plantillas).resolver("semana19-computo", x)


def test_synth_vacio_falla(tmp_path):
    with pytest.raises(SystemExit):
        V.documentos(tmp_path)


def _cliente_con(hallazgos):
    c = boto3.client("accessanalyzer", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
    s = Stubber(c)
    s.add_response("validate_policy", {"findings": hallazgos})
    s.activate()
    return c, s


def test_validar_pasa_el_tipo_y_lee_los_hallazgos():
    h = {"findingDetails": "d", "findingType": "SECURITY_WARNING", "issueCode": "PASS_ROLE_WITH_STAR_IN_RESOURCE",
         "learnMoreLink": "https://example.invalid", "locations": [{"path": [{"value": "Statement"}, {"index": 0}],
                                                                    "span": {"start": {"line": 1, "column": 1, "offset": 0},
                                                                             "end": {"line": 1, "column": 2, "offset": 1}}}]}
    c, s = _cliente_con([h])
    doc = {"documento": {"Version": "2012-10-17", "Statement": []}, "policyType": "RESOURCE_POLICY",
           "validatePolicyResourceType": "AWS::S3::Bucket"}
    r = V.validar(c, doc)
    assert r == [{"findingType": "SECURITY_WARNING", "issueCode": "PASS_ROLE_WITH_STAR_IN_RESOURCE", "detalle": "d",
                  "learnMoreLink": "https://example.invalid", "ruta": ["Statement", 0]}]
    s.assert_no_pending_responses()


@pytest.mark.parametrize("tipo,veredicto", [("ERROR", "revisar"), ("SECURITY_WARNING", "revisar"),
                                            ("WARNING", "ok"), ("SUGGESTION", "ok")])
def test_veredicto_por_tipo_de_hallazgo(tipo, veredicto):
    docs = [{"stack": "s", "recurso": "r", "tipo": "AWS::IAM::Policy", "campo": "PolicyDocument",
             "policyType": "IDENTITY_POLICY", "validatePolicyResourceType": None, "huella": "h", "documento": {},
             "hallazgos": [{"findingType": tipo, "issueCode": "X", "detalle": "arn:aws:iam::111122223333:role/x",
                            "learnMoreLink": None, "ruta": []}]}]
    r = V.informe({"lab": docs})
    assert r["veredicto"] == veredicto
    assert "111122223333" not in json.dumps(r["documentos"])
    assert "documento" not in r["documentos"]["lab"][0]


def test_snapshot_sin_errores_ni_advertencias_de_seguridad():
    r = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    malos = [(p, d["recurso"], h["issueCode"]) for p, docs in r["documentos"].items() for d in docs
             for h in d["hallazgos"] if h["findingType"] in V.MALAS]
    assert malos == [] and r["veredicto"] == "ok" and r["errores_o_advertencias_de_seguridad"] == 0
    assert set(r["por_perfil"]) == {"lab", "prod"}
    assert all(p["documentos"] > 0 for p in r["por_perfil"].values())
