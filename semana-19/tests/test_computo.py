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
    def __init__(self, error=None):
        self.llamadas = []
        self.error = error

    def send_task_success(self, taskToken, output):
        if self.error:
            raise self.error
        self.llamadas.append(("ok", taskToken, json.loads(output)))


class TaskTimedOut(Exception):
    """Same class name as botocore's: the token was already used or its wait ended."""


SOLICITANTE = "sub-comprador"
FILA = {"id": "sol-1", "token": "T1", "expira": 5000, "po_id": 7, "nivel_requerido": "gerente", "solicitante": SOLICITANTE}


def _registro(**cambios):
    return {"id": "sol-1", "token": "TOKEN-SECRETO-XYZ", "orden": {"po_id": 7, "nivel_requerido": "gerente"},
            "solicitud": {"solicitante": SOLICITANTE}, **cambios}


def test_registrar_guarda_token_orden_nivel_y_solicitante_con_ttl_y_no_devuelve_el_token():
    t = Tabla()
    res = A.registrar(_registro(), t, ahora=lambda: 1000)
    assert res == {"id": "sol-1"} and "TOKEN-SECRETO-XYZ" not in json.dumps(res)
    f = t.filas["sol-1"]
    assert f["token"] == "TOKEN-SECRETO-XYZ" and f["expira"] == 1000 + A.TTL_SEGUNDOS
    assert (f["po_id"], f["nivel_requerido"], f["solicitante"]) == (7, "gerente", SOLICITANTE)


@pytest.mark.parametrize("evento", [
    {"id": "sol-1"},
    _registro(orden={}),
    _registro(orden={"po_id": 7, "nivel_requerido": "jefe"}),
    _registro(solicitud={}),
])
def test_registrar_sin_token_orden_o_solicitante_falla(evento):
    with pytest.raises(ValueError):
        A.registrar(evento, Tabla())


def _aprobar(decision="aprobar", fila=FILA, sfn=None, **kw):
    t, s = Tabla(fila), sfn or Sfn()
    kw.setdefault("aprobador", "sub-gerente")
    kw.setdefault("nivel", "gerente")
    return A.aprobar("sol-1", decision, t, s, ahora=lambda: 1000, **kw), t, s


def test_aprobar_con_nivel_suficiente_envia_la_decision_con_quien_y_su_nivel_y_borra_la_fila():
    res, t, s = _aprobar()
    assert res == {"estado": "aprobada"}
    assert s.llamadas == [("ok", "T1", {"decision": "aprobar", "decidido_por": "sub-gerente", "nivel": "gerente"})]
    assert t.borradas == ["sol-1"]


def test_un_nivel_mayor_tambien_aprueba():
    res, _, s = _aprobar(aprobador="sub-director", nivel="director")
    assert res == {"estado": "aprobada"} and s.llamadas[0][2]["nivel"] == "director"


def test_nivel_insuficiente_no_envia_nada_ni_borra_la_fila():
    res, t, s = _aprobar(aprobador="sub-cmp", nivel="comprador")
    assert res == {"estado": "nivel_insuficiente", "nivel_requerido": "gerente"}
    assert s.llamadas == [] and t.borradas == [] and "sol-1" in t.filas


def test_quien_propuso_no_puede_decidir_su_propia_orden():
    for decision, motivo in (("aprobar", None), ("rechazar", "no")):
        res, t, s = _aprobar(decision, aprobador=SOLICITANTE, nivel="director", motivo=motivo)
        assert res == {"estado": "misma_persona"} and s.llamadas == [] and t.borradas == []


def test_sin_nivel_en_el_token_no_decide():
    for nivel in (None, "", "jefe"):
        res, _, s = _aprobar(nivel=nivel)
        assert res == {"estado": "sin_nivel_de_aprobacion"} and s.llamadas == []


def test_rechazar_envia_exito_con_el_motivo_y_cualquier_nivel_puede_rechazar():
    res, t, s = _aprobar("rechazar", aprobador="sub-cmp", nivel="comprador", motivo="  sin presupuesto ")
    assert res == {"estado": "rechazada"}
    assert s.llamadas[0][2] == {"decision": "rechazar", "decidido_por": "sub-cmp", "nivel": "comprador",
                                "nota": "sin presupuesto"}
    assert t.borradas == ["sol-1"]


@pytest.mark.parametrize("motivo", [None, "", "   ", "x" * 201, 7])
def test_rechazar_sin_motivo_es_invalido(motivo):
    with pytest.raises(ValueError):
        _aprobar("rechazar", motivo=motivo)


def test_fila_caducada_o_inexistente_no_revela_nada():
    s = Sfn()
    assert A.aprobar("no-existe", "aprobar", Tabla(), s, aprobador="a", nivel="gerente") == {"estado": "no_encontrada"}
    res, _, s = _aprobar(fila={**FILA, "expira": 10})
    assert res == {"estado": "no_encontrada"} and s.llamadas == []


def test_token_ya_usado_responde_no_encontrada_y_otro_error_se_propaga():
    res, t, _ = _aprobar(sfn=Sfn(error=TaskTimedOut("Task Timed Out")))
    assert res == {"estado": "no_encontrada"} and t.borradas == ["sol-1"]
    with pytest.raises(RuntimeError):
        _aprobar(sfn=Sfn(error=RuntimeError("caida")))


def test_decision_invalida_no_llama_a_nada():
    with pytest.raises(ValueError):
        _aprobar("tal-vez")


FILA_VIGENTE = {**FILA, "expira": 2**40}   # the handler reads the real clock


def _evento_http(decision="aprobar", claims=None, **extra):
    claims = {"sub": "sub-gerente", A.CLAIM_NIVEL: "gerente"} if claims is None else claims
    return {"pathParameters": {"id": "sol-1"}, "body": json.dumps({"decision": decision, **extra}),
            "requestContext": {"authorizer": {"jwt": {"claims": claims}}}}


def test_handler_toma_quien_y_su_nivel_de_los_claims_y_no_del_cuerpo():
    t, s = Tabla(FILA_VIGENTE), Sfn()
    evento = _evento_http(decidido_por="otro", nivel="director")      # body fields are ignored
    r = A.handler_aprobar(evento, None, tabla=t, sfn=s)
    assert r["statusCode"] == 200 and s.llamadas[0][2]["decidido_por"] == "sub-gerente"
    assert s.llamadas[0][2]["nivel"] == "gerente"


@pytest.mark.parametrize("claims,codigo", [
    ({"sub": "sub-cmp", A.CLAIM_NIVEL: "comprador"}, 403),     # level below the order's
    ({"sub": SOLICITANTE, A.CLAIM_NIVEL: "director"}, 403),     # the requester
    ({"sub": "sub-x"}, 403),                                    # no approval level in the token
])
def test_handler_niega_con_403_y_no_envia_nada(claims, codigo):
    t, s = Tabla(FILA_VIGENTE), Sfn()
    r = A.handler_aprobar(_evento_http(claims=claims), None, tabla=t, sfn=s)
    assert r["statusCode"] == codigo and s.llamadas == [] and "sol-1" in t.filas


def test_handler_404_sin_fila_y_400_con_cuerpo_o_decision_invalidos():
    assert A.handler_aprobar(_evento_http(), None, tabla=Tabla(), sfn=Sfn())["statusCode"] == 404
    assert A.handler_aprobar({**_evento_http(), "body": "{no"}, None, tabla=Tabla(FILA_VIGENTE), sfn=Sfn())["statusCode"] == 400
    assert A.handler_aprobar(_evento_http("rechazar"), None, tabla=Tabla(FILA_VIGENTE), sfn=Sfn())["statusCode"] == 400


def test_grupos_se_convierten_en_scopes_y_grupo_desconocido_no_da_nada():
    assert T.scopes_de_grupos(["analistas", "grupo-raro"]) == sorted(
        ["legacybridge/consultas", "legado/leer", "legado/proveedores", "legado/ventas"])
    assert T.scopes_de_grupos(["desconocido"]) == [] and T.scopes_de_grupos(["aprobadores"]) == []


def test_separacion_de_funciones_compradores_proponen_y_aprobadores_deciden():
    compradores = T.scopes_de_grupos(["compradores"])
    assert "legado/compras_proponer" in compradores and "legacybridge/aprobaciones" not in compradores
    for nivel in ("comprador", "gerente", "director"):
        aprob = T.scopes_de_grupos([f"aprobadores-{nivel}"])
        assert "legacybridge/aprobaciones" in aprob and "legado/compras_proponer" not in aprob


def test_nivel_es_el_mas_alto_de_los_grupos_de_aprobacion():
    assert T.nivel_de_grupos(["aprobadores-comprador"]) == "comprador"
    assert T.nivel_de_grupos(["aprobadores-gerente", "aprobadores-comprador"]) == "gerente"
    assert T.nivel_de_grupos(["aprobadores-director", "analistas"]) == "director"
    assert T.nivel_de_grupos(["compradores", "analistas"]) is None and T.nivel_de_grupos([]) is None
    assert T.RANGO == A.RANGO and T.CLAIM_NIVEL == A.CLAIM_NIVEL   # the trigger and the approver agree


def _generacion(grupos):
    evento = {"version": "2", "request": {"groupConfiguration": {"groupsToOverride": grupos}}}
    return T.handler(evento, None)["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]


def test_trigger_v2_anade_scopes_y_el_nivel_del_grupo():
    g = _generacion(["aprobadores-gerente"])
    assert "legacybridge/aprobaciones" in g["scopesToAdd"]
    assert g["claimsToAddOrOverride"] == {"tenant": T.TENANT, T.CLAIM_NIVEL: "gerente"}


def test_trigger_sin_grupo_de_aprobacion_no_anade_nivel():
    assert T.CLAIM_NIVEL not in _generacion(["compradores"])["claimsToAddOrOverride"]


def test_trigger_rechaza_otra_version():
    with pytest.raises(ValueError):
        T.handler({"version": "1"}, None)
