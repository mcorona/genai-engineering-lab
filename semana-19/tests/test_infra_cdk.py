"""Week 19, activity 3: tests of the foundation stacks. Synthesis only ($0, no AWS calls).

Needs aws-cdk-lib: it runs in the spike-iac job (requirements pinned in semana-19/spike/cdk/requirements.txt), and
sin-aws ignores this file. Set S19_REGENERAR=1 to rewrite the snapshot after an intended change.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "infra_lab.json"
sys.path.insert(0, str(S19 / "infra" / "cdk"))
from excepciones import EXCEPCIONES  # noqa: E402

PERFILES = ["lab", "prod"]
CONTROL, BASE, DATOS = "semana19-control", "semana19-base", "semana19-datos"
ARN_LIMITE = "policy/semana19-limite"


@lru_cache(maxsize=None)
def sintetizar(perfil: str) -> dict:
    salida = Path(tempfile.mkdtemp(prefix=f"s19-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida)}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    plantillas = {n: json.loads((salida / f"{n}.template.json").read_text(encoding="utf-8")) for n in (CONTROL, BASE, DATOS)}
    informes = {n: list(csv.DictReader((salida / f"AwsSolutions--{n}-NagReport.csv").open(encoding="utf-8")))
                for n in (CONTROL, BASE, DATOS)}
    return {"plantillas": plantillas, "nag": informes}


def texto(x) -> str:
    """Rendered value as text; intrinsic functions become readable placeholders."""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return "".join(texto(v) for v in x)
    if isinstance(x, dict):
        if "Ref" in x:
            return "{" + str(x["Ref"]) + "}"
        if "Fn::Join" in x:
            sep, partes = x["Fn::Join"]
            return sep.join(texto(v) for v in partes)
        if "Fn::Sub" in x:
            return texto(x["Fn::Sub"] if isinstance(x["Fn::Sub"], str) else x["Fn::Sub"][0])
        return json.dumps(x, sort_keys=True)
    return str(x)


def declaraciones(plantilla: dict):
    """Yields (logical id, type, statement) for every statement in IAM and KMS documents."""
    for lid, r in plantilla["Resources"].items():
        tipo, p = r["Type"], r.get("Properties", {})
        documentos = []
        if tipo in ("AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"):
            documentos.append(p.get("PolicyDocument"))
        if tipo == "AWS::IAM::Role":
            documentos += [x.get("PolicyDocument") for x in p.get("Policies", [])]
        if tipo == "AWS::KMS::Key":
            documentos.append(p.get("KeyPolicy"))
        for d in documentos:
            for st in (d or {}).get("Statement", []):
                yield lid, tipo, st


def recursos(plantilla: dict, tipo: str):
    return {lid: r for lid, r in plantilla["Resources"].items() if r["Type"] == tipo}


def de_control(perfil):
    return sintetizar(perfil)["plantillas"][CONTROL]


def de_base(perfil):
    return sintetizar(perfil)["plantillas"][BASE]


# ---------------------------------------------------------------- synthesis and cdk-nag


@pytest.mark.parametrize("perfil", PERFILES)
def test_los_tres_stacks_sintetizan_en_cada_perfil(perfil):
    s = sintetizar(perfil)
    assert set(s["plantillas"]) == {CONTROL, BASE, DATOS}


@pytest.mark.parametrize("perfil", PERFILES)
def test_cdk_nag_sin_hallazgos_sin_suprimir(perfil):
    for stack, informe in sintetizar(perfil)["nag"].items():
        no_cumplen = [r for r in informe if r["Compliance"] == "Non-Compliant"]
        assert no_cumplen == [], f"{stack}: {len(no_cumplen)} sin suprimir"


@pytest.mark.parametrize("perfil", PERFILES)
def test_cada_supresion_de_cdk_nag_tiene_razon(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for lid, r in pl["Resources"].items():
            reglas = (r.get("Metadata", {}).get("cdk_nag", {}) or {}).get("rules_to_suppress", [])
            for regla in reglas:
                assert regla.get("reason", "").strip(), f"{n}/{lid} {regla.get('id')} sin razón"


@pytest.mark.parametrize("perfil", PERFILES)
def test_checkov_sin_fallos_con_omisiones_con_razon(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for lid, r in pl["Resources"].items():
            for omision in (r.get("Metadata", {}).get("checkov", {}) or {}).get("skip", []):
                assert omision.get("comment", "").strip(), f"{n}/{lid} {omision.get('id')} sin comentario"


# ---------------------------------------------------------------- identity and boundary


@pytest.mark.parametrize("perfil", PERFILES)
def test_todo_rol_creado_por_los_stacks_tiene_el_limite(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for lid, r in recursos(pl, "AWS::IAM::Role").items():
            limite = texto(r["Properties"].get("PermissionsBoundary", ""))
            esperado = ARN_LIMITE
            assert esperado in limite, f"{n}/{lid} sin el permission boundary que le toca"


@pytest.mark.parametrize("perfil", PERFILES)
def test_no_hay_rol_sin_limite_aunque_lo_genere_cdk(perfil):
    # Custom resource roles are CfnRole too; the aspect reaches them. Count must match the role count.
    for pl in sintetizar(perfil)["plantillas"].values():
        roles = recursos(pl, "AWS::IAM::Role")
        con_limite = [lid for lid, r in roles.items() if "PermissionsBoundary" in r["Properties"]]
        assert len(con_limite) == len(roles)


@pytest.mark.parametrize("perfil", PERFILES)
def test_despliegue_crea_roles_solo_con_limite(perfil):
    pl = de_control(perfil)
    crear = [st for lid, _, st in declaraciones(pl) if "iam:CreateRole" in json.dumps(st.get("Action", []))]
    assert crear, "no hay statement que permita crear roles"
    for st in crear:
        assert st.get("Effect") == "Allow"
        assert "iam:PermissionsBoundary" in json.dumps(st.get("Condition", {}))


@pytest.mark.parametrize("perfil", PERFILES)
def test_despliegue_no_quita_ni_cambia_el_limite(perfil):
    deny = [st for _, _, st in declaraciones(de_control(perfil)) if st.get("Effect") == "Deny"]
    acciones = " ".join(texto(st.get("Action", "")) for st in deny)
    assert "iam:DeleteRolePermissionsBoundary" in acciones and "iam:PutRolePermissionsBoundary" in acciones


# ---------------------------------------------------------------- encryption and logs


@pytest.mark.parametrize("perfil", PERFILES)
def test_todos_los_grupos_de_logs_usan_la_llave_y_tienen_retencion(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for lid, r in recursos(pl, "AWS::Logs::LogGroup").items():
            assert "KmsKeyId" in r["Properties"], f"{n}/{lid} sin llave"
            assert r["Properties"].get("RetentionInDays"), f"{n}/{lid} sin retención"


@pytest.mark.parametrize("perfil", PERFILES)
def test_llave_tiene_rotacion_y_alias(perfil):
    llaves = recursos(de_base(perfil), "AWS::KMS::Key")
    assert len(llaves) == 1
    (r,) = llaves.values()
    assert r["Properties"]["EnableKeyRotation"] is True
    assert r["Properties"]["PendingWindowInDays"] == {"lab": 7, "prod": 30}[perfil]


@pytest.mark.parametrize("perfil", PERFILES)
def test_politica_de_llave_sin_principal_comodin(perfil):
    for lid, tipo, st in declaraciones(de_base(perfil)):
        if tipo == "AWS::KMS::Key" and st.get("Principal") in ("*", {"AWS": "*"}):
            assert st.get("Condition"), f"{lid} Principal * sin condición"


@pytest.mark.parametrize("perfil", PERFILES)
def test_roles_de_llave_con_nombre_y_servicio_con_contexto(perfil):
    st = {s.get("Sid"): s for _, _, s in declaraciones(de_base(perfil))}
    assert "RolesConNombre" in st and "LogsDelProyectoConLaLlave" in st
    assert "EncryptionContext" in json.dumps(st["LogsDelProyectoConLaLlave"].get("Condition", {}))


# ---------------------------------------------------------------- network


@pytest.mark.parametrize("perfil", PERFILES)
def test_ninguna_regla_de_entrada_admite_internet_ni_cidr_abierto(perfil):
    """Every inbound rule (inline or standalone) names a security group as its source. No CIDR at all: a rule with
    0.0.0.0/0, ::/0 or any other CIDR fails here, and so does a rule with no source."""
    for n, pl in sintetizar(perfil)["plantillas"].items():
        reglas = []
        for lid, r in recursos(pl, "AWS::EC2::SecurityGroup").items():
            reglas += [(f"{n}/{lid}", x) for x in r["Properties"].get("SecurityGroupIngress", [])]
        reglas += [(f"{n}/{lid}", r["Properties"]) for lid, r in recursos(pl, "AWS::EC2::SecurityGroupIngress").items()]
        for origen, regla in reglas:
            assert "CidrIp" not in regla and "CidrIpv6" not in regla and "PrefixListIds" not in regla, origen
            assert regla.get("SourceSecurityGroupId") is not None, origen
            assert regla.get("CidrIp") != "0.0.0.0/0" and regla.get("CidrIpv6") != "::/0", origen


@pytest.mark.parametrize("perfil", PERFILES)
def test_sin_nat_sin_internet_gateway_ni_subredes_publicas(perfil):
    pl = de_base(perfil)
    assert recursos(pl, "AWS::EC2::NatGateway") == {}
    assert recursos(pl, "AWS::EC2::InternetGateway") == {}
    assert recursos(pl, "AWS::EC2::EgressOnlyInternetGateway") == {}
    for lid, r in recursos(pl, "AWS::EC2::Subnet").items():
        assert r["Properties"].get("MapPublicIpOnLaunch") in (None, False), f"{lid} pública"


@pytest.mark.parametrize("perfil", PERFILES)
def test_dos_subredes_privadas_por_lo_menos(perfil):
    subredes = recursos(de_base(perfil), "AWS::EC2::Subnet")
    assert len(subredes) >= 2


@pytest.mark.parametrize("perfil", PERFILES)
def test_endpoints_son_exactamente_los_del_adr_0005(perfil):
    pl = de_base(perfil)
    interfaz = {}
    gateway = {}
    for lid, r in recursos(pl, "AWS::EC2::VPCEndpoint").items():
        p = r["Properties"]
        servicio = texto(p["ServiceName"]).split(".")[-1]
        if p["VpcEndpointType"] == "Interface":
            interfaz[servicio] = p
        else:
            gateway[servicio] = p
    assert set(interfaz) == {"logs", "states"}
    assert set(gateway) == {"s3"}
    for servicio, p in interfaz.items():
        assert p["PrivateDnsEnabled"] is True
        assert len(p["SubnetIds"]) == {"lab": 1, "prod": 3}[perfil], f"{servicio} en AZ de más o de menos"


@pytest.mark.parametrize("perfil", PERFILES)
def test_endpoints_limitados_a_la_cuenta(perfil):
    for lid, r in recursos(de_base(perfil), "AWS::EC2::VPCEndpoint").items():
        assert "aws:PrincipalAccount" in json.dumps(r["Properties"]["PolicyDocument"]), lid


@pytest.mark.parametrize("perfil", PERFILES)
def test_grupo_de_endpoints_solo_acepta_443_desde_la_lambda(perfil):
    pl = de_base(perfil)
    sgs = recursos(pl, "AWS::EC2::SecurityGroup")
    endpoints = [lid for lid in sgs if "SgEndpoints" in lid]
    herramientas = [lid for lid in sgs if "SgHerramientas" in lid]
    assert herramientas and endpoints
    # Cross-group rules are separate AWS::EC2::SecurityGroupIngress resources in CDK's output.
    reglas = [r["Properties"] for r in recursos(pl, "AWS::EC2::SecurityGroupIngress").values()]
    reglas += [r for r in sgs[endpoints[0]]["Properties"].get("SecurityGroupIngress", [])]
    assert reglas, "el grupo de endpoints no tiene entrada"
    assert all(r["FromPort"] == 443 and r["ToPort"] == 443 for r in reglas)
    assert all(r.get("IpProtocol") == "tcp" for r in reglas)
    assert any(herramientas[0] in texto(r.get("SourceSecurityGroupId", "")) for r in reglas)


@pytest.mark.parametrize("perfil", PERFILES)
def test_flow_logs_con_retencion_del_perfil(perfil):
    pl = de_base(perfil)
    flujos = recursos(pl, "AWS::EC2::FlowLog")
    assert len(flujos) == 1
    grupo = [r for r in recursos(pl, "AWS::Logs::LogGroup").values()
             if "flowlogs" in texto(r["Properties"].get("LogGroupName", ""))]
    assert grupo and grupo[0]["Properties"]["RetentionInDays"] == {"lab": 1, "prod": 365}[perfil]


# ---------------------------------------------------------------- spend controls


@pytest.mark.parametrize("perfil", PERFILES)
def test_accion_del_presupuesto_congela_al_100_por_ciento(perfil):
    pl = de_control(perfil)
    (accion,) = recursos(pl, "AWS::Budgets::BudgetsAction").values()
    p = accion["Properties"]
    assert p["ActionType"] == "APPLY_IAM_POLICY"
    assert p["ActionThreshold"] == {"Type": "PERCENTAGE", "Value": 100}
    roles = json.dumps(p["Definition"]["IamActionDefinition"]["Roles"])
    assert "semana19-despliegue" in roles
    assert "cdk-s19-deploy-role-" in roles and "cdk-s19-cfn-exec-role-" in roles
    assert "Fn::If" in roles and "HayBootstrap" in roles


@pytest.mark.parametrize("perfil", PERFILES)
def test_bootstrap_creado_es_parametro_y_por_omision_es_false(perfil):
    pl = de_control(perfil)
    p = pl["Parameters"]["BootstrapCreado"]
    assert p["Default"] == "false" and set(p["AllowedValues"]) == {"true", "false"}


@pytest.mark.parametrize("perfil", PERFILES)
def test_presupuesto_con_tres_alertas(perfil):
    (presupuesto,) = recursos(de_control(perfil), "AWS::Budgets::Budget").values()
    avisos = presupuesto["Properties"]["NotificationsWithSubscribers"]
    tipos = sorted((a["Notification"]["NotificationType"], a["Notification"]["Threshold"]) for a in avisos)
    assert tipos == [("ACTUAL", 50), ("ACTUAL", 100), ("FORECASTED", 100)]


@pytest.mark.parametrize("perfil", PERFILES)
def test_presupuesto_mensual_de_50_usd(perfil):
    """Manuel's cap for week 19 is USD 10 per week (2026-11-18). AWS Budgets has no weekly period, so the limit is
    monthly: USD 50, his choice (above the weekly cap's 42.86 per month)."""
    (presupuesto,) = recursos(de_control(perfil), "AWS::Budgets::Budget").values()
    datos = presupuesto["Properties"]["Budget"]
    assert datos["TimeUnit"] == "MONTHLY" and datos["BudgetType"] == "COST"
    assert float(datos["BudgetLimit"]["Amount"]) == 50.0 and datos["BudgetLimit"]["Unit"] == "USD"


@pytest.mark.parametrize("perfil", PERFILES)
def test_la_congelacion_no_bloquea_borrar(perfil):
    congelacion = [st for _, _, st in declaraciones(de_control(perfil))
                   if st.get("Sid") == "NoCrearNiActualizarMientrasEsteActiva"]
    assert len(congelacion) == 1 and congelacion[0]["Effect"] == "Deny"
    acciones = [a for st in congelacion for a in (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])]
    assert acciones, "la congelación no tiene acciones"
    prohibidas = re.compile(r"(Delete|Remove|Detach|Terminate|Revoke|Schedule|Cancel|Disable)", re.IGNORECASE)
    assert not [a for a in acciones if prohibidas.search(a)], "la congelación bloquea borrado"
    verbos = re.compile(r"^[a-z0-9-]+:(Create|Update|Put|Attach|Modify|Associate|Authorize|Enable|TagResource|Execute)")
    assert all(verbos.search(a) for a in acciones), [a for a in acciones if not verbos.search(a)]


@pytest.mark.parametrize("perfil", PERFILES)
def test_sin_monitor_de_anomalias_hasta_confirmar_su_precio(perfil):
    # Cost Anomaly Detection price is N (not in the Price List, not on the official page): not in the stack.
    assert recursos(de_control(perfil), "AWS::CE::AnomalyMonitor") == {}
    assert recursos(de_control(perfil), "AWS::CE::AnomalySubscription") == {}


# ---------------------------------------------------------------- wildcards and naming


def _plantilla_computo(perfil: str, pila: str = "semana19-computo") -> dict:
    """The compute stack (COMPUTO=1) is scanned too: its wildcards are in the same register. So is the judge's
    stack semana19-eval (activity 8), synthesized with it."""
    salida = Path(tempfile.mkdtemp(prefix=f"s19-computo-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1"}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads((salida / f"{pila}.template.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("perfil", PERFILES)
def test_comodines_coinciden_con_el_registro(perfil):
    usados = set()
    plantillas = list(sintetizar(perfil)["plantillas"].values()) + [_plantilla_computo(perfil),
                                                                    _plantilla_computo(perfil, "semana19-eval")]
    for pl in plantillas:
        for _, _, st in declaraciones(pl):
            if "*" in texto(st.get("Action", "")) or "*" in texto(st.get("Resource", "")):
                usados.add(st.get("Sid", "-"))
    assert usados == set(EXCEPCIONES), (
        f"sin registro: {sorted(usados - set(EXCEPCIONES))}; obsoletos: {sorted(set(EXCEPCIONES) - usados)}")


@pytest.mark.parametrize("perfil", PERFILES)
def test_no_hay_cuenta_ni_correo_en_las_plantillas(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        texto_pl = json.dumps(pl)
        assert not re.search(r"\b\d{12}\b", texto_pl), f"{n} contiene un número de 12 dígitos"
        assert "000000000000" not in texto_pl
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texto_pl), f"{n} contiene un correo"


@pytest.mark.parametrize("perfil", PERFILES)
def test_control_sin_assets_ni_version_de_bootstrap(perfil):
    pl = de_control(perfil)
    assert set(pl.get("Parameters", {})) == {"CorreoAlerta", "BootstrapCreado"}


# ---------------------------------------------------------------- profiles


def test_prod_cambia_solo_lo_que_dice_el_perfil():
    lab, prod = de_base("lab"), de_base("prod")
    llave_lab = next(iter(recursos(lab, "AWS::KMS::Key").values()))
    llave_prod = next(iter(recursos(prod, "AWS::KMS::Key").values()))
    assert llave_lab["DeletionPolicy"] == "Delete" and llave_prod["DeletionPolicy"] == "Retain"
    assert llave_lab["Properties"]["PendingWindowInDays"] == 7
    assert llave_prod["Properties"]["PendingWindowInDays"] == 30


# ---------------------------------------------------------------- snapshot


def _instantanea() -> dict:
    s = sintetizar("lab")["plantillas"]
    salida = {}
    for n, pl in s.items():
        salida[n] = sorted([re.sub(r"[0-9A-F]{8}$", "", lid), r["Type"]] for lid, r in pl["Resources"].items())
    return salida


def test_instantanea_del_synth_de_lab():
    actual = _instantanea()
    if os.environ.get("S19_REGENERAR") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    esperado = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert actual == esperado


# ---------------------------------------------------------------- scripts (no AWS)

SCRIPTS = S19 / "infra"


def _entorno_falso(tmp_path: Path) -> tuple[dict, Path]:
    """aws and cdk fakes first in PATH. Any call writes a marker and fails, so a passing test proves no call."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marcas = tmp_path / "marcas"
    for nombre in ("aws", "cdk"):
        f = bin_dir / nombre
        f.write_text(f'#!/usr/bin/env bash\necho "{nombre} $*" >> "{marcas}"\nexit 99\n', encoding="utf-8")
        f.chmod(0o755)
    entorno = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
               "S19_PYTHON": sys.executable, "TMPDIR": str(tmp_path)}
    entorno.pop("ALERTA_EMAIL", None)
    return entorno, marcas


@pytest.mark.parametrize("script", ["desplegar.sh", "destruir.sh"])
def test_scripts_tienen_sintaxis_valida(script):
    r = subprocess.run(["bash", "-n", str(SCRIPTS / script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_desplegar_sin_si_no_llama_a_aws(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    r = subprocess.run(["bash", str(SCRIPTS / "desplegar.sh")], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert not marcas.exists(), marcas.read_text() if marcas.exists() else ""
    assert "No se llamó a AWS" in r.stdout


def test_destruir_sin_si_no_llama_a_aws(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    r = subprocess.run(["bash", str(SCRIPTS / "destruir.sh")], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert not marcas.exists()
    assert "No se llamó a AWS" in r.stdout


def test_desplegar_si_sin_correo_se_detiene_antes_de_aws(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    r = subprocess.run(["bash", str(SCRIPTS / "desplegar.sh"), "--si"], env=entorno, capture_output=True, text=True)
    assert r.returncode == 2
    assert "ALERTA_EMAIL" in r.stderr
    assert not marcas.exists()


def test_solo_control_despliega_control_y_bootstrap_y_nada_mas(tmp_path):
    """--solo-control --si: semana19-control and the bootstrap only. The fakes answer OK and record every call."""
    entorno, marcas = _entorno_falso(tmp_path)
    for nombre in ("aws", "cdk"):
        (tmp_path / "bin" / nombre).write_text(
            f'#!/usr/bin/env bash\necho "{nombre} $*" >> "{marcas}"\necho falso\nexit 0\n', encoding="utf-8")
    (tmp_path / "bin" / "cdk").write_text(   # cdk prints the account in its ARNs (seen in the real run of 2026-11-18)
        f'#!/usr/bin/env bash\necho "cdk $*" >> "{marcas}"\necho "Trusted: arn:aws:iam::falso:role/x"\nexit 0\n',
        encoding="utf-8")
    entorno["ALERTA_EMAIL"] = "alertas" + chr(64) + "ejemplo.invalid"  # built, so the repo holds no address
    registro = S19 / "resultados" / "tiempos_despliegue.jsonl"
    antes = registro.read_bytes() if registro.exists() else None
    try:
        r = subprocess.run(["bash", str(SCRIPTS / "desplegar.sh"), "--solo-control", "--si"], env=entorno,
                           capture_output=True, text=True)
    finally:  # the fake run must not leave timing lines in the repo's log
        if antes is None:
            registro.unlink(missing_ok=True)
        else:
            registro.write_bytes(antes)
    assert r.returncode == 0, r.stderr[-800:]
    llamadas = marcas.read_text().splitlines()
    assert any("cloudformation deploy --stack-name semana19-control" in l for l in llamadas)
    assert any(l.startswith("cdk bootstrap") for l in llamadas)
    assert not any(l.startswith("cdk deploy") or "lambda invoke" in l or "start-ingestion-job" in l for l in llamadas)
    assert any("--s3-bucket falso" in l for l in llamadas if "cloudformation deploy" in l)  # the bootstrap's bucket
    assert "arn:aws:iam::<account>:role/x" in r.stdout and "iam::falso" not in r.stdout   # the account never prints


def test_solo_control_sin_correo_conserva_el_del_stack(tmp_path):
    """--solo-control --si without ALERTA_EMAIL, with semana19-control deployed: CorreoAlerta is not overridden, so
    CloudFormation keeps the stack's value; the address is never needed nor printed (2026-11-18)."""
    entorno, marcas = _entorno_falso(tmp_path)
    for nombre in ("aws", "cdk"):
        (tmp_path / "bin" / nombre).write_text(
            f'#!/usr/bin/env bash\necho "{nombre} $*" >> "{marcas}"\necho falso\nexit 0\n', encoding="utf-8")
    entorno.pop("ALERTA_EMAIL", None)
    registro = S19 / "resultados" / "tiempos_despliegue.jsonl"
    antes = registro.read_bytes() if registro.exists() else None
    try:
        r = subprocess.run(["bash", str(SCRIPTS / "desplegar.sh"), "--solo-control", "--si"], env=entorno,
                           capture_output=True, text=True)
    finally:
        if antes is None:
            registro.unlink(missing_ok=True)
        else:
            registro.write_bytes(antes)
    assert r.returncode == 0, r.stderr[-800:]
    (deploy,) = [l for l in marcas.read_text().splitlines() if "cloudformation deploy --stack-name semana19-control" in l]
    assert "CorreoAlerta" not in deploy and "BootstrapCreado=true" in deploy
    assert "conserva su CorreoAlerta" in r.stdout


def test_sin_correo_y_sin_stack_de_control_se_detiene(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    (tmp_path / "bin" / "aws").write_text(f'#!/usr/bin/env bash\necho "aws $*" >> "{marcas}"\nexit 254\n',
                                         encoding="utf-8")
    entorno.pop("ALERTA_EMAIL", None)
    r = subprocess.run(["bash", str(SCRIPTS / "desplegar.sh"), "--solo-control", "--si"], env=entorno,
                       capture_output=True, text=True)
    assert r.returncode == 2 and "ALERTA_EMAIL" in r.stderr
    assert "cloudformation deploy" not in (marcas.read_text() if marcas.exists() else "")


def test_argumentos_desconocidos_salen_con_2(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    for script in ("desplegar.sh", "destruir.sh"):
        r = subprocess.run(["bash", str(SCRIPTS / script), "--borrar-todo"], env=entorno, capture_output=True, text=True)
        assert r.returncode == 2
    assert not marcas.exists()


@pytest.mark.parametrize("script", ["desplegar.sh", "destruir.sh", "vaciar_bootstrap.py", "inventario.py", "vaciar_eval.py", "vaciar_datos.py"])
def test_scripts_sin_cuenta_ni_correo_ni_llaves(script):
    texto_script = (SCRIPTS / script).read_text(encoding="utf-8")
    assert not re.search(r"\b\d{12}\b", texto_script)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", texto_script)
    assert "AKIA" not in texto_script


def test_inventario_permitidos_son_explicitos():
    import importlib.util

    spec = importlib.util.spec_from_file_location("inv", SCRIPTS / "inventario.py")
    inv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inv)
    sin_control = inv.permitidos(False)
    assert set(sin_control) == {"roles_iam", "llaves_pendientes_borrado"}
    assert sin_control["roles_iam"] == {"semana19-lectura"}
    con_control = inv.permitidos(True)
    assert con_control["stacks_cloudformation"] == {"semana19-control"}
    assert not any("cdktoolkit" in str(v) for v in con_control.values())
    antes = inv.permitidos(True, con_base=True)
    assert antes["stacks_cloudformation"] == {"semana19-control", "semana19-base", "semana19-cdktoolkit"}
    assert antes["vpcs"] is None and antes["lambdas"] is None
    despues = inv.permitidos(True)
    assert "vpcs" not in despues and "semana19-base" not in despues["stacks_cloudformation"]


def test_categoria_vacia_con_subclaves_no_cuenta_como_recurso():
    # RDS returns {"instancias": [], "clusters": []}: empty, must not be reported as a leftover.
    import importlib.util
    spec = importlib.util.spec_from_file_location("inv2", SCRIPTS / "inventario.py")
    inv = importlib.util.module_from_spec(spec); spec.loader.exec_module(inv)
    assert inv.contar({"instancias": [], "clusters": []}) == 0
    assert inv.contar({"instancias": ["x"], "clusters": []}) == 1


def test_scripts_de_infra_son_ejecutables_en_git():
    import subprocess
    for script in ["semana-19/infra/desplegar.sh", "semana-19/infra/destruir.sh"]:
        modo = subprocess.run(["git", "ls-files", "-s", script], capture_output=True, text=True,
                              cwd=S19.parent).stdout.split()[0]
        assert modo == "100755", script
def test_destruir_no_pasa_toolkit_a_cdk_destroy_y_usa_python_con_boto():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    destroy = [l for l in texto.splitlines() if "cdk destroy" in l]
    assert destroy and not any("--toolkit-stack-name" in l for l in destroy)
    assert "PYTHON_BOTO" in texto and '"$PYTHON_BOTO" "$RAIZ/semana-19/infra/inventario.py"' in texto
    assert '"$PYTHON_BOTO" "$RAIZ/semana-19/infra/vaciar_bootstrap.py"' in texto


def test_vaciar_borra_el_bucket_retenido_despues_de_vaciarlo():
    texto = (SCRIPTS / "vaciar_bootstrap.py").read_text(encoding="utf-8")
    assert "delete_bucket(Bucket=r[\"bucket\"])" in texto


def test_vaciar_no_pagina_operaciones_no_paginables():
    texto = (SCRIPTS / "vaciar_bootstrap.py").read_text(encoding="utf-8")
    assert 'get_paginator("describe_stack_resources")' not in texto


def test_destruir_reintenta_base_en_delete_failed_reteniendo_solo_el_custom_resource():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    assert "DELETE_FAILED" in texto and "--retain-resources" in texto
    assert "Custom::VpcRestrictDefaultSG" in texto
    assert "--retain-resources \"$retenidos\"" in texto or "--retain-resources \\\"$retenidos" in texto or "--retain-resources" in texto
def test_llaves_pendientes_se_buscan_por_estado_no_por_alias():
    # CloudFormation removes the alias together with the key: the search must not depend on it.
    texto = (SCRIPTS / "inventario.py").read_text(encoding="utf-8")
    assert "list_keys" in texto and "PendingDeletion" in texto and "list_resource_tags" in texto


def test_destruir_evalua_delete_failed_antes_que_cdk_destroy():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    assert texto.index('== "DELETE_FAILED"') < texto.index("cdk destroy semana19-base --force")
    assert "elif [[ \"$ESTADO_BASE\" != \"NO_EXISTE\" ]]" in texto


# ---------------------------------------------------------------- cifrado y un rol por función (plan, actividad 3)

# Recursos cifrables y la propiedad que los ata a la llave. Lambda cuenta solo si tiene variables de entorno.
CIFRABLES = {
    "AWS::Logs::LogGroup": "KmsKeyId",
    "AWS::SQS::Queue": "KmsMasterKeyId",
    "AWS::SNS::Topic": "KmsMasterKeyId",
    "AWS::S3::Bucket": "BucketEncryption",
    "AWS::ECR::Repository": "EncryptionConfiguration",
    "AWS::RDS::DBInstance": "KmsKeyId",
}


# The project key as the base stack exports it (ARN) and as the base template names it (logical id).
LLAVE_DEL_PROYECTO = ("Llave0AEC6D4F", "semana19-base:ExportsOutputFnGetAttLlave0AEC6D4FArn4D8B99D4")


def _usa_la_llave_del_proyecto(valor) -> bool:
    """True when a property value points at the project key: a reference to the key in the base template, or the
    export that another stack imports. Any other key (AWS managed, another key) fails."""
    texto_valor = json.dumps(valor, sort_keys=True)
    return any(marca in texto_valor for marca in LLAVE_DEL_PROYECTO)


@pytest.mark.parametrize("perfil", PERFILES)
def test_cada_recurso_cifrable_apunta_a_la_llave_del_proyecto(perfil):
    """Stronger than checking that the property exists: the value must point at the project key, so a resource that
    names an AWS managed key or another key fails. Lambda counts only when it has environment variables."""
    vistos = set()
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for tipo, prop in CIFRABLES.items():
            for lid, r in recursos(pl, tipo).items():
                vistos.add(tipo)
                assert prop in r["Properties"], f"{n}/{lid} ({tipo}) sin {prop}"
                assert _usa_la_llave_del_proyecto(r["Properties"][prop]), f"{n}/{lid} ({tipo}) no usa la llave del proyecto"
        for lid, r in recursos(pl, "AWS::Lambda::Function").items():
            if r["Properties"].get("Environment"):
                vistos.add("AWS::Lambda::Function")
                assert _usa_la_llave_del_proyecto(r["Properties"].get("KmsKeyArn")), f"{n}/{lid} con variables sin la llave"
    # Not vacuous: the stacks must contain the encryptable types this test is about.
    assert {"AWS::Logs::LogGroup", "AWS::S3::Bucket", "AWS::RDS::DBInstance"} <= vistos


@pytest.mark.parametrize("perfil", PERFILES)
def test_cada_funcion_y_flujo_de_logs_tiene_su_propio_rol(perfil):
    # Un rol por función: cada Lambda y cada flow log consume un rol distinto, y ningún rol se comparte.
    for n, pl in sintetizar(perfil)["plantillas"].items():
        consumidores = []
        for lid, r in recursos(pl, "AWS::Lambda::Function").items():
            consumidores.append(r["Properties"]["Role"]["Fn::GetAtt"][0])
        for lid, r in recursos(pl, "AWS::EC2::FlowLog").items():
            consumidores.append(r["Properties"]["DeliverLogsPermissionArn"]["Fn::GetAtt"][0])
        assert len(consumidores) == len(set(consumidores)), f"{n}: un rol consumido por más de una función"


@pytest.mark.parametrize("perfil", PERFILES)
def test_solo_el_despliegue_o_un_rol_documentado_crea_roles_y_siempre_con_limite(perfil):
    from excepciones import ROLES_QUE_PUEDEN_CREAR_ROLES as DOCUMENTADOS

    control = sintetizar(perfil)["plantillas"][CONTROL]["Resources"]
    duenos_con_creacion = set()
    for lid, r in control.items():
        if r["Type"] not in ("AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"):
            continue
        for st in r["Properties"]["PolicyDocument"]["Statement"]:
            acciones = st.get("Action", [])
            acciones = [acciones] if isinstance(acciones, str) else acciones
            if st.get("Effect") != "Allow" or "iam:CreateRole" not in acciones:
                continue
            dueno = "Despliegue" if lid.startswith("DespliegueDefaultPolicy") else (
                "EjecucionCfn" if lid.startswith("EjecucionCfn") else lid)
            duenos_con_creacion.add(dueno)
            assert "PermissionsBoundary" in json.dumps(st.get("Condition", {})), f"{lid} crea roles sin boundary"
            assert ARN_LIMITE in texto(st.get("Condition", {})), f"{lid} crea roles con otro boundary"
    assert duenos_con_creacion <= {"Despliegue"} | set(DOCUMENTADOS), f"crean roles sin documentar: {duenos_con_creacion}"
    assert set(DOCUMENTADOS) <= duenos_con_creacion, "excepción documentada que ya no crea roles"


# ---------------------------------------------------------------- base de datos (actividad 4, primera rebanada)

@pytest.mark.parametrize("perfil", PERFILES)
def test_base_de_datos_cifrada_privada_sin_acceso_publico_con_iam(perfil):
    bd = recursos(sintetizar(perfil)["plantillas"][DATOS], "AWS::RDS::DBInstance")
    assert len(bd) == 1
    p = next(iter(bd.values()))["Properties"]
    assert p["StorageEncrypted"] is True and "KmsKeyId" in p
    assert p["PubliclyAccessible"] is False
    assert p["EnableIAMDatabaseAuthentication"] is True
    assert p["MultiAZ"] is False
    assert p["Engine"] == "postgres" and p["DBInstanceClass"] == "db.t4g.micro"
    assert p["AllocatedStorage"] in ("20", 20) and p["StorageType"] == "gp3"
    assert p["BackupRetentionPeriod"] in (1, "1")


@pytest.mark.parametrize("perfil", PERFILES)
def test_postgres_solo_desde_el_cargador(perfil):
    # Ingress is only from the loader security group: 5432 to the database, 443 to the Secrets Manager endpoint.
    pl = sintetizar(perfil)["plantillas"][DATOS]
    ingresos = [r["Properties"] for r in recursos(pl, "AWS::EC2::SecurityGroupIngress").values()]
    assert ingresos, "sin reglas de entrada"
    for r in ingresos:
        assert "CidrIp" not in r and "SourceSecurityGroupId" in r
    bd = [r for r in ingresos if r["FromPort"] == 5432]
    assert len(bd) == 1
    assert "KmsKeyId" not in json.dumps(bd)



def test_desplegar_crea_datos_despues_de_la_base():
    texto = (SCRIPTS / "desplegar.sh").read_text(encoding="utf-8")
    assert texto.index("cdk deploy semana19-base") < texto.index("cdk deploy semana19-datos")


def test_destruir_borra_datos_antes_que_la_red():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    assert texto.index("cdk destroy semana19-datos") < texto.index("cdk destroy semana19-base --force")


def test_destruir_vacia_el_bucket_versionado_de_documentos_antes_de_borrar_datos():
    """2026-11-19: semana19-datos ended DELETE_FAILED on DocsKb (versioned, no auto-delete, S3 409)."""
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    vaciado = texto.index('vaciar_datos.py" --perfil "$PERFIL_ADMIN" --region "$REGION" --si')
    assert texto.index("if existe_stack semana19-datos") < vaciado < texto.index("cdk destroy semana19-datos --force")


def test_vaciar_datos_encuentra_solo_el_bucket_de_documentos_que_queda():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vaciar_datos", SCRIPTS / "vaciar_datos.py")
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)

    class Cfn:
        def __init__(self, recursos=None, error=None):
            self.recursos, self.error = recursos, error

        def describe_stack_resources(self, StackName):
            assert StackName == "semana19-datos"
            if self.error:
                raise self.error
            return {"StackResources": self.recursos}

    def r(logico, tipo="AWS::S3::Bucket", estado="DELETE_FAILED", fisico="b-docs"):
        return {"LogicalResourceId": logico, "ResourceType": tipo, "ResourceStatus": estado, "PhysicalResourceId": fisico}

    assert V.bucket_de_documentos(Cfn([r("DocsKb68D14A8C"), r("BaseDeDatos", "AWS::RDS::DBInstance")])) == "b-docs"
    assert V.bucket_de_documentos(Cfn([r("DocsKb68D14A8C", estado="DELETE_COMPLETE")])) is None
    assert V.bucket_de_documentos(Cfn([r("OtroBucket")])) is None
    assert V.bucket_de_documentos(Cfn(error=Exception("Stack with id semana19-datos does not exist"))) is None
    with pytest.raises(RuntimeError):
        V.bucket_de_documentos(Cfn([r("DocsKbA", fisico="a"), r("DocsKbB", fisico="b")]))
    assert V.vaciar.__code__.co_filename == str(SCRIPTS / "vaciar_bootstrap.py")   # reused, not copied


def test_stack_ia_guardrail_por_custom_resource_sin_roles_extra_ni_recurso_de_guardrail():
    import json as _json
    import os as _os
    import subprocess as _sp
    import tempfile as _tf
    out = _tf.mkdtemp(prefix="s19ia_")
    _sp.run([sys.executable, str(APP)], env=dict(_os.environ, CDK_OUTDIR=out), check=True, capture_output=True)
    plantilla = _json.loads((Path(out) / "semana19-ia.template.json").read_text(encoding="utf-8"))
    tipos = [r["Type"] for r in plantilla["Resources"].values()]
    # CloudFormation has no tierConfig: the Guardrail itself is a custom resource, not AWS::Bedrock::Guardrail.
    assert "AWS::Bedrock::Guardrail" not in tipos
    assert tipos.count("AWS::Lambda::Function") == 1 and tipos.count("AWS::Logs::LogGroup") == 1
    # Every role carries the permissions boundary of the project.
    roles = [r for r in plantilla["Resources"].values() if r["Type"] == "AWS::IAM::Role"]
    assert roles and all(r["Properties"].get("PermissionsBoundary") for r in roles)
    custom = [r for r in plantilla["Resources"].values() if r["Type"].startswith("Custom::")
              or r["Type"] == "AWS::CloudFormation::CustomResource"]
    assert len(custom) == 1
    props = custom[0]["Properties"]
    assert "kmsKeyId" in props
    assert props["crossRegionConfig"] == {"guardrailProfileIdentifier": "us.guardrail.v1:0"}
    assert props["contentPolicyConfig"]["tierConfig"] == {"tierName": "STANDARD"}
    assert props["contextualGroundingPolicyConfig"]["tierConfig"] == {"tierName": "CLASSIC"}


def test_perfil_entre_regiones_autorizado_en_la_politica_del_creador_y_en_el_limite():
    # CreateGuardrail with a cross-Region config is authorized against the account-scoped guardrail profile.
    import json as _json
    import os as _os
    import subprocess as _sp
    import tempfile as _tf
    out = _tf.mkdtemp(prefix="s19perfil_")
    _sp.run([sys.executable, str(APP)], env=dict(_os.environ, CDK_OUTDIR=out), check=True, capture_output=True)
    ia = _json.loads((Path(out) / "semana19-ia.template.json").read_text(encoding="utf-8"))
    assert "guardrail-profile/us.guardrail.v1:0" in _json.dumps(ia)
    ctl = _json.loads((Path(out) / "semana19-control.template.json").read_text(encoding="utf-8"))
    assert "guardrail-profile/us.guardrail.v1:0" in _json.dumps(ctl)


# ---------------------------------------------------------------- activity 7: boundary size and AgentCore

def _resuelto(x):
    """A policy document with the intrinsics replaced by values of their real length (12-digit account)."""
    if isinstance(x, dict):
        if "Fn::Join" in x:
            return x["Fn::Join"][0].join(_resuelto(p) for p in x["Fn::Join"][1])
        if "Ref" in x:
            return {"AWS::AccountId": "1" * 12, "AWS::Partition": "aws", "AWS::Region": "us-east-1",
                    "AWS::URLSuffix": "amazonaws.com"}.get(x["Ref"], "x" * 40)
        if "Fn::GetAtt" in x:
            return "x" * 80
        return {k: _resuelto(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_resuelto(v) for v in x]
    return x


@pytest.mark.parametrize("perfil", PERFILES)
def test_politicas_administradas_caben_en_el_limite_de_iam(perfil):
    """IAM counts the managed policy document without whitespace: 6,144 characters at most."""
    for lid, r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").items():
        tam = len(json.dumps(_resuelto(r["Properties"]["PolicyDocument"]), separators=(",", ":")))
        assert tam <= 6144, f"{lid}: {tam} caracteres"


def _acciones_del_limite(perfil) -> dict:
    (limite,) = [r for lid, r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").items()
                 if r["Properties"].get("ManagedPolicyName") == "semana19-limite"]
    salida = {}
    for st in limite["Properties"]["PolicyDocument"]["Statement"]:
        acciones = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        salida[st["Sid"]] = (set(acciones), st)
    return salida


@pytest.mark.parametrize("perfil", PERFILES)
def test_limite_compactado_conserva_las_acciones_sin_arn(perfil):
    """The ten statements merged in activity 7 keep every action they had, on the same resources."""
    lim = _acciones_del_limite(perfil)
    sin_arn, st = lim["SinArnDelLimite"]
    assert st["Resource"] == "*" and "Condition" not in st
    assert sin_arn == {
        "logs:DescribeLogGroups", "logs:DescribeLogStreams", "logs:CreateLogDelivery", "logs:GetLogDelivery",
        "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
        "logs:DescribeResourcePolicies", "xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules",
        "xray:GetSamplingTargets", "cloudformation:Describe*", "cloudformation:Get*", "cloudformation:List*",
        "ec2:DescribeSecurityGroups", "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses",
        "states:SendTaskSuccess", "states:SendTaskFailure"}
    logs, st = lim["LogsDelLimite"]
    assert logs == {"logs:CreateLogStream", "logs:PutLogEvents"}
    destinos = sorted(texto(r) for r in st["Resource"])
    assert [d.split("log-group:")[1] for d in destinos] == ["/aws/lambda/semana19-datos*:*", "/semana19/*", "/semana19/ia/*:*"]


@pytest.mark.parametrize("perfil", PERFILES)
def test_limite_deja_al_gateway_evaluar_politicas_y_usar_la_llave(perfil):
    lim = _acciones_del_limite(perfil)
    acciones, st = lim["PolicyDelGatewayDelLimite"]
    assert acciones == {"bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions",
                        "bedrock-agentcore:GetPolicyEngine"}
    assert sorted(texto(r).rsplit(":", 1)[1] for r in st["Resource"]) == ["gateway/semana19-*", "policy-engine/semana19*"]
    _, kms = lim["KmsParaBedrockDelLimite"]
    servicios = kms["Condition"]["StringEquals"]["kms:ViaService"]
    assert sorted(texto(v).split(".")[0] for v in servicios) == ["bedrock", "bedrock-agentcore"]
    modelo, _ = lim["ModeloDelAgenteDelLimite"]
    assert modelo == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:GetInferenceProfile",
                      "bedrock:GetFoundationModel"}


def test_bootstrap_pasa_las_cinco_politicas_de_ejecucion():
    script = (SCRIPTS / "desplegar.sh").read_text(encoding="utf-8")
    linea = next(l for l in script.splitlines() if "--cloudformation-execution-policies" in l)
    assert linea.count("$ARN_EJECUCION") == 5 and "$ARN_EJECUCION_AGENTES" in linea
    assert "OutputKey=='ArnEjecucionCfnAgentes'" in script


@pytest.mark.parametrize("perfil", PERFILES)
def test_cloudformation_usa_la_llave_base_via_bedrock_y_agentcore(perfil):
    """Creating the gateway and its policy engine encrypted with the base key needs the caller's grant through
    AgentCore (activity 7); the boundary lets the gateway's role do the same."""
    (ia,) = [r for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
             if any(s.get("Sid") == "LlaveDeLosPromptsPorCfn" for s in r["Properties"]["PolicyDocument"]["Statement"])]
    (st,) = [s for s in ia["Properties"]["PolicyDocument"]["Statement"] if s["Sid"] == "LlaveDeLosPromptsPorCfn"]
    assert sorted(texto(v).split(".")[0] for v in st["Condition"]["StringEquals"]["kms:ViaService"]) == \
        ["bedrock", "bedrock-agentcore"]
    assert {"kms:CreateGrant", "kms:GenerateDataKey*", "kms:Decrypt", "kms:DescribeKey"} <= set(st["Action"])
    acciones, _ = _acciones_del_limite(perfil)["KmsParaBedrockDelLimite"]
    assert {"kms:CreateGrant", "kms:Decrypt", "kms:DescribeKey"} <= acciones and \
        any(a.startswith("kms:GenerateDataKey") for a in acciones)


# ---------------------------------------------------------------- activity 7: teardown of the disposable stacks

def test_destruir_simula_la_actividad7_sin_llamar_a_aws(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    r = subprocess.run(["bash", str(SCRIPTS / "destruir.sh"), "--solo-actividad7"], env=entorno, capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert not marcas.exists() and "No se llamó a AWS" in r.stdout
    assert r.stdout.index("semana19-agentes-comparacion") < r.stdout.index("semana19-gateway")
    assert "semana19-computo" not in r.stdout and "semana19-base" not in r.stdout


def test_solo_actividad7_y_todo_no_se_combinan(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    r = subprocess.run(["bash", str(SCRIPTS / "destruir.sh"), "--si", "--solo-actividad7", "--todo"], env=entorno,
                       capture_output=True, text=True)
    assert r.returncode == 2 and not marcas.exists()


def test_destruir_actividad7_borra_la_comparacion_luego_el_gateway_y_nada_mas(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    (tmp_path / "bin" / "aws").write_text(f'#!/usr/bin/env bash\necho "aws $*" >> "{marcas}"\necho CREATE_COMPLETE\nexit 0\n',
                                          encoding="utf-8")
    (tmp_path / "bin" / "cdk").write_text(
        f'#!/usr/bin/env bash\necho "cdk COMPUTO=$COMPUTO SIN=$S19_SIN_DEPENDENCIAS $*" >> "{marcas}"\nexit 0\n', encoding="utf-8")
    boto = tmp_path / "bin" / "python-boto"
    boto.write_text(f'#!/usr/bin/env bash\necho "inventario $*" >> "{marcas}"\nexit 0\n', encoding="utf-8")
    boto.chmod(0o755)
    entorno["S19_PYTHON_BOTO"] = str(boto)
    registro = S19 / "resultados" / "tiempos_despliegue.jsonl"
    antes = registro.read_bytes() if registro.exists() else None
    try:
        r = subprocess.run(["bash", str(SCRIPTS / "destruir.sh"), "--si", "--solo-actividad7"], env=entorno,
                           capture_output=True, text=True)
    finally:
        if antes is None:
            registro.unlink(missing_ok=True)
        else:
            registro.write_bytes(antes)
    assert r.returncode == 0, r.stderr[-800:]
    destroy = [l for l in marcas.read_text().splitlines() if l.startswith("cdk")]
    assert [l.split(" destroy ")[1].split()[0] for l in destroy] == ["semana19-agentes-comparacion", "semana19-gateway"]
    assert all("COMPUTO=1 SIN=1" in l and "--exclusively" in l and "--profile semana19-despliegue" in l for l in destroy)
    inventario = [l for l in marcas.read_text().splitlines() if l.startswith("inventario")]
    assert len(inventario) == 1 and "--solo-actividad7" in inventario[0] and "--perfil semana19-lectura" in inventario[0]


def test_destruir_completo_baja_computo_y_la_actividad7_antes_que_datos():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    orden = [texto.index(f"destruir_pila_computo {p} ") for p in
             ("semana19-agentes-comparacion", "semana19-gateway", "semana19-computo")]
    assert orden == sorted(orden) and orden[-1] < texto.index("cdk destroy semana19-datos")


def test_destruir_vacia_el_bucket_del_juez_y_borra_sus_trabajos_antes_de_su_stack():
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    vaciar = texto.index("vaciar_eval.py\" --perfil \"$PERFIL_ADMIN\" --region \"$REGION\" --si")
    assert texto.index("destruir_pila_computo semana19-gateway ") < vaciar < texto.index(
        "destruir_pila_computo semana19-eval ") < texto.index("cdk destroy semana19-datos --force")
    assert texto.index("if [[ \"$SOLO_A7\" == \"1\" ]]") < vaciar   # --solo-actividad7 does not touch it


def test_vaciar_eval_detiene_lo_activo_y_borra_lo_terminado_en_lotes_de_25():
    import importlib.util
    spec = importlib.util.spec_from_file_location("vaciar_eval", SCRIPTS / "vaciar_eval.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)

    class Bedrock:
        def __init__(self):
            self.detenidos, self.lotes = [], []

        def stop_evaluation_job(self, jobIdentifier):
            self.detenidos.append(jobIdentifier)

        def batch_delete_evaluation_job(self, jobIdentifiers):
            self.lotes.append(len(jobIdentifiers))
            return {"evaluationJobs": [{"jobIdentifier": j} for j in jobIdentifiers], "errors": []}

    lista = [{"arn": f"a{i}", "nombre": f"semana19-juez-{i}", "estado": "Completed"} for i in range(30)]
    lista.append({"arn": "corre", "nombre": "semana19-juez-x", "estado": "InProgress"})
    b = Bedrock()
    assert v.borrar_trabajos(b, lista, si=False)["borrados"] == 0 and b.lotes == []
    r = v.borrar_trabajos(b, lista, si=True)
    assert b.lotes == [25, 5] and b.detenidos == ["corre"] and r["borrados"] == 30 and r["detenidos"] == 1
    assert r["por_estado"] == {"Completed": 30, "InProgress": 1}


def test_el_inventario_cuenta_los_trabajos_del_juez():
    inv = _inventario_modulo()
    assert "trabajos_evaluacion_bedrock" in inv.categorias(None, "us-east-1")
    assert "trabajos_evaluacion_bedrock" not in inv.permitidos(True)   # nothing of the judge may be left


def _inventario_modulo():
    import importlib.util
    spec = importlib.util.spec_from_file_location("inv7", SCRIPTS / "inventario.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SesionInventario:
    """Only the AgentCore control plane and Bedrock Agents answer; any other client fails the test."""

    def __init__(self, motores=(), agentes=(), gateways=()):
        self.datos = {"motores": motores, "agentes": agentes, "gateways": gateways}

    def client(self, servicio, region_name=None):
        datos = self.datos

        class Paginador:
            def __init__(self, clave, nombres, campo):
                self.r = [{clave: [{campo: n} for n in nombres]}]

            def paginate(self):
                return self.r

        class AgentCore:
            def list_policy_engines(self, **kw):
                return {"policyEngines": [{"name": n} for n in datos["motores"]]}

            def get_paginator(self, op):
                assert op == "list_gateways"
                return Paginador("items", datos["gateways"], "name")

        class Agentes:
            def get_paginator(self, op):
                assert op == "list_agents"
                return Paginador("agentSummaries", datos["agentes"], "agentName")

        if servicio == "bedrock-agentcore-control":
            return AgentCore()
        if servicio == "bedrock-agent":
            return Agentes()
        raise AssertionError(f"--solo-actividad7 no consulta {servicio}")


def test_inventario_de_la_actividad7_solo_mira_sus_categorias():
    inv = _inventario_modulo()
    assert set(inv.CATEGORIAS_ACTIVIDAD7) == {"gateways_agentcore", "motores_de_politicas_agentcore", "agentes_bedrock"}
    limpio = inv.inventario(_SesionInventario(motores=["otro_motor"]), "us-east-1", solo=inv.CATEGORIAS_ACTIVIDAD7)
    assert limpio["quedan"] == "nada" and limpio["total"] == 0 and limpio["no_medido"] == []
    sucio = inv.inventario(_SesionInventario(motores=["semana19_politicas"], agentes=["semana19-agentes-comparacion"]),
                           "us-east-1", solo=inv.CATEGORIAS_ACTIVIDAD7)
    assert sucio["quedan"] == "revisar"
    assert sucio["inesperados"] == {"motores_de_politicas_agentcore": ["semana19_politicas"],
                                    "agentes_bedrock": ["semana19-agentes-comparacion"]}


def test_con_control_se_permite_la_quinta_politica_de_ejecucion():
    assert "semana19-cfn-exec-agentes" in _inventario_modulo().permitidos(True)["politicas_iam_locales"]
@pytest.mark.parametrize("perfil", PERFILES)
def test_cloudformation_administra_las_politicas_de_los_roles_de_la_actividad7(perfil):
    """CreateRole carries the boundary key; GetRolePolicy and PutRolePolicy do not (the first deploy of the comparison
    stack failed on iam:GetRolePolicy, 2026-11-18), so they are allowed on the two stacks' role names only."""
    (pol,) = [r for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
              if any(s.get("Sid") == "RolesDeActividad7PorCfn" for s in r["Properties"]["PolicyDocument"]["Statement"])]
    (st,) = [s for s in pol["Properties"]["PolicyDocument"]["Statement"] if s["Sid"] == "RolesDeActividad7PorCfn"]
    assert {"iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:DeleteRole"} <= set(st["Action"])
    assert "iam:CreateRole" not in st["Action"] and "iam:PutRolePermissionsBoundary" not in st["Action"]
    assert "iam:DeleteRolePermissionsBoundary" not in st["Action"] and "Condition" not in st
    assert sorted(texto(r).split(":role/")[1] for r in st["Resource"]) == ["semana19-agentes-comparacion-*",
                                                                         "semana19-gateway-*"]


@pytest.mark.parametrize("perfil", PERFILES)
def test_limite_deja_al_rol_del_gateway_usar_llaves_sin_via_service(perfil):
    """AgentCore encrypts the target's configuration calling KMS as the gateway's role (no kms:ViaService, first
    deploy 2026-11-18): the boundary allows it for the roles of semana19-gateway only."""
    acciones, st = _acciones_del_limite(perfil)["KmsDelGatewayDelLimite"]
    assert acciones == {"kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey", "kms:CreateGrant"}
    assert texto(st["Condition"]["ArnLike"]["aws:PrincipalArn"]).endswith(":role/semana19-gateway-*")
    assert list(st["Condition"]) == ["ArnLike"]


@pytest.mark.parametrize("perfil", PERFILES)
def test_ejecucion_crea_la_identidad_del_gateway_en_el_directorio_default(perfil):
    """The first gateway failed on CreateWorkloadIdentity over workload-identity-directory/default (2026-11-18): the
    directory itself and the gateway's identities only, not other workload identities."""
    (pol,) = [r for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
              if any(s.get("Sid") == "IdentidadDelGatewayPorCfn" for s in r["Properties"]["PolicyDocument"]["Statement"])]
    (st,) = [s for s in pol["Properties"]["PolicyDocument"]["Statement"] if s["Sid"] == "IdentidadDelGatewayPorCfn"]
    assert set(st["Action"]) == {"bedrock-agentcore:CreateWorkloadIdentity", "bedrock-agentcore:GetWorkloadIdentity",
                                 "bedrock-agentcore:UpdateWorkloadIdentity", "bedrock-agentcore:DeleteWorkloadIdentity"}
    assert sorted(texto(r).rsplit("}:", 1)[-1] for r in st["Resource"]) == [
        "workload-identity-directory/default", "workload-identity-directory/default/workload-identity/semana19-gateway-*"]


# ---------------------------------------------------------------- activity 8: the judge's stack semana19-eval

@lru_cache(maxsize=None)
def de_eval(perfil):
    return _plantilla_computo(perfil, "semana19-eval")


def _acciones(st) -> set:
    return set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_bucket_del_juez_esta_cifrado_cerrado_y_caduca(perfil):
    (b,) = recursos(de_eval(perfil), "AWS::S3::Bucket").values()
    p = b["Properties"]
    (cifrado,) = p["BucketEncryption"]["ServerSideEncryptionConfiguration"]
    assert cifrado["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms" and cifrado["BucketKeyEnabled"] is True
    assert "semana19-base" in texto(cifrado["ServerSideEncryptionByDefault"]["KMSMasterKeyID"])   # the base key, imported
    assert all(p["PublicAccessBlockConfiguration"][k] for k in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls",
                                                                 "RestrictPublicBuckets"))
    assert "VersioningConfiguration" not in p and b["DeletionPolicy"] == "Delete"
    (regla,) = p["LifecycleConfiguration"]["Rules"]
    assert regla["ExpirationInDays"] == 7 and regla["Status"] == "Enabled"
    (politica,) = recursos(de_eval(perfil), "AWS::S3::BucketPolicy").values()
    (tls,) = politica["Properties"]["PolicyDocument"]["Statement"]
    assert tls["Effect"] == "Deny" and tls["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_del_juez_lo_asume_bedrock_de_esta_cuenta_solo_para_evaluaciones(perfil):
    (rol,) = recursos(de_eval(perfil), "AWS::IAM::Role").values()
    (confianza,) = rol["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert confianza["Principal"] == {"Service": "bedrock.amazonaws.com"} and confianza["Action"] == "sts:AssumeRole"
    assert "AWS::AccountId" in texto(confianza["Condition"]["StringEquals"]["aws:SourceAccount"])
    assert texto(confianza["Condition"]["ArnLike"]["aws:SourceArn"]).endswith(":evaluation-job/*")
    assert "semana19-limite" in texto(rol["Properties"]["PermissionsBoundary"])


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_rol_del_juez_solo_puede_el_modelo_juez_su_bucket_y_la_llave_por_s3(perfil):
    sts = {st["Sid"]: st for _, tipo, st in declaraciones(de_eval(perfil)) if tipo == "AWS::IAM::Policy"}
    assert set(sts) == {"ModeloDelJuez", "BucketDelJuez", "LlaveDelBucketViaS3"}
    assert _acciones(sts["ModeloDelJuez"]) == {"bedrock:InvokeModel", "bedrock:CreateModelInvocationJob",
                                               "bedrock:StopModelInvocationJob"}
    destinos = [texto(r) for r in sts["ModeloDelJuez"]["Resource"]]
    assert sum(d.endswith("inference-profile/us.amazon.nova-pro-v1:0") for d in destinos) == 1
    assert sorted(re.search(r"bedrock:([a-z0-9-]+)::foundation-model/amazon.nova-pro-v1:0$", d).group(1)
                  for d in destinos if "foundation-model" in d) == ["us-east-1", "us-east-2", "us-west-2"]
    assert all("anthropic" not in d for d in destinos)        # the judge is not the evaluated model
    assert all("Juez" in texto(r) and "*" not in texto(r).replace("/*", "") for r in sts["BucketDelJuez"]["Resource"])
    assert sts["LlaveDelBucketViaS3"]["Condition"]["StringEquals"]["kms:ViaService"].startswith("s3.")


@pytest.mark.parametrize("perfil", PERFILES)
def test_lo_que_pide_el_rol_del_juez_cabe_en_el_limite(perfil):
    """A role's grant outside the boundary is denied at run time: each action of the judge's role is in the boundary."""
    lim = _acciones_del_limite(perfil)
    del_limite = set().union(*(a for a, _ in lim.values()))
    rol = set().union(*(_acciones(st) for _, tipo, st in declaraciones(de_eval(perfil)) if tipo == "AWS::IAM::Policy"))
    assert rol <= del_limite, sorted(rol - del_limite)
    _, bucket = lim["BucketDelJuezDelLimite"]
    assert sorted(texto(r).rsplit(":", 1)[1] for r in bucket["Resource"]) == ["semana19-eval-*", "semana19-eval-*/*"]
    _, modelo = lim["ModeloDelJuezDelLimite"]
    assert any(texto(r).endswith("inference-profile/us.amazon.nova-pro-v1:0") for r in modelo["Resource"])


@pytest.mark.parametrize("perfil", PERFILES)
def test_las_fusiones_del_limite_conservan_permisos(perfil):
    lim = _acciones_del_limite(perfil)
    assert "KmsParaDynamoDelLimite" not in lim and "CifrarSoloViaS3YSecretos" not in lim and "DocsDatosLeer" not in lim
    acciones, kms = lim["KmsViaServiciosDelLimite"]
    assert acciones == {"kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"}
    assert sorted(texto(v).split(".")[0] for v in kms["Condition"]["StringEquals"]["kms:ViaService"]) == [
        "dynamodb", "s3", "secretsmanager"]
    acciones, docs = lim["DocsDatosLeerYListar"]
    assert acciones == {"s3:GetObject", "s3:ListBucket"}
    assert sorted(texto(r).rsplit(":", 1)[1] for r in docs["Resource"]) == ["semana19-datos*", "semana19-datos*/*"]


@pytest.mark.parametrize("perfil", PERFILES)
def test_la_politica_de_ejecucion_cubre_el_stack_del_juez(perfil):
    (ia,) = [r for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
             if r["Properties"].get("ManagedPolicyName") == "semana19-cfn-exec-ia"]
    sts = {s["Sid"]: s for s in ia["Properties"]["PolicyDocument"]["Statement"]}
    assert {"s3:CreateBucket", "s3:DeleteBucket", "s3:PutLifecycleConfiguration", "s3:PutEncryptionConfiguration",
            "s3:PutBucketPolicy"} <= _acciones(sts["BucketDelJuezPorCfn"])
    assert texto(sts["BucketDelJuezPorCfn"]["Resource"]).endswith(":s3:::semana19-eval-*")
    assert {"iam:PutRolePolicy", "iam:DeleteRole"} <= _acciones(sts["RolDelJuezPorCfn"])


@pytest.mark.parametrize("perfil", PERFILES)
def test_el_stack_del_juez_da_lo_que_lee_juez_bedrock(perfil):
    assert set(de_eval(perfil)["Outputs"]) == {"BucketJuez", "ArnRolJuez", "ArnLlave"}
    fuente = (S19 / "eval" / "juez_bedrock.py").read_text(encoding="utf-8")
    assert all(f'"{k}"' in fuente for k in ("BucketJuez", "ArnRolJuez", "ArnLlave"))


def test_destruir_reintenta_control_solo_si_fallo_el_limite_de_permisos():
    """2026-11-19: semana19-control ended DELETE_FAILED on semana19-limite only (409, its roles still deleting)."""
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    paso4 = texto[texto.index("== Paso 4: borrar semana19-control"):texto.index("== Paso 4c")]
    assert 'if [[ "$fallidos" != Limite* || "$fallidos" == *[[:space:]]* ]]; then' in paso4
    assert paso4.index("exit 1") < paso4.index("Paso 4b")   # anything other than the boundary alone stops
    assert paso4.count("aws cloudformation delete-stack --stack-name semana19-control") == 2


def test_destruir_borra_los_log_groups_implicitos_de_lambda_despues_de_las_pilas_y_antes_del_inventario():
    """2026-11-19: the datos loader left /aws/lambda/semana19-datos-Cargador... outside CloudFormation."""
    texto = (SCRIPTS / "destruir.sh").read_text(encoding="utf-8")
    borrar = texto.index('aws logs delete-log-group --log-group-name "$grupo"')
    assert texto.index("== Paso 4: borrar semana19-control") < borrar < texto.index('echo "== Paso 5: inventario')
    assert "--log-group-name-prefix /aws/lambda/semana19- " in texto   # the project's functions only



@pytest.mark.parametrize("perfil", PERFILES)
def test_la_ejecucion_del_base_etiqueta_sus_roles_sin_la_llave_del_limite(perfil):
    """CloudFormation tags a new role with its own TagRole call, which carries no iam:PermissionsBoundary, so the
    boundary condition of RolesConLimite cannot cover it (2026-11-21, semana19-flow-logs)."""
    declaraciones = [d for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
                     for d in r["Properties"]["PolicyDocument"]["Statement"]]
    (etiquetar,) = [d for d in declaraciones if d.get("Sid") == "EtiquetarRolesDelBase"]
    assert sorted(etiquetar["Action"]) == ["iam:TagRole", "iam:UntagRole"] and "Condition" not in etiquetar
    recursos_ = json.dumps(etiquetar["Resource"])
    assert "role/semana19-flow-logs" in recursos_ and "role/semana19-base-*" in recursos_


@pytest.mark.parametrize("perfil", PERFILES)
def test_la_ejecucion_del_computo_etiqueta_el_stage_del_api(perfil):
    """The AWS::ApiGatewayV2::Stage handler checks apigateway:TagResource. ValidatePolicy calls it INVALID_ACTION;
    without it semana19-computo failed with AccessDenied (2026-11-21)."""
    declaraciones = [d for r in recursos(de_control(perfil), "AWS::IAM::ManagedPolicy").values()
                     for d in r["Properties"]["PolicyDocument"]["Statement"]]
    (api,) = [d for d in declaraciones if d.get("Sid") == "ApiHttpPorCfn"]
    assert {"apigateway:TagResource", "apigateway:UntagResource"} <= set(api["Action"])
