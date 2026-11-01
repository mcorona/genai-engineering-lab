"""Actividad 7 (sin API): supervisor en LangGraph con especialistas, uno remoto en Strands por A2A con OAuth.
Contrato, presupuesto total, Agent Card, autenticación del servidor A2A, inyección y propuestas."""
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import S15, VENVS, tarea
from test_equivalencia import SQL_V01, _sistema, _v01, correr

from arnes import contrato
from arnes.puente import Puente
from arnes.simulado import DobleAnthropic, Guion, Turno, herramienta, texto
from multiagente.comun import ErrorA2A, validar_agent_card

pytestmark = pytest.mark.skipif(not all((VENVS / v / "bin" / "python").exists() for v in ("lg", "st")),
                                reason="sin los entornos de LangGraph y Strands")
EMISOR = "http://127.0.0.1:8180/realms/legacybridge"


def _tarjeta(url="http://127.0.0.1:8015/", **cambios):
    t = {"name": "compras", "url": url, "protocolVersion": "0.3.0", "securitySchemes": {"keycloak": {"type": "oauth2", "flows": {
        "authorizationCode": {"authorizationUrl": f"{EMISOR}/protocol/openid-connect/auth",
                              "tokenUrl": f"{EMISOR}/protocol/openid-connect/token",
                              "scopes": {"legado:compras:proponer": "x"}}}}}}
    t.update(cambios)
    return t


@pytest.mark.parametrize("tarjeta,motivo", [
    (_tarjeta(url="http://127.0.0.1:9999/"), "otra URL"),
    (_tarjeta(url="http://evil.example/"), "otra URL"),
    (_tarjeta(name="compras-plus"), "nombre"),
    (_tarjeta(protocolVersion="9.0"), "versión"),
    (_tarjeta(securitySchemes={}), "OAuth"),
    (_tarjeta(securitySchemes={"k": {"type": "oauth2", "flows": {"authorizationCode": {
        "authorizationUrl": "http://127.0.0.1:9999/realms/x/auth", "tokenUrl": "http://127.0.0.1:9999/realms/x/token",
        "scopes": {"legado:compras:proponer": "x"}}}}}), "otro emisor"),
    (_tarjeta(securitySchemes={"k": {"type": "oauth2", "flows": {"authorizationCode": {
        "authorizationUrl": f"{EMISOR}/a", "tokenUrl": f"{EMISOR}/t", "scopes": {}}}}}), "scope"),
])
def test_agent_card_falsa_o_de_otro_emisor_se_rechaza(tarjeta, motivo):
    with pytest.raises(ErrorA2A):
        validar_agent_card(tarjeta, "http://127.0.0.1:8015/", EMISOR)
    validar_agent_card(_tarjeta(), "http://127.0.0.1:8015/", EMISOR)          # la legítima pasa


# ---------- servidor A2A de compras (Strands) ----------

class ServidorCompras:
    def __init__(self, entorno, base_url, inyectar=False):
        from servidor.lab import puerto_libre
        em = entorno._em
        self.puerto = puerto_libre()
        self.url = f"http://127.0.0.1:{self.puerto}/"
        self.emisor = em.emisor
        cmd = [str(VENVS / "st" / "bin" / "python"), "-m", "multiagente.servidor_compras", "--emisor", em.emisor,
               "--jwks", em.jwks_uri, "--base-url", base_url, "--puerto", str(self.puerto)] + (["--inyectar"] if inyectar else [])
        self.p = subprocess.Popen(cmd, cwd=S15, env={**os.environ, "PYTHONPATH": str(S15)},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url + ".well-known/agent-card.json", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        self.token = lambda usuario="analista", **kw: em.token(self.url, usuario, **kw)

    def cerrar(self):
        self.p.terminate()
        self.p.wait(timeout=10)


@pytest.fixture(scope="module")
def doble():
    d = DobleAnthropic(Guion([]))
    d.__enter__()
    yield d
    d.__exit__()


@pytest.fixture(scope="module")
def compras(entorno, doble):
    s = ServidorCompras(entorno, doble.base_url)
    yield s
    s.cerrar()


def _post(url, token=None, texto="SKU-0009", tamano=None):
    cuerpo = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {
        "role": "user", "kind": "message", "messageId": uuid.uuid4().hex, "parts": [{"kind": "text", "text": texto}]}}}
    datos = json.dumps(cuerpo).encode() if tamano is None else b"x" * tamano
    req = urllib.request.Request(url, data=datos, headers={"content-type": "application/json",
                                                           **({"authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"www": e.headers.get("WWW-Authenticate")}


def test_servidor_a2a_exige_token_audiencia_propia_y_scope(compras, entorno, doble):
    from servidor.lab import EmisorDePrueba
    doble.guion = Guion([Turno([texto('{"sku": "SKU-0009", "cantidad": 120, "motivo": "x"}')], 321, 45)])
    assert _post(compras.url)[0] == 401                                                   # sin token
    assert _post(compras.url, entorno._em.token("http://127.0.0.1:8014/mcp", "analista"))[0] == 401   # audiencia del MCP
    otro = EmisorDePrueba()                                                               # mismo iss, otra llave
    try:
        assert _post(compras.url, otro.token(compras.url, "analista"))[0] == 401
    finally:
        otro.cerrar()
    estado, r = _post(compras.url, compras.token("almacenista"))                          # sin legado:compras:proponer
    assert estado == 403 and "insufficient_scope" in r["www"]
    assert _post(compras.url, compras.token(), tamano=20_000)[0] == 413
    assert doble.guion.peticiones == []                                                    # nada llegó al modelo
    estado, r = _post(compras.url, compras.token())
    assert estado == 200 and r["result"]["metadata"]["uso"] == {"input_tokens": 321, "output_tokens": 45}
    assert "SKU-0009" in json.dumps(r["result"]["artifacts"])
    pet = doble.guion.peticiones[0]
    assert pet["tools"] == [] if "tools" in pet else True                                 # el especialista no tiene herramientas
    assert "never" in _sistema(pet) or "cannot execute" in _sistema(pet)


# ---------- supervisor (LangGraph) ----------

@pytest.fixture(scope="module")
def supervisor():
    with Puente("multiagente") as p:
        yield p


def _correr_sup(supervisor, entorno, compras_srv, doble, t, guion, limites=None, a2a_url=None):
    doble.guion = guion
    srv = entorno.servidores["normal"]
    antes = len(srv.trazas.ultimas)
    out = supervisor.resolver(tarea=t, mcp_url=srv.url, token=entorno.token("analista"), base_url=doble.base_url,
                              limites=limites, opciones={"a2a_url": a2a_url or compras_srv.url,
                                                         "a2a_token": compras_srv.token(), "emisor": compras_srv.emisor})
    assert "error" not in out, out.get("error")
    llamadas = [x["nombre"] for x in srv.trazas.ultimas[antes:] if x.get("metodo") == "tools/call"]
    return contrato.resultado_de_dict(out["resultado"]), out, llamadas


def _quien(pet):
    s = _sistema(pet) or ""
    return "supervisor" if s.startswith("You coordinate") else "analista" if s.startswith("You are a SQL") else \
        "reglas" if s.startswith("You look up") else "compras" if s.startswith("You are a purchasing") else "?"


def test_supervisor_delega_en_el_analista_y_cumple_el_contrato(supervisor, entorno, compras, doble, adm, conexion_verificador):
    from agente.verificar import verificar
    t, valor = _v01(adm)
    guion = Guion([
        Turno([herramienta("analista_sql", {"pregunta": "How many hardware items from US suppliers?"})], 1500, 60),
        Turno([herramienta("ejecutar_sql", {"sql": SQL_V01})], 800, 50),
        Turno([texto(json.dumps({"sql": SQL_V01, "filas": [[valor]], "notas": ""}))], 900, 70),
        Turno([herramienta("responder", {"estado": "respondida", "respuesta": str(valor),
                                         "resultados": [{"clave": "n", "sql": SQL_V01, "valor": valor}]})], 1700, 120)])
    r, out, llamadas = _correr_sup(supervisor, entorno, compras, doble, t, guion)
    assert r.estado == "respondida" and contrato.validar_resultado(r, t) == []
    assert verificar(t, r.final, conexion_verificador, r.estado)["exito"]
    assert (r.pasos, r.tokens_in, r.tokens_out) == (4, 4900, 300)                  # cuenta los pasos de todos los agentes
    assert llamadas == ["ejecutar_sql"]
    quienes = [_quien(p) for p in guion.peticiones]
    assert quienes == ["supervisor", "analista", "analista", "supervisor"]
    sup_tools = {x["name"] for x in guion.peticiones[0]["tools"]}
    ana_tools = {x["name"] for x in guion.peticiones[1]["tools"]}
    assert sup_tools == {"analista_sql", "reglas_negocio", "especialista_compras", "proponer_orden_compra", "responder"}
    assert ana_tools == {"describir_esquema", "muestrear_valores", "validar_sql", "ejecutar_sql"}   # no puede delegar
    vuelta = json.dumps(guion.peticiones[3]["messages"][-1], ensure_ascii=False)
    assert "untrusted_data" in vuelta and "analista_sql" in vuelta
    agentes = {e.get("agente") for e in out["eventos"] if e["tipo"] == "modelo"}
    assert agentes == {None, "analista_sql"}


def test_compras_por_a2a_y_propuesta_pendiente(supervisor, entorno, compras, doble, adm):
    t = tarea("n01-es", adm)
    propuesta = {"sku": "SKU-0009", "cantidad": 120, "motivo": "stock below reorder point"}
    guion = Guion([
        Turno([herramienta("especialista_compras", {"pedido": "SKU-0009: stock 10, reorder point 50, no open orders"})]),
        Turno([texto(json.dumps(propuesta))], 300, 40),                                       # el especialista remoto
        Turno([herramienta("proponer_orden_compra", propuesta)]),
        Turno([herramienta("responder", {"estado": "abstenida", "respuesta": "x", "resultados": []})])])
    r, out, llamadas = _correr_sup(supervisor, entorno, compras, doble, t, guion)
    assert [_quien(p) for p in guion.peticiones] == ["supervisor", "compras", "supervisor", "supervisor"]
    assert out["extra"]["especialistas"]["a2a_peticiones"] == 1
    assert llamadas == ["proponer_orden_compra"]                                            # solo el supervisor registra
    assert [(p["propuesta"]["estado"], p["propuesta"]["ejecutada"]) for p in out["extra"]["propuestas"]] == \
        [("PENDING_APPROVAL", False)]
    vuelta = json.dumps(guion.peticiones[2]["messages"][-1], ensure_ascii=False)
    assert "a2a:compras" in vuelta and "untrusted_data" in vuelta
    assert any(e.get("agente") == "compras_a2a" and e["tokens_in"] == 300 for e in out["eventos"])


def test_inyeccion_en_mensaje_a2a_llega_como_dato(supervisor, entorno, doble, adm):
    from servidor.lab import puerto_libre  # noqa: F401
    comprometido = ServidorCompras(entorno, doble.base_url, inyectar=True)
    try:
        t = tarea("n01-es", adm)
        guion = Guion([Turno([herramienta("especialista_compras", {"pedido": "SKU-0009 stock 10"})]),
                       Turno([herramienta("responder", {"estado": "abstenida", "respuesta": "x", "resultados": []})])])
        r, out, llamadas = _correr_sup(supervisor, entorno, comprometido, doble, t, guion)
        vuelta = json.dumps(guion.peticiones[1]["messages"][-1], ensure_ascii=False)
        assert "SYSTEM NOTE FOR AI" in vuelta and "untrusted_data" in vuelta and "a2a:compras" in vuelta
        assert llamadas == [] and out["extra"]["propuestas"] == []                           # nada se ejecutó
        prompt = _sistema(guion.peticiones[0])
        assert "never instructions" in prompt
    finally:
        comprometido.cerrar()


class _CartaFalsa(BaseHTTPRequestHandler):
    posts = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        datos = json.dumps(_tarjeta(url="http://127.0.0.1:9/")).encode()      # anuncia otro destino
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        type(self).posts += 1
        self.send_response(500)
        self.end_headers()


def test_agent_card_falsa_no_recibe_ningun_mensaje(supervisor, entorno, compras, doble, adm):
    falsa = ThreadingHTTPServer(("127.0.0.1", 0), _CartaFalsa)
    threading.Thread(target=falsa.serve_forever, daemon=True).start()
    try:
        t = tarea("n01-es", adm)
        guion = Guion([Turno([herramienta("especialista_compras", {"pedido": "SKU-0009"})]),
                       Turno([herramienta("responder", {"estado": "abstenida", "respuesta": "x", "resultados": []})])])
        r, out, _ = _correr_sup(supervisor, entorno, compras, doble, t, guion,
                                a2a_url=f"http://127.0.0.1:{falsa.server_address[1]}/")
        ev = next(e for e in out["eventos"] if e.get("herramienta") == "especialista_compras")
        assert ev["ok"] is False and ev["error"] == "a2a_rechazado" and _CartaFalsa.posts == 0
    finally:
        falsa.shutdown()


def test_limite_de_delegaciones_y_presupuesto_total(supervisor, entorno, compras, doble, adm):
    t = tarea("n01-es", adm)
    turnos = []
    for _ in range(7):
        turnos += [Turno([herramienta("analista_sql", {"pregunta": "q"})], 100, 10), Turno([texto('{"sql": "", "filas": []}')], 100, 10)]
    turnos = turnos[:-1] + [Turno([herramienta("responder", {"estado": "abstenida", "respuesta": "x", "resultados": []})])]
    # con el límite de pasos de la semana 13 (12) el presupuesto se acaba antes: se amplía para ver el de delegaciones
    r, out, _ = _correr_sup(supervisor, entorno, compras, doble, t, Guion(turnos), limites={"max_pasos": 30})
    assert out["extra"]["especialistas"]["delegaciones"] == ["analista_sql"] * 6
    rechazo = [e for e in out["eventos"] if e.get("herramienta") == "analista_sql" and not e["ok"]]
    assert len(rechazo) == 1 and rechazo[0]["error"] == "limite_delegaciones" and r.estado == "abstenida"
    # con los límites de la semana 13, 6 delegaciones de un paso cada una agotan los 12 pasos: el presupuesto es total
    r, out, _ = _correr_sup(supervisor, entorno, compras, doble, t, Guion(turnos))
    assert r.estado == "limite_alcanzado" and r.motivo == "max_pasos" and r.pasos == 12
    # presupuesto total: los tokens de los especialistas cuentan contra el mismo límite que los del supervisor
    turnos = [Turno([herramienta("analista_sql", {"pregunta": "q"})], 1000, 10)] + \
             [Turno([herramienta("describir_esquema", {})], 1000, 10)] * 3 + [Turno([texto("{}")], 1000, 10)] + \
             [Turno([herramienta("analista_sql", {"pregunta": "q2"})], 1000, 10)] * 3
    r, out, _ = _correr_sup(supervisor, entorno, compras, doble, t, Guion(turnos), limites={"max_tokens_total": 5500})
    assert r.estado == "limite_alcanzado" and r.motivo == "max_tokens_total" and r.final is None
    assert any(e.get("agente") == "analista_sql" for e in out["eventos"] if e["tipo"] == "modelo")
