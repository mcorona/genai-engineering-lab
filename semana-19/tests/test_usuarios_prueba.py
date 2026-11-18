"""Week 19, activity 6: the test-user script, offline ($0, moto). No real pool is touched."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19 / "infra"))

import usuarios as U  # noqa: E402


@pytest.fixture
def pool():
    with mock_aws():
        cliente = boto3.client("cognito-idp", region_name="us-east-1")
        pool_id = cliente.create_user_pool(PoolName="semana19-usuarios")["UserPool"]["Id"]
        for grupo in {g for _, g, _ in U.USUARIOS}:
            cliente.create_group(UserPoolId=pool_id, GroupName=grupo)
        yield cliente, pool_id


def test_simulacion_no_llama_a_aws_y_muestra_el_plan(capsys):
    assert U.crear("pool-x", None, False)[0].startswith("crear analista-prueba")
    assert "pool-x" in U.plan("pool-x")[1]


def test_un_usuario_por_grupo_del_trigger_y_ninguno_propone_y_aprueba():
    sys.path.insert(0, str(S19))
    from computo import tokens as T
    grupos = [g for _, g, _ in U.USUARIOS]
    assert sorted(grupos) == sorted(T.GRUPOS_A_SCOPES) and len(set(grupos)) == len(grupos)
    for g in grupos:
        scopes = T.scopes_de_grupos([g])
        assert not ("legado/compras_proponer" in scopes and "legacybridge/aprobaciones" in scopes), g


def test_crea_cada_usuario_en_su_grupo_y_guarda_contrasenas_en_0600(pool, tmp_path):
    cliente, pid = pool
    ruta = tmp_path / ".secretos.env"
    estados = U.crear(pid, cliente, True, ruta)
    assert all("creado" in e for e in estados)
    for usuario, grupo, _ in U.USUARIOS:
        grupos = [g["GroupName"] for g in cliente.admin_list_groups_for_user(UserPoolId=pid, Username=usuario)["Groups"]]
        assert grupos == [grupo]
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert {l.split("=", 1)[0] for l in lineas} == {c for _, _, c in U.USUARIOS}
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600


def test_usuario_existente_conserva_su_contrasena_y_pasa_a_su_grupo(pool, tmp_path):
    cliente, pid = pool
    cliente.create_group(UserPoolId=pid, GroupName="aprobadores")            # the old group of activity 6
    cliente.admin_create_user(UserPoolId=pid, Username="aprobador-prueba", MessageAction="SUPPRESS")
    cliente.admin_add_user_to_group(UserPoolId=pid, Username="aprobador-prueba", GroupName="aprobadores")
    ruta = tmp_path / ".secretos.env"
    estados = U.crear(pid, cliente, True, ruta)
    assert "aprobador-prueba: ya existe, contraseña sin cambios; grupo ahora aprobadores-gerente" in estados
    grupos = [g["GroupName"] for g in cliente.admin_list_groups_for_user(UserPoolId=pid, Username="aprobador-prueba")["Groups"]]
    assert grupos == ["aprobadores-gerente"]
    assert "APROBADOR_PRUEBA_PASSWORD" not in ruta.read_text(encoding="utf-8")   # no new password for it


def test_la_contrasena_nunca_sale_por_la_salida(pool, tmp_path, capsys):
    cliente, pid = pool
    estados = U.crear(pid, cliente, True, tmp_path / ".secretos.env")
    secreto = (tmp_path / ".secretos.env").read_text(encoding="utf-8").splitlines()[0].split("=", 1)[1]
    salida = capsys.readouterr()
    assert secreto not in salida.out and secreto not in salida.err and secreto not in " ".join(estados)


def test_segunda_ejecucion_no_cambia_ni_repite_contrasenas(pool, tmp_path):
    cliente, pid = pool
    ruta = tmp_path / ".secretos.env"
    U.crear(pid, cliente, True, ruta)
    antes = ruta.read_text(encoding="utf-8")
    estados = U.crear(pid, cliente, True, ruta)
    assert all(e.endswith("ya existe, contraseña sin cambios") for e in estados)
    assert ruta.read_text(encoding="utf-8") == antes


def test_la_contrasena_cumple_la_politica_del_pool():
    for _ in range(50):
        c = U.generar_contrasena()
        assert len(c) >= 12 and any(x.islower() for x in c) and any(x.isupper() for x in c)
        assert any(x.isdigit() for x in c) and any(not x.isalnum() for x in c)
