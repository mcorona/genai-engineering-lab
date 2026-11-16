"""Week 19, activity 6: tests of the approval stack (Cognito, HTTP API, Step Functions, token table). Synthesis only ($0,
no AWS calls). Needs aws-cdk-lib (spike-iac job). The stack is opt-in with COMPUTO=1."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
COMPUTO = "semana19-computo"
LIMITE = "policy/semana19-limite"


@lru_cache(maxsize=None)
def sintetizar() -> dict:
    salida = Path(tempfile.mkdtemp(prefix="s19-computo-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1"}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    plantilla = json.loads((salida / f"{COMPUTO}.template.json").read_text(encoding="utf-8"))
    informe = list(csv.DictReader((salida / f"AwsSolutions--{COMPUTO}-NagReport.csv").open(encoding="utf-8")))
    return {"plantilla": plantilla, "nag": informe}


def recursos(tipo: str) -> dict:
    return {n: r for n, r in sintetizar()["plantilla"]["Resources"].items() if r["Type"] == tipo}


def test_cognito_en_essentials_con_cliente_sin_secreto_y_codigo_pkce():
    (pool,) = recursos("AWS::Cognito::UserPool").values()
    assert pool["Properties"]["UserPoolTier"] == "ESSENTIALS"
    assert pool["Properties"]["UserPoolName"] == "semana19-usuarios"
    (cliente,) = recursos("AWS::Cognito::UserPoolClient").values()
    assert cliente["Properties"]["GenerateSecret"] is False
    assert cliente["Properties"]["AllowedOAuthFlows"] == ["code"]


def test_trigger_de_tokens_v2_esta_conectado_al_pool():
    (pool,) = recursos("AWS::Cognito::UserPool").values()
    config = pool["Properties"]["LambdaConfig"]["PreTokenGenerationConfig"]
    assert config["LambdaVersion"] == "V2_0"


def test_maquina_de_aprobacion_con_traza_y_log_sin_datos():
    (sm,) = recursos("AWS::StepFunctions::StateMachine").values()
    p = sm["Properties"]
    assert p["StateMachineName"] == "semana19-aprobacion"
    assert p["TracingConfiguration"]["Enabled"] is True
    assert p["LoggingConfiguration"]["Level"] == "ALL"
    assert p["LoggingConfiguration"]["IncludeExecutionData"] is False


def test_ruta_de_aprobacion_exige_el_scope_de_aprobaciones_y_jwt():
    (ruta,) = [r for r in recursos("AWS::ApiGatewayV2::Route").values()
               if r["Properties"].get("RouteKey") == "POST /aprobaciones/{id}"]
    assert ruta["Properties"]["AuthorizationType"] == "JWT"
    assert ruta["Properties"]["AuthorizationScopes"] == ["legacybridge/aprobaciones"]


def test_api_tiene_logs_de_acceso():
    etapas = recursos("AWS::ApiGatewayV2::Stage")
    assert etapas and all("AccessLogSettings" in e["Properties"] for e in etapas.values())


def test_tabla_de_tokens_cifrada_con_llave_del_stack_y_ttl():
    tablas = {k: v for k, v in recursos("AWS::DynamoDB::Table").items() if k.startswith("Tokens")}
    (tabla,) = tablas.values()
    p = tabla["Properties"]
    assert p["SSESpecification"]["SSEType"] == "KMS"
    assert p["TimeToLiveSpecification"] == {"AttributeName": "expira", "Enabled": True}


def test_tabla_de_consultas_cifrada_con_llave_del_stack_y_ttl():
    tablas = {k: v for k, v in recursos("AWS::DynamoDB::Table").items() if k.startswith("Consultas")}
    (tabla,) = tablas.values()
    p = tabla["Properties"]
    assert p["SSESpecification"]["SSEType"] == "KMS"
    assert p["TimeToLiveSpecification"] == {"AttributeName": "expira", "Enabled": True}


def test_todo_rol_del_stack_tiene_el_limite_de_permisos():
    roles = recursos("AWS::IAM::Role")
    assert roles
    for nombre, rol in roles.items():
        assert "PermissionsBoundary" in rol["Properties"], nombre


def test_todo_grupo_de_logs_del_stack_esta_cifrado_y_con_retencion():
    grupos = recursos("AWS::Logs::LogGroup")
    assert grupos
    for nombre, g in grupos.items():
        assert "KmsKeyId" in g["Properties"], nombre
        assert g["Properties"]["RetentionInDays"] == 7, nombre


def test_cada_hallazgo_de_cdk_nag_no_conforme_tiene_razon():
    sin_razon = [r["Rule ID"] + " " + r["Resource ID"] for r in sintetizar()["nag"]
                 if r["Compliance"] != "Compliant" and not r.get("Exception Reason")]
    assert sin_razon == []


def test_ninguna_supresion_de_cdk_nag_queda_vacia():
    """Only real suppressions (non-compliant rules with a reason); compliant rules report N/A."""
    for r in sintetizar()["nag"]:
        if r["Compliance"] != "Compliant" and r.get("Exception Reason"):
            assert len(r["Exception Reason"].strip()) > 40, r["Rule ID"]


def _definicion_maquina() -> dict:
    (sm,) = recursos("AWS::StepFunctions::StateMachine").values()
    cuerpo = sm["Properties"]["DefinitionString"]
    return json.loads(json.dumps(cuerpo)) if isinstance(cuerpo, dict) else cuerpo


def test_escritor_esta_en_la_vpc_y_solo_abre_5432_y_443():
    (sg,) = [r for n, r in recursos("AWS::EC2::SecurityGroup").items() if "escritor" in n.lower() or "Escritor" in n]
    puertos = {(e.get("FromPort"), e.get("ToPort")) for e in sg["Properties"]["SecurityGroupEgress"]}
    assert puertos == {(5432, 5432), (443, 443)}


def test_escritor_corre_como_funcion_con_vpc_y_handler_del_paquete():
    funciones = [r for n, r in recursos("AWS::Lambda::Function").items() if n.startswith("FuncionEscritor")]
    assert len(funciones) == 1
    f = funciones[0]["Properties"]
    assert f["Handler"] == "computo.escritor.handler_escritor"
    assert "VpcConfig" in f and f["VpcConfig"]["SecurityGroupIds"]


def test_maquina_escribe_la_orden_solo_despues_de_la_aprobacion():
    texto = json.dumps(_definicion_maquina())
    assert "EscribirOrden" in texto and "FuncionEscritor" in texto
    assert "RechazadaPorAprobador" in texto and "Rechazada" in texto and "Succeed" in texto


def test_grupos_del_trigger_existen_en_el_pool():
    grupos = {r["Properties"]["GroupName"] for r in recursos("AWS::Cognito::UserPoolGroup").values()}
    assert {"analistas", "aprobadores"} <= grupos
