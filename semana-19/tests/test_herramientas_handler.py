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
    assert res["filas"] == [[1, "x"]] and res["truncado"] is False   # lists: what JSON carries
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


PROPUESTA = {"sku": "SKU-0009", "cantidad": 3, "motivo": "stock bajo", "cedis": 2, "fecha_requerida": "2026-12-05"}


class Lecturas:
    """copilot_ro's read-only pre-checks: which of the three lookups find a row."""

    def __init__(self, sku=True, cedis=True, pendiente=False):
        self.respuestas = {"artmst": sku, "almmst": cedis, "ocpcab": pendiente}
        self.sql = []
        self.cerrada = False

    def run(self, sql, **kw):
        self.sql.append((sql, kw))
        for vista, hay in self.respuestas.items():
            if f"legado.{vista}" in sql:
                return [[1]] if hay else []
        return []

    def close(self):
        self.cerrada = True


def test_orden_de_compra_solo_inicia_la_maquina_con_el_solicitante_del_token():
    import json
    inicios, con = [], Lecturas()
    res = H.proponer_orden_compra(PROPUESTA, lambda entrada: inicios.append(entrada) or "sol-1",
                                  solicitante="sub-comprador", conectar=lambda: con)
    assert res["solicitud_id"] == "sol-1" and res["estado"] == "PENDING_APPROVAL"
    assert json.loads(inicios[0]) == {**PROPUESTA, "solicitante": "sub-comprador"}
    assert all(s.startswith(("SET statement_timeout", "SELECT 1 FROM legado.")) for s, _ in con.sql) and con.cerrada
    assert {kw.get("sku") or kw.get("cedis") for _, kw in con.sql[1:]} == {"SKU-0009", 2}   # bound parameters


@pytest.mark.parametrize("lecturas,tipo", [
    (Lecturas(sku=False), "sku_desconocido"),
    (Lecturas(cedis=False), "cedis_desconocido"),
    (Lecturas(pendiente=True), "orden_pendiente_existente"),
])
def test_lo_que_la_base_rechazaria_se_dice_antes_de_iniciar(lecturas, tipo):
    with pytest.raises(ToolError) as e:
        H.proponer_orden_compra(PROPUESTA, lambda x: pytest.fail("no debe iniciar"), solicitante="s", conectar=lambda: lecturas)
    assert e.value.kind == tipo and lecturas.cerrada


@pytest.mark.parametrize("cambio", [
    {"cantidad": 0}, {"cantidad": "3"}, {"cantidad": True}, {"sku": "A1"}, {"motivo": ""}, {"motivo": "x" * 201},
    {"cedis": "2"}, {"cedis": 0}, {"fecha_requerida": "5 de diciembre"}, {"fecha_requerida": "2026-13-01"},
    {"proveedor_id": 7}, {"solicitante": "otro"},
])
def test_orden_invalida_se_rechaza_sin_conectar_ni_iniciar(cambio):
    with pytest.raises(ToolError):
        H.proponer_orden_compra({**PROPUESTA, **cambio}, lambda e: pytest.fail("no debe iniciar"), solicitante="s",
                                conectar=lambda: pytest.fail("no debe conectar"))


@pytest.mark.parametrize("campo", ["cedis", "fecha_requerida", "motivo"])
def test_cada_dato_obligatorio_de_la_politica_falta_y_se_rechaza(campo):
    entrada = {k: v for k, v in PROPUESTA.items() if k != campo}
    with pytest.raises(ToolError):
        H.proponer_orden_compra(entrada, lambda e: pytest.fail("no debe iniciar"), solicitante="s")


@pytest.mark.parametrize("solicitante", [None, "", "x" * 129])
def test_sin_solicitante_no_inicia(solicitante):
    with pytest.raises(ToolError) as e:
        H.proponer_orden_compra(PROPUESTA, lambda e: pytest.fail("no debe iniciar"), solicitante=solicitante)
    assert e.value.kind == "sin_solicitante"


def test_el_handler_pasa_el_solicitante_del_evento_y_no_de_la_entrada():
    import json
    inicios = []
    evento = {"herramienta": "proponer_orden_compra", "entrada": PROPUESTA, "solicitante": "sub-del-token"}
    res = H.handler(evento, None, conectar=lambda: Lecturas(), iniciar=lambda e: inicios.append(e) or "sol-9")
    assert res["solicitud_id"] == "sol-9" and json.loads(inicios[0])["solicitante"] == "sub-del-token"
    sin = H.handler({**evento, "solicitante": None}, None, conectar=lambda: Lecturas(), iniciar=lambda e: "x")
    assert sin["error"] == "sin_solicitante"


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


def test_numeric_y_fechas_salen_como_json():
    # Live: the agent asking for costs got herramienta_no_disponible (Decimal cannot leave a Lambda as JSON).
    import datetime as dt
    import json
    from decimal import Decimal
    fabrica = Fabrica([["SKU-0009", Decimal("12.50"), dt.date(2026, 12, 5), dt.datetime(2026, 1, 1, 8, 0), "x" * 300]])
    res = H.ejecutar_sql("SELECT art_cd, art_cst FROM legado.artmst", fabrica)
    json.dumps(res)
    assert res["filas"][0][:4] == ["SKU-0009", 12.5, "2026-12-05", "2026-01-01T08:00:00"]
    assert len(res["filas"][0][4]) == 201
