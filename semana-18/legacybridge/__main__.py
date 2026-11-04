"""LegacyBridge v1 command line (from `semana-18/`, after `legacybridge/arrancar.sh`).

    python -m legacybridge preguntar "Which critical SKUs are below their reorder point?" [--modo multiagente] [--lang en]
    python -m legacybridge pendientes                                   # proposals waiting for approval
    python -m legacybridge aprobar <id> --como gerente [--rechazar]     # decide with the approver's own token, then resume the run
    python -m legacybridge tablero                                      # the dashboard snapshot (week 17, activity 8)
    python -m legacybridge runbook tarea c08-es                         # the five operator questions

Real model calls need ANTHROPIC_API_KEY and cost money (each answer prints its cost). Nothing here prints a token, a password or a DSN.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

S18 = Path(__file__).resolve().parents[1]
S17 = S18.parent / "semana-17"


def _resultado(r, ag=None) -> dict:
    final = r.final or {}
    out = {"estado": r.estado, "motivo": r.motivo, "respuesta": final.get("respuesta"), "pasos": r.pasos, "herramientas": r.herramientas,
           "costo_usd": round(r.costo_usd, 6)}
    if final.get("solicitud"):
        out["solicitud"] = final["solicitud"]
    if final.get("evidencia"):
        out["evidencia"] = final["evidencia"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="legacybridge", description="LegacyBridge v1")
    ap.add_argument("--modo", choices=("simple", "multiagente"), default="simple")
    ap.add_argument("--emisor", choices=("auto", "keycloak", "prueba"), default="auto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preguntar")
    p.add_argument("texto")
    p.add_argument("--lang", choices=("en", "es"), default="en")
    p.add_argument("--usuario", default="analista")
    sub.add_parser("pendientes")
    a = sub.add_parser("aprobar")
    a.add_argument("solicitud")
    a.add_argument("--como", required=True, help="the approver (comprador, gerente, director)")
    a.add_argument("--rechazar", action="store_true")
    sub.add_parser("tablero")
    r = sub.add_parser("runbook")
    r.add_argument("args", nargs=argparse.REMAINDER)
    x = ap.parse_args(argv)

    if x.cmd in ("tablero", "runbook"):
        mod = ["tablero.exportar"] if x.cmd == "tablero" else ["tablero.preguntar", *x.args]
        return subprocess.call([sys.executable, "-m", *mod], cwd=S17)

    from legacybridge.nucleo import LegacyBridge
    with LegacyBridge(modo=x.modo, emisor=x.emisor) as lb:
        if x.cmd == "preguntar":
            res, _ = lb.preguntar(x.texto, usuario=x.usuario, lang=x.lang)
            salida = _resultado(res)
            if x.modo == "multiagente":
                salida["costo_especialista_usd"] = round(lb.costo_especialista(), 6)
            print(json.dumps(salida, ensure_ascii=False, indent=1, default=str))
        elif x.cmd == "pendientes":
            print(json.dumps(lb.pendientes(), ensure_ascii=False, indent=1, default=str))
        elif x.cmd == "aprobar":
            v, s = lb.decidir(x.solicitud, aprobador=x.como, decision="reject" if x.rechazar else "approve")
            print(json.dumps({"aplicada": v.aplicado, "motivo": v.motivo, "estado": (s or {}).get("estado")}, ensure_ascii=False))
            if (s or {}).get("estado") in ("aprobada", "rechazada", "expirada"):
                print(json.dumps(_resultado(lb.reanudar(x.solicitud)), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
