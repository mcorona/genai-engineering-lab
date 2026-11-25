"""Week 20, activity 1: the corrected run of the 20 tasks, the regression gate (Manuel's OK of 2026-11-23).

    .venv/bin/python semana-20/linea_base/corrida.py                         simulation: the plan and the caps, no AWS
    S19_PERFIL=manuel-admin .venv/bin/python semana-20/linea_base/corrida.py --si     the run (Manuel runs it)
    .venv/bin/python semana-20/linea_base/corrida.py --informe               the detail file, offline

The same run as week 19's `eval/eval_aws.py` (the warm-up, then the 10 + 10 CI golden tasks one at a time, through
the public API with real Cognito tokens, the week 13 verifier, the week 17 graders and the week 10 rule), with three
differences, from `resultados/linea_base.md` section 3:
- the deployed agent must run the per-task ceiling (`PRESUPUESTO_TAREA=techo_semana20`, 0.12 USD and 100,000 tokens),
  so the budget cuts no task. The run checks the agent's environment and sends nothing otherwise;
- its own caps, over this run only (and any rerun of it, discarded ones included), not week 19's runs;
- no `cachePoint` (week 20 measures caching alone, in activity 3).

Its output goes to `resultados/corrida_corregida/`, and the detail to `resultados/corrida_corregida_detalle.jsonl`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
S19 = RAIZ / "semana-19"
SALIDA = S20 / "resultados" / "corrida_corregida"
DETALLE = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
PRESUPUESTO = "techo_semana20"
# Hard caps over the warm-up and the 20 tasks of this run. 2.50 USD is Manuel's OK; the tokens follow from 22 tasks at
# the ceiling's 100,000. The expected spend is about 0.90 USD (resultados/linea_base.md, section 3).
TOPE_USD = 2.50
TOPE_TOKENS = 2_200_000
COSTO_ESPERADO_TAREA = 0.045   # USD: week 19's median 0.037, plus the steps the cut tasks still needed


def _eval_aws():
    """Week 19's eval module, with the agent's budget set to the ceiling, so the per-task reservation of the script's
    cap (comparar.limite_de_tarea) is the same limit the deployed agent enforces."""
    os.environ["PRESUPUESTO_TAREA"] = PRESUPUESTO
    for ruta in (S19, RAIZ / "semana-17"):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    spec = importlib.util.spec_from_file_location("eval_aws_s19", S19 / "eval" / "eval_aws.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tope(E, carpeta: Path = SALIDA):
    """This run's cap minus what its earlier attempts spent (their raw files, discarded ones included)."""
    t = E.C.Tope(usd=TOPE_USD, tokens=TOPE_TOKENS)
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        g = json.loads(archivo.read_text(encoding="utf-8"))["gasto"]
        t.sumar(g["usd"], g["tokens"])
    return t


def plan(E, tareas: list[dict], calentamiento: list[dict]) -> dict:
    t = tope(E)
    lim = E.C.limite_de_tarea()
    return {"tareas": [x["id"] for x in tareas], "calentamiento": [x["id"] for x in calentamiento],
            "presupuesto_del_agente": {"valor": PRESUPUESTO, "usd": lim.usd, "tokens": lim.tokens},
            "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
            "gastado_antes": {"usd": round(t.gastado_usd, 6), "tokens": t.gastado_tokens},
            "esperado_usd_modelo": round(COSTO_ESPERADO_TAREA * (len(tareas) + len(calentamiento)), 2)}


def exigir_presupuesto(variables: dict) -> None:
    valor = variables.get("PRESUPUESTO_TAREA", "semana17")
    if valor != PRESUPUESTO:
        raise SystemExit(f"the deployed agent uses PRESUPUESTO_TAREA={valor}: deploy computo with "
                         f"PRESUPUESTO_TAREA={PRESUPUESTO}; no task is sent")


def descartar_previa(carpeta: Path = SALIDA) -> Path | None:
    actual = carpeta / "crudo_eval.json"
    if not actual.exists():
        return None
    destino = carpeta / f"crudo_eval_descartada_{1 + len(list(carpeta.glob('crudo_eval_descartada_*.json')))}.json"
    actual.rename(destino)
    return destino


def main(argv=None) -> int:  # pragma: no cover - the CLI around the tested functions
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--si", "--yes", action="store_true", help="act (by default it only simulates)")
    ap.add_argument("--informe", "--report", action="store_true", help="writes the detail from the raw file, without AWS")
    a = ap.parse_args(argv)
    E = _eval_aws()
    tareas, calentamiento = E.tareas_ci(), E.tareas_de_calentamiento()
    if a.informe:
        datos = json.loads((SALIDA / "crudo_eval.json").read_text(encoding="utf-8"))
        print(E.escribir_detalle(E.detalle(datos), DETALLE))
        print(json.dumps({k: datos[k] for k in ("resumen", "gasto", "acceso")}, ensure_ascii=False, indent=2))
        return 0
    if not a.si:
        print(json.dumps(plan(E, tareas, calentamiento), ensure_ascii=False, indent=2))
        print("Simulation: no AWS calls were made. Add --si (--yes) to act.")
        return 0
    aws = E.AwsEval(os.environ.get("S19_PERFIL", "manuel-admin"))
    if aws.camino_desplegado != "directo":
        raise SystemExit(f"the deployed agent uses {aws.camino_desplegado}; the run goes through the direct path")
    exigir_presupuesto(aws.lam.get_function_configuration(FunctionName=aws.computo["ArnAgente"])
                       ["Environment"]["Variables"])
    todas = tareas + calentamiento
    esperados = aws.cargador_invoca({"modo": "esperados", "consultas": E.consultas_esperadas(todas)})["esperados"]
    tareas, calentamiento = E.con_esperados(tareas, esperados), E.con_esperados(calentamiento, esperados)
    token = aws.token("analista")
    acceso = E.controles_de_acceso(aws.http, token)
    if not all(c["ok"] for c in acceso):
        print(json.dumps(acceso, ensure_ascii=False, indent=2))
        raise SystemExit("the access checks did not return 401 and 403: no task is sent")
    previa = descartar_previa()
    if previa:
        print(f"previous run kept as {previa.name}; its spend still counts toward the cap")
    t = tope(E)
    medir = lambda x: E.C.medir_api(x, "directo", token=token, http=aws.http, spans_entre=aws.spans_entre,  # noqa: E731
                                    largo_respuesta=E.LARGO_RESPUESTA)
    comun = dict(medir=medir, ejecutar_sql=aws.ejecutar_sql, reportes=aws.reportes, tope=t, referencias=E.CR.cargar())
    frio = E.correr(calentamiento, en_paralelo=True, **comun)
    principal = E.correr(tareas, **comun)
    datos = {"fecha": time.strftime("%Y-%m-%d"), "presupuesto_del_agente": PRESUPUESTO, "acceso": acceso,
             "calentamiento": frio, "filas": principal, "esperados": esperados,
             "gasto": E.gasto(frio + principal), "tope": {"usd": TOPE_USD, "tokens": TOPE_TOKENS},
             "resumen": {"exito": E.resumen_exito(principal), "latencia": E.resumen_latencia(frio + principal),
                         "trayectoria": E.resumen_trayectoria(principal), "costo": E.resumen_costo(frio + principal),
                         "comparacion": E.comparar_con_lineas_base(principal)}}
    print(E.escribir("crudo_eval.json", datos, [aws.cuenta], carpeta=SALIDA))
    print(json.dumps(datos["resumen"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
