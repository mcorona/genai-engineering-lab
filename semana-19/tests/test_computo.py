"""Week 19, activity 6: the approval Lambdas and the pre-token trigger, offline ($0, no AWS)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from computo import aprobacion as A  # noqa: E402
from computo import tokens as T  # noqa: E402


class Tabla:
    def __init__(self, fila=None):
        self.filas = {}
        if fila:
            self.filas[fila["id"]] = dict(fila)
        self.borradas = []

    def put_item(self, Item):
        self.filas[Item["id"]] = dict(Item)

    def get_item(self, Key):
        f = self.filas.get(Key["id"])
        return {"Item": dict(f)} if f else {}

    def delete_item(self, Key):
        self.borradas.append(Key["id"])
        self.filas.pop(Key["id"], None)


class Sfn:
    def __init__(self):
        self.llamadas = []

    def send_task_success(self, taskToken, output):
        self.llamadas.append(("ok", taskToken, output))

    def send_task_failure(self, taskToken, error, cause):
        self.llamadas.append(("fallo", taskToken, error))


def test_registrar_guarda_el_token_con_ttl_y_no_lo_devuelve():
    t = Tabla()
    res = A.registrar({"id": "sol-1", "token": "TOKEN-SECRETO-XYZ"}, t, ahora=lambda: 1000)
    assert res == {"id": "sol-1"} and "TOKEN-SECRETO-XYZ" not in json.dumps(res)
    assert t.filas["sol-1"]["token"] == "TOKEN-SECRETO-XYZ"
    assert t.filas["sol-1"]["expira"] == 1000 + A.TTL_SEGUNDOS


def test_registrar_sin_token_falla():
    with pytest.raises(ValueError):
        A.registrar({"id": "sol-1"}, Tabla())


def test_aprobar_envia_exito_a_step_functions_y_borra_la_fila():
    t = Tabla({"id": "sol-1", "token": "T1", "expira": 5000})
    s = Sfn()
    res = A.aprobar("sol-1", "aprobar", t, s, ahora=lambda: 1000)
    assert res == {"estado": "aprobada"} and s.llamadas == [("ok", "T1", '{"decision": "aprobada"}')]
    assert t.borradas == ["sol-1"]


def test_rechazar_envia_fallo_a_step_functions():
    t = Tabla({"id": "sol-1", "token": "T1", "expira": 5000})
    s = Sfn()
    assert A.aprobar("sol-1", "rechazar", t, s, ahora=lambda: 1000) == {"estado": "rechazada"}
    assert s.llamadas[0][0] == "fallo"


def test_fila_caducada_o_inexistente_no_revela_nada():
    s = Sfn()
    assert A.aprobar("no-existe", "aprobar", Tabla(), s) == {"estado": "no_encontrada"}
    t = Tabla({"id": "sol-2", "token": "T2", "expira": 10})
    assert A.aprobar("sol-2", "aprobar", t, s, ahora=lambda: 1000) == {"estado": "no_encontrada"}
    assert s.llamadas == []


def test_decision_invalida_no_llama_a_nada():
    s = Sfn()
    with pytest.raises(ValueError):
        A.aprobar("sol-1", "tal-vez", Tabla({"id": "sol-1", "token": "T", "expira": 9999}), s)
    assert s.llamadas == []


def test_grupos_se_convierten_en_scopes_y_grupo_desconocido_no_da_nada():
    assert T.scopes_de_grupos(["analistas", "grupo-raro"]) == ["legacybridge/consultas"]
    assert T.scopes_de_grupos(["aprobadores"]) == ["legacybridge/aprobaciones", "legacybridge/consultas"]
    assert T.scopes_de_grupos(["desconocido"]) == []


def test_trigger_v2_anade_scopes_del_grupo():
    evento = {"version": "2", "request": {"groupConfiguration": {"groupsToOverride": ["aprobadores"]}}}
    res = T.handler(evento, None)
    assert "legacybridge/aprobaciones" in res["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["scopesToAdd"]


def test_trigger_rechaza_otra_version():
    with pytest.raises(ValueError):
        T.handler({"version": "1"}, None)
