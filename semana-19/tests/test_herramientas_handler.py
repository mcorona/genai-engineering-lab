"""Week 19, activity 6: the tools Lambda handler, offline ($0, no database, no AWS).

The connection and the state-machine starter are fakes. A rejected SQL must never reach the connection; the only user
is copilot_ro; TLS verifies the certificate; the statement timeout and the read-only transaction are set before the query.
"""
from __future__ import annotations

import ssl
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from herramientas import handler as H  # noqa: E402
from herramientas.guardia_sql import ToolError  # noqa: E402


class Conexion:
    def __init__(self, filas=None):
        self.sql = []
        self.cerrada = False
        self._filas = filas or []

    def run(self, sql, **kw):
        self.sql.append(sql)
        if sql.startswith("SELECT * FROM"):
            return self._filas
        return []

    def close(self):
        self.cerrada = True


class Fabrica:
    def __init__(self, filas=None):
        self.llamadas = 0
        self.conexion = Conexion(filas)

    def __call__(self):
        self.llamadas += 1
        return self.conexion


def test_escritura_se_rechaza_y_no_hay_conexion():
    fabrica = Fabrica()
    res = H.handler({"herramienta": "ejecutar_sql", "sql": "DELETE FROM legado.prvmst"}, None, conectar=fabrica)
    assert res["error"] == "write_blocked"
    assert fabrica.llamadas == 0


def test_seleccion_fija_timeout_solo_lectura_y_limite():
    fabrica = Fabrica(filas=[(1, "x")])
    res = H.handler({"herramienta": "ejecutar_sql", "sql": "SELECT prv_nom FROM legado.prvmst"}, None, conectar=fabrica)
    sql = fabrica.conexion.sql
    assert sql[0] == f"SET statement_timeout = {H.TIMEOUT_MS}"
    assert sql[1] == "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    assert sql[2].startswith("SELECT * FROM (") and f"LIMIT {H.LIMITE_FILAS + 1}" in sql[2]
    assert res["filas"] == [(1, "x")] and res["truncado"] is False
    assert fabrica.conexion.cerrada


def test_resultado_mayor_al_limite_se_marca_truncado():
    filas = [(i,) for i in range(H.LIMITE_FILAS + 1)]
    fabrica = Fabrica(filas=filas)
    res = H.handler({"herramienta": "ejecutar_sql", "sql": "SELECT prv_id FROM legado.prvmst"}, None, conectar=fabrica)
    assert res["truncado"] is True and len(res["filas"]) == H.LIMITE_FILAS


def test_objeto_fuera_del_esquema_no_conecta():
    fabrica = Fabrica()
    res = H.handler({"herramienta": "ejecutar_sql", "sql": "SELECT * FROM public.suppliers"}, None, conectar=fabrica)
    assert res["error"] == "out_of_scope" and fabrica.llamadas == 0


def test_describir_esquema_agrupa_columnas_por_tabla():
    con = Conexion()
    con.run = lambda sql, **kw: [("prvmst", "prv_id", "integer"), ("prvmst", "prv_nom", "text")]
    res = H.describir_esquema(lambda: con)
    assert res["tablas"]["prvmst"][0] == {"columna": "prv_id", "tipo": "integer"}
    assert con.cerrada


def test_orden_de_compra_solo_inicia_la_maquina_y_no_escribe():
    inicios = []
    res = H.proponer_orden_compra({"sku": "SKU-0009", "cantidad": 3, "motivo": "stock bajo"},
                                  lambda entrada: inicios.append(entrada) or "sol-1")
    assert res == {"solicitud_id": "sol-1"}
    assert len(inicios) == 1 and '"sku": "SKU-0009"' in inicios[0]


@pytest.mark.parametrize("entrada", [
    {"sku": "SKU-0009", "cantidad": 0, "motivo": "x"},
    {"sku": "SKU-0009", "cantidad": "3", "motivo": "x"},
    {"sku": "SKU-0009", "cantidad": True, "motivo": "x"},
    {"sku": "A1", "cantidad": 3, "motivo": "x"},
    {"sku": "SKU-0009", "cantidad": 3, "motivo": ""},
    {"sku": "SKU-0009", "cantidad": 3, "motivo": "x" * 201},
    {"sku": "SKU-0009", "cantidad": 3},
    {"sku": "SKU-0009", "cantidad": 3, "motivo": "x", "proveedor_id": 7},
])
def test_orden_invalida_se_rechaza_sin_iniciar(entrada):
    with pytest.raises(ToolError):
        H.proponer_orden_compra(entrada, lambda e: pytest.fail("no debe iniciar"))


def test_token_iam_es_solo_para_copilot_ro():
    capturado = {}

    def generar(**kw):
        capturado.update(kw)
        return "token"

    H.token_iam("db.example", generar, "us-east-1")
    assert capturado["DBUsername"] == "copilot_ro"
    assert capturado["Port"] == 5432 and capturado["Region"] == "us-east-1"


def test_tls_verifica_certificado_y_nombre_de_host(tmp_path):
    """Self-signed CA made here with openssl; the real RDS bundle is not in the repo and is not downloaded in tests."""
    import subprocess
    pem = tmp_path / "ca.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(tmp_path / "k.pem"),
                    "-out", str(pem), "-days", "1", "-subj", "/CN=test-ca"], check=True, capture_output=True)
    ctx = H.contexto_tls(cafile=pem)
    assert ctx.check_hostname is True and ctx.verify_mode == ssl.CERT_REQUIRED


def test_tls_sin_bundle_falla_antes_de_conectar(tmp_path):
    with pytest.raises(FileNotFoundError):
        H.contexto_tls(cafile=tmp_path / "no-existe.pem")


def test_herramienta_desconocida_responde_sin_ejecutar_nada():
    fabrica = Fabrica()
    assert H.handler({"herramienta": "borrar_todo"}, None, conectar=fabrica) == {"error": "herramienta_desconocida"}
    assert fabrica.llamadas == 0
