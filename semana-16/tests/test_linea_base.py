"""Semana 16, actividad 1 ($0, sin modelo): la línea base de Claude Code se verifica con la CLI instalada."""
import importlib.util
import shutil
from pathlib import Path

import pytest

S16 = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verificar16", S16 / "linea_base" / "verificar.py")
verificar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verificar)


@pytest.mark.parametrize("herramienta,entrada,esperado", [
    ("Write", {"file_path": "notas.txt"}, 2),
    ("Write", {"file_path": "auditoria/r.md"}, 0),
    ("Edit", {"file_path": "auditoria/../x.py"}, 2),
    ("MultiEdit", {"file_path": "/etc/hosts"}, 2),
    ("Bash", {"command": "psql -c 'UPDATE artmst SET art_ptr = 0'"}, 2),
    ("Bash", {"command": "psql -c 'select count(*) from artmst'"}, 0),
    ("Read", {"file_path": "/etc/hosts"}, 0),
])
def test_guardia_pretooluse(tmp_path, herramienta, entrada, esperado):
    codigo, motivo = verificar.guardia({"tool_name": herramienta, "tool_input": entrada, "cwd": str(tmp_path)})
    assert codigo == esperado, motivo
    assert bool(motivo) == (esperado == 2)


@pytest.mark.skipif(shutil.which("claude") is None, reason="sin Claude Code")
def test_linea_base_sin_modelo_en_verde():
    malos = [r for r in verificar.sin_modelo() if not r["ok"]]
    assert malos == []
