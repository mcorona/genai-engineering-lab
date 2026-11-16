"""Week 19, activity 6: the span sink. Writes the exporter's lines to a CloudWatch Logs stream (ADR 0012 spans).

The client is injected (boto3 logs client in the Lambda). Lines are sent in batches; `vaciar()` sends what is pending.
The lines are already validated by the exporter against the week 17 schema, so nothing else is written here.
"""
from __future__ import annotations

import time

LOTE_MAXIMO = 100


class SumideroCloudWatch:
    def __init__(self, cliente, grupo: str, flujo: str, ahora=time.time):
        self.cliente, self.grupo, self.flujo = cliente, grupo, flujo
        self.ahora = ahora
        self.pendientes: list[dict] = []
        self._creado = False

    def _asegurar_flujo(self) -> None:
        if self._creado:
            return
        try:
            self.cliente.create_log_stream(logGroupName=self.grupo, logStreamName=self.flujo)
        except self.cliente.exceptions.ResourceAlreadyExistsException:
            pass
        self._creado = True

    def __call__(self, linea: str) -> None:
        self.pendientes.append({"timestamp": int(self.ahora() * 1000), "message": linea})
        if len(self.pendientes) >= LOTE_MAXIMO:
            self.vaciar()

    def vaciar(self) -> int:
        if not self.pendientes:
            return 0
        self._asegurar_flujo()
        enviados = len(self.pendientes)
        self.cliente.put_log_events(logGroupName=self.grupo, logStreamName=self.flujo,
                                    logEvents=sorted(self.pendientes, key=lambda e: e["timestamp"]))
        self.pendientes = []
        return enviados
