"""Actividad 3: transporte Streamable HTTP. Uvicorn real en 127.0.0.1 con el cliente HTTP del SDK y peticiones HTTP
crudas (http.client) para los casos que un cliente correcto nunca manda. Sin API."""
import asyncio
import http.client
import json
import os
import sys
import threading
import time
from pathlib import Path

import jsonschema
import pytest
from conftest import HAY_BASE, S14, ServidorHTTP, con_cliente, fabrica
from herramientas import Contexto, Herramientas
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from servidor.http import HOST, LimitesHTTP, Trazas
from servidor.primitivas import LimitesHerramientas, crear_servidor, herramientas_mcp, manifiesto
from test_primitivas import CASOS_CON_BASE, CASOS_SIN_BASE, normal

PROTO = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": PROTO,
        "io.modelcontextprotocol/clientInfo": {"name": "prueba-cruda", "version": "0"},
        "io.modelcontextprotocol/clientCapabilities": {}}


def http_srv(usuario="analista", conexion=None, limites_h=LimitesHerramientas(), **kw):
    return ServidorHTTP(crear_servidor(fabrica(usuario, conexion), limites_h), usuario=usuario, **kw)


def crudo(s, metodo="POST", cuerpo=None, headers=None, encabezados_mcp=True, chunks=None, ruta="/mcp"):
    """Petición HTTP cruda; devuelve (estado, headers, cuerpo)."""
    c = http.client.HTTPConnection(HOST, s.puerto, timeout=20)
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if encabezados_mcp and isinstance(cuerpo, dict):
        h |= {"MCP-Protocol-Version": PROTO, "Mcp-Method": cuerpo.get("method", "")}
        p = cuerpo.get("params", {})
        if p.get("name") or p.get("uri"):
            h["Mcp-Name"] = p.get("name") or p.get("uri")
    h |= headers or {}
    datos = json.dumps(cuerpo).encode() if isinstance(cuerpo, dict) else cuerpo
    if chunks is not None:
        c.request(metodo, ruta, body=iter(chunks), headers=h, encode_chunked=True)
    else:
        c.request(metodo, ruta, body=datos, headers=h)
    r = c.getresponse()
    out = r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    c.close()
    return out


def peticion(metodo, id_=1, **params):
    return {"jsonrpc": "2.0", "id": id_, "method": metodo, "params": {**params, "_meta": META}}


def con_url(url, fn):
    async def _c():
        async with Client(url) as c:
            return await fn(c)
    return asyncio.run(_c())


# ---------- cliente HTTP del SDK ----------


def _trazas(s, n=1, espera_s=2.0):
    """La traza se escribe después de enviar la respuesta (incluye estado y bytes): se espera a que exista."""
    fin = time.monotonic() + espera_s
    while len(s.trazas.ultimas) < n and time.monotonic() < fin:
        time.sleep(0.01)
    return list(s.trazas.ultimas)

def test_cliente_sdk_por_http():
    with http_srv("almacenista") as s:
        async def fn(c):
            return (c.protocol_version, await c.list_tools(), await c.list_resources(), await c.list_resource_templates(),
                    await c.read_resource("legado://manifiesto"), await c.list_prompts(),
                    await c.get_prompt("analizar_exceso_inventario", {"max_skus": "3"}),
                    await c.call_tool("buscar_regla_negocio", {"consulta": "R-EXCEDENTE"}),
                    await c.call_tool("proponer_orden_compra", {"sku": "SKU-0001", "cantidad": 1, "motivo": "x"}))
        proto, tools, recursos, plantillas, man, prompts, prompt, regla, prop = con_url(s.url, fn)
    assert proto == PROTO
    assert [t.model_dump() for t in tools.tools] == [t.model_dump() for t in herramientas_mcp()]
    assert json.loads(man.contents[0].text) == manifiesto()
    assert len(recursos.resources) == 1 + 4 + 15 and len(plantillas.resource_templates) == 2
    assert [p.name for p in prompts.prompts] == ["analizar_exceso_inventario"]
    assert "hasta 3 SKU" in prompt.messages[0].content.text
    assert regla.structured_content["reglas"][0]["id"] == "R-EXCEDENTE" and regla.is_error is False
    assert prop.is_error is True and prop.structured_content["error"]["tipo"] == "permiso_denegado"


def test_escucha_solo_en_loopback():
    with http_srv() as s:
        assert {d[0] for d in s.direcciones()} == {"127.0.0.1"}
    assert "--host" not in (S14 / "servidor" / "__main__.py").read_text(encoding="utf-8")


# ---------- Origin, Host y encabezados de método (A08, A11) ----------

def test_origin_hostil_403():
    with http_srv() as s:
        ok = crudo(s, cuerpo=peticion("tools/list"), headers={"Origin": f"http://127.0.0.1:{s.puerto}"})
        hostil = crudo(s, cuerpo=peticion("tools/list"), headers={"Origin": "http://evil.example"})
        otro_puerto = crudo(s, cuerpo=peticion("tools/list"), headers={"Origin": f"http://127.0.0.1:{s.puerto + 1}"})
        trazas = _trazas(s, 3)
    assert ok[0] == 200
    assert hostil[0] == 403 and otro_puerto[0] == 403
    assert [t["resultado"] for t in trazas] == ["ok", "rechazado", "rechazado"]


def test_host_no_permitido():
    with http_srv() as s:
        for host in ("evil.example", f"evil.example:{s.puerto}", f"192.168.1.10:{s.puerto}"):
            assert crudo(s, cuerpo=peticion("tools/list"), headers={"Host": host})[0] == 421, host
        assert crudo(s, cuerpo=peticion("tools/list"), headers={"Host": f"localhost:{s.puerto}"})[0] == 200


def test_mcp_name_distinto_400():
    llamada = peticion("tools/call", name="buscar_regla_negocio", arguments={"consulta": "R-COB"})
    with http_srv() as s:
        casos = {
            "Mcp-Name distinto": crudo(s, cuerpo=llamada, headers={"Mcp-Name": "ejecutar_sql"}),
            "Mcp-Method distinto": crudo(s, cuerpo=llamada, headers={"Mcp-Method": "tools/list"}),
            "sin Mcp-Name": crudo(s, cuerpo=llamada, headers={"Mcp-Name": ""}),
            "versión distinta al _meta": crudo(s, cuerpo=llamada, headers={"MCP-Protocol-Version": "2025-11-25"}),
        }
        bien = crudo(s, cuerpo=llamada)
    for caso, (estado, _, cuerpo) in casos.items():
        assert estado == 400, caso
        assert json.loads(cuerpo)["error"]["code"] == -32020, caso
    assert bien[0] == 200 and json.loads(bien[2])["result"]["isError"] is False


# ---------- sin estado ----------

def test_sin_estado():
    with http_srv() as s:
        r1 = crudo(s, cuerpo=peticion("tools/list", 1))
        r2 = crudo(s, cuerpo=peticion("tools/call", 2, name="validar_sql", arguments={"sql": "SELECT 1"}))
        # cliente de una versión con handshake: se le contesta sin crear sesión
        ini = crudo(s, cuerpo={"jsonrpc": "2.0", "id": 9, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "viejo", "version": "0"}}},
            encabezados_mcp=False, headers={"MCP-Protocol-Version": "2025-11-25"})
        get = crudo(s, metodo="GET")
        delete = crudo(s, metodo="DELETE")
    for estado, h, _ in (r1, r2, ini):
        assert estado == 200 and "mcp-session-id" not in h
    assert json.loads(ini[2])["result"]["protocolVersion"] == "2025-11-25"
    assert get[0] == 405 and delete[0] == 405 and get[1]["allow"] == "POST"


# ---------- límites (A13) ----------

def test_cuerpo_excesivo_413():
    limites = LimitesHTTP(max_cuerpo_bytes=2048)
    grande = peticion("tools/call", name="validar_sql", arguments={"sql": "SELECT '" + "x" * 4000 + "'"})
    with http_srv(limites=limites) as s:
        declarado = crudo(s, cuerpo=grande)
        datos = json.dumps(grande).encode()
        por_partes = crudo(s, cuerpo=grande, chunks=[datos[i:i + 512] for i in range(0, len(datos), 512)])
        normal_ = crudo(s, cuerpo=peticion("tools/list"))
        trazas = _trazas(s, 3)
    assert declarado[0] == 413 and por_partes[0] == 413
    assert json.loads(declarado[2])["error"]["code"] == -32600
    assert normal_[0] == 200
    assert [t["estado"] for t in trazas] == [413, 413, 200]


class Lenta(Herramientas):
    """Herramientas reales con una demora y un contador de ejecuciones simultáneas."""

    def __init__(self, demora):
        super().__init__(Contexto.de_usuario("analista"))
        self.demora, self.activas, self.max_activas = demora, 0, 0
        self._lock = threading.Lock()

    def llamar(self, nombre, argumentos):
        with self._lock:
            self.activas += 1
            self.max_activas = max(self.max_activas, self.activas)
        try:
            time.sleep(self.demora)
            return super().llamar(nombre, argumentos)
        finally:
            with self._lock:
                self.activas -= 1


def test_tiempo_agotado():
    lenta = Lenta(2.0)
    srv = crear_servidor(lambda: lenta, LimitesHerramientas(tiempo_s=0.3))
    with ServidorHTTP(srv) as s:
        inicio = time.perf_counter()
        r = con_url(s.url, lambda c: c.call_tool("buscar_regla_negocio", {"consulta": "R-COB"}))
        seg = time.perf_counter() - inicio
        traza = _trazas(s)[-1]
    assert seg < 1.5
    assert r.is_error is True and r.structured_content["error"]["tipo"] == "tiempo_agotado"
    jsonschema.validate(r.structured_content, next(t for t in herramientas_mcp() if t.name == "buscar_regla_negocio").output_schema)
    assert traza["resultado"] == "error_herramienta" and traza["error"] == "tiempo_agotado"


def test_concurrencia_de_herramientas_limitada():
    lenta = Lenta(0.4)
    srv = crear_servidor(lambda: lenta, LimitesHerramientas(concurrentes=2))
    with ServidorHTTP(srv) as s:
        async def fn(c):
            return await asyncio.gather(*[c.call_tool("buscar_regla_negocio", {"consulta": "R-COB"}) for _ in range(6)])
        rs = con_url(s.url, fn)
    assert all(not r.is_error for r in rs)
    assert lenta.max_activas == 2


def test_peticiones_en_curso_limitadas_503():
    lenta = Lenta(0.6)
    srv = crear_servidor(lambda: lenta, LimitesHerramientas(concurrentes=8))
    with ServidorHTTP(srv, limites=LimitesHTTP(max_en_curso=2)) as s:
        resultados = [None] * 6

        def una(i):
            resultados[i] = crudo(s, cuerpo=peticion("tools/call", i, name="buscar_regla_negocio",
                                                     arguments={"consulta": "R-COB"}))
        hilos = [threading.Thread(target=una, args=(i,)) for i in range(6)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        trazas = _trazas(s, 6)
    estados = sorted(r[0] for r in resultados)
    assert estados.count(200) >= 2 and estados.count(503) >= 1 and set(estados) <= {200, 503}
    assert all(r[1]["retry-after"] == "1" for r in resultados if r[0] == 503)
    assert lenta.max_activas <= 2
    assert sum(t["estado"] == 503 for t in trazas) == estados.count(503)


# ---------- trazas JSONL ----------

def test_trazas_jsonl(tmp_path):
    ruta = tmp_path / "trazas.jsonl"
    with http_srv("vendedor", trazas=Trazas(ruta)) as s:
        async def fn(c):
            await c.list_tools()
            await c.call_tool("buscar_regla_negocio", {"consulta": "VALOR-SECRETO-123"})
            await c.call_tool("muestrear_valores", {"tabla": "prvmst", "columna": "prv_nm"})
            await c.read_resource("legado://reglas/R-COB")
        con_url(s.url, fn)
        crudo(s, cuerpo=peticion("tools/list"), headers={"Origin": "http://evil.example",
                                                       "Authorization": "Bearer TOKEN-QUE-NO-SE-REGISTRA"})
    texto = ruta.read_text(encoding="utf-8")
    lineas = [json.loads(x) for x in texto.splitlines()]
    claves = {"ts", "http", "metodo", "nombre", "sujeto", "scopes", "cliente", "protocolo", "estado", "resultado",
              "error", "ms", "bytes_in", "bytes_out"}
    assert all(claves <= set(x) for x in lineas)
    por_metodo = {(x["metodo"], x["nombre"]): x for x in lineas}
    assert por_metodo[("tools/call", "buscar_regla_negocio")]["resultado"] == "ok"
    denegado = por_metodo[("tools/call", "muestrear_valores")]
    assert denegado["resultado"] == "error_herramienta" and denegado["error"] == "permiso_denegado"
    assert por_metodo[("resources/read", "legado://reglas/R-COB")]["estado"] == 200
    assert lineas[-1]["resultado"] == "rechazado" and lineas[-1]["estado"] == 403
    assert all(x["sujeto"] == "vendedor" and x["protocolo"] in (PROTO, None) for x in lineas)
    assert all(isinstance(x["ms"], float) and x["ms"] >= 0 for x in lineas)
    # nunca argumentos, resultados ni credenciales
    assert "VALOR-SECRETO-123" not in texto and "TOKEN-QUE-NO-SE-REGISTRA" not in texto and "prv_nm" not in texto


# ---------- equivalencia HTTP = stdio = memoria ----------

def _stdio(usuario):
    return StdioServerParameters(command=sys.executable, args=["-m", "servidor", "--transporte", "stdio", "--usuario", usuario],
                                 cwd=str(S14), env={**os.environ})


def _llamar(destino, casos):
    async def fn(c):
        return [await c.call_tool(n, a) for n, a in casos]
    return con_url(destino, fn) if isinstance(destino, str) else asyncio.run(_con(destino, fn))


async def _con(destino, fn):
    async with Client(destino) as c:
        return await fn(c)


def _equivalencia(usuario, casos, conexion=None):
    memoria = con_cliente(crear_servidor(fabrica(usuario, conexion)), lambda c: _todas(c, casos))
    stdio = _llamar(_stdio(usuario), casos)
    with http_srv(usuario, conexion) as s:
        por_http = _llamar(s.url, casos)
    for (nombre, args), m, e, h in zip(casos, memoria, stdio, por_http):
        assert normal(m.structured_content) == normal(e.structured_content) == normal(h.structured_content), (nombre, args)
        assert m.is_error == e.is_error == h.is_error
        assert m.meta["io.legacybridge/source"] == e.meta["io.legacybridge/source"] == h.meta["io.legacybridge/source"]


async def _todas(c, casos):
    return [await c.call_tool(n, a) for n, a in casos]


@pytest.mark.parametrize("usuario", ["analista", "almacenista"])
def test_equivalencia_http_stdio_sin_base(usuario, monkeypatch):
    for v in ("NLQ_LEGADO_DSN", "PG_ADMIN_DSN", "PG_DSN"):
        monkeypatch.delenv(v, raising=False)
    _equivalencia(usuario, CASOS_SIN_BASE)


def test_equivalencia_http_stdio_con_base(conexion):
    # el proceso stdio hereda NLQ_LEGADO_DSN (lo fija conectar()), así usa el mismo rol copilot_nlq
    assert os.environ.get("NLQ_LEGADO_DSN")
    _equivalencia("analista", CASOS_CON_BASE, conexion)
