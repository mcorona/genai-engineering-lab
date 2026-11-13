"""Week 19, preparation: the `semana19` monthly budget ($5) with alerts, dry run by default.

SUPERSEDED in activity 3: the budget and its action are now declared in the semana19-control stack
(semana-19/infra/cdk/app.py). Do not run --si here: it would create a budget with the same name first.

Alerts (email subscribers): ACTUAL at 50%, ACTUAL at 100%, FORECASTED at 100% of the limit.
The filter is the cost allocation tag `proyecto=semana19`. That tag must be activated in Billing before the budget sees
any cost; AWS takes up to 24 hours to show a newly activated tag.

    uv run --group semana19 python semana-19/infra/presupuesto.py                       # simulation: prints the request
    ALERTA_EMAIL=<correo> uv run --group semana19 python semana-19/infra/presupuesto.py --perfil <admin> --si   # creates it

- Simulation is the default. Without --si nothing is called in AWS (no STS, no Budgets).
- The alert email comes from the ALERTA_EMAIL environment variable. It is never written to the repo or to results.
- If the budget already exists, --si reports it and changes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

NOMBRE = "semana19"
LIMITE_USD = "5"
ETIQUETA = "user:proyecto$semana19"
MARCADOR_CORREO = "<correo de ALERTA_EMAIL>"


def construir_presupuesto(correo: str | None = None) -> dict:
    """Pure: returns the budget and its notifications for create_budget. Tested offline."""
    destino = correo or MARCADOR_CORREO
    suscriptores = [{"SubscriptionType": "EMAIL", "Address": destino}]

    def aviso(tipo: str, umbral: str) -> dict:
        return {
            "Notification": {"NotificationType": tipo, "ComparisonOperator": "GREATER_THAN",
                             "Threshold": float(umbral), "ThresholdType": "PERCENTAGE",
                             "NotificationState": "ALARM"},
            "Subscribers": suscriptores,
        }

    return {
        "Budget": {
            "BudgetName": NOMBRE,
            "BudgetLimit": {"Amount": LIMITE_USD, "Unit": "USD"},
            "TimeUnit": "MONTHLY",
            "BudgetType": "COST",
            "CostFilters": {"TagKeyValue": [ETIQUETA]},
            "CostTypes": {"IncludeTax": True, "IncludeSubscription": True, "UseBlended": False,
                          "IncludeRefund": False, "IncludeCredit": False, "IncludeUpfront": True,
                          "IncludeRecurring": True, "IncludeOtherSubscription": True,
                          "IncludeSupport": True, "IncludeDiscount": True, "UseAmortized": False},
        },
        "NotificationsWithSubscribers": [
            aviso("ACTUAL", "50"),
            aviso("ACTUAL", "100"),
            aviso("FORECASTED", "100"),
        ],
    }


def crear(perfil: str, correo: str) -> dict:
    import boto3  # imported here so the simulation and the tests do not need AWS access
    sesion = boto3.Session(profile_name=perfil, region_name="us-east-1")
    cuenta = sesion.client("sts").get_caller_identity()["Account"]
    cliente = sesion.client("budgets")
    solicitud = construir_presupuesto(correo)
    try:
        cliente.describe_budget(AccountId=cuenta, BudgetName=NOMBRE)
        return {"accion": "sin cambios", "motivo": "el presupuesto ya existe", "cuenta": "<account>"}
    except cliente.exceptions.NotFoundException:
        pass
    cliente.create_budget(AccountId=cuenta, **solicitud)
    return {"accion": "creado", "nombre": NOMBRE, "cuenta": "<account>", "limite_usd": LIMITE_USD,
            "alertas": ["ACTUAL 50%", "ACTUAL 100%", "FORECASTED 100%"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--si", action="store_true", help="crea el presupuesto (sin esta bandera solo simula)")
    ap.add_argument("--perfil", help="perfil admin para crear el presupuesto")
    a = ap.parse_args()
    correo = os.environ.get("ALERTA_EMAIL")

    if not a.si:
        print(json.dumps({"modo": "simulacion", "solicitud": construir_presupuesto(correo),
                          "correo_desde_entorno": bool(correo)}, indent=2, ensure_ascii=False))
        print("Simulación: no se llamó a AWS. Para crearlo: ALERTA_EMAIL=... ... --perfil <admin> --si",
              file=sys.stderr)
        return 0
    if not correo or not a.perfil:
        print("Faltan ALERTA_EMAIL (entorno) o --perfil.", file=sys.stderr)
        return 2
    print(json.dumps(crear(a.perfil, correo), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
