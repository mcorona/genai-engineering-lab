"""Week 19, activity 6: who may connect to the database as which user, checked in the synthesized computo template.

Only two functions connect: the order writer as order_writer (the only writer of purchase_orders) and the tools Lambda as
copilot_ro (read-only). No other role in the template may hold rds-db:connect. Synthesis only, $0.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"


@lru_cache(maxsize=None)
def plantilla_computo() -> dict:
    salida = Path(tempfile.mkdtemp(prefix="s19-rds-"))
    entorno = {**os.environ, "COMPUTO": "1", "CDK_OUTDIR": str(salida)}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True, cwd=str(S19))
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads((salida / "semana19-computo.template.json").read_text(encoding="utf-8"))


def _sentencias_con_connect():
    for nombre, r in plantilla_computo()["Resources"].items():
        if r["Type"] != "AWS::IAM::Policy":
            continue
        for st in r["Properties"]["PolicyDocument"]["Statement"]:
            acciones = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            if "rds-db:connect" in acciones:
                yield nombre, st


def _usuarios_de(st) -> list[str]:
    recursos = st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]]
    finales = []
    for r in recursos:
        assert isinstance(r, dict) and "Fn::Join" in r, r  # ARN built from parts: the last part is the database user
        finales.append(r["Fn::Join"][1][-1])
    return finales


def _de(funcion: str):
    (st,) = [s for n, s in _sentencias_con_connect() if n.startswith(funcion)]
    return _usuarios_de(st)


def test_solo_el_escritor_y_las_herramientas_pueden_conectar():
    nombres = sorted(n for n, _ in _sentencias_con_connect())
    assert len(nombres) == 2 and any(n.startswith("FuncionEscritor") for n in nombres) \
        and any(n.startswith("FuncionHerramientas") for n in nombres), nombres


def test_el_escritor_solo_conecta_como_order_writer():
    usuarios = _de("FuncionEscritor")
    assert usuarios and all(u.endswith("/order_writer") for u in usuarios), usuarios


def test_las_herramientas_solo_conectan_como_copilot_ro():
    usuarios = _de("FuncionHerramientas")
    assert usuarios and all(u.endswith("/copilot_ro") for u in usuarios), usuarios
