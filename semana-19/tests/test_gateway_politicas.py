"""Week 19, activity 7: the gateway's Cedar policies, evaluated locally with cedarpy (offline, $0).

The principal is built as AgentCore builds it from a Cognito access token: an AgentCore::OAuthUser whose id is the
token's `sub` and whose claims are string tags (bedrock-agentcore/latest/devguide/policy-conditions.html). The scopes
of each group come from computo/tokens.py, the same source the pre-token trigger uses.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cedarpy
import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from computo import tokens as T  # noqa: E402
from gateway import esquemas as E  # noqa: E402
from gateway import politicas as P  # noqa: E402
from herramientas import contrato  # noqa: E402

ARN = "arn:aws:bedrock-agentcore:us-east-1:<account>:gateway/semana19-gateway-abc123"
POLITICAS = "\n".join(P.con_gateway(t, ARN) for t in P.politicas().values())
LEER = [contrato.nombre_en_gateway(n) for n in ("describir_esquema", "ejecutar_sql")]
PROPONER = contrato.nombre_en_gateway("proponer_orden_compra")


def decide(grupo: str | None, accion: str, entrada: dict | None = None, *, sub: str = "sub-1", scope: str | None = None,
           gateway: str = ARN) -> str:
    if scope is None:
        scope = " ".join(T.scopes_de_grupos([grupo]) if grupo else [])
    entidades = [{"uid": {"type": "AgentCore::OAuthUser", "id": sub}, "attrs": {}, "parents": [],
                  "tags": {"sub": sub, "scope": scope, "client_id": "cliente", "token_use": "access"}},
                 {"uid": {"type": "AgentCore::Gateway", "id": gateway}, "attrs": {}, "parents": []}]
    peticion = {"principal": f'AgentCore::OAuthUser::"{sub}"', "action": f'AgentCore::Action::"{accion}"',
                "resource": f'AgentCore::Gateway::"{gateway}"', "context": {"input": entrada or {}}}
    return cedarpy.is_authorized(peticion, POLITICAS, entidades).decision.name


PROPUESTA = {"sku": "SKU-0009", "cantidad": 40, "motivo": "reorden", "cedis": 1, "fecha_requerida": "2026-12-05"}
LECTORES = ["analistas", "compradores", "aprobadores-comprador", "aprobadores-gerente", "aprobadores-director"]


@pytest.mark.parametrize("grupo", LECTORES)
@pytest.mark.parametrize("accion", LEER)
def test_analistas_y_aprobadores_leen(grupo, accion):
    assert decide(grupo, accion, {"sql": "SELECT 1"}) == "Allow"


@pytest.mark.parametrize("grupo", ["analistas", "aprobadores-comprador", "aprobadores-gerente", "aprobadores-director"])
def test_un_token_sin_compras_proponer_no_alcanza_la_herramienta_protegida(grupo):
    assert decide(grupo, PROPONER, {**PROPUESTA, "solicitante": "sub-1"}) == "Deny"


def test_el_comprador_propone_a_su_nombre():
    assert decide("compradores", PROPONER, {**PROPUESTA, "solicitante": "sub-1"}) == "Allow"


def test_el_comprador_no_propone_a_nombre_de_otro():
    assert decide("compradores", PROPONER, {**PROPUESTA, "solicitante": "sub-de-otro"}) == "Deny"


def test_propuesta_sin_solicitante_se_niega():
    assert decide("compradores", PROPONER, dict(PROPUESTA)) == "Deny"


@pytest.mark.parametrize("scope", ["", "legacybridge/consultas", "legado/leerX", "xlegado/leer",
                                   "legado/compras_proponerX legado/leer"])
def test_los_scopes_se_comparan_completos(scope):
    """Delimiters matter: a scope that only contains the name does not pass."""
    esperado_leer = "Allow" if scope.split() and "legado/leer" in scope.split() else "Deny"
    assert decide(None, LEER[1], {"sql": "x"}, scope=scope) == esperado_leer
    assert decide(None, PROPONER, {**PROPUESTA, "solicitante": "sub-1"}, scope=scope) == "Deny"


def test_sin_politica_no_hay_permiso():
    """Default deny: a tool no policy names (a decision tool, say) is denied to everyone."""
    for grupo in LECTORES:
        assert decide(grupo, contrato.nombre_en_gateway("decidir_orden")) == "Deny"


def test_otro_gateway_no_esta_permitido():
    otro = ARN.replace("abc123", "zzz999")
    assert decide("analistas", LEER[0], gateway=otro) == "Deny"


def test_las_politicas_nombran_solo_herramientas_del_target():
    nombres = {contrato.nombre_en_gateway(d["name"]) for d in E.leer()}
    citadas = set()
    for texto in P.politicas().values():
        citadas |= {t.split('"')[1] for t in texto.split("AgentCore::Action::")[1:]}
    assert citadas == nombres


def test_cada_politica_nombra_el_gateway_una_vez():
    for texto in P.politicas().values():
        assert texto.count(P.MARCADOR) == 1
    with pytest.raises(ValueError):
        P.con_gateway("permit(principal, action, resource);", ARN)
