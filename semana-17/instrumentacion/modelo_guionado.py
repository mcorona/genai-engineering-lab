"""Week 17, activity 3: a scripted model for the agent loop ($0, no API).

`ModeloGuionado` is a callable with the shape of `api_anthropic` (request body -> Messages API response). It plays a fixed
list of turns, so the loop, the MCP client, the server and the database run for real and only the model is scripted.
The token numbers in `usage` and the `latencia_s` of each turn are inputs of the test, not measurements: the tests check that
the spans add up to the tokens and last at least as long as the scripted latency.
"""
from __future__ import annotations

import time

SQL_BAJO_PUNTO_DE_REORDEN = (
    "SELECT a.art_cd FROM artmst a JOIN (SELECT exi_art, SUM(exi_qty) AS total FROM exidet GROUP BY exi_art) e "
    "ON e.exi_art = a.art_cd WHERE e.total < a.art_ptr ORDER BY a.art_cd LIMIT 5")

TAREA = {"id": "s01-en", "lang": "en",
         "tarea": "Which products have total stock (all warehouses) below their reorder point?"}


class ModeloGuionado:
    """Plays `turnos` in order. A turn is `{"herramientas": [(name, input), ...], "usage": {...}}` or, to finish,
    `{"final": {...responder input...}, "usage": {...}}`. After the last turn it raises, like an API that stops answering."""

    def __init__(self, turnos: list[dict], *, falla_en: int | None = None, mensaje_de_falla: str = "scripted API failure"):
        self.turnos, self.falla_en, self.mensaje_de_falla = turnos, falla_en, mensaje_de_falla
        self.llamadas: list[dict] = []

    def __call__(self, cuerpo: dict) -> dict:
        n = len(self.llamadas)
        self.llamadas.append({"modelo": cuerpo.get("model"), "mensajes": len(cuerpo.get("messages", [])),
                              "max_tokens": cuerpo.get("max_tokens")})
        if self.falla_en is not None and n == self.falla_en:
            raise RuntimeError(self.mensaje_de_falla)
        turno = self.turnos[n]
        time.sleep(turno.get("latencia_s", 0))        # the scripted model "thinks": the `chat` span must last at least this
        limite = cuerpo.get("max_tokens")
        if limite is not None and turno["usage"].get("output_tokens", 0) > limite:
            # like the API: the answer is cut at `max_tokens`, with no tool use, and the output is billed at that size
            return {"id": f"msg_scripted_{n + 1:03d}", "type": "message", "role": "assistant", "model": cuerpo["model"],
                    "stop_reason": "max_tokens", "content": [{"type": "text", "text": "..."}],
                    "usage": {**turno["usage"], "output_tokens": limite}}
        pedidos = turno.get("herramientas") or [("responder", turno["final"])]
        bloques = [{"type": "tool_use", "id": f"toolu_scripted_{n + 1:02d}_{k + 1}", "name": nombre, "input": entrada}
                   for k, (nombre, entrada) in enumerate(pedidos)]
        return {"id": f"msg_scripted_{n + 1:03d}", "type": "message", "role": "assistant", "model": cuerpo["model"],
                "stop_reason": "tool_use", "content": bloques, "usage": dict(turno["usage"])}


def final_ok(texto: str = "Scripted answer.") -> dict:
    return {"estado": "respondida", "respuesta": texto, "resultados": [], "evidencia": [], "supuestos": []}


def turnos_principal(prefijo: str = "legado__", sql: str = SQL_BAJO_PUNTO_DE_REORDEN) -> list[dict]:
    """Schema, one SQL, final answer. The first call writes the prompt cache, the next two read it."""
    return [
        {"herramientas": [(f"{prefijo}describir_esquema", {"tablas": ["artmst", "exidet"]})],
         "usage": {"input_tokens": 1180, "output_tokens": 64, "cache_creation_input_tokens": 800}, "latencia_s": 0.05},
        {"herramientas": [(f"{prefijo}ejecutar_sql", {"sql": sql})],
         "usage": {"input_tokens": 420, "output_tokens": 96, "cache_read_input_tokens": 800}, "latencia_s": 0.08},
        {"final": final_ok("Scripted answer."),
         "usage": {"input_tokens": 380, "output_tokens": 150, "cache_read_input_tokens": 800}, "latencia_s": 0.06},
    ]


def turnos_con_error_de_sql(prefijo: str = "legado__") -> list[dict]:
    """The model writes SQL with a wrong column; the tool errors, the model corrects it and answers."""
    malo = "SELECT a.no_existe FROM artmst a LIMIT 1"
    return [
        {"herramientas": [(f"{prefijo}ejecutar_sql", {"sql": malo})],
         "usage": {"input_tokens": 900, "output_tokens": 50}},
        {"herramientas": [(f"{prefijo}ejecutar_sql", {"sql": SQL_BAJO_PUNTO_DE_REORDEN})],
         "usage": {"input_tokens": 700, "output_tokens": 60}},
        {"final": final_ok(), "usage": {"input_tokens": 600, "output_tokens": 90}},
    ]


def turnos_sin_permiso(prefijo: str = "legado__", motivo: str = "reorder") -> list[dict]:
    """A profile without `legado:compras:proponer` asks for a purchase proposal: 403 at the boundary, then it gives up."""
    return [
        {"herramientas": [(f"{prefijo}proponer_orden_compra", {"sku": "SKU-0009", "cantidad": 10, "motivo": motivo})],
         "usage": {"input_tokens": 800, "output_tokens": 40}},
        {"final": {"estado": "abstenida", "respuesta": "I am not allowed to propose purchase orders.", "resultados": [],
                   "evidencia": [], "supuestos": []},
         "usage": {"input_tokens": 500, "output_tokens": 60}},
    ]


def turnos_herramienta_inventada(nombre: str) -> list[dict]:
    """The model asks for a tool that does not exist (the name could carry anything: it comes from the model)."""
    return [
        {"herramientas": [(nombre, {})], "usage": {"input_tokens": 700, "output_tokens": 30}},
        {"final": final_ok(), "usage": {"input_tokens": 500, "output_tokens": 40}},
    ]
