"""Week 17, activity 5: the held-out set (`heldout.py`), run ONCE against the frozen rules. $0, no model, no database.

    cd semana-17
    uv run --group semana17 python -m guardrails.correr_heldout

The set was written before the rules and is never used to tune them: this report is what it showed, misses included. The report keeps ids,
categories and decisions; the texts are in `heldout.py`. It refuses to overwrite an existing report unless `--otra-vez` is given, so a second
run (and a second look to tune against) is a decision, not an accident.

`--reglas-finales` is the one exception, and it is only a RECOMPUTATION: after the one-shot run a unit test found a defect in a rule (an order
counted as a write target in English only, which blocked "create a purchase order proposal"). Fixing it changed one held-out decision. The
one-shot report stays untouched; this writes a second file with the decisions of the FINAL rules and the ids whose decision changed. Nothing is
tuned to what it shows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from guardrails import nucleo as N  # noqa: E402
from guardrails.heldout import CASOS  # noqa: E402


def decidir(caso: dict) -> tuple[str, str] | None:
    """(guardrail, reason) of the first decision other than allow the stack takes on the text, or None."""
    if caso["tipo"] == "resultado":
        _, d = N.revisar_resultado({"ok": True, "nota": caso["texto"]}, "es")
        return None if d.permite else (d.guardrail, d.motivo)
    d = next((d for d in N.revisar_peticion(caso["texto"]) if not d.permite), None)
    return None if d is None else (d.guardrail, d.motivo)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--otra-vez", action="store_true", help="overwrite the report of a previous run (it is run once)")
    ap.add_argument("--reglas-finales", action="store_true",
                    help="recompute with the final rules into a second file, next to the untouched one-shot report")
    a = ap.parse_args(argv)
    primera = S17 / "resultados" / "guardrails_heldout.json"
    ruta = S17 / "resultados" / "guardrails_heldout_reglas_finales.json" if a.reglas_finales else primera
    if a.reglas_finales and not primera.exists():
        print("[heldout] there is no one-shot report to compare with.", file=sys.stderr)
        return 2
    if ruta.exists() and not a.otra_vez:
        print(f"[heldout] {ruta.name} already exists: the set is run once. --otra-vez to overwrite it.", file=sys.stderr)
        return 2
    filas = []
    for c in CASOS:
        d = decidir(c)
        filas.append({"id": c["id"], "tipo": c["tipo"], "ataque": c["ataque"], "detectado": d is not None,
                      "guardrail": d[0] if d else None, "motivo": d[1] if d else None, "esperado": c.get("esperado"),
                      "guardrail_esperado": (d[0] == c["esperado"]) if d and c.get("esperado") else None})
    ataques, benignos = [f for f in filas if f["ataque"]], [f for f in filas if not f["ataque"]]
    informe = {
        "fecha": time.strftime("%Y-%m-%d"), "casos": len(filas),
        "ataques": {"total": len(ataques), "detectados": sum(f["detectado"] for f in ataques),
                    "no_detectados": [f["id"] for f in ataques if not f["detectado"]],
                    "por_tipo": {t: {"total": sum(1 for f in ataques if f["tipo"] == t),
                                     "detectados": sum(1 for f in ataques if f["tipo"] == t and f["detectado"])}
                                 for t in ("resultado", "peticion")},
                    "con_el_guardrail_esperado": {"total": sum(1 for f in ataques if f["esperado"]),
                                                  "acierto": sum(1 for f in ataques if f["guardrail_esperado"])}},
        "benignos_dificiles": {"total": len(benignos), "falsos_positivos": sum(f["detectado"] for f in benignos),
                               "ids_con_falso_positivo": [f["id"] for f in benignos if f["detectado"]]},
        "por_caso": filas}
    if a.reglas_finales:
        antes = {f["id"]: f for f in json.loads(primera.read_text(encoding="utf-8"))["por_caso"]}
        informe["nota"] = ("recomputed with the final rules after a rule defect was fixed; the one-shot report (guardrails_heldout.json) is "
                           "unchanged and nothing was tuned to this output")
        informe["decisiones_que_cambiaron_desde_la_corrida_unica"] = [
            {"id": f["id"], "antes": [antes[f["id"]]["guardrail"], antes[f["id"]]["motivo"]], "ahora": [f["guardrail"], f["motivo"]]}
            for f in filas if (f["guardrail"], f["motivo"]) != (antes[f["id"]]["guardrail"], antes[f["id"]]["motivo"])]
    ruta.write_text(json.dumps(informe, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a_, b_ = informe["ataques"], informe["benignos_dificiles"]
    print(f"attacks detected {a_['detectados']}/{a_['total']} (missed: {a_['no_detectados'] or 'none'}) · "
          f"hard benign flagged {b_['falsos_positivos']}/{b_['total']} ({b_['ids_con_falso_positivo'] or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
