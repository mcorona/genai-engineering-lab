"""Week 19, activity 6: the span sink to CloudWatch Logs, offline ($0, moto)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente.sumidero_logs import LOTE_MAXIMO, SumideroCloudWatch  # noqa: E402

GRUPO, FLUJO = "/semana19/agente/spans", "agente"


@pytest.fixture
def logs():
    with mock_aws():
        cliente = boto3.client("logs", region_name="us-east-1")
        cliente.create_log_group(logGroupName=GRUPO)
        yield cliente


def _eventos(cliente):
    return [e["message"] for e in cliente.get_log_events(logGroupName=GRUPO, logStreamName=FLUJO)["events"]]


def test_las_lineas_llegan_al_flujo_en_orden(logs):
    sumidero = SumideroCloudWatch(logs, GRUPO, FLUJO)
    sumidero(json.dumps({"span": "a"}))
    sumidero(json.dumps({"span": "b"}))
    assert sumidero.vaciar() == 2
    assert [json.loads(m)["span"] for m in _eventos(logs)] == ["a", "b"]


def test_se_envia_por_lotes_y_el_resto_con_vaciar(logs):
    sumidero = SumideroCloudWatch(logs, GRUPO, FLUJO)
    for i in range(LOTE_MAXIMO + 3):
        sumidero(json.dumps({"i": i}))
    assert len(sumidero.pendientes) == 3
    sumidero.vaciar()
    assert len(_eventos(logs)) == LOTE_MAXIMO + 3


def test_vaciar_sin_pendientes_no_llama_a_aws(logs):
    sumidero = SumideroCloudWatch(logs, GRUPO, FLUJO)
    assert sumidero.vaciar() == 0


def test_el_exportador_escribe_por_el_sumidero(logs):
    from agente.exportador import ExportadorSpans
    from test_agente_exportador import CHAT_OK
    sumidero = SumideroCloudWatch(logs, GRUPO, FLUJO)
    exportador = ExportadorSpans(escribir=sumidero)
    exportador.exportar([{"name": "chat x", "tipo": "chat", "attrs": CHAT_OK}])
    sumidero.vaciar()
    fila = json.loads(_eventos(logs)[0])
    assert fila["span"] == "chat x" and fila["tipo"] == "chat"
