"""Week 19, activity 8, step 4: the AWS charges of the run from Cost Explorer, the day after.

At most 3 Cost Explorer calls in the activity, each with Manuel's OK; resultados/eval_aws/cost_explorer.json is the
ledger (call 1 was ListCostAllocationTags). This script makes the remaining two, both GetCostAndUsage, DAILY,
UnblendedCost, over the UTC days of the run's window:
  A. filtered by the tag proyecto=semana19, grouped by SERVICE: what the project's tagged resources cost;
  B. not filtered, grouped by SERVICE and RECORD_TYPE: the model tokens (an inference call is not a tagged resource,
     so A misses it) and the credits, reported apart from usage.
It refuses to run if the ledger has fewer calls left than it needs, and writes each call into the ledger.

Split of the charges (the cost model's split, costos/modelo.py): fixed by the hour (VPC endpoints, RDS, KMS, Secrets
Manager) versus per query (Bedrock and its model lines, Lambda, API Gateway, DynamoDB, Step Functions, Cognito, S3,
CloudWatch). The per-query cost is the per-query usage of the run's days divided by the agent tasks of the run. With
DAILY granularity the day also holds what ran outside the run that day: it is reported as an upper bound, not as an
exact figure.

    .venv/bin/python semana-19/eval/costo_real.py                       # simulation: prints the two requests
    S19_PERFIL=semana19-lectura .venv/bin/python semana-19/eval/costo_real.py --si
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
CARPETA = S19 / "resultados" / "eval_aws"
REGISTRO = CARPETA / "cost_explorer.json"
SALIDA = CARPETA / "costo_real.json"
MAX_LLAMADAS = 3
ETIQUETA = ("proyecto", "semana19")
FIJOS = ("Amazon Virtual Private Cloud", "Amazon Relational Database Service", "AWS Key Management Service",
         "AWS Secrets Manager")


def es_fijo(servicio: str) -> bool:
    return servicio in FIJOS


def dias_de(inicio_s: float, fin_s: float) -> tuple[str, str]:
    """Cost Explorer's [Start, End) over the UTC days the window touches."""
    a = dt.datetime.fromtimestamp(inicio_s, dt.timezone.utc).date()
    b = dt.datetime.fromtimestamp(fin_s, dt.timezone.utc).date() + dt.timedelta(days=1)
    return a.isoformat(), b.isoformat()


def ventana(crudo: dict, extra: list[dict] = ()) -> tuple[float, float]:
    """From the first task's POST to the last task's final GET, over the eval and the approval test."""
    filas = [f for f in crudo.get("calentamiento", []) + crudo["filas"] if f.get("inicio") is not None]
    filas += [t for t in extra if t.get("inicio") is not None]
    return min(f["inicio"] for f in filas), max(f["fin"] for f in filas)


def solicitudes(desde: str, hasta: str) -> list[dict]:
    base = {"TimePeriod": {"Start": desde, "End": hasta}, "Granularity": "DAILY", "Metrics": ["UnblendedCost"]}
    return [{**base, "Filter": {"Tags": {"Key": ETIQUETA[0], "Values": [ETIQUETA[1]], "MatchOptions": ["EQUALS"]}},
             "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}]},
            {**base, "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "RECORD_TYPE"}]}]


def quedan(registro: dict) -> int:
    return MAX_LLAMADAS - len(registro["llamadas"])


def por_servicio(respuesta: dict, *, con_tipo: bool) -> dict:
    """{day: {service: {record type: USD}}} (record type 'Todo' when the call does not group by it), plus whether
    every day is still estimated."""
    dias, estimado = {}, True
    for r in respuesta["ResultsByTime"]:
        estimado = estimado and r.get("Estimated", False)
        d = dias.setdefault(r["TimePeriod"]["Start"], {})
        for g in r.get("Groups", []):
            servicio = g["Keys"][0]
            tipo = g["Keys"][1] if con_tipo else "Todo"
            d.setdefault(servicio, {})[tipo] = round(float(g["Metrics"]["UnblendedCost"]["Amount"]), 10)
    return {"dias": dias, "estimado": estimado}


def desglose(b: dict, tareas: int) -> dict:
    """From call B: usage split into fixed and per query, credits apart, and the per-query cost over the run's tasks."""
    fijo = consulta = creditos = 0.0
    lineas: dict[str, float] = {}
    for d in b["dias"].values():
        for servicio, tipos in d.items():
            for tipo, usd in tipos.items():
                if tipo == "Usage":
                    lineas[servicio] = round(lineas.get(servicio, 0.0) + usd, 10)
                    if es_fijo(servicio):
                        fijo += usd
                    else:
                        consulta += usd
                elif tipo == "Credit":
                    creditos += usd
    dominante = max(lineas, key=lineas.get) if lineas else None
    return {"uso_fijo_usd": round(fijo, 6), "uso_por_consulta_usd": round(consulta, 6),
            "creditos_usd": round(creditos, 6), "neto_usd": round(fijo + consulta + creditos, 6),
            "por_servicio_usd": dict(sorted(lineas.items(), key=lambda x: -x[1])), "partida_dominante": dominante,
            "tareas": tareas, "costo_por_consulta_usd_cota": round(consulta / tareas, 6) if tareas else None}


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", action="store_true", help="hace las 2 llamadas (por omisión solo las muestra)")
    a = ap.parse_args(argv)
    crudo = json.loads((CARPETA / "crudo_eval.json").read_text(encoding="utf-8"))
    aprob = CARPETA / "aprobacion_e2e.json"
    tareas_aprob = json.loads(aprob.read_text(encoding="utf-8"))["tareas"] if aprob.exists() else []
    inicio, fin = ventana(crudo, tareas_aprob)
    desde, hasta = dias_de(inicio, fin)
    pedidos = solicitudes(desde, hasta)
    registro = json.loads(REGISTRO.read_text(encoding="utf-8"))
    print(json.dumps({"ventana_utc": [desde, hasta], "solicitudes": pedidos, "quedan": quedan(registro)},
                     ensure_ascii=False, indent=2))
    if quedan(registro) < len(pedidos):
        raise SystemExit(f"quedan {quedan(registro)} llamadas a Cost Explorer; hacen falta {len(pedidos)}")
    if not a.si:
        print("Simulación: no se llamó a Cost Explorer. Agrega --si para actuar (USD 0.01 por llamada).")
        return 0
    import boto3
    ce = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "semana19-lectura"), region_name="us-east-1").client("ce")
    respuestas = []
    for i, p in enumerate(pedidos):
        r = ce.get_cost_and_usage(**p)
        if r.get("NextPageToken"):
            raise SystemExit("la respuesta tiene más páginas: no se pide otra llamada sin OK")
        respuestas.append(r)
        registro["llamadas"].append({"n": len(registro["llamadas"]) + 1, "operacion": "GetCostAndUsage",
                                     "parametros": p, "perfil": os.environ.get("S19_PERFIL", "semana19-lectura"),
                                     "hora_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                     "paginas": 1})
        registro["quedan"] = quedan(registro)
        REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    a_, b_ = por_servicio(respuestas[0], con_tipo=False), por_servicio(respuestas[1], con_tipo=True)
    tareas = sum(1 for f in crudo.get("calentamiento", []) + crudo["filas"] if f.get("estado") != "no_corrida")
    tareas += len(tareas_aprob)
    salida = {"ventana_utc": [desde, hasta], "ventana_de_la_corrida_s": [round(inicio), round(fin)],
              "por_etiqueta": a_, "por_servicio_y_tipo": b_, "desglose": desglose(b_, tareas)}
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SALIDA)
    print(json.dumps(salida["desglose"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
