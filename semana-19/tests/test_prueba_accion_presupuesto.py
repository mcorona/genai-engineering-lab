"""Week 19, activity 9, step 4.5: the budget action test script, offline ($0). IAM is moto; Budgets is a fake (moto has
no budget actions)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prueba_accion", S19 / "seguridad" / "prueba_accion_presupuesto.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
CUENTA = "123456789012"
CORREO = "alertas" + chr(64) + "ejemplo.invalid"


class _NoExiste(Exception):
    pass


class _Budgets:
    """Enough of the Budgets API for the script: one budget, its actions, and NotFoundException."""

    class exceptions:
        NotFoundException = _NoExiste

    def __init__(self):
        self.presupuestos, self.acciones = {}, {}

    def create_budget(self, AccountId, Budget):
        self.presupuestos[Budget["BudgetName"]] = Budget

    def describe_budget(self, AccountId, BudgetName):
        if BudgetName not in self.presupuestos:
            raise _NoExiste()
        return {"Budget": {**self.presupuestos[BudgetName], "CalculatedSpend": {"ActualSpend": {"Amount": "3.2"}}}}

    def create_budget_action(self, **kw):
        self.acciones.setdefault(kw["BudgetName"], []).append({**kw, "ActionId": "a-1", "Status": "STANDBY"})

    def describe_budget_actions_for_budget(self, AccountId, BudgetName):
        if BudgetName not in self.presupuestos:
            raise _NoExiste()
        return {"Actions": self.acciones.get(BudgetName, [])}

    def delete_budget_action(self, AccountId, BudgetName, ActionId):
        self.acciones[BudgetName] = [a for a in self.acciones[BudgetName] if a["ActionId"] != ActionId]

    def delete_budget(self, AccountId, BudgetName):
        if BudgetName not in self.presupuestos:
            raise _NoExiste()
        del self.presupuestos[BudgetName]


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    with mock_aws():
        yield boto3.client("iam", region_name="us-east-1"), _Budgets()


def test_sin_si_solo_muestra_el_plan(capsys):
    assert P.main([]) == 0 and P.main(["--crear"]) == 0 and P.main(["--limpiar"]) == 0
    salida = capsys.readouterr().out
    assert salida.count("Simulation: no AWS calls were made.") == 3 and "USD 0.01" in salida


def test_crear_sin_correo_valido_se_detiene(monkeypatch):
    monkeypatch.setenv("ALERTA_EMAIL", "TU_CORREO")
    assert P.main(["--crear", "--si"], sesion=object()) == 2


def test_la_ejecucion_solo_adjunta_la_politica_de_prueba_al_rol_de_prueba():
    d = P.documentos(CUENTA)
    (s,) = d["permisos_ejecucion"]["Statement"]
    assert sorted(s["Action"]) == ["iam:AttachRolePolicy", "iam:DetachRolePolicy"]
    assert s["Resource"].endswith(f":role/{P.OBJETIVO}")
    assert s["Condition"] == {"ArnEquals": {"iam:PolicyARN": f"arn:aws:iam::{CUENTA}:policy/{P.POLITICA}"}}
    (c,) = d["confianza_ejecucion"]["Statement"]
    assert c["Principal"] == {"Service": "budgets.amazonaws.com"}
    assert c["Condition"] == {"StringEquals": {"aws:SourceAccount": CUENTA}}
    assert d["negar"]["Statement"][0]["Effect"] == "Deny"


def test_ciclo_crear_estado_limpiar(aws, tmp_path):
    iam, budgets = aws
    P.crear(iam, budgets, CUENTA, CORREO)
    accion = budgets.acciones[P.PRESUPUESTO][0]
    assert budgets.presupuestos[P.PRESUPUESTO]["BudgetLimit"] == {"Amount": "0.01", "Unit": "USD"}
    tipos = budgets.presupuestos[P.PRESUPUESTO]["CostTypes"]
    assert tipos["IncludeCredit"] is False and tipos["IncludeRefund"] is False   # gross spend, as semana19 counts it
    assert accion["ApprovalModel"] == "AUTOMATIC" and accion["ActionType"] == "APPLY_IAM_POLICY"
    assert accion["Definition"]["IamActionDefinition"]["Roles"] == [P.OBJETIVO]
    assert "despliegue" not in json.dumps(accion)          # never the real deploy role
    e = P.estado(iam, budgets, CUENTA)
    assert e["accion"] == "STANDBY" and e["adjunta"] is False and e["politicas_del_rol_de_prueba"] == []
    # What the action does when it runs:
    iam.attach_role_policy(RoleName=P.OBJETIVO, PolicyArn=f"arn:aws:iam::{CUENTA}:policy/{P.POLITICA}")
    assert P.estado(iam, budgets, CUENTA)["adjunta"] is True
    hecho = P.limpiar(iam, budgets, CUENTA)
    assert "acción borrada" in hecho and f"{P.POLITICA} quitada de {P.OBJETIVO}" in hecho
    assert not [r for r in iam.list_roles()["Roles"] if r["RoleName"].startswith(P.PREFIJO)]
    assert not [p for p in iam.list_policies(Scope="Local")["Policies"] if p["PolicyName"].startswith(P.PREFIJO)]
    assert P.limpiar(iam, budgets, CUENTA) == []           # a second cleanup finds nothing
    assert P.estado(iam, budgets, CUENTA) | {"fecha": None} == {
        "fecha": None, "accion": None, "gasto_real_del_mes_usd": None, "politicas_del_rol_de_prueba": None,
        "adjunta": False}


def test_el_registro_no_lleva_cuenta_ni_correo(aws, tmp_path):
    iam, budgets = aws
    P.crear(iam, budgets, CUENTA, CORREO)
    ruta = tmp_path / "registro.jsonl"
    P.registrar(P.estado(iam, budgets, CUENTA), ruta)
    texto = ruta.read_text(encoding="utf-8")
    assert CUENTA not in texto and CORREO not in texto


def test_cuenta_el_gasto_como_el_presupuesto_de_produccion():
    """The production budget (app.py, semana19) has include_credit=False and include_refund=False; with credits
    subtracted, the test budget read 0.0 USD on 2026-11-22 and its action could never run."""
    app = (S19 / "infra" / "cdk" / "app.py").read_text(encoding="utf-8")
    assert "include_credit=False" in app and "include_refund=False" in app
    assert P.TIPOS_DE_COSTO["IncludeCredit"] is False and P.TIPOS_DE_COSTO["IncludeRefund"] is False
