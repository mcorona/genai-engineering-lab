"""Week 19, activity 6: the pre-token trigger adds the tenant claim the agent requires, with the scopes of the groups."""
from __future__ import annotations

import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from computo import tokens  # noqa: E402


def _evento(grupos):
    return {"version": "2", "request": {"groupConfiguration": {"groupsToOverride": grupos}}}


def test_el_token_trae_el_tenant_del_laboratorio_aunque_no_tenga_grupos():
    out = tokens.handler(_evento([]), None)
    assert out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"] == {
        "tenant": tokens.TENANT}


def test_el_tenant_viaja_junto_con_los_scopes_de_los_grupos():
    out = tokens.handler(_evento(["aprobadores"]), None)["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]
    assert out["claimsToAddOrOverride"]["tenant"] == tokens.TENANT and out["scopesToAdd"]
