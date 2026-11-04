"""Week 17, activity 7 (part 1): the reference trajectories of the 84 golden tasks, frozen with a hash manifest ($0, no model call).

    cd semana-17 && uv run --group semana17 python -m trayectorias.construir_referencias            # writes referencias.jsonl + manifiesto.json
    cd semana-17 && uv run --group semana17 python -m trayectorias.construir_referencias --verificar   # rebuilds and compares, writes nothing

What a reference is and where each part comes from is written in `criterios.py`. In short: the required tools, the order pairs and the
forbidden tool come from the golden task (and from what a tool does); the step ceiling is `pasos_min` plus a margin per task type, and
that margin is the one number taken from recorded runs, the calibration set only (`criterios.CALIBRACION`).

The files are frozen like the other golden sets: `manifiesto.json` holds the sha256 of `referencias.jsonl`, of the two golden files it
derives from and of the calibration file, so a change to any of them is a visible diff and a failing test, not a silent drift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias import criterios as C  # noqa: E402
from trayectorias.evaluadores import Referencia  # noqa: E402

RAIZ = S17.parent
GOLDEN = RAIZ / "semana-13" / "golden"
RESULTADOS13 = RAIZ / "semana-13" / "resultados"
SALIDA = Path(__file__).resolve().parent
ARCHIVO = SALIDA / "referencias.jsonl"
MANIFIESTO = SALIDA / "manifiesto.json"


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def leer_jsonl(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]


def tareas_doradas() -> list[dict]:
    out = leer_jsonl(GOLDEN / "tareas_es.jsonl") + leer_jsonl(GOLDEN / "tareas_en.jsonl")
    assert len(out) == C.TAREAS_DORADAS and len({t["id"] for t in out}) == len(out)
    return out


def percentil(valores: list, q: float):
    """Nearest rank: the smallest value with at least a fraction `q` of the sample at or below it."""
    v = sorted(valores)
    return v[max(0, math.ceil(q * len(v)) - 1)]


def holguras(filas: list[dict]) -> dict[str, dict]:
    """The step margin per task type from the SUCCESSFUL runs of the calibration set: p90 of `pasos - pasos_min`, never below
    `HOLGURA_MINIMA`. Returns {type: {"holgura", "corridas", "p90", "maximo"}}."""
    por_tipo: dict[str, list[int]] = defaultdict(list)
    for f in filas:
        if f.get("exito"):
            por_tipo[f["tipo"]].append(f["pasos"] - f["pasos_min"])
    return {t: {"corridas": len(v), "p90": percentil(v, C.PERCENTIL_DE_LA_HOLGURA), "maximo": max(v),
                "holgura": max(C.HOLGURA_MINIMA, percentil(v, C.PERCENTIL_DE_LA_HOLGURA))} for t, v in sorted(por_tipo.items())}


def referencia(tarea: dict, holgura_del_tipo: int) -> Referencia:
    req = tuple(sorted(tarea["herramientas_min"]))
    permitidas = [h for h in C.HERRAMIENTAS_DE_INFORMACION if h not in req]
    if tarea.get("salida") and C.HERRAMIENTA_DE_DATOS not in req:
        permitidas.append(C.HERRAMIENTA_DE_DATOS)            # not reached by the 84 tasks today: every task with output requires it
    orden = tuple((a, b) for a, b in C.PARES_DE_ORDEN if a in req and b in req)
    return Referencia(id=tarea["id"], tipo=tarea["tipo"], estado_esperado=tarea["estado_esperado"], requeridas=req,
                      permitidas=tuple(sorted(permitidas)), prohibidas=(C.HERRAMIENTA_CONSECUENTE,), orden=orden,
                      pasos_min=int(tarea["pasos_min"]), pasos_max=min(C.MAX_PASOS_DEL_BUCLE, int(tarea["pasos_min"]) + holgura_del_tipo))


def construir() -> tuple[list[Referencia], dict]:
    """The 84 references (sorted by id) and the manifest, from the golden files and the calibration runs."""
    tareas = tareas_doradas()
    calibracion = leer_jsonl(RESULTADOS13 / f"{C.CALIBRACION}_detalle.jsonl")
    h = holguras(calibracion)
    refs = sorted((referencia(t, h[t["tipo"]]["holgura"]) for t in tareas), key=lambda r: r.id)
    cuerpo = "".join(json.dumps(r.a_dict(), ensure_ascii=False, sort_keys=True) + "\n" for r in refs)
    manifiesto = {
        "descripcion": "Reference trajectories of the 84 golden tasks (week 17, activity 7). Frozen: a change needs to be regenerated and reviewed in a PR.",
        "tareas": len(refs),
        "por_tipo": {t: sum(1 for r in refs if r.tipo == t) for t in sorted({r.tipo for r in refs})},
        "origen": {"tareas_es.jsonl": sha256(GOLDEN / "tareas_es.jsonl"), "tareas_en.jsonl": sha256(GOLDEN / "tareas_en.jsonl")},
        "calibracion": {"archivo": f"semana-13/resultados/{C.CALIBRACION}_detalle.jsonl", "sha256": sha256(RESULTADOS13 / f"{C.CALIBRACION}_detalle.jsonl"),
                        "corridas": len(calibracion), "exitosas": sum(1 for f in calibracion if f.get("exito")),
                        "percentil": C.PERCENTIL_DE_LA_HOLGURA, "holgura_minima": C.HOLGURA_MINIMA,
                        "maximo_del_bucle": C.MAX_PASOS_DEL_BUCLE, "por_tipo": h},
        "evaluadas": list(C.EVALUADAS),
        "sha256": {"referencias.jsonl": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()},
    }
    return refs, manifiesto


def escribir(refs: list[Referencia], manifiesto: dict) -> None:
    ARCHIVO.write_text("".join(json.dumps(r.a_dict(), ensure_ascii=False, sort_keys=True) + "\n" for r in refs), encoding="utf-8")
    MANIFIESTO.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cargar() -> dict[str, Referencia]:
    """The frozen references by task id, from `referencias.jsonl`."""
    return {r["id"]: Referencia.de_dict(r) for r in leer_jsonl(ARCHIVO)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verificar", action="store_true", help="rebuild and compare with the frozen files; write nothing")
    a = ap.parse_args()
    refs, manifiesto = construir()
    if a.verificar:
        igual = (ARCHIVO.exists() and MANIFIESTO.exists() and sha256(ARCHIVO) == manifiesto["sha256"]["referencias.jsonl"]
                 and json.loads(MANIFIESTO.read_text(encoding="utf-8")) == manifiesto)
        print("references match the frozen files" if igual else "references DIFFER from the frozen files")
        return 0 if igual else 1
    escribir(refs, manifiesto)
    print(f"{len(refs)} references written; margins by type: " + ", ".join(f"{t}={v['holgura']}" for t, v in manifiesto["calibracion"]["por_tipo"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
