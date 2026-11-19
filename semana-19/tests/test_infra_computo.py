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


def _estados_en_orden(definicion: dict) -> list[tuple[str, dict]]:
    orden, actual = [], definicion["StartAt"]
    while actual:
        estado = definicion["States"][actual]
        orden.append((actual, estado))
        actual = None if estado.get("End") else estado.get("Next")
    return orden


def _definicion_resuelta() -> dict:
    """The state machine definition with each Fn::GetAtt/Ref of the template replaced by the logical id it names."""
    def texto(parte):
        if isinstance(parte, str):
            return parte
        if "Fn::GetAtt" in parte:
            return f"<{parte['Fn::GetAtt'][0]}>"
        if "Ref" in parte:
            return f"<{parte['Ref']}>"
        raise AssertionError(parte)
    (maquina,) = recursos("AWS::StepFunctions::StateMachine").values()
    cuerpo = maquina["Properties"]["DefinitionString"]
    if isinstance(cuerpo, dict):
        cuerpo = "".join(texto(p) for p in cuerpo["Fn::Join"][1])
    return json.loads(cuerpo)


def test_maquina_escribe_pendiente_espera_la_decision_y_la_registra():
    # Spec: the workflow writes the PENDING_APPROVAL request, waits for the task token, then the writer records the
    # decision. Approval and rejection both continue to the decision write (no Succeed or Catch that skips it).
    d = _definicion_resuelta()
    estados = _estados_en_orden(d)
    assert [n for n, _ in estados] == ["EscribirPropuesta", "RegistrarToken", "EscribirDecision"]
    proponer, espera, decidir = (e for _, e in estados)
    # payload_response_only: the writer's states pass the payload as their Parameters and keep only its result
    assert proponer["Parameters"]["operacion"] == "proponer" and "FuncionEscritor" in proponer["Resource"]
    assert espera["Resource"].endswith("waitForTaskToken") and espera["TimeoutSeconds"] == 24 * 3600
    assert espera["Parameters"]["Payload"]["orden.$"] == "$.orden"
    assert decidir["Parameters"] == {"operacion": "decidir", "po_id.$": "$.orden.po_id", "decision.$": "$.decision"}
    assert "FuncionEscritor" in decidir["Resource"] and decidir.get("End") is True
    assert not any(e.get("Catch") for _, e in estados) and set(d["States"]) == {n for n, _ in estados}


def test_grupos_del_trigger_existen_en_el_pool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import computo.tokens as T
    grupos = {r["Properties"]["GroupName"] for r in recursos("AWS::Cognito::UserPoolGroup").values()}
    assert grupos == set(T.GRUPOS_A_SCOPES), grupos   # every group the trigger knows, and no other (no old `aprobadores`)


def _limite_desplegado() -> list[dict]:
    """The boundary's Allow statements, from the control template synthesized next to the computo one."""
    import glob
    salida = Path(tempfile.mkdtemp(prefix="s19-limite-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1"}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    for ruta in glob.glob(str(salida / "*.template.json")):
        pl = json.loads(Path(ruta).read_text(encoding="utf-8"))
        for res in pl["Resources"].values():
            if res["Type"] == "AWS::IAM::ManagedPolicy" and res["Properties"].get("ManagedPolicyName") == "semana19-limite":
                return [s for s in res["Properties"]["PolicyDocument"]["Statement"] if s["Effect"] == "Allow"]
    raise AssertionError("no se encontró la política semana19-limite")


def _lista(valor) -> list:
    return valor if isinstance(valor, list) else [valor]


def test_cada_accion_de_los_roles_de_computo_cabe_en_el_limite():
    # A role's own policy is not enough: the boundary must allow the action too, or AWS answers implicitDeny
    # (the agent's model call failed live for this reason). Every action granted inline must match a boundary action.
    from fnmatch import fnmatchcase
    permitidas = [a for s in _limite_desplegado() for a in _lista(s["Action"])]
    faltan = []
    for n, pol in recursos("AWS::IAM::Policy").items():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            if st["Effect"] != "Allow":
                continue
            for accion in _lista(st["Action"]):
                if not any(fnmatchcase(accion, p) or fnmatchcase(p, accion) for p in permitidas):
                    faltan.append(f"{n}/{st.get('Sid', '-')}: {accion}")
    assert not faltan, faltan


def test_el_guardrail_del_agente_incluye_su_perfil_entre_regiones_y_la_decision_va_sobre_comodin():
    # ApplyGuardrail with us.guardrail.v1:0 is authorized against the profile in each destination Region, and
    # SendTaskSuccess/Failure take no resource type (AWS evaluates them against '*').
    declaraciones = {st.get("Sid"): st for pol in recursos("AWS::IAM::Policy").values()
                     for st in pol["Properties"]["PolicyDocument"]["Statement"]}
    guardrail = json.dumps(declaraciones["GuardrailDelAgente"]["Resource"])
    for region in ("us-east-1", "us-east-2", "us-west-2"):
        assert f"bedrock:{region}:" in guardrail and "guardrail-profile/us.guardrail.v1:0" in guardrail
    assert declaraciones["DecisionAlFlujo"]["Resource"] == "*"


@lru_cache(maxsize=None)
def _con_activos() -> tuple[Path, dict]:
    """Synthesis with asset metadata on (what the CDK CLI does), so each function names its asset folder."""
    salida = Path(tempfile.mkdtemp(prefix="s19-activos-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1",
               "CDK_CONTEXT_JSON": json.dumps({"aws:cdk:enable-asset-metadata": True})}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    plantilla = json.loads((salida / f"{COMPUTO}.template.json").read_text(encoding="utf-8"))
    return salida, {n: r for n, r in plantilla["Resources"].items() if r["Type"] == "AWS::Lambda::Function"}


def test_el_handler_de_cada_funcion_existe_en_su_propio_activo():
    # The tools function once pointed at app.herramientas... while its asset was semana-19/ (no app/): ImportModuleError
    # live. Every function's handler module must exist inside the asset folder CloudFormation deploys for it.
    salida, funciones = _con_activos()
    sin_activo = []
    for n, f in funciones.items():
        ruta = f.get("Metadata", {}).get("aws:asset:path")
        if ruta is None:
            sin_activo.append(n)
            continue
        modulo = f["Properties"]["Handler"].rsplit(".", 1)[0].replace(".", "/")
        base = salida / ruta
        assert any((base / f"{modulo}{ext}").is_file() for ext in (".py", ".js", ".mjs")), f"{n}: {modulo} no está en {ruta}"
    assert not sin_activo, sin_activo


def test_la_funcion_de_herramientas_lleva_su_guardia_su_driver_y_su_entorno():
    salida, funciones = _con_activos()
    (f,) = [f for n, f in funciones.items() if n.startswith("FuncionHerramientas")]
    base = salida / f["Metadata"]["aws:asset:path"]
    for pieza in ("semana-16/legacy-schema-audit/servidor/sql_lectura.py", "app/infra/loader/vendor/pg8000",
                  "app/herramientas/rds-ca.pem"):
        assert (base / pieza).exists(), pieza
    entorno = f["Properties"]["Environment"]["Variables"]
    assert {"HOST_BD", "ARN_APROBACION"} <= set(entorno)   # herramientas/construccion.REQUERIDAS (AWS_REGION is the runtime's)


def test_todo_rol_con_acceso_a_elementos_de_dynamodb_puede_descifrar_con_la_llave():
    # The tables are encrypted with the stack key: DynamoDB calls kms:Decrypt for item reads AND writes (live: the
    # token registrar's PutItem was denied when its grant lacked Decrypt). Every role with item access needs it.
    por_rol: dict[str, set] = {}
    for pol in recursos("AWS::IAM::Policy").values():
        acciones = {a for st in pol["Properties"]["PolicyDocument"]["Statement"] if st["Effect"] == "Allow"
                    for a in _lista(st["Action"])}
        for rol in pol["Properties"]["Roles"]:
            por_rol.setdefault(json.dumps(rol, sort_keys=True), set()).update(acciones)
    items = {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"}
    sin_decrypt = [r for r, acciones in por_rol.items() if acciones & items and "kms:Decrypt" not in acciones]
    assert not sin_decrypt, sin_decrypt


def _sintetizar_con(**extra) -> subprocess.CompletedProcess:
    salida = Path(tempfile.mkdtemp(prefix="s19-computo-espera-"))
    entorno = {**os.environ, "PERFIL": "lab", "CDK_OUTDIR": str(salida), "COMPUTO": "1", **extra}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    r.salida = salida
    return r


def test_la_espera_de_aprobacion_corta_de_la_actividad_8_llega_a_la_maquina():
    # Activity 8 deploys a short wait to show that an expired request writes no decision; 24 h stays the default.
    r = _sintetizar_con(S19_ESPERA_APROBACION_S="120")
    assert r.returncode == 0, r.stderr[-2000:]
    plantilla = json.loads((r.salida / f"{COMPUTO}.template.json").read_text(encoding="utf-8"))
    (maquina,) = (x for x in plantilla["Resources"].values() if x["Type"] == "AWS::StepFunctions::StateMachine")
    cuerpo = maquina["Properties"]["DefinitionString"]
    texto_cuerpo = cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo)
    assert '\\"TimeoutSeconds\\":120' in texto_cuerpo or '"TimeoutSeconds":120' in texto_cuerpo
    assert "86400" in texto_cuerpo  # the state machine's own timeout stays 24 h


@pytest.mark.parametrize("valor", ["30", "86401", "dos", "-5"])
def test_una_espera_de_aprobacion_fuera_de_rango_detiene_la_sintesis(valor):
    r = _sintetizar_con(S19_ESPERA_APROBACION_S=valor)
    assert r.returncode != 0 and "S19_ESPERA_APROBACION_S" in r.stderr
