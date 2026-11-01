"""Modelo simulado para pruebas deterministas sin API: un doble local de la API de Mensajes de Anthropic
(POST /v1/messages, con y sin streaming SSE) que sigue un guion.

Todos los frameworks de la semana hablan con Claude por esa API (nativa o por LiteLLM) y aceptan otra `base_url`, así
que el mismo guion recorre el código real de cada framework: su loop, su despacho de herramientas por MCP y su conteo de
tokens. Nada sale del equipo y el costo es $0. Cada turno del guion es una lista de bloques (`texto(...)`,
`herramienta(...)`) con su uso de tokens; si el guion se acaba, el doble responde un texto sin herramientas.
"""
from __future__ import annotations

import itertools
import json
import threading
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ids = itertools.count(1)


def texto(t: str) -> dict:
    return {"type": "text", "text": t}


def herramienta(nombre: str, entrada: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_{next(_ids):04d}", "name": nombre, "input": entrada}


@dataclass
class Turno:
    bloques: list
    tokens_in: int = 1000
    tokens_out: int = 100


@dataclass
class Guion:
    turnos: list[Turno]
    peticiones: list[dict] = field(default_factory=list)
    _i: int = 0
    _candado: threading.Lock = field(default_factory=threading.Lock)

    def siguiente(self, cuerpo: dict) -> Turno:
        with self._candado:
            self.peticiones.append(cuerpo)
            if self._i < len(self.turnos):
                self._i += 1
                return self.turnos[self._i - 1]
            return Turno([texto("(fin del guion)")], 10, 1)


def _mensaje(cuerpo: dict, t: Turno) -> dict:
    con_herr = any(b["type"] == "tool_use" for b in t.bloques)
    return {"id": f"msg_{next(_ids):04d}", "type": "message", "role": "assistant", "model": cuerpo.get("model"),
            "content": t.bloques, "stop_reason": "tool_use" if con_herr else "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": t.tokens_in, "output_tokens": t.tokens_out}}


def _sse(msg: dict) -> bytes:
    ev = [("message_start", {"type": "message_start", "message": {**msg, "content": [], "stop_reason": None,
                                                                  "usage": {"input_tokens": msg["usage"]["input_tokens"],
                                                                            "output_tokens": 1}}})]
    for i, b in enumerate(msg["content"]):
        if b["type"] == "text":
            ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}),
                   ("content_block_delta", {"type": "content_block_delta", "index": i,
                                            "delta": {"type": "text_delta", "text": b["text"]}})]
        else:
            ev += [("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                        "type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}}),
                   ("content_block_delta", {"type": "content_block_delta", "index": i,
                                            "delta": {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}})]
        ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    ev += [("message_delta", {"type": "message_delta", "delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None},
                              "usage": {"output_tokens": msg["usage"]["output_tokens"]}}),
           ("message_stop", {"type": "message_stop"})]
    return b"".join(f"event: {n}\ndata: {json.dumps(d)}\n\n".encode() for n, d in ev)


class DobleAnthropic:
    """`with DobleAnthropic(guion) as d:` → `d.base_url` para el cliente de Anthropic del framework."""

    def __init__(self, guion: Guion):
        self.guion = guion
        doble = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                if not self.path.rstrip("/").endswith("/messages"):
                    self.send_error(404)
                    return
                msg = _mensaje(cuerpo, doble.guion.siguiente(cuerpo))
                datos, tipo = ((_sse(msg), "text/event-stream") if cuerpo.get("stream")
                               else (json.dumps(msg).encode(), "application/json"))
                self.send_response(200)
                self.send_header("content-type", tipo)
                self.send_header("content-length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base_url = f"http://127.0.0.1:{self._srv.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self._srv.shutdown()
        self._srv.server_close()


def api_doble(base_url: str):
    """Sustituto de `api_anthropic` de la semana 13 que llama al doble (para el loop propio)."""
    def api(cuerpo: dict) -> dict:
        req = urllib.request.Request(base_url + "/v1/messages", data=json.dumps(cuerpo).encode(),
                                     headers={"content-type": "application/json", "x-api-key": "doble"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    return api


def guion_respuesta(tarea: dict, resultados: list[dict] | None = None, estado: str | None = None,
                    sql_exploracion: str | None = None) -> Guion:
    """Guion de un agente disciplinado: describe el esquema, ejecuta el SQL de cada clave y responde.
    `resultados`: [{"clave", "sql", "valor"}]; `estado` por omisión es el esperado de la tarea."""
    estado = estado or tarea["estado_esperado"]
    turnos = [Turno([herramienta("describir_esquema", {})], 1200, 40)]
    for r in resultados or []:
        turnos.append(Turno([herramienta("ejecutar_sql", {"sql": r["sql"]})], 1500, 80))
    if sql_exploracion:
        turnos.append(Turno([herramienta("ejecutar_sql", {"sql": sql_exploracion})], 1500, 80))
    final = {"estado": estado, "respuesta": "respuesta guionada", "resultados": resultados or [],
             "evidencia": [], "supuestos": []}
    if estado == "requiere_aclaracion":
        final["pregunta_aclaracion"] = "¿A qué almacén se refiere?"
    turnos.append(Turno([herramienta("responder", final)], 1800, 150))
    return Guion(turnos)
