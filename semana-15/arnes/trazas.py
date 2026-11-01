"""Trazas JSONL comunes a todos los frameworks: un evento por llamada al modelo, por herramienta, por la respuesta final
y por la parada, con los mismos campos sin importar el framework (se reutilizan en la semana 17)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

TIPOS = ("modelo", "herramienta", "final", "parada")
COMUNES = ("ts", "framework", "modelo", "corrida", "tarea", "tipo", "paso")
POR_TIPO = {
    "modelo": ("ms", "tokens_in", "tokens_out", "costo_usd", "herramientas_pedidas"),
    "herramienta": ("herramienta", "ms", "ok", "error"),
    "final": ("estado",),
    "parada": ("estado", "motivo", "pasos", "herramientas", "tokens_in", "tokens_out", "costo_usd", "segundos"),
}
_CANDADO = threading.Lock()


class Trazador:
    def __init__(self, ruta: Path | None, framework: str, modelo: str, corrida: str, tarea: str):
        self.ruta, self.base = ruta, {"framework": framework, "modelo": modelo, "corrida": corrida, "tarea": tarea}
        self.eventos: list[dict] = []

    def __call__(self, tipo: str, paso: int, **campos):
        ev = {"ts": round(time.time(), 3), **self.base, "tipo": tipo, "paso": paso, **campos}
        if problemas := validar_evento(ev):
            raise ValueError(f"evento de traza inválido: {problemas}")
        self.eventos.append(ev)
        if self.ruta:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with _CANDADO, open(self.ruta, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        return ev


def validar_evento(ev: dict) -> list[str]:
    if ev.get("tipo") not in TIPOS:
        return [f"tipo inválido: {ev.get('tipo')!r}"]
    faltan = [k for k in COMUNES + POR_TIPO[ev["tipo"]] if k not in ev]
    return [f"faltan campos: {faltan}"] if faltan else []
