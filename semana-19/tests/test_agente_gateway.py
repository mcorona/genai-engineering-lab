"""Week 19, activity 7: the agent Lambda as an MCP client of the gateway (CAMINO_HERRAMIENTAS=gateway), offline.

The MCP session is simulated (no network, no AWS): it records what the agent sends. The real session builder is
checked separately: it puts the user's token in the Authorization header of the HTTP client it gives the transport.
"""
from __future__ import annotations

import base64
import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agente import cliente_gateway as G  # noqa: E402
from agente import construccion as K  # noqa: E402
from agente import handler as H  # noqa: E402
from consultas import worker  # noqa: E402
from test_agente_construccion import CLAIMS, ENTORNO, PREGUNTA, Converse, Lambda  # noqa: E402

ENTORNO_GW = {**ENTORNO, "CAMINO_HERRAMIENTAS": "gateway", "GATEWAY_URL": "https://gw.invalid/mcp"}
AHORA = 1_800_000_000


def jwt(exp: int | None = AHORA + 3600, **claims) -> str:
    """An unsigned token of the right shape (the gateway verifies signatures; the client only reads `exp`)."""
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return ".".join([b64({"alg": "RS256"}), b64({**claims, **({"exp": exp} if exp else {})}), "firma"])


class SesionSimulada:
    """Stands in for mcp.ClientSession after initialize: records each call, answers like the Lambda target."""

    def __init__(self, respuesta=None, error: Exception | None = None):
        self.llamadas, self.abiertas, self.cerradas = [], 0, 0
        self.respuesta = respuesta if respuesta is not None else {"filas": [[12]], "truncado": False, "limite": 200}
        self.error = error

    def abrir(self):
        @contextlib.asynccontextmanager
        async def cm():
            self.abiertas += 1
            try:
                yield self
            finally:
                self.cerradas += 1
        return cm()

    async def call_tool(self, nombre, argumentos):
        self.llamadas.append((nombre, argumentos))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.respuesta))], is_error=False)


def llamador(sesion, token=None, reloj=lambda: AHORA):
    return G.LlamadorGateway("https://gw.invalid/mcp", token or jwt(), al_contrato=K._al_contrato_semana13,
                             abrir=sesion.abrir, reloj=reloj)


# ---------------------------------------------------------------- the MCP client

def test_una_sesion_por_pregunta_con_nombres_del_target():
    s = SesionSimulada()
    ll = llamador(s)
    assert ll("ejecutar_sql", {"sql": "SELECT 1"}) == {"ok": True, "filas": [[12]], "truncado": False, "limite": 200}
    ll("describir_esquema", {})
    ll.cerrar()
    assert s.abiertas == 1 and s.cerradas == 1
    assert [n for n, _ in s.llamadas] == ["herramientas___ejecutar_sql", "herramientas___describir_esquema"]


def test_la_propuesta_lleva_el_solicitante_del_token_y_las_lecturas_no():
    s = SesionSimulada(respuesta={"solicitud_id": "x", "estado": "PENDING_APPROVAL"})
    ll = llamador(s)
    ll("proponer_orden_compra", {"sku": "SKU-0009"}, solicitante="sub-comprador")
    ll("ejecutar_sql", {"sql": "SELECT 1"}, solicitante="sub-comprador")
    ll.cerrar()
    assert s.llamadas[0][1] == {"sku": "SKU-0009", "solicitante": "sub-comprador"}
    assert s.llamadas[1][1] == {"sql": "SELECT 1"}


def test_la_sesion_real_manda_el_token_del_usuario_en_authorization(monkeypatch):
    """_abrir_mcp builds the HTTP client with `Authorization: Bearer <token>` and hands it to the transport."""
    import mcp
    import mcp.client.streamable_http as transporte
    visto = {}

    @contextlib.asynccontextmanager
    async def cliente_http(headers=None, **_):
        visto["headers"] = headers
        yield "http"

    @contextlib.asynccontextmanager
    async def streamable(url, *, http_client=None, **_):
        visto["url"], visto["http_client"] = url, http_client
        yield ("leer", "escribir", lambda: None)

    class Sesion:
        def __init__(self, leer, escribir):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def initialize(self):
            visto["inicializada"] = True

        async def call_tool(self, nombre, argumentos):
            return SimpleNamespace(content=[SimpleNamespace(text='{"filas": []}')], is_error=False)

    monkeypatch.setattr(transporte, "create_mcp_http_client", cliente_http)
    monkeypatch.setattr(transporte, "streamable_http_client", streamable)
    monkeypatch.setattr(mcp, "ClientSession", Sesion)
    token = jwt(sub="sub-1")
    ll = G.LlamadorGateway("https://gw.invalid/mcp", token, al_contrato=K._al_contrato_semana13, reloj=lambda: AHORA)
    assert ll("describir_esquema", {})["ok"] is True
    ll.cerrar()
    assert visto == {"headers": {"Authorization": f"Bearer {token}"}, "url": "https://gw.invalid/mcp",
                     "http_client": "http", "inicializada": True}


@pytest.mark.parametrize("exp", [None, AHORA - 1, AHORA + G.MARGEN_S - 1])
def test_un_token_vencido_o_sin_exp_nunca_se_envia(exp):
    s = SesionSimulada()
    with pytest.raises(G.TokenVencido):
        llamador(s, token=jwt(exp=exp))("ejecutar_sql", {"sql": "SELECT 1"})
    assert s.llamadas == [] and s.abiertas == 0


def test_un_401_del_gateway_es_token_vencido():
    class Respuesta:
        status_code = 401

    error = RuntimeError("http")
    error.response = Respuesta()
    with pytest.raises(G.TokenVencido):
        llamador(SesionSimulada(error=ExceptionGroup("tarea", [error])))("ejecutar_sql", {"sql": "SELECT 1"})


def test_un_rechazo_jsonrpc_del_gateway_llega_cerrado_con_su_codigo():
    from mcp.shared.exceptions import MCPError
    res = llamador(SesionSimulada(error=MCPError(-32002, "denegado por la política: detalle interno")))(
        "proponer_orden_compra", {"sku": "SKU-0009"}, solicitante="x")
    assert res["ok"] is False and res["error"]["tipo"] == G.RECHAZO_DEL_GATEWAY and res["error"]["codigo"] == -32002
    assert "detalle interno" not in json.dumps(res)


def test_un_rechazo_anidado_en_dos_grupos_llega_cerrado_con_su_codigo():
    from mcp.shared.exceptions import MCPError
    anidado = ExceptionGroup("cliente", [ExceptionGroup("sesion", [MCPError(-32002, "detalle interno")])])
    res = llamador(SesionSimulada(error=anidado))("proponer_orden_compra", {"sku": "SKU-0009"}, solicitante="x")
    assert res["ok"] is False and res["error"]["tipo"] == G.RECHAZO_DEL_GATEWAY and res["error"]["codigo"] == -32002
    assert "detalle interno" not in json.dumps(res)


def test_otra_falla_del_transporte_es_un_error_cerrado():
    res = llamador(SesionSimulada(error=ConnectionError("dns")))("ejecutar_sql", {"sql": "SELECT 1"})
    assert res["ok"] is False and res["error"]["tipo"] == "herramienta_no_disponible"


# ---------------------------------------------------------------- the flag and the loop

def test_por_omision_el_camino_es_directo_y_un_valor_desconocido_falla():
    assert K.camino({}) == "directo"
    with pytest.raises(RuntimeError):
        K.camino({"CAMINO_HERRAMIENTAS": "otro"})


@pytest.mark.parametrize("quitar,token", [("GATEWAY_URL", jwt()), (None, None)])
def test_camino_gateway_sin_url_o_sin_token_falla_cerrado(quitar, token):
    entorno = {k: v for k, v in ENTORNO_GW.items() if k != quitar}
    with pytest.raises(RuntimeError):
        K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=entorno, exportar=lambda _: None,
                    token=token, abrir_mcp=SesionSimulada().abrir)


def _deps_gateway(sesion, token, reloj=lambda: AHORA, lam=None):
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=lam or Lambda(), entorno=ENTORNO_GW,
                       exportar=lambda _: None, token=token, abrir_mcp=sesion.abrir)
    deps["llamar_herramienta"]._reloj = reloj
    return deps


def test_el_bucle_no_cambia_y_las_herramientas_van_por_el_gateway():
    s, lam = SesionSimulada(), Lambda()
    deps = _deps_gateway(s, jwt(), lam=lam)
    res = H.tratar_pregunta(PREGUNTA, H.alcance_desde_claims(CLAIMS), **deps)
    assert res.estado == "respondida" and res.respuesta == "Hay 12 proveedores"
    assert s.llamadas == [("herramientas___ejecutar_sql", {"sql": "SELECT COUNT(*) FROM legado.prvmst"})]
    assert lam.cargas == [] and s.cerradas == 1   # nothing by lambda.invoke; the session ends with the question
    herramienta, agente = [x for x in res.spans if x["tipo"] != "chat"]   # week 20: chat spans per model call
    assert herramienta["attrs"]["gen_ai.tool.type"] == "extension" and agente["tipo"] == "invoke_agent"


def test_el_camino_directo_registra_function_en_el_span():
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=ENTORNO, exportar=lambda _: None)
    res = H.tratar_pregunta(PREGUNTA, H.alcance_desde_claims(CLAIMS), **deps)
    assert res.spans[0]["attrs"]["gen_ai.tool.type"] == "function"


def test_un_token_que_vence_a_mitad_del_bucle_cierra_con_error_y_no_sigue():
    """The token is valid for the first tool call and expired at the second: the question ends as `error` (week 17's
    state), with its spans, and no further call or model turn happens."""
    instantes = iter([AHORA, AHORA + 7200])

    class ConverseDosConsultas(Converse):
        def converse(self, **req):
            self.pedidos.append(req)
            self.turno += 1
            bloque = {"toolUse": {"toolUseId": f"t{self.turno}", "name": "ejecutar_sql",
                                  "input": {"sql": "SELECT COUNT(*) FROM legado.prvmst"}}}
            return {"output": {"message": {"role": "assistant", "content": [bloque]}}, "stopReason": "tool_use",
                    "usage": {"inputTokens": 100, "outputTokens": 20}}

    s = SesionSimulada()
    modelo = ConverseDosConsultas()
    deps = K.construir(cliente_converse=modelo, cliente_lambda=Lambda(), entorno=ENTORNO_GW, exportar=lambda _: None,
                       token=jwt(), abrir_mcp=s.abrir)
    deps["llamar_herramienta"]._reloj = lambda: next(instantes)
    res = H.tratar_pregunta(PREGUNTA, H.alcance_desde_claims(CLAIMS), **deps)
    assert res.estado == "error" and res.respuesta == H.TEXTO_TOKEN_VENCIDO
    assert len(s.llamadas) == 1 and modelo.turno == 2 and s.cerradas == 1
    ok, vencida, agente = [x for x in res.spans if x["tipo"] != "chat"]
    assert ok["attrs"]["lab.tool.status"] == "ok"
    assert vencida["attrs"]["error.type"] == "token_vencido" and agente["attrs"]["lab.outcome.status"] == "error"


def test_el_worker_pasa_el_token_al_agente():
    recibido = {}
    worker.procesar({"id": "c-1", "claims": CLAIMS, "pregunta": "hola", "token": "t"},
                    correr=lambda ev: recibido.update(ev) or {"estado": "respondida", "respuesta": "x"},
                    actualizar=lambda *_: None)
    assert recibido["token"] == "t" and recibido["id"] == "c-1"


@pytest.mark.parametrize("entorno,token", [(ENTORNO, None), (ENTORNO_GW, "gw")])
def test_los_spans_execute_tool_cumplen_el_esquema_bloqueado_de_la_semana_17(monkeypatch, entorno, token):
    """ESTRICTO: an attribute outside week 17's shape, or with a value it does not accept, raises instead of dropping."""
    from instrumentacion import esquema
    monkeypatch.setattr(esquema, "ESTRICTO", True)
    lineas = []
    deps = K.construir(cliente_converse=Converse(), cliente_lambda=Lambda(), entorno=entorno, exportar=lineas.append,
                       token=jwt() if token else None, abrir_mcp=SesionSimulada().abrir)
    if token:
        deps["llamar_herramienta"]._reloj = lambda: AHORA
    H.tratar_pregunta(PREGUNTA, H.alcance_desde_claims(CLAIMS), **deps)
    exportadas = [json.loads(l) for l in lineas]
    # week 20, activity 3: one chat span per model call, also inside the locked shape (strict mode raised nothing)
    assert [e["tipo"] for e in exportadas] == ["execute_tool", "chat", "chat", "invoke_agent"]
    assert all(e["omitidos"] == [] for e in exportadas)
