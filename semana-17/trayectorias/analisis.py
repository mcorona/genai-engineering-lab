"""Week 17, activity 7: the analysis, with confidence intervals as in week 13 ($0, reads committed files only).

    cd semana-17 && uv run --group semana17 python -m trayectorias.analisis

* the loop agent against the Claude Agent SDK agent (week 13's recorded runs, k = 3 each, same 84 tasks);
* before and after the guardrails and budgets (week 13's loop with neither, k = 3, against this activity's paid run with both, k = 1);
* trajectory quality against answer success, for each of them.

Intervals: week 13's own `boot` (bootstrap over TASKS, 2,000 resamples, seed 13); differences by paired bootstrap over tasks (the same
resampled task set for both sides). A sensitivity line scores the SDK without the steps rule, because the SDK always makes one model
call after `responder` (measured on all 252 of its runs): it shows how much of the gap is that structural turn.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias import adaptadores as AD  # noqa: E402
from trayectorias import construir_referencias as CR  # noqa: E402
from trayectorias.evaluadores import evaluar  # noqa: E402

S13 = S17.parent / "semana-13"
if str(S13) not in sys.path:
    sys.path.insert(0, str(S13))
from agente.evaluar import boot  # noqa: E402  (week 13's bootstrap, unchanged)

R13 = S17.parent / "semana-13" / "resultados"
SALIDA = S17 / "resultados" / "trayectorias_analisis.json"
N, SEMILLA = 2000, 13


def _media(listas) -> float:
    vals = [x for lista in listas for x in lista]
    return sum(vals) / len(vals)


def serie_grabada(nombre: str, refs: dict, sin: tuple = ()) -> dict[str, dict[str, list]]:
    """{task id: {"tray": [ok per run], "resp": [success per run]}} for a recorded week 13 set. `sin` drops pass rules (sensitivity)."""
    detalle = CR.leer_jsonl(R13 / f"{nombre}_detalle.jsonl")
    trazas = AD.por_corrida(CR.leer_jsonl(R13 / "trazas" / f"{nombre}.jsonl"))
    out: dict[str, dict[str, list]] = defaultdict(lambda: {"tray": [], "resp": []})
    for f in detalle:
        res = evaluar(refs[f["id"]], AD.desde_traza_del_bucle(trazas[f["corrida"]]))
        ok = not [x for x in res["fallan"] if x not in sin]
        out[f["id"]]["tray"].append(int(ok))
        out[f["id"]]["resp"].append(int(bool(f.get("exito"))))
    return dict(out)


def serie_de_informe(nombre: str) -> dict[str, dict[str, list]]:
    d = json.loads((S17 / "resultados" / nombre).read_text(encoding="utf-8"))
    return {f["id"]: {"tray": [int(f["trayectoria_ok"])], "resp": [int(f["exito"])]} for f in d["por_tarea"]}


def resumen(serie: dict) -> dict:
    tray = {t: v["tray"] for t, v in serie.items()}
    resp = {t: v["resp"] for t, v in serie.items()}
    corridas = sum(len(v) for v in tray.values())
    pares = [(a, b) for t in serie for a, b in zip(serie[t]["tray"], serie[t]["resp"])]
    return {"tareas": len(serie), "corridas": corridas,
            "trayectoria_ok": round(_media(tray.values()), 4), "ic95_trayectoria": [round(x, 4) for x in boot(tray, _media, N, SEMILLA)],
            "respuesta_ok": round(_media(resp.values()), 4), "ic95_respuesta": [round(x, 4) for x in boot(resp, _media, N, SEMILLA)],
            "respuesta_ok_con_trayectoria_mala": sum(1 for a, b in pares if b and not a),
            "respuesta_mala_con_trayectoria_ok": sum(1 for a, b in pares if a and not b), "pares": len(pares)}


def diferencia(a: dict, b: dict, clave: str = "tray") -> dict:
    """b minus a, paired by task (each task's mean over its runs), with a paired bootstrap over the shared tasks."""
    ids = sorted(set(a) & set(b))
    d = {t: sum(b[t][clave]) / len(b[t][clave]) - sum(a[t][clave]) / len(a[t][clave]) for t in ids}
    rnd = random.Random(SEMILLA)
    vals = sorted(sum(d[rnd.choice(ids)] for _ in ids) / len(ids) for _ in range(N))
    return {"diferencia": round(sum(d.values()) / len(ids), 4), "ic95": [round(vals[int(0.025 * N)], 4), round(vals[int(0.975 * N) - 1], 4)],
            "tareas": len(ids)}


def main() -> int:
    refs = CR.cargar()
    bucle = serie_grabada("eval_haiku_low", refs)
    sdk = serie_grabada("eval_sdk_low", refs)
    sdk_sin_pasos = serie_grabada("eval_sdk_low", refs, sin=("pasos",))
    despues = serie_de_informe("trayectorias_real.json")
    informe = {
        "metodo": "bootstrap over tasks, 2,000 resamples, seed 13 (week 13's `boot`); differences by paired bootstrap over tasks",
        "series": {"bucle_semana13_k3": resumen(bucle), "sdk_semana13_k3": resumen(sdk), "sdk_semana13_k3_sin_regla_de_pasos": resumen(sdk_sin_pasos),
                   "bucle_con_guardrails_y_presupuesto_k1": resumen(despues)},
        "comparaciones": {
            "sdk_menos_bucle_trayectoria": diferencia(bucle, sdk),
            "sdk_sin_pasos_menos_bucle_trayectoria": diferencia(bucle, sdk_sin_pasos),
            "sdk_menos_bucle_respuesta": diferencia(bucle, sdk, "resp"),
            "despues_menos_antes_trayectoria": diferencia(bucle, despues),
            "despues_menos_antes_respuesta": diferencia(bucle, despues, "resp"),
        },
    }
    SALIDA.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for n, s in informe["series"].items():
        print(f"{n:40s} trajectory {s['trayectoria_ok']:.3f} {s['ic95_trayectoria']} · answer {s['respuesta_ok']:.3f} {s['ic95_respuesta']} · "
              f"good answer/bad path {s['respuesta_ok_con_trayectoria_mala']} · bad answer/good path {s['respuesta_mala_con_trayectoria_ok']}")
    for n, c in informe["comparaciones"].items():
        print(f"{n:40s} {c['diferencia']:+.3f} {c['ic95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
