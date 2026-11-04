"""Week 17, activity 4: the control for `s10` (the task that failed without an explanation in the paid run).

    cd semana-13 && uv run --group semana17 python -m agente.correr --tareas s10 --k 3 --paralelo 2 --tope-usd 0.03 --corrida control_s17_s10
    cd ../semana-17 && uv run --group semana17 python -m presupuestos.resumir_control control_s17_s10

The first command is the week 13 loop as it was: no budget, no tracing. This one reads its detail file and writes the comparison
(`resultados/presupuestos_s10_control.json`): ids, success, steps and cost only, never an answer or a query.
The detail file itself is not kept: it holds the model's final answers.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
S13 = S17.parent / "semana-13"
TAREAS = ("s10-es", "s10-en")


def _filas(ruta: Path) -> list[dict]:
    return [json.loads(x) for x in open(ruta, encoding="utf-8")]


def _resumen(filas: list[dict]) -> dict:
    return {t: {"corridas": sum(1 for f in filas if f["id"] == t), "exitos": sum(1 for f in filas if f["id"] == t and f["exito"])} for t in TAREAS}


def main(argv=None) -> int:
    corrida = (argv or sys.argv[1:])[0]
    control = [f for f in _filas(S13 / "resultados" / f"{corrida}_detalle.jsonl") if f["id"] in TAREAS]
    semana_13 = [f for f in _filas(S13 / "resultados" / "eval_haiku_low_detalle.jsonl") if f["id"] in TAREAS]
    con_presupuesto = json.loads((S17 / "resultados" / "presupuestos_s10_repeticiones.json").read_text(encoding="utf-8"))["por_corrida"]
    consola = (S17 / "resultados" / "presupuestos_eval_consola.txt").read_text(encoding="utf-8").splitlines()
    en_las_84 = [{"id": p[0], "exito": p[3] == "exito=si"} for p in (l.split() for l in consola) if p and p[0] in TAREAS and len(p) > 6]
    fila = lambda f: {"id": f["id"], "rep": f.get("rep", 0), "exito": f["exito"], "pasos": f["pasos"], "usd": round(f.get("costo_usd", f.get("usd", 0)), 6)}  # noqa: E731
    informe = {
        "fecha": time.strftime("%Y-%m-%d"), "modelo": "claude-haiku-5-5", "esfuerzo": "low",
        "pregunta": "s10 pasaba 6 de 6 en la semana 13 y falló en la corrida con presupuesto: ¿es la capa de presupuesto o es el modelo?",
        "semana_13_haiku_low": {"resumen": _resumen(semana_13)},
        "corrida_de_84_con_presupuesto": {"resumen": {t: {"corridas": sum(1 for f in en_las_84 if f["id"] == t),
                                                          "exitos": sum(1 for f in en_las_84 if f["id"] == t and f["exito"])} for t in TAREAS}},
        "repeticion_con_presupuesto": {"resumen": _resumen(con_presupuesto), "corridas": [fila(f) for f in con_presupuesto],
                                       "max_tokens_minimo_enviado": min(f["max_tokens_minimo"] for f in con_presupuesto)},
        "control_bucle_de_la_semana_13_sin_presupuesto": {"resumen": _resumen(control), "corridas": [fila(f) for f in control]}}
    tot = lambda k: (sum(v["exitos"] for v in informe[k]["resumen"].values()), sum(v["corridas"] for v in informe[k]["resumen"].values()))  # noqa: E731
    informe["totales"] = {k: {"exitos": tot(k)[0], "corridas": tot(k)[1]} for k in
                          ("semana_13_haiku_low", "corrida_de_84_con_presupuesto", "repeticion_con_presupuesto",
                           "control_bucle_de_la_semana_13_sin_presupuesto")}
    (S17 / "resultados" / "presupuestos_s10_control.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(informe["totales"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
