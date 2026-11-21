"""Week 19, activity 9: the ValidatePolicy snapshot covers every policy document of the current synth.

It synthesizes every stack (COMPUTO=1), lab and prod, so sin-aws ignores this file and spike-iac runs it. A changed or
new policy document has a new fingerprint: rerun seguridad/validar_politicas.py and commit the snapshot.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
APP = S19 / "infra" / "cdk" / "app.py"
spec = importlib.util.spec_from_file_location("validar_politicas", S19 / "seguridad" / "validar_politicas.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


@pytest.mark.parametrize("perfil", ["lab", "prod"])
def test_snapshot_cubre_el_synth_actual(perfil):
    salida = Path(tempfile.mkdtemp(prefix=f"s19-vp-{perfil}-"))
    entorno = {**os.environ, "PERFIL": perfil, "CDK_OUTDIR": str(salida), "COMPUTO": "1"}
    r = subprocess.run([sys.executable, str(APP)], env=entorno, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    actuales = {(d["stack"], d["recurso"], d["campo"], d["huella"]) for d in V.documentos(salida)}
    snapshot = json.loads((S19 / "resultados" / "seguridad" / "validate_policy.json").read_text(encoding="utf-8"))
    validados = {(d["stack"], d["recurso"], d["campo"], d["huella"]) for d in snapshot["documentos"][perfil]}
    assert actuales == validados, (f"not validated: {sorted(actuales - validados)[:5]}; "
                                   f"stale: {sorted(validados - actuales)[:5]}")
