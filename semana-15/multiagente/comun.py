"""Pieces shared by the A2A server (the Strands environment) and the supervisor (the LangGraph environment). No dependencies
outside the standard library, except PyJWT to validate tokens."""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

A2A_PUERTO = 8015
A2A_URL = f"http://127.0.0.1:{A2A_PUERTO}/"          # the specialist's own OAuth resource (RFC 8707)
SCOPE_COMPRAS = "legado:compras:proponer"
NOMBRE_ESPECIALISTA = "compras"
VERSIONES_A2A = ("0.3.0",)                            # what Strands 1.63 speaks (activity 1)
MAX_PEDIDO = 4000                                      # characters the supervisor can send in a message
MAX_CUERPO = 16_384                                    # bytes the server accepts per request


class ErrorA2A(Exception):
    pass


def validar_agent_card(card: dict, url_esperada: str, emisor: str) -> None:
    """The supervisor only talks to a specialist whose Agent Card matches the configuration. It rejects: another URL
    (another host or port: impersonation or SSRF), another name, a protocol version it does not speak, and a card whose
    OAuth scheme points to another authorization server (token theft through mix-up) or does not require the purchasing scope."""
    if not isinstance(card, dict):
        raise ErrorA2A("agent card inválida")
    if card.get("name") != NOMBRE_ESPECIALISTA:
        raise ErrorA2A(f"nombre inesperado: {card.get('name')!r}")
    u, e = urlparse(card.get("url", "")), urlparse(url_esperada)
    if (u.scheme, u.hostname, u.port) != (e.scheme, e.hostname, e.port):
        raise ErrorA2A(f"la tarjeta anuncia otra URL: {card.get('url')!r}")
    if u.hostname not in ("127.0.0.1", "localhost") and u.scheme != "https":
        raise ErrorA2A("solo https o loopback")
    if card.get("protocolVersion") not in VERSIONES_A2A:
        raise ErrorA2A(f"versión de protocolo no soportada: {card.get('protocolVersion')!r}")
    esquemas = card.get("securitySchemes") or {}
    oauth = [s for s in esquemas.values() if s.get("type") == "oauth2"]
    if not oauth:
        raise ErrorA2A("la tarjeta no exige OAuth")
    for s in oauth:
        for flujo in (s.get("flows") or {}).values():
            for campo in ("authorizationUrl", "tokenUrl"):
                if flujo.get(campo) and not flujo[campo].startswith(emisor.rstrip("/") + "/"):
                    raise ErrorA2A(f"{campo} de otro emisor: {flujo[campo]!r}")
            if SCOPE_COMPRAS not in (flujo.get("scopes") or {}):
                raise ErrorA2A("la tarjeta no pide el scope de compras")


def leer_agent_card(url: str) -> dict:
    with urllib.request.urlopen(url.rstrip("/") + "/.well-known/agent-card.json", timeout=10) as r:
        return json.load(r)
