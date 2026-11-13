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
CONTROL, BASE = "semana19-control", "semana19-base"
ARN_LIMITE = "policy/semana19-limite"


@lru_cache(maxsize=None)
def sintetizar(perfil: str) -> dict:
    salida = Path(tempfile.mkdtemp(prefix=f"s19-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida)}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    plantillas = {n: json.loads((salida / f"{n}.template.json").read_text(encoding="utf-8")) for n in (CONTROL, BASE)}
    informes = {n: list(csv.DictReader((salida / f"AwsSolutions--{n}-NagReport.csv").open(encoding="utf-8")))
                for n in (CONTROL, BASE)}
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
def test_los_dos_stacks_sintetizan_en_cada_perfil(perfil):
    s = sintetizar(perfil)
    assert set(s["plantillas"]) == {CONTROL, BASE}


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
            assert ARN_LIMITE in limite, f"{n}/{lid} sin permission boundary"


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
def test_ningun_grupo_de_seguridad_acepta_entrada_desde_internet(perfil):
    for n, pl in sintetizar(perfil)["plantillas"].items():
        for lid, r in recursos(pl, "AWS::EC2::SecurityGroup").items():
            for regla in r["Properties"].get("SecurityGroupIngress", []):
                assert regla.get("CidrIp") not in ("0.0.0.0/0", None) or regla.get("SourceSecurityGroupId")
                assert regla.get("CidrIpv6") != "::/0"


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


@pytest.mark.parametrize("perfil", PERFILES)
def test_comodines_coinciden_con_el_registro(perfil):
    usados = set()
    for pl in sintetizar(perfil)["plantillas"].values():
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


def test_argumentos_desconocidos_salen_con_2(tmp_path):
    entorno, marcas = _entorno_falso(tmp_path)
    for script in ("desplegar.sh", "destruir.sh"):
        r = subprocess.run(["bash", str(SCRIPTS / script), "--borrar-todo"], env=entorno, capture_output=True, text=True)
        assert r.returncode == 2
    assert not marcas.exists()


@pytest.mark.parametrize("script", ["desplegar.sh", "destruir.sh", "vaciar_bootstrap.py", "inventario.py"])
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
