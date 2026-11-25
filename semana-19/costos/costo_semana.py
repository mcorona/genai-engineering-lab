"""Week 19, activity 10, step 5: the week's total from Cost Explorer, in one call, only with Manuel's OK.

    .venv/bin/python semana-19/costos/costo_semana.py          simulation: prints the request, no AWS call
    .venv/bin/python semana-19/costos/costo_semana.py --si     the one call (semana19-lectura)

One GetCostAndUsage call, MONTHLY, UnblendedCost, over the whole account, from 2026-11-13 (activity 3, the first one
that created resources) to the end of 2026-11-23 UTC, grouped by SERVICE and RECORD_TYPE:
- usage (RECORD_TYPE Usage) is the gross spend;
- credits (Credit) are reported apart, and gross plus credits is the net.
The account is not filtered by the `proyecto` tag: model tokens are not a tagged resource, so a tag filter would miss
the largest line. The tagged split is in each activity's report (costo_real.md, seguridad.md).

`resultados/costo_semana_llamadas.json` is the ledger: the call is recorded before it is made, and the script
refuses to run once one is recorded. The result goes to `resultados/costo_semana.json`.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
SALIDA = S19 / "resultados" / "costo_semana.json"
REGISTRO = S19 / "resultados" / "costo_semana_llamadas.json"
INICIO, FIN = "2026-11-13", "2026-11-24"      # End is exclusive: through 2026-11-23 UTC
MAX_LLAMADAS = 1
FIJOS = ("Amazon Virtual Private Cloud", "Amazon Relational Database Service", "AWS Key Management Service",
         "AWS Secrets Manager")   # by the hour while the stack is up (eval/costo_real.py's split)
TOPE_SEMANA_USD = 10.0            # Manuel's weekly cap for week 19 (2026-11-18)

# The written estimate of each activity that created resources, with its source. None: no estimate in the repository.
ESTIMACIONES = [
    (3, 0.05, "about 0.05 USD for about 2 h of the base stack at 0.02273973 USD/h", "resultados/base.md"),
    (4, 0.06, "about 0.06 USD for a planned session", "resultados/costo_actividad4.md"),
    (5, None, "no written figure: guardrail/prueba_viva.py prints its estimate at run time (cap 5 USD)",
     "guardrail/prueba_viva.py"),
    (6, None, "no written figure", "Fas5Sema19.md (Log)"),
    (7, 0.90, "about 0.90 USD", "Fas5Sema19.md (Log, 2026-11-18)"),
    (8, 0.14105, "the judge's job only, 0.14105 USD; the eval had caps, not an estimate (1.90, 0.20, 0.45 USD)",
     "resultados/eval_aws.md"),
    (9, 0.52, "about 0.52 USD nominal, 0.89 USD upper bound", "resultados/seguridad/estimacion.md"),
]


def solicitud() -> dict:
    return {"TimePeriod": {"Start": INICIO, "End": FIN}, "Granularity": "MONTHLY", "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "RECORD_TYPE"}]}


def resumen(respuesta: dict) -> dict:
    uso: dict[str, float] = {}
    otros: dict[str, float] = {}
    for periodo in respuesta["ResultsByTime"]:
        for g in periodo.get("Groups", []):
            servicio, tipo = g["Keys"]
            usd = float(g["Metrics"]["UnblendedCost"]["Amount"])
            if tipo == "Usage":
                uso[servicio] = round(uso.get(servicio, 0.0) + usd, 6)
            else:
                otros[tipo] = round(otros.get(tipo, 0.0) + usd, 6)
    bruto = round(sum(uso.values()), 6)
    return {"periodo": {"inicio": INICIO, "fin_exclusivo": FIN}, "granularidad": "MONTHLY",
            "bruto_usd": bruto, "otros_tipos_usd": dict(sorted(otros.items())),
            "neto_usd": round(bruto + sum(otros.values()), 6),
            "uso_por_servicio_usd": dict(sorted(uso.items(), key=lambda kv: -kv[1])),
            "estimado": [p.get("Estimated") for p in respuesta["ResultsByTime"]]}


def informe_md(r: dict) -> list[str]:
    """The week's section of resultados/costo_real.md, from costo_semana.json and ESTIMACIONES."""
    uso = r["uso_por_servicio_usd"]
    fijo = round(sum(v for k, v in uso.items() if k in FIJOS), 6)
    escritas = [e for e in ESTIMACIONES if e[1] is not None]
    suma = round(sum(e[1] for e in escritas), 6)
    l = ["## Week 19 total (activity 10)", "",
         f"One GetCostAndUsage call (`costos/costo_semana.py`, `resultados/costo_semana.json`): the whole account, "
         f"[{r['periodo']['inicio']}, {r['periodo']['fin_exclusivo']}) UTC, MONTHLY, by service and record type. "
         f"Still Estimated: {'yes' if all(r['estimado']) else 'no'}.", "",
         f"- **Gross: {r['bruto_usd']:.6f} USD**; credits {r['otros_tipos_usd'].get('Credit', 0.0):.6f} USD; "
         f"net {r['neto_usd'] + 0.0:.6f} USD. Weekly cap: {TOPE_SEMANA_USD:.2f} USD.",
         f"- Fixed by the hour (VPC, RDS, KMS, Secrets Manager): {fijo:.6f} USD, "
         f"{fijo / r['bruto_usd'] * 100:.1f}% of the gross.", "",
         "| Service | Usage (USD) |", "|---|---|"]
    l += [f"| {k} | {v:.6f} |" for k, v in uso.items() if v]
    l += ["", "Against the written estimates of the activities that created resources (3 to 9):", "",
          "| Activity | Estimate (USD) | What it covered | Source |", "|---|---|---|---|"]
    l += [f"| {a} | {'—' if e is None else f'{e:.5f}'} | {q} | `{f}` |" for a, e, q, f in ESTIMACIONES]
    l += ["", f"The written estimates add up to {suma:.5f} USD ({len(escritas)} of {len(ESTIMACIONES)} activities); "
          f"the week's gross is {r['bruto_usd']:.6f} USD. Most of the gap is the fixed part: each estimate priced "
          "one session, while the stack stayed up between sessions, across several days. Activities 5 and 6 left no "
          "written figure."]
    return l


def correr(cliente, ruta_registro: Path = REGISTRO) -> dict:
    llamadas = json.loads(ruta_registro.read_text(encoding="utf-8")) if ruta_registro.exists() else []
    if len(llamadas) >= MAX_LLAMADAS:
        raise SystemExit(f"The record already has {len(llamadas)} call(s) out of {MAX_LLAMADAS}: no further call is made.")
    llamadas.append({"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "operacion": "GetCostAndUsage", "solicitud": solicitud()})
    ruta_registro.write_text(json.dumps(llamadas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumen(cliente.get_cost_and_usage(**solicitud()))


def main(argv=None, cliente=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--si", "--yes", action="store_true", help="make the one call (by default only prints it)")
    a = ap.parse_args(argv)
    if not a.si:
        print(json.dumps(solicitud(), ensure_ascii=False, indent=2))
        print("Simulation: no AWS calls were made.")
        return 0
    if cliente is None:
        import boto3
        cliente = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "semana19-lectura"),
                                region_name="us-east-1").client("ce")
    r = correr(cliente)
    SALIDA.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("bruto_usd", "otros_tipos_usd", "neto_usd", "estimado")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
