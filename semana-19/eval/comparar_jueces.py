"""Week 19, activity 8: the Bedrock judge against the execution verifier, task by task.

The reference is week 13's verifier (agente/verificar.py): it runs the expected query and compares rows. The judge is
a Bedrock model evaluation job (juez_bedrock.py) with built-in metrics. A task "passes the judge" when every metric in
CRITERIO reaches its threshold.

The thresholds are fixed here, BEFORE any judge result exists (committed with this file, ahead of the live run):
- Builtin.Correctness >= 0.75. Bedrock normalizes the judge's rating to [0, 1]. On its three-point scale (incorrect,
  partially correct, correct: 0, 0.5, 1) only "correct" passes, because the verifier accepts only the exact rows.
- Builtin.Faithfulness >= 0.75: the answer must stay inside the tool results that go in the prompt.
Completeness is reported, not used for the verdict: the verifier does not check the wording of the answer.

Report: agreement, Cohen's kappa, the confusion matrix, false passes (the judge passes what the verifier fails) and
false fails, and one redacted example of each disagreement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
if str(S19) not in sys.path:
    sys.path.insert(0, str(S19))

from comun.redaccion import redactar  # noqa: E402

CRITERIO = {"Builtin.Correctness": 0.75, "Builtin.Faithfulness": 0.75}
REPORTADAS = ("Builtin.Correctness", "Builtin.Faithfulness", "Builtin.Completeness")
LARGO_EJEMPLO = 400


def _nombre(metrica: str) -> str:
    return metrica if metrica.startswith("Builtin.") else f"Builtin.{metrica}"


def veredicto(puntajes: dict[str, float | None], criterio: dict[str, float] = CRITERIO) -> dict:
    """{"aprobado": bool | None, "fallan": [...]}. A missing score (the judge did not rate it) makes the verdict
    None: it is not counted as a pass or a fail and is reported apart."""
    p = {_nombre(k): v for k, v in puntajes.items()}
    faltan = [m for m in criterio if p.get(m) is None]
    if faltan:
        return {"aprobado": None, "fallan": [], "sin_puntaje": faltan}
    fallan = [m for m, u in criterio.items() if p[m] < u]
    return {"aprobado": not fallan, "fallan": fallan}


def kappa(a: list[bool], b: list[bool]) -> float | None:
    """Cohen's kappa for two binary raters. None when chance agreement is 1 (both raters constant and equal)."""
    n = len(a)
    if n == 0 or n != len(b):
        raise ValueError("empty lists or lists of different lengths")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def _ejemplo(fila: dict, cuentas) -> dict:
    corto = lambda t: (t or "")[:LARGO_EJEMPLO]  # noqa: E731
    return redactar({"id": fila["id"], "puntajes": fila["puntajes"], "verificador": fila["verificador"],
                     "respuesta": corto(fila.get("respuesta")), "explicacion": corto(fila.get("explicacion"))}, cuentas)


def comparar(filas: list[dict], *, cuentas=(), criterio: dict[str, float] = CRITERIO) -> dict:
    """filas: [{"id", "verificador": bool, "puntajes": {metric: score}, "respuesta"?, "explicacion"?}]."""
    juzgadas, sin = [], []
    for f in filas:
        v = veredicto(f["puntajes"], criterio)
        (sin if v["aprobado"] is None else juzgadas).append({**f, "juez": v})
    ver = [bool(f["verificador"]) for f in juzgadas]
    juez = [f["juez"]["aprobado"] for f in juzgadas]
    matriz = {"ambos_aprueban": 0, "ambos_reprueban": 0, "falso_aprobado": 0, "falso_reprobado": 0}
    ejemplos: dict[str, dict] = {}
    for f, v, j in zip(juzgadas, ver, juez):
        clave = ("ambos_aprueban" if v else "falso_aprobado") if j else ("falso_reprobado" if v else "ambos_reprueban")
        matriz[clave] += 1
        if clave in ("falso_aprobado", "falso_reprobado") and clave not in ejemplos:
            ejemplos[clave] = _ejemplo(f, cuentas)
    n = len(juzgadas)
    return {
        "criterio": criterio, "n": n, "sin_puntaje": [f["id"] for f in sin],
        "acuerdo": round(sum(x == y for x, y in zip(ver, juez)) / n, 4) if n else None,
        "kappa": kappa(ver, juez) if n else None,
        "matriz": matriz, "falsos_aprobados": [f["id"] for f, v, j in zip(juzgadas, ver, juez) if j and not v],
        "falsos_reprobados": [f["id"] for f, v, j in zip(juzgadas, ver, juez) if v and not j],
        "ejemplos": ejemplos,
        "promedios": {m: (round(sum(xs) / len(xs), 4) if xs else None) for m in REPORTADAS
                      for xs in [[f["puntajes"][m] for f in filas if f["puntajes"].get(m) is not None]]},
    }


def main(argv=None) -> int:  # pragma: no cover - reads the files the live steps wrote
    carpeta = S19 / "resultados" / "eval_aws"
    detalle = [json.loads(l) for l in (S19 / "resultados" / "eval_aws_detalle.jsonl").read_text().splitlines() if l]
    juez = json.loads((carpeta / "juez_bedrock.json").read_text())
    filas = [{"id": d["id"], "verificador": d["exito"], **juez["por_tarea"][d["id"]]}
             for d in detalle if d["fase"] == "principal" and d["id"] in juez["por_tarea"]]
    r = comparar(filas)
    (carpeta / "comparar_jueces.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("n", "acuerdo", "kappa", "matriz")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
