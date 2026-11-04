"""Week 17, activity 7 (part 1): the graders on the recorded week 13 runs ($0, no model call).

    cd semana-17 && uv run --group semana17 python -m trayectorias.puntuar_semana13

For each recorded set (the calibration set the step margin came from, and the three held-out sets that were never used to define
anything) it scores every run against its frozen reference and reports: the pass rate of each grader, the overall `ok` rate by task type,
and how the trajectory verdict lines up with the golden verdict (week 13's execution-based check of the ANSWER). The two are different
questions: a good answer can come from a wasteful path, and a clean path can still compute the wrong number. The cross table is there to
see how often they disagree, not to make one predict the other.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias import adaptadores as AD  # noqa: E402
from trayectorias import construir_referencias as CR  # noqa: E402
from trayectorias import criterios as C  # noqa: E402
from trayectorias.evaluadores import evaluar  # noqa: E402

R13 = S17.parent / "semana-13" / "resultados"
SALIDA = S17 / "resultados" / "trayectorias_semana13.json"


def puntuar_serie(nombre: str, refs: dict) -> dict:
    detalle = CR.leer_jsonl(R13 / f"{nombre}_detalle.jsonl")
    trazas = AD.por_corrida(CR.leer_jsonl(R13 / "trazas" / f"{nombre}.jsonl"))
    pasa = Counter()
    por_tipo: dict[str, list[bool]] = defaultdict(list)
    cruce = Counter()
    puntajes = []
    fallas = Counter()
    for f in detalle:
        res = evaluar(refs[f["id"]], AD.desde_traza_del_bucle(trazas[f["corrida"]]))
        for n, nota in res["notas"].items():
            if nota["ok"]:
                pasa[n] += 1
        for n in res["fallan"]:
            fallas[n] += 1
        por_tipo[refs[f["id"]].tipo].append(res["ok"])
        cruce[f"trayectoria_{'ok' if res['ok'] else 'falla'}__respuesta_{'ok' if f.get('exito') else 'falla'}"] += 1
        puntajes.append(res["puntaje"])
    n = len(detalle)
    return {"corridas": n, "trayectoria_ok": round(sum(x for v in por_tipo.values() for x in v) / n, 4),
            "puntaje_medio": round(sum(puntajes) / n, 4),
            "pasa_por_evaluador": {e: round(pasa[e] / n, 4) for e in C.EVALUADORES_CON_REGLA},
            "fallas_por_evaluador": dict(fallas.most_common()),
            "ok_por_tipo": {t: round(sum(v) / len(v), 4) for t, v in sorted(por_tipo.items())},
            "cruce_con_la_respuesta": dict(sorted(cruce.items()))}


def main() -> int:
    refs = CR.cargar()
    informe = {"referencias": "trayectorias/referencias.jsonl (frozen, manifiesto.json)", "calibracion": C.CALIBRACION,
               "series": {n: puntuar_serie(n, refs) for n in (C.CALIBRACION, *C.EVALUADAS)}}
    SALIDA.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for n, s in informe["series"].items():
        print(f"{n:22s} runs {s['corridas']:3d} · trajectory ok {s['trayectoria_ok']:.1%} · mean score {s['puntaje_medio']:.3f} · "
              f"failing graders {s['fallas_por_evaluador']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
