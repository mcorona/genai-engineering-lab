"""LegacyBridge v1: the measured pieces of weeks 13 to 17 behind one object (`LegacyBridge`) and one command (`python -m legacybridge`).

    with LegacyBridge(modo="multiagente") as lb:                      # Keycloak if it is up, the lab issuer otherwise
        r = lb.preguntar("Which critical SKUs are below their reorder point?", usuario="analista", lang="en")
        lb.pendientes(); lb.decidir(solicitud, aprobador="gerente", decision="approve"); lb.reanudar(solicitud)

What it puts together, without copying any of it:
* week 14's MCP server (Streamable HTTP, OAuth: Keycloak's realm or the lab issuer) with its server spans, and week 14's client with its
  defenses (allowlist, pins, prefixes), the user's own token;
* week 17's agent: instrumented (activity 3), budgeted (4), guarded (5), approvable (6), exporting to the Collector when it is up;
* in multi-agent mode, week 15's purchasing specialist over A2A (Strands, its own OAuth audience, no credentials), as one more tool;
* approvers: Keycloak's approver roles (activity 10) or, with the lab issuer, a lab approver issuer.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
S14, S15, S17 = RAIZ / "semana-14", RAIZ / "semana-15", RAIZ / "semana-17"
for p in (str(S17), str(S14), str(S15)):
    if p not in sys.path:
        sys.path.insert(0, p)

import jwt  # noqa: E402

from aprobaciones import maquina as M  # noqa: E402
from aprobaciones.agente import AgenteAprobable  # noqa: E402
from aprobaciones.almacen import Almacen  # noqa: E402
from aprobaciones.identidad import AUDIENCIA, EmisorDePrueba, VerificadorAprobador  # noqa: E402
from aprobaciones.servicio import Aprobaciones  # noqa: E402
from instrumentacion.laboratorio import ClienteInstrumentado, ServidorMCP, cerrar_trazas, configurar_trazas, manifiesto  # noqa: E402
from instrumentacion.trazas_servidor import InstrumentorServidor  # noqa: E402

from .delegacion import HerramientasDelegadas  # noqa: E402

MODOS = ("simple", "multiagente")
OTLP = "http://127.0.0.1:4318/v1/traces"
A2A_PUERTO = 8015
A2A_URL = f"http://127.0.0.1:{A2A_PUERTO}/"
SCOPE_COMPRAS = "legado:compras:proponer"


def _modulo(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def keycloak_arriba() -> bool:
    try:
        from auth import pkce
        pkce.descubrimiento()
        return pkce.SECRETOS.exists()
    except Exception:   # noqa: BLE001
        return False


def collector_arriba() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:13133/", timeout=1)
        return True
    except Exception:   # noqa: BLE001
        return False


class EspecialistaA2A:
    """Week 15's Strands specialist as a subprocess (its own virtual env), reached with week 15's A2A client."""

    def __init__(self, emisor: str, jwks: str, token):
        python = Path(os.environ.get("VENVS_S15", S15 / ".venvs")) / "st" / "bin" / "python"
        self.p = subprocess.Popen([str(python), "-m", "multiagente.servidor_compras", "--emisor", emisor, "--jwks", jwks,
                                   "--puerto", str(A2A_PUERTO)], cwd=S15, env={**os.environ, "PYTHONPATH": str(S15)},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            try:
                urllib.request.urlopen(A2A_URL + ".well-known/agent-card.json", timeout=1)
                break
            except Exception:   # noqa: BLE001
                time.sleep(0.1)
        else:
            self.cerrar()
            raise RuntimeError("the A2A specialist did not start (port 8015 in use?)")
        from multiagente.cliente import ClienteA2A
        self.cliente = ClienteA2A(A2A_URL, token(), emisor)

    def __call__(self, texto: str):
        return self.cliente.enviar(texto)

    def cerrar(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()


class LegacyBridge:
    def __init__(self, *, modo: str = "simple", emisor: str = "auto", api=None, especialista=None, esquema_hitl: str = "hitl",
                 otlp: str | None = "auto", simulado: bool = False, tenant: str = "lab"):
        if modo not in MODOS:
            raise ValueError(f"modo must be one of {MODOS}")
        self.modo, self.tenant, self.simulado = modo, tenant, simulado
        self.emisor_modo = ("keycloak" if keycloak_arriba() else "prueba") if emisor == "auto" else emisor
        if api is None:
            from agente.loop import api_anthropic
            api = api_anthropic
        self.api = api
        configurar_trazas(OTLP if (otlp == "auto" and collector_arriba()) else (otlp if otlp not in (None, "auto") else None))
        self.instrumentor = InstrumentorServidor().instrument()
        self.entorno = _modulo("seguridad14_v1", S14 / "seguridad" / "correr.py").Entorno(self.emisor_modo, con_base=True)
        self.almacen = Almacen(esquema=esquema_hitl)
        self.almacen.crear()
        self.especialista = especialista
        self._a2a = None
        self._clientes = []
        self._aprobador = None
        if modo == "multiagente" and especialista is None:
            self._a2a = EspecialistaA2A(*self._emisor_y_jwks(), self._token_a2a)
            self.especialista = self._a2a

    # ---------- identity ----------

    def _emisor_y_jwks(self) -> tuple[str, str]:
        if self.emisor_modo == "keycloak":
            from auth import pkce
            meta = pkce.descubrimiento()
            return meta["issuer"], meta["jwks_uri"]
        return self.entorno._em.emisor, self.entorno._em.jwks_uri

    def _token_a2a(self) -> str:
        if self.emisor_modo == "keycloak":
            from auth import pkce
            return pkce.obtener_token("analista", scopes=["legado:leer", SCOPE_COMPRAS], resource=A2A_URL,
                                      cliente="legacybridge-supervisor")["access_token"]
        return self.entorno._em.token(A2A_URL, "analista")

    def costo_especialista(self) -> float:
        """What the delegations of the last agent cost (the specialist's own model calls; its usage comes back over A2A)."""
        from agente.loop import costo
        fuente = getattr(self, "ultima_fuente", None)
        total = 0.0
        for d in getattr(fuente, "delegaciones", []):
            u = d.get("uso") or {}
            total += costo("claude-haiku-5-5", int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0))
        return total

    def token_mcp(self, usuario: str) -> str:
        return self.entorno.token(usuario)

    # ---------- the agent ----------

    def agente(self, usuario: str):
        token = self.token_mcp(usuario)
        scopes = frozenset(jwt.decode(token, options={"verify_signature": False})["scope"].split())
        srv = self.entorno.servidores["normal"]
        cliente = ClienteInstrumentado([ServidorMCP("legado", srv.url, token)], allowlist={"legado": {"pins": manifiesto()["herramientas"]}},
                                       defensas=True).abrir()
        self._clientes.append(cliente)
        fuente = HerramientasDelegadas(cliente, self.especialista) if self.modo == "multiagente" else cliente
        self.ultima_fuente = fuente
        return AgenteAprobable(fuente, api=self.api, tenant=self.tenant, almacen=self.almacen, scopes_de=lambda s: scopes,
                               simulado=self.simulado)

    def preguntar(self, texto: str, *, usuario: str = "analista", lang: str = "en", id_: str = "v1"):
        ag = self.agente(usuario)
        # the tools answer in Spanish (legacy data, rules, notes) and week 13's prompt alone does not hold the language (activity 6, finding 3)
        idioma = {"en": "Write the whole answer in English.", "es": "Escribe toda la respuesta en español."}[lang]
        r = ag.resolver({"id": f"{id_}-{lang}", "lang": lang, "tarea": f"{texto}\n\n{idioma}"}, jwt.decode(self.token_mcp(usuario), options={"verify_signature": False})["sub"])
        return r, ag

    # ---------- approvals ----------

    def _servicio(self) -> tuple[Aprobaciones, callable]:
        if self._aprobador is None:
            if self.emisor_modo == "keycloak":
                from aprobaciones import keycloak as K
                from legacybridge import identidades
                claves = identidades.asegurar()
                verificador = VerificadorAprobador(jwt.PyJWKClient(f"{K.pkce.EMISOR}/protocol/openid-connect/certs"),
                                                   emisor=K.pkce.EMISOR, audiencia=AUDIENCIA)
                self._aprobador = (Aprobaciones(self.almacen, verificador), lambda sub, roles: K.token_de(sub, claves[sub]))
            else:
                em = EmisorDePrueba()             # the lab approver issuer: the approver's name is its level (comprador, gerente, director)
                self._aprobador = (Aprobaciones(self.almacen, em.verificador()),
                                   lambda sub, roles: em.token(sub, roles if roles is not None else [M.ROL_DE_NIVEL[sub]] if sub in M.ROL_DE_NIVEL else []))
        return self._aprobador

    def pendientes(self) -> list[dict]:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(self.almacen.dsn, row_factory=dict_row) as c:
            return c.execute(f"SELECT id, sku, cantidad, monto_mxn, nivel, solicitante, creada_en, expira_en FROM {self.almacen.s}.solicitudes "
                             f"WHERE estado = 'pendiente' ORDER BY creada_en").fetchall()

    def decidir(self, solicitud: str, *, aprobador: str, decision: str = "approve", roles=None):
        servicio, token_de = self._servicio()
        return servicio.decidir(solicitud, token_de(aprobador, roles), decision)

    def reanudar(self, solicitud: str, *, usuario: str = "analista"):
        return self.agente(usuario).reanudar(solicitud)

    # ---------- lifecycle ----------

    def cerrar(self):
        for c in self._clientes:
            try:
                c.cerrar()
            except Exception:   # noqa: BLE001
                pass
        if self._a2a:
            self._a2a.cerrar()
        try:
            self.entorno.cerrar()
        finally:
            self.instrumentor.uninstrument()
            cerrar_trazas()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.cerrar()
