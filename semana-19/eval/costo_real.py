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

Before the live call (2026-11-19, reviewed in simulation):
- `--hasta` (exclusive End, YYYY-MM-DD) extends the period past the run to the end of the teardown. The base was
  deleted at 02:00 UTC of the next day, so its last fixed hours are outside the run's own days.
- The per-query cost divides by every agent task that ran in the period: the official run, the discarded runs
  (crudo_eval_descartada_*.json, their tokens are billed on the same days) and the approval test.
- The real figures are compared with activity 2's model (costos/modelo.py, imported, lab and prod) per query and per
  hour of stack. The hours are the base stack's own, from CloudFormation's stack history, inside the period. An error
  beyond ±20 % is flagged: the model is corrected, never the number.

After the live call (2026-11-21, offline, no new call): `--informe` recomputes the split from the saved
costo_real.json and renders resultados/costo_real.md.
- Activity 7's paths (a) and (b) ran the evening of 2026-11-18 CST, which is 2026-11-19 UTC, inside this period. Their
  model spend (their spans, resultados/agentes/crudo_*.json) is set apart from the Haiku line. It reconciles to the
  cent: the Haiku line minus those runs equals the spans of the 57 tasks of activity 8.
- Charges in the period that are not the queries' (FUERA) are reported apart: Cost Explorer itself, and AgentCore,
  activity 7's gateway, which was destroyed before this run.
- The per-query cost has two figures: the model alone (exact, reconciled with the spans) and every per-query line
  (an upper bound: Cost Explorer's "Amazon Bedrock" line joins the judge's job, ApplyGuardrail and Titan).
- The prediction is compared in both versions of the model (v1 and v2, costos/modelo.py). The per-hour row applies
  to lab only: prod was never deployed.

    .venv/bin/python semana-19/eval/costo_real.py --hasta 2026-11-21          # simulation: prints the two requests
    S19_PERFIL=semana19-lectura .venv/bin/python semana-19/eval/costo_real.py --hasta 2026-11-21 --si
    .venv/bin/python semana-19/eval/costo_real.py --informe                   # offline: costo_real.json and .md
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
INFORME = S19 / "resultados" / "costo_real.md"
MODELO = "Claude Haiku 4.5 (Amazon Bedrock Edition)"
# In the period but not the queries' cost: reported apart, never divided by the tasks.
FUERA = {"AWS Cost Explorer": "the cost calls themselves: measurement, not the workload",
         "Amazon Bedrock AgentCore": "activity 7's gateway and Policy, destroyed before this run"}
# Activity 7's runs on the same UTC day (2026-11-19): their model spend is set apart from the Haiku line.
OTRAS_CORRIDAS = (S19 / "resultados" / "agentes" / "crudo_directo.json",
                  S19 / "resultados" / "agentes" / "crudo_gateway.json")
MAX_LLAMADAS = 3
ETIQUETA = ("proyecto", "semana19")
FIJOS = ("Amazon Virtual Private Cloud", "Amazon Relational Database Service", "AWS Key Management Service",
         "AWS Secrets Manager")


UMBRAL_ERROR = 0.20
PILA_FIJA = "semana19-base"   # the fixed part per hour: VPC endpoints and the key live here, RDS in datos (same hours)


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


def periodo(desde: str, hasta_de_la_ventana: str, hasta: str | None) -> tuple[str, str]:
    """[Start, End): End is the run's own unless --hasta extends it. It may not cut the run short."""
    if hasta is None:
        return desde, hasta_de_la_ventana
    dt.date.fromisoformat(hasta)
    if hasta < hasta_de_la_ventana:
        raise ValueError(f"--hasta {hasta} corta la corrida (su ventana termina en {hasta_de_la_ventana})")
    return desde, hasta


def tareas_de_las_corridas(carpeta: Path) -> dict:
    """Agent tasks that ran (warm-up included, aborted ones not), per run file, plus the approval test's tasks."""
    por_archivo = {}
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        crudo = json.loads(archivo.read_text(encoding="utf-8"))
        por_archivo[archivo.name] = sum(1 for f in crudo.get("calentamiento", []) + crudo["filas"]
                                        if f.get("estado") != "no_corrida")
    aprob = carpeta / "aprobacion_e2e.json"
    if aprob.exists():
        por_archivo[aprob.name] = len(json.loads(aprob.read_text(encoding="utf-8"))["tareas"])
    return {"por_archivo": por_archivo, "total": sum(por_archivo.values())}


def gasto_de_otras_corridas(rutas=OTRAS_CORRIDAS) -> dict[str, float]:
    """Model USD of the other activities' runs inside the period, from their own spans."""
    return {r.name: json.loads(r.read_text(encoding="utf-8"))["gasto"]["usd"] for r in rutas if r.exists()}


def modelo_de_las_tareas(carpeta: Path = CARPETA) -> float:
    """Model USD of activity 8's tasks from their spans (the reconciliation with Cost Explorer)."""
    total = 0.0
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        crudo = json.loads(archivo.read_text(encoding="utf-8"))
        total += sum(f.get("costo_usd") or 0.0 for f in crudo.get("calentamiento", []) + crudo["filas"])
    aprob = carpeta / "aprobacion_e2e.json"
    if aprob.exists():
        total += sum(t.get("costo_usd") or 0.0 for t in json.loads(aprob.read_text(encoding="utf-8"))["tareas"])
    return round(total, 6)


def horas_de_pila(resumenes: list[dict], pila: str, desde: str, hasta: str) -> float:
    """Hours the stack existed inside [desde, hasta) UTC, from list_stacks summaries (creation to deletion start)."""
    a = dt.datetime.fromisoformat(desde).replace(tzinfo=dt.timezone.utc)
    b = dt.datetime.fromisoformat(hasta).replace(tzinfo=dt.timezone.utc)
    segundos = 0.0
    for r in resumenes:
        if r["StackName"] != pila:
            continue
        ini = max(a, r["CreationTime"])
        fin = min(b, r.get("DeletionTime") or b)
        segundos += max(0.0, (fin - ini).total_seconds())
    return round(segundos / 3600, 4)


def _error(real, pred):
    return round((real - pred) / pred, 4) if real is not None and pred else None


def comparar(desglose: dict, horas: float, prediccion: dict[str, dict], desplegado: str = "lab") -> dict:
    """Real per query and per hour of stack against the model's, per profile. Error = (real − predicted) / predicted.
    Per query: against every per-query line (real_usd, an upper bound) and, when known, the model alone
    (real_modelo_usd, exact). Per hour: only the deployed profile applies."""
    real_hora = round(desglose["uso_fijo_usd"] / horas, 6) if horas else None
    filas = {}
    for perfil, pred in prediccion.items():
        p = pred["costo_por_consulta_usd"]
        fila = {"predicho_usd": round(p, 8), "real_usd": desglose["costo_por_consulta_usd_cota"],
                "error": _error(desglose["costo_por_consulta_usd_cota"], p)}
        if desglose.get("costo_por_consulta_modelo_usd") is not None:
            fila |= {"real_modelo_usd": desglose["costo_por_consulta_modelo_usd"],
                     "error_modelo": _error(desglose["costo_por_consulta_modelo_usd"], p)}
        errores = [e for k, e in fila.items() if k.startswith("error") and e is not None]
        fila["fuera_de_umbral"] = any(abs(e) > UMBRAL_ERROR for e in errores)
        filas[f"{perfil}.por_consulta"] = fila
        ph = pred["costo_por_hora_usd"]
        if perfil == desplegado:
            e = _error(real_hora, ph)
            filas[f"{perfil}.por_hora"] = {"predicho_usd": round(ph, 8), "real_usd": real_hora, "error": e,
                                           "fuera_de_umbral": e is not None and abs(e) > UMBRAL_ERROR}
        else:
            filas[f"{perfil}.por_hora"] = {"predicho_usd": round(ph, 8), "real_usd": None, "error": None,
                                           "fuera_de_umbral": False,
                                           "no_aplica": f"{perfil} was never deployed; the real hours are {desplegado}'s"}
    return {"horas_de_pila": horas, "umbral": UMBRAL_ERROR, "filas": filas,
            "corregir_modelo": any(f["fuera_de_umbral"] for f in filas.values())}


def prediccion_del_modelo(version: str = "v1") -> dict[str, dict]:
    """The cost model with the parameters of cotizacion.md (its defaults), lab and prod, in one version: v1 is
    activity 2's, v2 the corrected one (costos/modelo.py)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("modelo_costos_s19", S19 / "costos" / "modelo.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return {p: {k: m.modelo(m.Parametros(perfil=p, version=version))[k]
                for k in ("costo_por_hora_usd", "costo_por_consulta_usd")} for p in ("lab", "prod")}


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


def desglose(b: dict, tareas: int, otras_corridas: dict[str, float] | None = None,
             modelo_spans_usd: float | None = None) -> dict:
    """From call B: usage split into fixed, per query and outside the queries (FUERA), credits apart, and the
    per-query cost over the run's tasks. The other activities' model spend (otras_corridas) is taken off the model
    line; with the tasks' own span total, the model part is reconciled and reported exactly."""
    fijo = consulta = creditos = 0.0
    lineas: dict[str, float] = {}
    fuera: dict[str, float] = {}
    for d in b["dias"].values():
        for servicio, tipos in d.items():
            for tipo, usd in tipos.items():
                if tipo == "Usage":
                    lineas[servicio] = round(lineas.get(servicio, 0.0) + usd, 10)
                    if es_fijo(servicio):
                        fijo += usd
                    elif servicio in FUERA:
                        fuera[servicio] = round(fuera.get(servicio, 0.0) + usd, 10)
                    else:
                        consulta += usd
                elif tipo == "Credit":
                    creditos += usd
    otras = round(sum((otras_corridas or {}).values()), 6)
    consulta -= otras
    modelo = round(lineas.get(MODELO, 0.0) - otras, 6) if MODELO in lineas else None
    dominante = max(lineas, key=lineas.get) if lineas else None
    salida = {"uso_fijo_usd": round(fijo, 6), "uso_por_consulta_usd": round(consulta, 6),
              "creditos_usd": round(creditos, 6), "neto_usd": round(sum(lineas.values()) + creditos, 6),
              "por_servicio_usd": dict(sorted(lineas.items(), key=lambda x: -x[1])), "partida_dominante": dominante,
              "fuera_usd": fuera, "otras_corridas_modelo_usd": otras_corridas or {}, "modelo_atribuible_usd": modelo,
              "tareas": tareas, "costo_por_consulta_usd_cota": round(consulta / tareas, 6) if tareas else None,
              "costo_por_consulta_modelo_usd": round(modelo / tareas, 6) if tareas and modelo is not None else None}
    if modelo_spans_usd is not None and modelo is not None:
        salida["conciliacion"] = {"spans_usd": modelo_spans_usd, "cost_explorer_usd": modelo,
                                  "diferencia_usd": round(modelo - modelo_spans_usd, 6)}
    return salida


def armar(a_: dict, b_: dict, ventana_utc, ventana_s, horas: float, carpeta: Path = CARPETA) -> dict:
    """Everything the report needs, from the two answers: split, reconciliation and both model versions."""
    tareas = tareas_de_las_corridas(carpeta)
    d = desglose(b_, tareas["total"], gasto_de_otras_corridas(), modelo_de_las_tareas(carpeta))
    return {"ventana_utc": list(ventana_utc), "ventana_de_la_corrida_s": list(ventana_s), "tareas": tareas,
            "por_etiqueta": a_, "por_servicio_y_tipo": b_, "desglose": d,
            "comparacion": {v: comparar(d, horas, prediccion_del_modelo(v)) for v in ("v1", "v2")}}


def _usd(x, n=6):
    return "—" if x is None else f"{x:.{n}f}"


def _pct(x):
    return "—" if x is None else f"{x * 100:+.1f} %"


def informe_md(r: dict) -> str:
    """resultados/costo_real.md, rendered from costo_real.json only: no figure is typed by hand."""
    d, c = r["desglose"], r["comparacion"]
    desde, hasta = r["ventana_utc"]
    horas = c["v1"]["horas_de_pila"]
    l = ["# Week 19, activity 8: real cost from Cost Explorer", "",
         "Rendered by `eval/costo_real.py --informe` from `resultados/eval_aws/costo_real.json`. "
         "Do not edit by hand.", "",
         "## Period and calls", "",
         f"- Period: [{desde}, {hasta}) UTC, DAILY. The base stack was up {horas} h inside it "
         "(CloudFormation's stack history).",
         "- Two GetCostAndUsage calls (calls 2 and 3 of 3 in `cost_explorer.json`): A filtered by the tag "
         "`proyecto=semana19` and grouped by service; B unfiltered, grouped by service and record type.",
         f"- Every day still Estimated: {'yes' if r['por_servicio_y_tipo']['estimado'] else 'no'}. "
         f"Credits covered {_usd(-d['creditos_usd'], 4)} USD; net {_usd(d['neto_usd'] + 0.0, 4)} USD.",
         f"- Agent tasks billed in the period: {r['tareas']['total']} "
         f"({', '.join(f'{k} {v}' for k, v in r['tareas']['por_archivo'].items())}).", "",
         "## By service (call B, usage)", "", "| Service | Usage (USD) | Split |", "|---|---|---|"]
    for servicio, usd in d["por_servicio_usd"].items():
        parte = ("no charge" if not usd else "fixed per hour" if es_fijo(servicio)
                 else "outside the queries" if servicio in FUERA else "per query")
        l.append(f"| {servicio} | {_usd(usd)} | {parte} |")
    l += ["", "## By the tag proyecto=semana19 (call A)", "",
          "Only tagged resources: inference calls are not resources, so the model lines are missing here.", "",
          "| Day | Service | USD |", "|---|---|---|"]
    for dia, servicios in r["por_etiqueta"]["dias"].items():
        for servicio, tipos in servicios.items():
            l.append(f"| {dia} | {servicio} | {_usd(sum(tipos.values()))} |")
    l += ["", "## Split", "",
          f"- Fixed per hour (VPC, RDS, KMS, Secrets Manager): {_usd(d['uso_fijo_usd'])} USD, "
          f"{_usd(d['uso_fijo_usd'] / horas if horas else None)} USD per hour of stack.",
          f"- Per query: {_usd(d['uso_por_consulta_usd'])} USD after setting apart the other activities' runs.",
          "- Outside the queries: " + "; ".join(f"{k} {_usd(v)} USD ({FUERA[k]})" for k, v in d["fuera_usd"].items())
          + ".",
          "- Other activities' model spend in the period, from their spans: "
          + "; ".join(f"`{k}` {_usd(v)} USD" for k, v in d["otras_corridas_modelo_usd"].items())
          + " (activity 7's paths (a) and (b), the evening of 2026-11-18 CST).", ""]
    if "conciliacion" in d:
        k = d["conciliacion"]
        l += [f"**Reconciliation:** the Haiku line minus those runs is {_usd(k['cost_explorer_usd'])} USD; the spans of "
              f"the {d['tareas']} tasks add up to {_usd(k['spans_usd'])} USD (difference {_usd(k['diferencia_usd'])}).", ""]
    l += ["## Cost per query", "",
          f"- Model alone (exact): {_usd(d['costo_por_consulta_modelo_usd'])} USD per task.",
          f"- Every per-query line (upper bound): {_usd(d['costo_por_consulta_usd_cota'])} USD per task. "
          "Cost Explorer's \"Amazon Bedrock\" line joins the Bedrock judge's job (an eval cost, not a query's), "
          "ApplyGuardrail and Titan; grouping by service cannot split them.", "",
          "## Predicted against real", "",
          "| Version | Row | Predicted (USD) | Real (USD) | Error | Real, model alone (USD) | Error | Beyond ±20 % |",
          "|---|---|---|---|---|---|---|---|"]
    for v, comp in c.items():
        for fila, f in comp["filas"].items():
            if f.get("no_aplica"):
                l.append(f"| {v} | {fila} | {_usd(f['predicho_usd'], 8)} | n/a | — | — | — | {f['no_aplica']} |")
                continue
            l.append(f"| {v} | {fila} | {_usd(f['predicho_usd'], 8)} | {_usd(f['real_usd'])} | {_pct(f['error'])} | "
                     f"{_usd(f.get('real_modelo_usd'))} | {_pct(f.get('error_modelo'))} | "
                     f"{'yes' if f['fuera_de_umbral'] else 'no'} |")
    l += ["", "## What stayed out or could not be attributed", "",
          "- The \"Amazon Bedrock\" line cannot be split between the judge, ApplyGuardrail and Titan; it only enters "
          "the upper bound.",
          "- DAILY granularity: anything else that ran on those UTC days is in the lines. The other activities' runs "
          "that are known are set apart above.",
          "- The days were still Estimated when read: the final bill may move by cents."]
    return "\n".join(l)


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", action="store_true", help="hace las 2 llamadas (por omisión solo las muestra)")
    ap.add_argument("--hasta", help="End exclusivo AAAA-MM-DD: extiende el periodo hasta el fin del teardown")
    ap.add_argument("--informe", action="store_true", help="sin llamadas: recalcula costo_real.json y escribe costo_real.md")
    a = ap.parse_args(argv)
    if a.informe:
        previo = json.loads(SALIDA.read_text(encoding="utf-8"))
        horas = (previo["comparacion"].get("v1") or previo["comparacion"])["horas_de_pila"]
        salida = armar(previo["por_etiqueta"], previo["por_servicio_y_tipo"], previo["ventana_utc"],
                       previo["ventana_de_la_corrida_s"], horas)
        SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        INFORME.write_text(informe_md(salida) + "\n", encoding="utf-8")
        print(SALIDA, INFORME, sep="\n")
        return 0
    crudo = json.loads((CARPETA / "crudo_eval.json").read_text(encoding="utf-8"))
    aprob = CARPETA / "aprobacion_e2e.json"
    tareas_aprob = json.loads(aprob.read_text(encoding="utf-8"))["tareas"] if aprob.exists() else []
    inicio, fin = ventana(crudo, tareas_aprob)
    desde, hasta = periodo(*dias_de(inicio, fin), a.hasta)
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
    sesion = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "semana19-lectura"), region_name="us-east-1")
    # Free, read-only, before any paid call: the base stack's hours inside the period.
    resumenes = [s for p in sesion.client("cloudformation").get_paginator("list_stacks").paginate()
                 for s in p["StackSummaries"] if s["StackName"] == PILA_FIJA]
    horas = horas_de_pila(resumenes, PILA_FIJA, desde, hasta)
    ce = sesion.client("ce")
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
    salida = armar(a_, b_, (desde, hasta), (round(inicio), round(fin)), horas)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INFORME.write_text(informe_md(salida) + "\n", encoding="utf-8")
    print(SALIDA)
    print(json.dumps({"desglose": salida["desglose"], "comparacion": salida["comparacion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
