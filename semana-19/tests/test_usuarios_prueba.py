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
        for grupo in ("analistas", "aprobadores"):
            cliente.create_group(UserPoolId=pool_id, GroupName=grupo)
        yield cliente, pool_id


def test_simulacion_no_llama_a_aws_y_muestra_el_plan(capsys):
    assert U.crear("pool-x", None, False)[0].startswith("crear analista-prueba")
    assert "pool-x" in U.plan("pool-x")[1]


def test_crea_los_dos_usuarios_en_sus_grupos_y_guarda_contrasenas_en_0600(pool, tmp_path):
    cliente, pid = pool
    ruta = tmp_path / ".secretos.env"
    estados = U.crear(pid, cliente, True, ruta)
    assert all("creado" in e for e in estados)
    for usuario, grupo in (("analista-prueba", "analistas"), ("aprobador-prueba", "aprobadores")):
        grupos = [g["GroupName"] for g in cliente.admin_list_groups_for_user(UserPoolId=pid, Username=usuario)["Groups"]]
        assert grupos == [grupo]
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert {l.split("=", 1)[0] for l in lineas} == {"ANALISTA_PRUEBA_PASSWORD", "APROBADOR_PRUEBA_PASSWORD"}
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600


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
    assert all("ya existe, sin cambios" in e for e in estados)
    assert ruta.read_text(encoding="utf-8") == antes


def test_la_contrasena_cumple_la_politica_del_pool():
    for _ in range(50):
        c = U.generar_contrasena()
        assert len(c) >= 12 and any(x.islower() for x in c) and any(x.isupper() for x in c)
        assert any(x.isdigit() for x in c) and any(not x.isalnum() for x in c)
