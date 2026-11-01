"""Piezas compartidas por el servidor A2A (entorno de Strands) y el supervisor (entorno de LangGraph). Sin dependencias
fuera de la biblioteca estándar, salvo PyJWT para validar tokens."""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

A2A_PUERTO = 8015
A2A_URL = f"http://127.0.0.1:{A2A_PUERTO}/"          # recurso OAuth propio del especialista (RFC 8707)
SCOPE_COMPRAS = "legado:compras:proponer"
NOMBRE_ESPECIALISTA = "compras"
VERSIONES_A2A = ("0.3.0",)                            # lo que habla Strands 1.63 (actividad 1)
MAX_PEDIDO = 4000                                      # caracteres que el supervisor puede mandar en un mensaje
MAX_CUERPO = 16_384                                    # bytes que el servidor acepta por petición


class ErrorA2A(Exception):
    pass


def validar_agent_card(card: dict, url_esperada: str, emisor: str) -> None:
    """El supervisor solo habla con un especialista cuya Agent Card coincide con lo configurado. Rechaza: otra URL
    (otro host o puerto: suplantación o SSRF), otro nombre, una versión de protocolo que no habla, y una tarjeta cuyo
    esquema OAuth apunta a otro servidor de autorización (robo de token por mix-up) o no exige el scope de compras."""
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
