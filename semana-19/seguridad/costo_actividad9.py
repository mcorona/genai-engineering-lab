"""Week 19, activity 9, step 4.7: what the live review cost, from Cost Explorer, at least a day after the teardown.

Two calls at most, both GetCostAndUsage, DAILY, UnblendedCost, over the UTC days of the live run (the deploy began
on 2026-11-21; the teardown ended on 2026-11-22, about 20:00 UTC):
  A. filtered by the tag proyecto=semana19, grouped by SERVICE: what the project's tagged resources cost;
  B. not filtered, grouped by SERVICE and RECORD_TYPE: the model tokens (an inference call is not a tagged resource,
     so A misses it) and the credits, reported apart from usage.
Manuel approved both calls (estimacion.md, step 4.7). `resultados/seguridad/cost_explorer.json` is the ledger: the
script refuses to run when the ledger already holds 2 calls, and records each call before it is made.

The comparison is with `resultados/seguridad/estimacion.md`: nominal about 0.52 USD, upper bound about 0.89 USD,
activity cap 1.00 USD (its "Total without the unused access analyzer" row and its limits table); and with the spans of the two poisoning runs (0.367471 USD). DAILY granularity puts whatever
else ran on those days into the same figures, so the totals are an upper bound for the activity.

    .venv/bin/python semana-19/seguridad/costo_actividad9.py                 simulation: prints the two requests
    .venv/bin/python semana-19/seguridad/costo_actividad9.py --si            the two calls (semana19-lectura)
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
SALIDA = S19 / "resultados" / "seguridad" / "costo.json"
REGISTRO = S19 / "resultados" / "seguridad" / "cost_explorer.json"
INICIO, FIN = "2026-11-21", "2026-11-23"      # End is exclusive: the UTC days 2026-11-21 and 2026-11-22
MAX_LLAMADAS = 2
ESTIMACION = {"nominal_usd": 0.52, "cota_usd": 0.89, "tope_usd": 1.00}
SPANS_ENVENENAMIENTO_USD = round(0.179818 + 0.187653, 6)
ETIQUETA = {"Tags": {"Key": "proyecto", "Values": ["semana19"]}}


def solicitudes() -> dict[str, dict]:
    base = {"TimePeriod": {"Start": INICIO, "End": FIN}, "Granularity": "DAILY", "Metrics": ["UnblendedCost"]}
    return {"A": {**base, "Filter": ETIQUETA, "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}]},
            "B": {**base, "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"},
                                      {"Type": "DIMENSION", "Key": "RECORD_TYPE"}]}}


def _filas(respuesta: dict) -> list[dict]:
    filas = []
    for dia in respuesta["ResultsByTime"]:
        for g in dia.get("Groups", []):
            filas.append({"dia": dia["TimePeriod"]["Start"], "claves": g["Keys"],
                          "usd": float(g["Metrics"]["UnblendedCost"]["Amount"])})
    return filas


def resumen(a: dict, b: dict) -> dict:
    fa, fb = _filas(a), _filas(b)
    uso = [f for f in fb if f["claves"][1] == "Usage"]
    creditos = round(sum(f["usd"] for f in fb if f["claves"][1] == "Credit"), 6)
    por_servicio: dict[str, float] = {}
    for f in uso:
        por_servicio[f["claves"][0]] = round(por_servicio.get(f["claves"][0], 0.0) + f["usd"], 6)
    total_uso = round(sum(f["usd"] for f in uso), 6)
    etiquetado = round(sum(f["usd"] for f in fa), 6)
    return {"periodo": {"inicio": INICIO, "fin_exclusivo": FIN},
            "etiquetado_proyecto_usd": etiquetado,
            "uso_total_de_la_cuenta_usd": total_uso,
            "uso_por_servicio_usd": dict(sorted(por_servicio.items(), key=lambda kv: -kv[1])),
            "creditos_usd": creditos, "neto_usd": round(total_uso + creditos, 6),
            "spans_envenenamiento_usd": SPANS_ENVENENAMIENTO_USD, "estimacion": ESTIMACION,
            "dentro_de_la_cota": total_uso <= ESTIMACION["cota_usd"],
            "dentro_del_tope": total_uso <= ESTIMACION["tope_usd"],
            "nota": "DAILY: the totals hold everything that ran in the account on those UTC days, an upper bound "
                    "for the activity."}


def _registro(ruta: Path) -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []


def correr(cliente, ruta_registro: Path = REGISTRO) -> dict:
    llamadas = _registro(ruta_registro)
    if len(llamadas) + 2 > MAX_LLAMADAS:
        raise SystemExit(f"El registro ya tiene {len(llamadas)} llamadas de {MAX_LLAMADAS}: no se llama otra vez.")
    respuestas = {}
    for nombre, solicitud in solicitudes().items():
        llamadas.append({"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "operacion": "GetCostAndUsage", "consulta": nombre})
        ruta_registro.parent.mkdir(parents=True, exist_ok=True)
        ruta_registro.write_text(json.dumps(llamadas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        respuestas[nombre] = cliente.get_cost_and_usage(**solicitud)
    return resumen(respuestas["A"], respuestas["B"])


def main(argv=None, cliente=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--si", action="store_true", help="make the two calls (by default only prints them)")
    a = ap.parse_args(argv)
    if not a.si:
        print(json.dumps(solicitudes(), ensure_ascii=False, indent=2))
        print("Simulación: no se llamó a AWS.")
        return 0
    if cliente is None:
        import boto3
        cliente = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "semana19-lectura"),
                                region_name="us-east-1").client("ce")
    r = correr(cliente)
    SALIDA.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("etiquetado_proyecto_usd", "uso_total_de_la_cuenta_usd", "creditos_usd",
                                        "neto_usd", "dentro_de_la_cota", "dentro_del_tope")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
