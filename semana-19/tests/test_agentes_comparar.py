"""Week 19, activity 7: the comparison script, offline (no AWS: every client is a fake)."""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import cliente_gateway as G  # noqa: E402
from agentes import comparar as C  # noqa: E402
from comun.redaccion import redactar  # noqa: E402

SQL_OK = "SELECT art_cd FROM legado.artmst WHERE art_cd = 'SKU-0009'"


def tarea(id_="t1", esperado=(("SKU-0009",),)):
    return {"id": id_, "tarea": "¿Qué SKU?", "estado_esperado": "respondida",
            "salida": {"filas": {"tipo": "filas", "descripcion": "lo pedido", "orden": False,
                                 "esperado": [list(f) for f in esperado]}}}


# ---------------------------------------------------------------- tasks, caps, simulation

def test_diez_tareas_en_espanol_con_una_clave_en_orden_del_archivo():
    ts = C.seleccionar_tareas()
    assert len(ts) == 10 and all(t["lang"] == "es" and t["estado_esperado"] == "respondida" for t in ts)
    assert all(len(t["salida"]) == 1 for t in ts)
    assert [t["id"] for t in ts] == sorted((t["id"] for t in ts), key=[t["id"] for t in ts].index)
    assert ts[0]["id"] == "s01-es"


def test_topes_en_el_codigo():
    assert (C.TOPE_USD, C.TOPE_TOKENS) == (1.20, 500_000)


def test_el_tope_reserva_el_limite_de_una_tarea_antes_de_empezarla():
    lim = C.limite_de_tarea()
    t = C.Tope(usd=lim.usd * 2, tokens=10**9)
    assert t.cabe_otra()
    t.sumar(lim.usd * 1.01, 0)
    assert not t.cabe_otra()
    t = C.Tope(usd=10, tokens=lim.tokens)
    assert t.cabe_otra()
    t.sumar(0, 1)
    assert not t.cabe_otra()


def test_el_tope_descuenta_lo_que_gastaron_los_otros_caminos(tmp_path):
    (tmp_path / "crudo_directo.json").write_text(json.dumps({"gasto": {"usd": 0.3, "tokens": 120_000}}))
    (tmp_path / "crudo_agentes.json").write_text(json.dumps({"gasto": {"usd": 0.5, "tokens": 9}}))
    t = C.tope_con_lo_previo(tmp_path, excepto="agentes")
    assert (t.gastado_usd, t.gastado_tokens) == (0.3, 120_000)


def test_correr_camino_se_detiene_en_el_tope_y_lo_registra():
    lim = C.limite_de_tarea()
    medidas = []

    def medir(t):
        medidas.append(t["id"])
        return {"id_tarea": t["id"], "estado": "respondida", "costo_usd": lim.usd, "tokens_entrada": 10,
                "tokens_salida": 1, "resultados": []}

    datos = C.correr_camino("directo", [tarea("a"), tarea("b"), tarea("c")], medir=medir, ejecutar_sql=None,
                           tope=C.Tope(usd=lim.usd * 2, tokens=10**9),
                           verificador=lambda *a: {"exito": False})
    assert medidas == ["a", "b"] and datos["filas"][2] == {"id_tarea": "c", "camino": "directo", "estado": "no_corrida",
                                                           "motivo": "tope_del_script"}
    assert datos["gasto"] == {"usd": round(lim.usd * 2, 6), "tokens": 22} and datos["resumen"]["corridas"] == 2


@pytest.mark.parametrize("args", [[], ["--camino", "directo"], ["--camino", "agentes"], ["--politica"]])
def test_por_omision_simula_y_no_llama_a_aws(monkeypatch, capsys, args):
    monkeypatch.setattr(C, "Aws", lambda *a, **k: pytest.fail("la simulación no crea clientes"))
    assert C.main(args) == 0
    salida = capsys.readouterr().out
    assert '"simulacion": true' in salida and "--si" in salida


# ---------------------------------------------------------------- week 13's verifier over the tools function

def test_el_verificador_de_la_semana_13_reejecuta_la_consulta_por_la_funcion():
    vistas = []

    def ejecutar(sql):
        vistas.append(sql)
        return {"filas": [["SKU-0009"]], "truncado": False, "limite": 200}

    v = C.verificar(tarea(), "respondida", [{"clave": "filas", "sql": SQL_OK, "valor": [["SKU-0009"]]}], ejecutar)
    assert v["exito"] is True and v["claves"]["filas"]["exacta"] and v["claves"]["filas"]["coherente"]
    assert vistas == [SQL_OK]


def test_filas_distintas_o_sin_clave_no_son_exito():
    distinto = C.verificar(tarea(), "respondida", [{"clave": "filas", "sql": SQL_OK, "valor": "x"}],
                           lambda sql: {"filas": [["SKU-0001"]], "truncado": False})
    assert distinto["exito"] is False and distinto["claves"]["filas"]["exacta"] is False
    sin_clave = C.verificar(tarea(), "respondida", [], lambda sql: pytest.fail("no hay SQL que correr"))
    assert sin_clave["exito"] is False and sin_clave["claves"]["filas"]["reportada"] is False
    otro_estado = C.verificar(tarea(), "limite_alcanzado", [], lambda sql: {})
    assert otro_estado["estado_ok"] is False


@pytest.mark.parametrize("respuesta", [{"error": "write_blocked", "mensaje": "x"}, {"filas": [["a"]], "truncado": True}])
def test_un_error_o_un_resultado_truncado_cuenta_como_no_exacto(respuesta):
    v = C.verificar(tarea(), "respondida", [{"clave": "filas", "sql": SQL_OK, "valor": "x"}], lambda sql: respuesta)
    assert v["exito"] is False and v["claves"]["filas"]["error"]


def test_la_guardia_de_la_semana_13_rechaza_una_escritura_sin_llamar_a_la_funcion():
    v = C.verificar(tarea(), "respondida", [{"clave": "filas", "sql": "DELETE FROM legado.artmst", "valor": 1}],
                    lambda sql: pytest.fail("la guardia corre antes"))
    assert v["exito"] is False and v["claves"]["filas"]["error"]


# ---------------------------------------------------------------- paths (a) and (b)

class Http:
    def __init__(self, id_consulta="0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", final=None):
        self.id, self.pedidos, self.gets = id_consulta, [], 0
        self.final = final or {"id": id_consulta, "estado": "respondida", "respuesta": "SKU-0009",
                               "decisiones": [{"accion": "allow"}, {"accion": "block"}],
                               "resultados": [{"clave": "filas", "sql": SQL_OK, "valor": [["SKU-0009"]]}]}

    def __call__(self, metodo, ruta, token, cuerpo):
        self.pedidos.append((metodo, ruta, token, cuerpo))
        if metodo == "POST":
            return 202, {"id": self.id, "estado": "en_curso"}
        self.gets += 1
        return (200, {"id": self.id, "estado": "en_curso"}) if self.gets < 3 else (200, self.final)


def spans(run_id="0f1e2d3c4b5a", tipo="extension", error=None):
    herramienta = {"gen_ai.tool.type": tipo, "lab.tool.status": "error" if error else "ok"}
    if error:
        herramienta["error.type"] = error
    return [{"tipo": "execute_tool", "attrs": herramienta},
            {"tipo": "invoke_agent", "attrs": {"lab.run.id": run_id, "lab.run.tokens.input": 1000,
                                               "lab.run.tokens.output": 100, "lab.run.cost_usd": 0.0016,
                                               "lab.run.steps": 3, "lab.run.tool_calls": 1, "lab.run.tool_errors": 0,
                                               "lab.outcome.reason": "responder"}}]


def test_medir_api_sondea_hasta_la_respuesta_y_lee_sus_spans():
    http, reloj = Http(), iter(range(0, 100))
    ventanas = []
    f = C.medir_api(tarea(), "gateway", token="tok", http=http, reloj=lambda: next(reloj), dormir=lambda s: None,
                    spans_entre=lambda a, b: ventanas.append((a, b)) or spans(error="rechazada_por_el_gateway"))
    assert http.pedidos[0] == ("POST", "/consultas", "tok", {"pregunta": C.texto_de_la_tarea(tarea())}) and http.gets == 3
    assert f["estado"] == "respondida" and f["latencia_s"] > 0 and f["spans_completos"]
    assert (f["tokens_entrada"], f["tokens_salida"], f["costo_usd"], f["pasos"], f["herramientas"]) == (1000, 100, 0.0016, 3, 1)
    assert f["tipos_de_herramienta"] == ["extension"] and f["bloqueos_politica"] == 1 and f["bloqueos_capa"] == 1
    assert f["resultados"][0]["sql"] == SQL_OK
    assert ventanas[0][1] > ventanas[0][0]


def test_la_tarea_va_como_la_arma_la_semana_13_con_sus_claves():
    texto = C.texto_de_la_tarea(tarea())
    assert texto.startswith("¿Qué SKU?") and "- filas: lo pedido (filas)" in texto
    assert all(len(C.texto_de_la_tarea(t)) <= 1000 for t in C.seleccionar_tareas())   # the API's MAX_PREGUNTA


def test_los_spans_tardios_se_reintentan_y_la_espera_es_acotada():
    llamadas, esperas = [], []

    def tardios(a, b):
        llamadas.append(1)
        return spans() if len(llamadas) == 3 else []

    f = C.medir_api(tarea(), "directo", token="t", http=Http(), dormir=esperas.append, spans_entre=tardios)
    assert f["spans_completos"] and f["tokens_entrada"] == 1000 and len(llamadas) == 3
    nunca = []
    f = C.medir_api(tarea(), "directo", token="t", http=Http(), dormir=lambda s: None,
                    spans_entre=lambda a, b: nunca.append(1) or [])
    assert f["spans_completos"] is False and len(nunca) == C.INTENTOS_SPANS


def test_una_corrida_repetida_conserva_la_previa_y_su_gasto_cuenta(tmp_path):
    (tmp_path / "crudo_directo.json").write_text(json.dumps({"gasto": {"usd": 0.16, "tokens": 110_000}}))
    (tmp_path / "crudo_gateway.json").write_text(json.dumps({"gasto": {"usd": 0.2, "tokens": 5}}))
    assert C.descartar_previa("directo", tmp_path).name == "crudo_directo_descartada_1.json"
    assert not (tmp_path / "crudo_directo.json").exists() and C.descartar_previa("directo", tmp_path) is None
    t = C.tope_con_lo_previo(tmp_path, excepto="directo")
    assert (round(t.gastado_usd, 2), t.gastado_tokens) == (0.36, 110_005)
    (tmp_path / "crudo_directo.json").write_text(json.dumps({"gasto": {"usd": 0.1, "tokens": 1}}))
    assert C.descartar_previa("directo", tmp_path).name == "crudo_directo_descartada_2.json"


def test_spans_de_otra_consulta_no_se_atribuyen():
    f = C.medir_api(tarea(), "directo", token="t", http=Http(), dormir=lambda s: None,
                    spans_entre=lambda a, b: spans(run_id="ffffffffffff"))
    assert f["spans_completos"] is False and f["tokens_entrada"] == 0


def test_un_post_rechazado_es_error_de_api():
    f = C.medir_api(tarea(), "directo", token="t", http=lambda *a: (401, {}), spans_entre=lambda a, b: [])
    assert f["estado"] == "error_api" and f["http"] == 401


# ---------------------------------------------------------------- path (c)

def traza(*partes):
    return [{"trace": {"trace": p}} for p in partes]


def eventos_agentes(tokens=(800, 50)):
    return [
        *traza({"orchestrationTrace": {"modelInvocationInput": {}}},
               {"orchestrationTrace": {"modelInvocationOutput": {"metadata": {"usage": {
                   "inputTokens": tokens[0], "outputTokens": tokens[1]}}}}},
               {"orchestrationTrace": {"invocationInput": {"actionGroupInvocationInput": {
                   "actionGroupName": "herramientas", "function": "ejecutar_sql",
                   "parameters": [{"name": "sql", "type": "string", "value": "SELECT 1 FROM legado.artmst"}]}}}},
               {"orchestrationTrace": {"observation": {"actionGroupInvocationOutput": {"text": '{"error": "x"}'}}}},
               {"orchestrationTrace": {"invocationInput": {"actionGroupInvocationInput": {
                   "function": "ejecutar_sql", "parameters": [{"name": "sql", "value": SQL_OK}]}}}},
               {"orchestrationTrace": {"observation": {"actionGroupInvocationOutput": {"text": '{"filas": [["SKU-0009"]]}'}}}},
               {"orchestrationTrace": {"modelInvocationInput": {}}},
               {"guardrailTrace": {"action": "NONE"}}),
        {"chunk": {"bytes": "Es el ".encode()}}, {"chunk": {"bytes": "SKU-0009.".encode()}}]


def test_la_traza_de_bedrock_agents_da_pasos_herramientas_tokens_y_la_ultima_consulta_valida():
    tr = C.leer_traza(eventos_agentes(), limite_tokens=10**6)
    assert tr["texto"] == "Es el SKU-0009." and tr["pasos"] == 2 and tr["llamadas"] == ["ejecutar_sql", "ejecutar_sql"]
    assert tr["consultas_ok"] == [SQL_OK] and (tr["tokens_entrada"], tr["tokens_salida"]) == (800, 50)
    assert tr["intervenciones"] == 0 and tr["cortada"] is False


def test_la_traza_cuenta_las_intervenciones_del_guardrail_y_corta_sobre_el_limite():
    tr = C.leer_traza(traza({"guardrailTrace": {"action": "INTERVENED"}}) + eventos_agentes(), limite_tokens=100)
    assert tr["intervenciones"] == 1 and tr["cortada"] is True and tr["texto"] == ""


def test_medir_agentes_pasa_el_solicitante_en_la_sesion_y_reporta_la_consulta():
    vistos = {}

    def invocar(*, sesion, texto, atributos):
        vistos.update(sesion=sesion, texto=texto, atributos=atributos)
        return eventos_agentes()

    f = C.medir_agentes(tarea(), invocar=invocar, solicitante="sub-analista")
    assert vistos["atributos"] == {"solicitante": "sub-analista"} and len(vistos["sesion"]) == 32
    assert vistos["texto"] == C.texto_de_la_tarea(tarea())
    assert f["estado"] == "respondida" and f["resultados"] == [{"clave": "filas", "sql": SQL_OK, "valor": "Es el SKU-0009."}]
    assert f["herramientas"] == 2 and f["errores_herramienta"] == 1 and f["costo_usd"] == C.costo(800, 50)


def test_sin_consulta_valida_no_hay_resultado_que_verificar():
    f = C.medir_agentes(tarea(), invocar=lambda **k: [{"chunk": {"bytes": b"no se"}}], solicitante="s")
    assert f["estado"] == "sin_consulta" and f["resultados"] == []


# ---------------------------------------------------------------- aggregation

def test_percentil_de_rango_cercano():
    v = [float(i) for i in range(1, 11)]
    assert C.percentil(v, 50) == 5.0 and C.percentil(v, 95) == 10.0 and C.percentil([], 50) is None


def test_resumir_cuenta_exito_costo_y_bloqueos():
    filas = [{"estado": "respondida", "verificacion": {"exito": True}, "latencia_s": 2.0, "tokens_entrada": 10,
              "tokens_salida": 1, "costo_usd": 0.1, "pasos": 2, "herramientas": 1, "bloqueos_guardrail": 1,
              "bloqueos_capa": 0, "bloqueos_politica": 0},
             {"estado": "respondida", "verificacion": {"exito": False}, "latencia_s": 4.0, "costo_usd": 0.2,
              "pasos": 4, "herramientas": 3},
             {"estado": "no_corrida"}]
    r = C.resumir(filas)
    assert (r["tareas"], r["corridas"], r["exito"], r["tasa_exito"]) == (3, 2, 1, 0.5)
    assert (r["latencia_p50_s"], r["latencia_p95_s"], r["tokens"], r["costo_usd"]) == (2.0, 4.0, 11, 0.3)
    assert (r["pasos_promedio"], r["herramientas_promedio"], r["bloqueos_guardrail"]) == (3.0, 2.0, 1)


# ---------------------------------------------------------------- the live Policy test

def test_la_prueba_de_la_politica_cubre_negado_permitido_y_solicitante_ajeno():
    llamadas = []
    permitidos = {("comprador", "sub-c")}

    def llamar(usuario, solicitante):
        llamadas.append((usuario, solicitante))
        if (usuario, solicitante) in permitidos:
            return {"paso": True, "error_herramienta": "cedis_desconocido"}
        return {"paso": False, "codigo": -32002}

    filas = C.probar_politica(llamar, lambda u: ["herramientas___ejecutar_sql"] + (
        ["herramientas___proponer_orden_compra"] if u == "comprador" else []),
        {"analista": "sub-a", "comprador": "sub-c", "aprobador": "sub-p"})
    decisiones = [f for f in filas if "ok" in f]
    assert all(f["ok"] for f in decisiones) and len(decisiones) == 4
    assert llamadas == [("analista", "sub-a"), ("comprador", "sub-c"), ("aprobador", "sub-p"), ("comprador", "sub-a")]
    assert [f["ve_proponer"] for f in filas if "ve_proponer" in f] == [False, True, False]
    assert C.PROPUESTA_DE_PRUEBA["cedis"] == 99999   # refused by the tool before any workflow starts


class SesionPolitica:
    def __init__(self, resultado=None, error=None, nombres=()):
        self.resultado, self.error, self.nombres, self.llamadas = resultado, error, nombres, []

    def abrir(self):
        @contextlib.asynccontextmanager
        async def cm():
            yield self
        return cm()

    async def call_tool(self, nombre, argumentos):
        self.llamadas.append((nombre, argumentos))
        if self.error:
            raise self.error
        return self.resultado

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in self.nombres])


def test_probar_como_distingue_el_rechazo_del_gateway_de_la_respuesta_de_la_herramienta():
    from mcp.shared.exceptions import MCPError
    negado = G.probar_como("u", "t", {"a": 1}, abrir=SesionPolitica(error=MCPError(-32002, "detalle")).abrir)
    assert negado == {"paso": False, "forma": "jsonrpc", "codigo": -32002, "error_herramienta": None}
    s = SesionPolitica(resultado=SimpleNamespace(content=[SimpleNamespace(text='{"error": "cedis_desconocido"}')],
                                                 is_error=False))
    assert G.probar_como("u", "t", {"a": 1}, abrir=s.abrir)["paso"] is True
    assert s.llamadas == [("herramientas___proponer_orden_compra", {"a": 1})]
    sin_json = SesionPolitica(resultado=SimpleNamespace(content=[SimpleNamespace(text="Not authorized")], is_error=True))
    assert G.probar_como("u", "t", {}, abrir=sin_json.abrir)["paso"] is False


def test_listar_como_devuelve_los_nombres_que_ve_el_usuario():
    s = SesionPolitica(nombres=["herramientas___ejecutar_sql"])
    assert G.listar_como("u", "t", abrir=s.abrir) == ["herramientas___ejecutar_sql"]


def test_claims_sin_verificar_y_token_mal_formado():
    import base64
    carga = base64.urlsafe_b64encode(json.dumps({"sub": "s", "exp": 5}).encode()).rstrip(b"=").decode()
    assert G.claims(f"h.{carga}.f") == {"sub": "s", "exp": 5} and G.expiracion(f"h.{carga}.f") == 5
    assert G.claims("no-es-jwt") == {} and G.expiracion("x") is None


# ---------------------------------------------------------------- redaction

def test_redactar_cuenta_token_home_y_correo_sin_tocar_otros_numeros():
    home = str(Path.home())
    datos = {"arn": "arn:aws:lambda:us-east-1:123456789012:function:x", "suelto": "cuenta 123456789012",
             "dato": "folio 999999999999", "ruta": f"{home}/s19", "token": "eyJhbGciOi.eyJzdWIiOiJ4In0.firma",
             "correo": "alguien" + chr(64) + "ejemplo.invalid", "n": 7}
    r = redactar(datos, ["123456789012"])
    assert r == {"arn": "arn:aws:lambda:us-east-1:<account>:function:x", "suelto": "cuenta <account>",
                 "dato": "folio 999999999999", "ruta": "~/s19", "token": "<token>", "correo": "<correo>", "n": 7}


def test_los_archivos_del_script_salen_redactados(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "SALIDA", tmp_path)
    archivo = C._escribir("x.json", {"t": "eyJhbGciOi.eyJzdWIiOiJ4In0.firma", "a": "arn:aws:iam::123456789012:role/r"})
    texto = archivo.read_text()
    assert "<token>" in texto and "<account>" in texto and "123456789012" not in texto
