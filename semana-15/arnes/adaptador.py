"""Interfaz única por framework: `Adaptador.resolver(tarea) -> Resultado` (el de la semana 13).

Cada adaptador (LangGraph en la actividad 3, Strands en la 4, los spikes en la 6) usa el mismo prompt de sistema, el
mismo mensaje de tarea, las herramientas del servidor MCP de la semana 14 con el token del usuario, la herramienta
`responder` validada igual que en la semana 13 y los mismos límites. `Registro` concentra lo común para que ningún
adaptador reimplemente conteos, costo, validación de la respuesta final ni trazas:

    reg = Registro(framework, modelo, tarea, limites, ruta_trazas)
    reg.modelo(uso, ms, pedidas)        # después de cada llamada al modelo (uso en el formato del framework)
    salida = reg.responder(entrada)     # dentro de la herramienta `responder` del framework
    reg.herramienta(nombre, ms, salida) # después de cada herramienta MCP
    return reg.parar(estado, motivo)    # Resultado con costo normalizado y evento de parada

`AdaptadorPropio` es la referencia: el loop de la semana 13 sin cambios, con las herramientas por MCP.
"""
from __future__ import annotations

import json
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from .contrato import Resultado, costo, normalizar_uso, semana13
from .trazas import Trazador


class Registro:
    def __init__(self, framework: str, modelo: str, tarea: dict, limites=None, ruta_trazas: Path | None = None,
                 sistema: str | None = None):
        l13 = semana13()
        self._sistema = sistema
        self.tarea, self.modelo_id = tarea, modelo
        self.lim = limites or l13.Limites()
        self.r = Resultado(corrida=uuid.uuid4().hex[:12])
        self.final: dict | None = None
        self.t0 = time.perf_counter()
        tid = tarea.get("id", "") + (f"#{tarea['rep']}" if "rep" in tarea else "")
        self.traza = Trazador(ruta_trazas, framework, modelo, self.r.corrida, tid)

    # ----- prompt y herramienta final, idénticos a la semana 13 -----
    def sistema(self) -> str:
        """El prompt de sistema de la semana 13, o el que se pase (p. ej. `sistema_seguro` de la semana 14)."""
        return self._sistema or semana13().SISTEMA

    def mensaje(self) -> str:
        return semana13().mensaje_tarea(self.tarea)

    @staticmethod
    def herramienta_responder() -> dict:
        return semana13().herramienta_responder()

    # ----- eventos -----
    def modelo(self, uso, ms: float, pedidas: list[str] | None = None):
        tin, tout = normalizar_uso(uso)
        self.r.pasos += 1
        self.r.tokens_in += tin
        self.r.tokens_out += tout
        c = costo(self.modelo_id, tin, tout)
        self.r.costo_usd += c
        if pedidas and len(pedidas) > 1:
            self.r.turnos_paralelos += 1
        self.traza("modelo", self.r.pasos, ms=round(ms), tokens_in=tin, tokens_out=tout, costo_usd=round(c, 8),
                   herramientas_pedidas=list(pedidas or []))

    def herramienta(self, nombre: str, ms: float, salida: dict | str):
        if isinstance(salida, str):
            try:
                salida = json.loads(salida)
            except json.JSONDecodeError:
                salida = {"ok": False, "error": {"tipo": "salida_no_json"}}
        ok = bool(salida.get("ok", False))
        self.r.herramientas += 1
        self.r.errores_herramienta += 0 if ok else 1
        self.traza("herramienta", self.r.pasos, herramienta=nombre, ms=round(ms), ok=ok,
                   error=(salida.get("error") or {}).get("tipo") if isinstance(salida.get("error"), dict) else salida.get("error"))

    def responder(self, entrada: dict) -> dict:
        """Valida la respuesta final como la semana 13. Devuelve la salida para el modelo; si es válida, la guarda."""
        l13 = semana13()
        t = time.perf_counter()
        try:
            final = l13.RespuestaFinal.model_validate(entrada).model_dump()
            if problema := l13.revisar_final(final, self.tarea):
                raise ValueError(problema)
            self.final, salida = final, {"ok": True}
        except (ValidationError, ValueError) as e:
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()) \
                if isinstance(e, ValidationError) else str(e)
            salida = {"ok": False, "error": {"tipo": "respuesta_invalida", "mensaje": msg[:800],
                                             "sugerencia": "Corrige los campos y llama responder de nuevo."}}
        self.herramienta("responder", 1000 * (time.perf_counter() - t), salida)
        if self.final:
            self.traza("final", self.r.pasos, estado=self.final["estado"], respuesta=self.final)
        return salida

    def excedido(self) -> str | None:
        """Límites que la semana 13 revisa antes de cada llamada al modelo. `max_herramientas` se revisa antes de cada
        herramienta (`herramientas_agotadas`), igual que en su loop."""
        if self.r.pasos >= self.lim.max_pasos:
            return "max_pasos"
        if self.r.tokens_in + self.r.tokens_out >= self.lim.max_tokens_total:
            return "max_tokens_total"
        if time.perf_counter() - self.t0 >= self.lim.max_segundos:
            return "max_segundos"
        return None

    def herramientas_agotadas(self) -> bool:
        return self.r.herramientas >= self.lim.max_herramientas

    def parar(self, estado: str | None = None, motivo: str = ""):
        if self.final and estado is None:
            estado, motivo = self.final["estado"], motivo or "responder"
        self.r.estado, self.r.motivo = estado or "limite_alcanzado", motivo or "sin_responder"
        self.r.final = self.final if self.r.estado == (self.final or {}).get("estado") else None
        self.r.segundos = round(time.perf_counter() - self.t0, 2)
        self.r.costo_usd = costo(self.modelo_id, self.r.tokens_in, self.r.tokens_out)   # sin error de redondeo acumulado
        self.traza("parada", self.r.pasos, estado=self.r.estado, motivo=self.r.motivo, pasos=self.r.pasos,
                   herramientas=self.r.herramientas, tokens_in=self.r.tokens_in, tokens_out=self.r.tokens_out,
                   costo_usd=round(self.r.costo_usd, 8), segundos=self.r.segundos)
        return self.r


class Adaptador(ABC):
    """Un framework. `mcp_url` y `token`: el servidor de la semana 14 y el token OAuth del usuario.
    `base_url`: la API de Anthropic o el doble del modelo simulado."""
    framework = "?"

    def __init__(self, mcp_url: str, token: str, modelo: str = "claude-haiku-5-5", esfuerzo: str = "low",
                 limites=None, base_url: str | None = None, ruta_trazas: Path | None = None, sistema: str | None = None):
        self.mcp_url, self.token, self.modelo, self.esfuerzo = mcp_url, token, modelo, esfuerzo
        self.limites, self.base_url, self.ruta_trazas, self.sistema = limites, base_url, ruta_trazas, sistema

    def registro(self, tarea: dict) -> Registro:
        return Registro(self.framework, self.modelo, tarea, self.limites, self.ruta_trazas, self.sistema)

    @abstractmethod
    def resolver(self, tarea: dict):
        ...


class AdaptadorPropio(Adaptador):
    """Referencia: el loop propio de la semana 13 sin cambios, con las herramientas del servidor MCP (cliente de la
    semana 14 en modo directo). Sus trazas se traducen al formato común."""
    framework = "propio"

    def resolver(self, tarea: dict):
        import sys
        s14 = Path(__file__).resolve().parents[2] / "semana-14"
        if str(s14) not in sys.path:
            sys.path.insert(0, str(s14))
        from cliente.seguro import ClienteSeguro, ServidorMCP

        from .simulado import api_doble
        l13 = semana13()
        api = api_doble(self.base_url) if self.base_url else l13.api_anthropic
        with tempfile.TemporaryDirectory() as d:
            propia = Path(d) / "t.jsonl"
            with ClienteSeguro([ServidorMCP("legado", self.mcp_url, self.token)], defensas=False) as cliente:
                r = l13.Agente(cliente, self.modelo, self.esfuerzo, self.limites, api=api, trazas=propia).resolver(tarea)
            eventos = [json.loads(x) for x in propia.read_text().splitlines()] if propia.exists() else []
        traza = Trazador(self.ruta_trazas, self.framework, self.modelo, r.corrida,
                         tarea.get("id", "") + (f"#{tarea['rep']}" if "rep" in tarea else ""))
        for ev in eventos:
            campos = {k: v for k, v in ev.items() if k not in ("ts", "corrida", "tarea", "tipo", "paso", "modelo")}
            if ev["tipo"] == "final":
                campos["estado"] = ev["respuesta"]["estado"]
            traza(ev["tipo"], ev.get("paso", r.pasos), **campos)
        self.ultimas_trazas = traza.eventos
        return r
