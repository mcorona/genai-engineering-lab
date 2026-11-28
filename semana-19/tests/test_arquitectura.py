"""Week 19, activity 2: the ADRs share one format and the diagram sources exist ($0, no AWS)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
ADR = sorted((S19 / "arquitectura" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
SECCIONES = ["Context", "Alternatives", "Decision", "Consequences"]


def test_hay_quince_adrs_numerados_del_0001_al_0015():
    # 0014: week 20, activity 3 (prompt caching); 0015: week 20, activity 4 (model routing)
    assert [a.name[:4] for a in ADR] == [f"{n:04d}" for n in range(1, 16)]


@pytest.mark.parametrize("ruta", ADR, ids=lambda p: p.name)
def test_cada_adr_tiene_el_formato_comun(ruta):
    t = ruta.read_text(encoding="utf-8")
    assert t.startswith("# ADR "), "title"
    secciones = re.findall(r"^## (.+)$", t, re.M)
    assert [s.split(" (")[0] for s in secciones[:4]] == SECCIONES, secciones
    assert secciones[4].startswith("Costs"), "the fifth section is the cost"
    assert len(secciones) == 5, "only five level-2 sections"


@pytest.mark.parametrize("ruta", ADR, ids=lambda p: p.name)
def test_cada_adr_cifra_su_costo_con_marca(ruta):
    t = ruta.read_text(encoding="utf-8")
    assert re.search(r"\b(M|D|N)\b", t), "the cost must carry a mark: M, D or N"


def test_el_adr_0001_registra_la_decision():
    t = (S19 / "arquitectura" / "adr" / "0001-cdk-vs-terraform.md").read_text(encoding="utf-8")
    assert "CDK in Python" in t
