"""Week 19, activity 9, step 4.5: the budget action test, in a sandbox budget.

Fas5Sema19.md: "in a sandbox budget, set a $0.01 threshold, confirm the deny policy attaches to a test role, then
detach it". The production action (semana19-control, `AccionPresupuesto`) attaches the freeze policy to the deploy role
at 100 % of USD 50; this test proves the same mechanism end to end without touching that role.

    .venv/bin/python semana-19/seguridad/prueba_accion_presupuesto.py                  plan only, no AWS call
    S19_PERFIL=manuel-admin ALERTA_EMAIL=... ... --crear --si                           creates the five resources
    .venv/bin/python semana-19/seguridad/prueba_accion_presupuesto.py --estado         read-only (semana19-lectura)
    S19_PERFIL=manuel-admin ... --limpiar --si                                          detaches and deletes everything

Resources, all named semana19-prueba-accion*:
- a managed policy that denies everything (`semana19-prueba-accion-negar`);
- a test role with no permissions, that nobody can assume except Lambda (`semana19-prueba-accion-objetivo`);
- the action's execution role, trusted by budgets.amazonaws.com for this account only, that may attach and detach
  only that policy and only on the test role (`semana19-prueba-accion-ejecucion`);
- a monthly COST budget of USD 0.01 over the whole account (`semana19-prueba-accion`), so this month's actual spend is
  already above it;
- its action: APPLY_IAM_POLICY at 100 % of ACTUAL, approval AUTOMATIC.

Budgets evaluates actual spend a few times a day, so the action may take hours to run. `--estado` reads the action's
status and the test role's attached policies, and appends one line to `resultados/seguridad/accion_presupuesto.jsonl`.
The account ID and the e-mail address are never printed or written. Cost: 0 USD (the first two action-enabled budgets
of a month are free; IAM is free).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
REGISTRO = S19 / "resultados" / "seguridad" / "accion_presupuesto.jsonl"
PREFIJO = "semana19-prueba-accion"
PRESUPUESTO = PREFIJO
POLITICA = f"{PREFIJO}-negar"
OBJETIVO = f"{PREFIJO}-objetivo"
EJECUCION = f"{PREFIJO}-ejecucion"
LIMITE_USD = "0.01"
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def documentos(cuenta: str) -> dict[str, dict]:
    arn_politica = f"arn:aws:iam::{cuenta}:policy/{POLITICA}"
    return {
        "negar": {"Version": "2012-10-17", "Statement": [
            {"Sid": "NegarTodo", "Effect": "Deny", "Action": "*", "Resource": "*"}]},
        "confianza_objetivo": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole",
             "Condition": {"StringEquals": {"aws:SourceAccount": cuenta}}}]},
        "confianza_ejecucion": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"Service": "budgets.amazonaws.com"}, "Action": "sts:AssumeRole",
             "Condition": {"StringEquals": {"aws:SourceAccount": cuenta}}}]},
        "permisos_ejecucion": {"Version": "2012-10-17", "Statement": [
            {"Sid": "SoloLaPoliticaDePruebaEnElRolDePrueba", "Effect": "Allow",
             "Action": ["iam:AttachRolePolicy", "iam:DetachRolePolicy"],
             "Resource": f"arn:aws:iam::{cuenta}:role/{OBJETIVO}",
             "Condition": {"ArnEquals": {"iam:PolicyARN": arn_politica}}}]},
    }


def plan() -> list[str]:
    return [f"crear la política {POLITICA} (Deny * sobre *)",
            f"crear el rol {OBJETIVO} (sin permisos; confianza: Lambda de esta cuenta)",
            f"crear el rol {EJECUCION} (confianza: budgets.amazonaws.com de esta cuenta; solo adjunta y quita "
            f"{POLITICA} en {OBJETIVO})",
            f"crear el presupuesto {PRESUPUESTO}: COST mensual de USD {LIMITE_USD} sobre toda la cuenta",
            f"crear su acción APPLY_IAM_POLICY al 100 % de ACTUAL, AUTOMATIC: adjunta {POLITICA} a {OBJETIVO}"]


def crear(iam, budgets, cuenta: str, correo: str) -> list[str]:
    d = documentos(cuenta)
    arn_politica = iam.create_policy(PolicyName=POLITICA, PolicyDocument=json.dumps(d["negar"]),
                                     Description="Activity 9 budget action test: denies everything.")["Policy"]["Arn"]
    iam.create_role(RoleName=OBJETIVO, AssumeRolePolicyDocument=json.dumps(d["confianza_objetivo"]),
                    Description="Activity 9 budget action test: the role the action freezes. No permissions.")
    arn_ejecucion = iam.create_role(RoleName=EJECUCION, AssumeRolePolicyDocument=json.dumps(d["confianza_ejecucion"]),
                                    Description="Activity 9 budget action test: execution role of the action."
                                    )["Role"]["Arn"]
    iam.put_role_policy(RoleName=EJECUCION, PolicyName="adjuntar-solo-la-prueba",
                        PolicyDocument=json.dumps(d["permisos_ejecucion"]))
    budgets.create_budget(AccountId=cuenta, Budget={
        "BudgetName": PRESUPUESTO, "BudgetLimit": {"Amount": LIMITE_USD, "Unit": "USD"},
        "TimeUnit": "MONTHLY", "BudgetType": "COST"})
    time.sleep(10)   # a new role is not usable by Budgets right away (IAM is eventually consistent)
    budgets.create_budget_action(
        AccountId=cuenta, BudgetName=PRESUPUESTO, NotificationType="ACTUAL", ActionType="APPLY_IAM_POLICY",
        ActionThreshold={"ActionThresholdValue": 100.0, "ActionThresholdType": "PERCENTAGE"},
        Definition={"IamActionDefinition": {"PolicyArn": arn_politica, "Roles": [OBJETIVO]}},
        ExecutionRoleArn=arn_ejecucion, ApprovalModel="AUTOMATIC",
        Subscribers=[{"SubscriptionType": "EMAIL", "Address": correo}])
    return ["creado: " + p.split(" (")[0].split(":")[0] for p in plan()]


def _accion(budgets, cuenta: str) -> dict | None:
    try:
        acciones = budgets.describe_budget_actions_for_budget(AccountId=cuenta, BudgetName=PRESUPUESTO)["Actions"]
    except budgets.exceptions.NotFoundException:
        return None
    return acciones[0] if acciones else None


def estado(iam, budgets, cuenta: str) -> dict:
    a = _accion(budgets, cuenta)
    try:
        adjuntas = [p["PolicyName"] for p in iam.list_attached_role_policies(RoleName=OBJETIVO)["AttachedPolicies"]]
    except iam.exceptions.NoSuchEntityException:
        adjuntas = None
    try:
        gasto = budgets.describe_budget(AccountId=cuenta, BudgetName=PRESUPUESTO)["Budget"].get(
            "CalculatedSpend", {}).get("ActualSpend", {}).get("Amount")
    except budgets.exceptions.NotFoundException:
        gasto = None
    return {"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "accion": a["Status"] if a else None, "gasto_real_del_mes_usd": gasto,
            "politicas_del_rol_de_prueba": adjuntas,
            "adjunta": adjuntas is not None and POLITICA in adjuntas}


def limpiar(iam, budgets, cuenta: str) -> list[str]:
    hecho = []
    arn_politica = f"arn:aws:iam::{cuenta}:policy/{POLITICA}"
    a = _accion(budgets, cuenta)
    if a:
        budgets.delete_budget_action(AccountId=cuenta, BudgetName=PRESUPUESTO, ActionId=a["ActionId"])
        hecho.append("acción borrada")
    try:
        budgets.delete_budget(AccountId=cuenta, BudgetName=PRESUPUESTO)
        hecho.append("presupuesto borrado")
    except budgets.exceptions.NotFoundException:
        pass
    try:
        iam.detach_role_policy(RoleName=OBJETIVO, PolicyArn=arn_politica)
        hecho.append(f"{POLITICA} quitada de {OBJETIVO}")
    except iam.exceptions.NoSuchEntityException:
        pass
    for rol, inline in ((EJECUCION, ["adjuntar-solo-la-prueba"]), (OBJETIVO, [])):
        try:
            for nombre in inline:
                iam.delete_role_policy(RoleName=rol, PolicyName=nombre)
            iam.delete_role(RoleName=rol)
            hecho.append(f"rol {rol} borrado")
        except iam.exceptions.NoSuchEntityException:
            pass
    try:
        iam.delete_policy(PolicyArn=arn_politica)
        hecho.append(f"política {POLITICA} borrada")
    except iam.exceptions.NoSuchEntityException:
        pass
    return hecho


def registrar(fila: dict, ruta: Path = REGISTRO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def main(argv=None, sesion=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--crear", action="store_true")
    modo.add_argument("--estado", action="store_true")
    modo.add_argument("--limpiar", action="store_true")
    ap.add_argument("--si", action="store_true", help="act (--crear and --limpiar simulate without it)")
    a = ap.parse_args(argv)
    if not (a.estado or ((a.crear or a.limpiar) and a.si)):
        print("\n".join(plan() if not a.limpiar else ["borrar la acción, el presupuesto, la política adjunta, los dos "
                                                       "roles y la política de prueba"]))
        print("Simulación: no se llamó a AWS.")
        return 0
    correo = os.environ.get("ALERTA_EMAIL", "")
    if a.crear and not _CORREO.match(correo):
        print("ALERTA_EMAIL falta o no tiene forma de correo; no se imprime.", file=sys.stderr)
        return 2
    if sesion is None:
        import boto3
        perfil = os.environ.get("S19_PERFIL", "semana19-lectura" if a.estado else "manuel-admin")
        sesion = boto3.Session(profile_name=perfil, region_name="us-east-1")
    cuenta = sesion.client("sts").get_caller_identity()["Account"]
    iam, budgets = sesion.client("iam"), sesion.client("budgets")
    if a.crear:
        print("\n".join(crear(iam, budgets, cuenta, correo)))
        registrar({"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "evento": "creado"})
    elif a.estado:
        fila = estado(iam, budgets, cuenta)
        registrar(fila)
        print(json.dumps(fila, ensure_ascii=False))
    else:
        hecho = limpiar(iam, budgets, cuenta)
        registrar({"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "evento": "limpiado",
                   "hecho": hecho})
        print("\n".join(hecho) or "nada que borrar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
