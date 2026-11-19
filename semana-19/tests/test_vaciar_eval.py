"""Week 19, activity 8: the judge's jobs listing in the teardown (infra/vaciar_eval.py), offline ($0)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import botocore.session

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vaciar_eval", S19 / "infra" / "vaciar_eval.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def _patron_name_contains() -> str:
    modelo = botocore.session.get_session().get_service_model("bedrock")
    return modelo.operation_model("ListEvaluationJobs").input_shape.members["nameContains"].metadata["pattern"]


def test_el_filtro_de_nombre_cumple_el_patron_del_servicio():
    patron = _patron_name_contains()
    assert re.fullmatch(patron, V.FILTRO_NOMBRE)
    assert not re.fullmatch(patron, V.PREFIJO_TRABAJOS)   # the value that failed on 2026-11-19


class Bedrock:
    def __init__(self, nombres):
        self.nombres, self.filtros = nombres, []

    def get_paginator(self, operacion):
        assert operacion == "list_evaluation_jobs"
        return self

    def paginate(self, **kw):
        self.filtros.append(kw)
        yield {"jobSummaries": [{"jobArn": f"arn:{n}", "jobName": n, "status": "Completed"}
                                for n in self.nombres if kw["nameContains"] in n]}


def test_solo_cuenta_los_trabajos_del_juez_aunque_el_servicio_devuelva_otros():
    b = Bedrock(["semana19-juez-20261119-220841", "semana19-juezx", "otro-semana19-juez-1", "ajeno"])
    assert [j["nombre"] for j in V.trabajos(b)] == ["semana19-juez-20261119-220841"]
    assert b.filtros == [{"nameContains": "semana19-juez"}]
