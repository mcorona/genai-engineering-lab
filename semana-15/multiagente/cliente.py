"""Cliente A2A mínimo del supervisor (JSON-RPC sobre HTTP, protocolo 0.3, solo biblioteca estándar): lee y valida la
Agent Card una vez, y manda `message/send` con el token OAuth de audiencia propia del especialista. Nunca le reenvía el
token del servidor MCP (sin token passthrough)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

from multiagente.comun import MAX_PEDIDO, ErrorA2A, leer_agent_card, validar_agent_card


class ClienteA2A:
    def __init__(self, url: str, token: str, emisor: str):
        self.url, self.token, self.emisor = url, token, emisor
        self.card: dict | None = None
        self.peticiones = 0

    def conectar(self):
        if self.card is None:
            card = leer_agent_card(self.url)
            validar_agent_card(card, self.url, self.emisor)        # ErrorA2A: no se manda nada
            self.card = card
        return self.card

    def enviar(self, texto: str, contexto: str | None = None) -> tuple[str, dict]:
        self.conectar()
        if len(texto) > MAX_PEDIDO:
            raise ErrorA2A(f"pedido de {len(texto)} caracteres (máximo {MAX_PEDIDO})")
        cuerpo = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "message/send", "params": {"message": {
            "role": "user", "kind": "message", "messageId": uuid.uuid4().hex, "parts": [{"kind": "text", "text": texto}],
            **({"contextId": contexto} if contexto else {})}}}
        req = urllib.request.Request(self.card["url"], data=json.dumps(cuerpo).encode(), headers={
            "content-type": "application/json", "authorization": f"Bearer {self.token}"})
        self.peticiones += 1
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            raise ErrorA2A(f"HTTP {e.code} {e.headers.get('WWW-Authenticate', '')}") from None
        if "error" in d:
            raise ErrorA2A(f"JSON-RPC {d['error']}")
        res = d.get("result") or {}
        partes = [p.get("text", "") for a in res.get("artifacts", []) for p in a.get("parts", [])] or \
                 [p.get("text", "") for p in (res.get("status", {}).get("message") or {}).get("parts", [])]
        return "".join(partes).strip(), (res.get("metadata") or {}).get("uso") or {}
