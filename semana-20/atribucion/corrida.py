"""Week 20, activity 2: the cost of a query three ways, on one small run of four tasks.

    .venv/bin/python semana-20/atribucion/corrida.py                          simulation: tasks, caps, estimate; no AWS
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/atribucion/corrida.py --si        the run (Manuel runs it)
    .venv/bin/python semana-20/atribucion/corrida.py --metricas --si          the EMF sums (read-only profile)
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/atribucion/corrida.py --cost-explorer --si   next day, 0.01 USD
    .venv/bin/python semana-20/atribucion/corrida.py --informe                the reconciliation, offline

The run is activity 1's corrected run (`linea_base/corrida.py`: the public API, real Cognito tokens, the week 13
verifier) on four tasks that passed there, with three checks before anything is sent: the agent runs the ceiling
budget, the direct path, and calls an APPLICATION inference profile (its MODELO variable). Its own caps.

The three figures per run:
1. spans: each task's tokens from its agent span, times the Price List prices of `resultados/precios.json`
   (regional on-demand, the price of the `us.` profile), recomputed here, not read from `lab.run.cost_usd`;
2. EMF: the sum of the `LegacyBridge` metric `CostoUSD` over the run's window (GetMetricData, about 0.0001 USD);
3. Cost Explorer: Bedrock cost on the run's day grouped by the tag `componente` (one GetCostAndUsage, 0.01 USD).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
SALIDA = S20 / "resultados" / "atribucion"
PRECIOS = S20 / "resultados" / "precios.json"
# Four tasks that passed in activity 1's corrected run, two per language, from 3 to 6 steps: 0.117 USD there.
TAREAS = ("s03-es", "s06-es", "s03-en", "v01-en")
COSTO_LINEA_BASE = {"s03-es": 0.0175769, "s06-es": 0.0392337, "s03-en": 0.0315029, "v01-en": 0.0282931}
TOPE_USD = 0.40            # model, over this run and any rerun of it (Manuel's OK pending)
TOPE_TOKENS = 400_000      # the four tasks at the 100,000-token ceiling
MODELO_PRECIO = "Claude Haiku 4.5"
TIPOS = {"entrada": "USE1-MP:USE1_InputTokenCount-Units", "salida": "USE1-MP:USE1_OutputTokenCount-Units",
         "cache_lectura": "USE1-MP:USE1_CacheReadInputTokenCount-Units",
         "cache_escritura": "USE1-MP:USE1_CacheWriteInputTokenCount-Units"}
MARGEN_EMF_S = 120         # EMF timestamps are the agent's; the window is widened by this on each side


def _linea_base():
    spec = importlib.util.spec_from_file_location("corrida_linea_base", S20 / "linea_base" / "corrida.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- pure parts (tested)

def precios_por_millon(ruta: Path = PRECIOS) -> dict[str, float]:
    """USD per 1M tokens of each token kind, from the Price List rows of activity 1 (regional on-demand)."""
    filas = json.loads(ruta.read_text(encoding="utf-8"))["precios"]
    salida = {}
    for clave, uso in TIPOS.items():
        (fila,) = [f for f in filas if f["modelo"] == MODELO_PRECIO and f["uso"] == uso]
        (p,) = [x for x in fila["precios"] if x["unidad"] == "1M tokens"]
        salida[clave] = float(p["usd"])
    return salida


def costo_desde_spans(fila: dict, precios: dict[str, float]) -> float:
    return round(sum((fila.get(f"tokens_{k}") or 0) * precios[k] / 1e6 for k in precios), 7)


def ventana(filas: list[dict]) -> tuple[float, float]:
    hechas = [f for f in filas if f.get("inicio") is not None]
    return min(f["inicio"] for f in hechas) - MARGEN_EMF_S, max(f["fin"] for f in hechas) + MARGEN_EMF_S


def consulta_metricas(desde: float, hasta: float, ruta: str = "fija") -> dict:
    """GetMetricData: the sum of each metric over the window, one period, dimensions as the agent emits them (activity
    4: the route metrics by Ruta, the rest without dimensions)."""
    from agente import metricas as M  # noqa: PLC0415

    def dims(n: str) -> list[dict]:
        return [{"Name": "Ruta", "Value": ruta}] if n in M.POR_RUTA else []
    periodo = max(60, int((hasta - desde) // 60 + 1) * 60)
    return {"StartTime": datetime.fromtimestamp(desde, timezone.utc), "EndTime": datetime.fromtimestamp(hasta, timezone.utc),
            "MetricDataQueries": [{"Id": f"m{i}", "Label": n, "ReturnData": True, "MetricStat": {
                "Metric": {"Namespace": M.ESPACIO, "MetricName": n, "Dimensions": dims(n)}, "Period": periodo,
                "Stat": "Sum"}} for i, n in enumerate(M.METRICAS)]}


def consulta_cost_explorer(dia: str) -> dict:
    fin = (datetime.fromisoformat(dia) + timedelta(days=1)).date().isoformat()
    return {"TimePeriod": {"Start": dia, "End": fin}, "Granularity": "DAILY", "Metrics": ["UnblendedCost"],
            "Filter": {"Tags": {"Key": "proyecto", "Values": ["semana19"]}},
            "GroupBy": [{"Type": "TAG", "Key": "componente"}, {"Type": "DIMENSION", "Key": "USAGE_TYPE"}]}


def conciliar(filas: list[dict], precios: dict[str, float], emf: dict | None, ce: dict | None) -> dict:
    hechas = [f for f in filas if f.get("estado") != "no_corrida"]
    por_tarea = [{"id": f["id_tarea"], "spans_recalculado": costo_desde_spans(f, precios),
                  "span_lab_run_cost_usd": f.get("costo_usd")} for f in hechas]
    spans = round(sum(t["spans_recalculado"] for t in por_tarea), 7)
    salida = {"tareas": por_tarea, "spans_usd": spans,
              "span_lab_run_cost_usd": round(sum(t["span_lab_run_cost_usd"] or 0 for t in por_tarea), 7)}
    if emf is not None:
        salida["emf_usd"] = round(emf.get("CostoUSD", 0.0), 7)
        salida["emf_menos_spans_usd"] = round(salida["emf_usd"] - spans, 7)
    if ce is not None:
        salida["cost_explorer"] = ce
    return salida


def exigir_agente(variables: dict) -> None:
    """Nothing is sent unless the agent calls an application inference profile (the run measures its tag)."""
    if ":application-inference-profile/" not in variables.get("MODELO", ""):
        raise SystemExit("the deployed agent does not call an application inference profile (MODELO); "
                         "no task is sent")


# ---------------------------------------------------------------- CLI

def _crudo() -> dict:
    return json.loads((SALIDA / "crudo.json").read_text(encoding="utf-8"))


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", "--yes", action="store_true", help="act (by default it only simulates)")
    ap.add_argument("--metricas", "--metrics", action="store_true", help="sums the EMF of the run's window")
    ap.add_argument("--cost-explorer", action="store_true", help="GetCostAndUsage for the day of the run (0.01 USD)")
    ap.add_argument("--informe", "--report", action="store_true", help="the reconciliation, without AWS")
    a = ap.parse_args(argv)
    LB = _linea_base()
    E = LB._eval_aws()
    precios = precios_por_millon()
    if a.informe:
        emf = json.loads((SALIDA / "emf.json").read_text()) if (SALIDA / "emf.json").exists() else None
        ce = json.loads((SALIDA / "cost_explorer.json").read_text()) if (SALIDA / "cost_explorer.json").exists() else None
        print(json.dumps(conciliar(_crudo()["filas"], precios, emf, ce), ensure_ascii=False, indent=2))
        return 0
    if a.metricas or a.cost_explorer:
        import boto3  # noqa: PLC0415
        if a.metricas:
            desde, hasta = ventana(_crudo()["filas"])
            consulta = consulta_metricas(desde, hasta)
            if not a.si:
                print(json.dumps(consulta, default=str, indent=2))
                return 0
            cw = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "semana19-lectura"),
                               region_name="us-east-1").client("cloudwatch")
            r = cw.get_metric_data(**consulta)
            sumas = {m["Label"]: round(sum(m["Values"]), 7) for m in r["MetricDataResults"]}
            print(E.escribir("emf.json", sumas, carpeta=SALIDA))
            return 0
        consulta = consulta_cost_explorer(_crudo()["fecha"])
        if not a.si:
            print(json.dumps(consulta, indent=2))
            return 0
        ce = boto3.Session(profile_name=os.environ.get("S19_PERFIL", "manuel-admin")).client("ce", region_name="us-east-1")
        r = ce.get_cost_and_usage(**consulta)
        grupos = [{"claves": g["Keys"], "usd": float(g["Metrics"]["UnblendedCost"]["Amount"])}
                  for d in r["ResultsByTime"] for g in d["Groups"]]
        print(E.escribir("cost_explorer.json", {"consulta": consulta, "grupos": grupos}, carpeta=SALIDA))
        return 0

    todas = {t["id"]: t for t in E.tareas_ci()}
    tareas = [todas[i] for i in TAREAS]
    t = E.C.Tope(usd=TOPE_USD, tokens=TOPE_TOKENS)
    for archivo in sorted(SALIDA.glob("crudo*.json")):
        g = json.loads(archivo.read_text(encoding="utf-8"))["gasto"]
        t.sumar(g["usd"], g["tokens"])
    if not a.si:
        print(json.dumps({"tareas": list(TAREAS), "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
                          "gastado_antes": {"usd": round(t.gastado_usd, 6), "tokens": t.gastado_tokens},
                          "esperado_usd_modelo": round(sum(COSTO_LINEA_BASE.values()), 4)}, indent=2))
        print("Simulation: no AWS calls were made. Add --si (--yes) to act.")
        return 0
    aws = E.AwsEval(os.environ.get("S19_PERFIL", "manuel-admin"))
    if aws.camino_desplegado != "directo":
        raise SystemExit(f"the deployed agent uses {aws.camino_desplegado}; the run goes through the direct path")
    variables = aws.lam.get_function_configuration(FunctionName=aws.computo["ArnAgente"])["Environment"]["Variables"]
    LB.exigir_presupuesto(variables)
    exigir_agente(variables)
    esperados = aws.cargador_invoca({"modo": "esperados", "consultas": E.consultas_esperadas(tareas)})["esperados"]
    tareas = E.con_esperados(tareas, esperados)
    token = aws.token("analista")
    medir = lambda x: E.C.medir_api(x, "directo", token=token, http=aws.http, spans_entre=aws.spans_entre,  # noqa: E731
                                    largo_respuesta=E.LARGO_RESPUESTA)
    filas = E.correr(tareas, medir=medir, ejecutar_sql=aws.ejecutar_sql, reportes=aws.reportes, tope=t,
                     referencias=E.CR.cargar())
    datos = {"fecha": time.strftime("%Y-%m-%d", time.gmtime()), "modelo": "perfil de aplicación semana19-agente",
             "filas": filas, "gasto": E.gasto(filas), "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
             "exito": E.resumen_exito(filas)}
    print(E.escribir("crudo.json", datos, [aws.cuenta], carpeta=SALIDA))
    print(json.dumps(conciliar(filas, precios, None, None), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(S20.parent / "semana-19"))
    raise SystemExit(main())
