"""Activity 3 (LegacyBridge instrumented end to end), no API ($0): the model is scripted, everything else is real.

Real: the week 13 agent loop, the week 14 MCP client, a Streamable HTTP server behind the OAuth boundary (lab issuer,
RS256 tokens), PostgreSQL with the legacy schema, the MCP SDK's own spans, and the Collector's real processors.
Scripted: the model (`instrumentacion/modelo_guionado.py`); its `usage` numbers are inputs the spans must add up to.

One module-scoped bench runs seven scenarios once; the tests read what the spans recorded."""
import copy
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import Laboratorio, configurar_trazas, resumen  # noqa: E402
from instrumentacion.modelo_guionado import (  # noqa: E402
    SQL_BAJO_PUNTO_DE_REORDEN,
    TAREA,
    turnos_con_error_de_sql,
    turnos_herramienta_inventada,
    turnos_principal,
    turnos_sin_permiso,
)
from instrumentacion.trazas_cliente import ClienteSeguro  # noqa: E402

SAL = "sal-de-prueba-actividad-3"
CANARIOS = {
    "email": "ana.garcia@example.com", "rfc": "XAXX010101000", "telefono": "55 1234 5678",
    "literal_sql": "CANARIO-SQL-77", "motivo": "canario-motivo-de-compra", "prompt": "CANARIO-PROMPT-ZETA",
    "dsn": "postgresql://canario:secreto@db.example/inventory", "clave_api": "sk-ant-api03-CANARIOABCDEFGH",
}
TAREA_CON_CANARIOS = {**TAREA, "tarea": f"{TAREA['tarea']} Customer {CANARIOS['email']}, tax id {CANARIOS['rfc']}, "
                                         f"phone {CANARIOS['telefono']}. {CANARIOS['prompt']}"}
SQL_CON_CANARIO = SQL_BAJO_PUNTO_DE_REORDEN.replace(
    "ORDER BY", f"AND a.art_cd <> '{CANARIOS['literal_sql']}' ORDER BY", 1)
RAIZ_NOMBRE = "invoke_agent legacybridge"


def _estable(exp, minimo_ms=400):
    """Server spans end in another thread: wait until the number of finished spans stops growing."""
    n, t0 = -1, time.time()
    while time.time() - t0 < 10:
        actual = len(exp.get_finished_spans())
        if actual == n:
            return
        n = actual
        time.sleep(minimo_ms / 1000)


@pytest.fixture(scope="module")
def banco():
    mp = pytest.MonkeyPatch()
    mp.setenv("LAB_OBS_SALT", SAL)
    mp.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT")
    E.ESTRICTO = True
    exp = configurar_trazas()
    lab = Laboratorio(tenant="lab")
    banco = {"escenarios": {}, "lab": lab}
    try:
        def correr(nombre, turnos, **kw):
            exp.clear()
            r, modelo, cliente = lab.correr(turnos, **kw)
            _estable(exp)
            crudos = list(exp.get_finished_spans())
            banco["escenarios"][nombre] = {"resultado": r, "modelo": modelo, "cliente": cliente, "crudos": crudos,
                                           "spans": resumen(crudos)}

        correr("principal", turnos_principal(sql=SQL_CON_CANARIO), tarea=TAREA_CON_CANARIOS)
        correr("error_sql", turnos_con_error_de_sql())
        correr("sin_permiso", turnos_sin_permiso(motivo=CANARIOS["motivo"]), usuario="almacenista",
               catalogo_obsoleto={"legado__proponer_orden_compra": ("legado", "proponer_orden_compra")})
        correr("sin_ver_la_herramienta", turnos_sin_permiso(), usuario="almacenista")
        correr("api_falla", turnos_principal(), modelo_falla=1,
               mensaje_de_falla=f"boom {CANARIOS['dsn']} {CANARIOS['clave_api']} {CANARIOS['email']}")
        correr("inventada", turnos_herramienta_inventada(f"legado__{CANARIOS['email']}"))
        correr("control_sin_contexto", turnos_principal(), cliente_clase=ClienteSeguro)
        mp.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_ONLY")
        correr("captura_span_only", turnos_principal(sql=SQL_CON_CANARIO), tarea=TAREA_CON_CANARIOS)
        mp.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT")
        banco["registros_frontera"] = list(lab.entorno.servidores["normal"].trazas.ultimas)
        banco["tokens"] = list(lab.entorno._tokens.values())
        yield banco
    finally:
        lab.cerrar()
        E.ESTRICTO = False
        mp.undo()


def de(banco, nombre):
    return banco["escenarios"][nombre]


def raiz_de(spans):
    return next(s for s in spans if s["name"] == RAIZ_NOMBRE)


def tarea_de(spans):
    """The spans of the task's trace (the discovery spans of the MCP session open are separate traces)."""
    t = raiz_de(spans)["trace"]
    return [s for s in spans if s["trace"] == t]


def hijos(spans, padre):
    return sorted((s for s in spans if s["parent"] == padre["span"]), key=lambda s: s["inicio"])


def arbol(spans, nodo):
    return (nodo["name"], [arbol(spans, h) for h in hijos(spans, nodo)])


def categoria(nombre: str) -> str | None:
    if nombre.startswith("invoke_agent "):
        return "invoke_agent"
    if nombre.startswith("chat "):
        return "chat"
    if nombre.startswith("execute_tool "):
        return "execute_tool"
    if nombre == "authorize":
        return "autorizacion"
    if nombre.startswith("handle_tool "):
        return "herramienta_servidor"
    if nombre.startswith(("SELECT ", "EXPLAIN ")):
        return "sql"
    if nombre.startswith("MCP send "):
        return "mcp_cliente"
    if nombre.startswith(("tools/", "resources/", "prompts/", "server/")):
        return "mcp_servidor"
    return None


# ---------- plan bullet: the span tree matches the locked schema ----------

def test_la_forma_del_arbol_coincide_con_el_esquema_fijado(banco):
    spans = tarea_de(de(banco, "principal")["spans"])
    esperado = (RAIZ_NOMBRE, [
        ("chat claude-haiku-5-5", []),
        ("execute_tool legado__describir_esquema", [("MCP send tools/call describir_esquema", [
            ("authorize", []),
            ("tools/call describir_esquema", [("handle_tool describir_esquema", [])])])]),
        ("chat claude-haiku-5-5", []),
        ("execute_tool legado__ejecutar_sql", [("MCP send tools/call ejecutar_sql", [
            ("authorize", []),
            ("tools/call ejecutar_sql", [("handle_tool ejecutar_sql", [("SELECT legado", [])])])])]),
        ("chat claude-haiku-5-5", []),
    ])

    def ordenar(a):   # authorize and the SDK server span start within microseconds: compare as sorted children
        return (a[0], sorted(map(ordenar, a[1])))
    assert ordenar(arbol(spans, raiz_de(spans))) == ordenar(esperado)
    tipos = {s["name"].split(" ")[0]: s["kind"] for s in spans}
    assert tipos["invoke_agent"] == "INTERNAL" and tipos["chat"] == "CLIENT" and tipos["execute_tool"] == "INTERNAL"
    assert tipos["MCP"] == "CLIENT" and tipos["tools/call"] == "SERVER" and tipos["SELECT"] == "CLIENT"
    assert tipos["authorize"] == "INTERNAL" and tipos["handle_tool"] == "INTERNAL"


def test_el_agente_registra_tarea_idioma_tenant_usuario_presupuesto_y_resultado(banco):
    d = de(banco, "principal")
    a = raiz_de(d["spans"])["attrs"]
    assert (a["gen_ai.operation.name"], a["gen_ai.agent.name"], a["gen_ai.request.model"]) == (
        "invoke_agent", "legacybridge", "claude-haiku-5-5")
    assert (a["lab.task.id"], a["lab.task.language"], a["lab.tenant.id"]) == ("s01-en", "en", "lab")
    assert a["user.id"] == E.seudonimo("sub-analista") and "analista" not in json.dumps(a)
    assert (a["lab.budget.max_steps"], a["lab.budget.max_tool_calls"], a["lab.budget.max_tokens_total"],
            a["lab.budget.max_seconds"], a["lab.budget.max_output_tokens"]) == (12, 30, 200_000, 180.0, 4000)
    assert (a["lab.outcome.status"], a["lab.outcome.reason"]) == ("respondida", "responder")
    assert a["lab.run.id"] == d["resultado"].corrida and a["lab.schema.version"] == "1" and a["lab.model.scripted"] is True


def test_cada_llamada_al_modelo_registra_tokens_con_cache_costo_y_latencia(banco):
    d = de(banco, "principal")
    chats = [s for s in tarea_de(d["spans"]) if s["name"].startswith("chat ")]
    assert [c["attrs"]["lab.step"] for c in sorted(chats, key=lambda s: s["inicio"])] == [1, 2, 3]
    primero = min(chats, key=lambda s: s["inicio"])["attrs"]
    # the scripted usage was input 1180 + cache creation 800: the span reports the TOTAL input, as OTel defines it
    assert primero["gen_ai.usage.input_tokens"] == 1180 + 800 and primero["gen_ai.usage.output_tokens"] == 64
    assert primero["gen_ai.usage.cache_creation.input_tokens"] == 800 and "gen_ai.usage.cache_read.input_tokens" not in primero
    ultimo = max(chats, key=lambda s: s["inicio"])["attrs"]
    assert ultimo["gen_ai.usage.input_tokens"] == 380 + 800 and ultimo["gen_ai.usage.cache_read.input_tokens"] == 800
    for c in chats:
        a = c["attrs"]
        assert (a["gen_ai.provider.name"], a["gen_ai.request.model"], a["gen_ai.request.reasoning.level"]) == (
            "anthropic", "claude-haiku-5-5", "low")
        assert a["gen_ai.response.finish_reasons"] == ("tool_use",) and a["gen_ai.response.id"].startswith("msg_scripted_")
        assert a["lab.model.scripted"] is True and a["lab.cost.usd"] > 0
        assert json.loads(a["langfuse.observation.cost_details"]) == {"total": a["lab.cost.usd"]}
    # latency is the span's own duration: each `chat` lasts at least the scripted latency of its turn (0.05, 0.08, 0.06 s)
    duraciones = [(c["fin"] - c["inicio"]) / 1e9 for c in sorted(chats, key=lambda s: s["inicio"])]
    assert all(d >= m for d, m in zip(duraciones, (0.05, 0.08, 0.06))), duraciones
    assert all(d < m + 1.0 for d, m in zip(duraciones, (0.05, 0.08, 0.06))), duraciones


def test_la_llamada_a_herramienta_registra_argumentos_como_tamano_y_hash_y_estado(banco):
    d = de(banco, "principal")
    spans = tarea_de(d["spans"])
    herr = {s["name"]: s["attrs"] for s in spans if s["name"].startswith("execute_tool ")}
    esquema = herr["execute_tool legado__describir_esquema"]
    args = {"tablas": ["artmst", "exidet"]}
    assert esquema["lab.tool.args.chars"] == len(E.canonico(args)) and esquema["lab.tool.args.hmac"] == E.seudonimo(E.canonico(args))
    assert esquema["lab.tool.status"] == "ok" and esquema["lab.tool.known"] is True and esquema["lab.tool.result.chars"] > 100
    assert esquema["gen_ai.tool.call.id"] == "toolu_scripted_01_1" and esquema["gen_ai.tool.type"] == "function"
    assert herr["execute_tool legado__ejecutar_sql"]["gen_ai.tool.call.id"] == "toolu_scripted_02_1"
    # the server saw the same arguments: the keyed hash is equal on both sides of the MCP boundary
    servidor = {s["name"]: s["attrs"] for s in spans if s["name"].startswith("handle_tool ")}
    assert servidor["handle_tool describir_esquema"]["lab.tool.args.hmac"] == esquema["lab.tool.args.hmac"]
    assert servidor["handle_tool ejecutar_sql"]["lab.tool.args.hmac"] == herr["execute_tool legado__ejecutar_sql"]["lab.tool.args.hmac"]


# ---------- plan bullet: client spans carry the traceparent, server spans continue the same trace ----------

def test_los_enlaces_padre_hijo_cruzan_la_frontera_mcp(banco):
    spans = de(banco, "principal")["spans"]
    tarea = tarea_de(spans)
    por_id = {s["span"]: s for s in tarea}
    for llamada in ("describir_esquema", "ejecutar_sql"):
        cliente = next(s for s in tarea if s["name"] == f"MCP send tools/call {llamada}")
        servidor = next(s for s in tarea if s["name"] == f"tools/call {llamada}")
        autorizar = [s for s in tarea if s["name"] == "authorize" and s["parent"] == cliente["span"]]
        assert servidor["parent"] == cliente["span"] and servidor["trace"] == cliente["trace"]
        assert len(autorizar) == 1                                         # the boundary continues the trace too
        assert por_id[cliente["parent"]]["name"] == f"execute_tool legado__{llamada}"
    sql = next(s for s in tarea if s["name"] == "SELECT legado")
    assert por_id[por_id[sql["parent"]]["parent"]]["name"] == "tools/call ejecutar_sql"
    # every span of the task but the root has its parent in the same trace
    assert all(s["parent"] in por_id for s in tarea if s["span"] != raiz_de(spans)["span"])


def test_el_usuario_pseudonimo_es_el_mismo_en_el_agente_la_frontera_y_la_herramienta(banco):
    tarea = tarea_de(de(banco, "principal")["spans"])
    esperado = E.seudonimo("sub-analista")
    vistos = {s["name"]: s["attrs"]["user.id"] for s in tarea if "user.id" in s["attrs"]}
    assert set(vistos) == {RAIZ_NOMBRE, "authorize", "handle_tool describir_esquema", "handle_tool ejecutar_sql"}
    assert set(vistos.values()) == {esperado}


def test_la_decision_de_autorizacion_y_el_span_de_sql_llevan_sus_atributos(banco):
    tarea = tarea_de(de(banco, "principal")["spans"])
    autorizar = [s["attrs"] for s in tarea if s["name"] == "authorize"]
    assert {a["lab.authz.decision"] for a in autorizar} == {"allow"}
    llamada = next(a for a in autorizar if a.get("lab.tool.name") == "ejecutar_sql")
    assert llamada["mcp.method.name"] == "tools/call" and llamada["lab.authz.scopes.required"] == "legado:leer"
    assert llamada["lab.authz.scopes.granted"] == "legado:compras:proponer legado:leer legado:proveedores legado:ventas"
    sql = next(s for s in tarea if s["name"] == "SELECT legado")["attrs"]
    assert (sql["db.system.name"], sql["db.namespace"], sql["db.operation.name"]) == ("postgresql", "legado", "SELECT")
    assert sql["db.response.returned_rows"] == 5 and sql["lab.db.tables"] == "artmst exidet"
    assert sql["lab.db.query.chars"] == len(SQL_CON_CANARIO) and sql["lab.db.query.hmac"] == E.seudonimo(SQL_CON_CANARIO)
    assert sql["lab.db.role"] == "legado_perfil_lvp"


def test_cada_peticion_que_llega_a_la_frontera_tiene_su_span_authorize(banco):
    """Proves the `authorize` span covers every request, so the extra root `tools/list` spans (the SDK server calling its own
    list handler while serving a `tools/call`) are not HTTP requests."""
    autorizar = [s for e in banco["escenarios"].values() for s in e["spans"] if s["name"] == "authorize"]
    mcp = [r for r in banco["registros_frontera"] if r.get("ruta") == "/mcp" and r.get("http") == "POST"]
    assert len(autorizar) == len(mcp)
    internos = [s for e in banco["escenarios"].values() for s in e["spans"]
                if s["name"] == "tools/list" and s["parent"] is None]
    assert internos and all(s["kind"] == "SERVER" for s in internos)


def test_sin_propagar_el_contexto_el_servidor_queda_en_otra_traza(banco):
    """The week 14 client hands each call to a session thread: without `ClienteInstrumentado` the SDK client span is a root of
    another trace (finding of activity 1). This control pins why the fix exists."""
    spans = de(banco, "control_sin_contexto")["spans"]
    agente = raiz_de(spans)["trace"]
    llamadas = [s for s in spans if s["name"].startswith(("MCP send tools/call", "tools/call ", "handle_tool ", "SELECT "))]
    assert llamadas and all(s["trace"] != agente for s in llamadas)
    assert all(s["parent"] is None for s in llamadas if s["name"].startswith("MCP send"))


# ---------- plan bullet: tokens and cost add up to the run totals ----------

def test_los_tokens_y_el_costo_de_las_llamadas_suman_los_totales_de_la_corrida(banco):
    d = de(banco, "principal")
    r = d["resultado"]
    spans = tarea_de(d["spans"])
    chats = [s["attrs"] for s in spans if s["name"].startswith("chat ")]
    total = raiz_de(d["spans"])["attrs"]
    assert (r.tokens_in, r.tokens_out) == (1180 + 420 + 380, 64 + 96 + 150)          # the scripted usage
    assert sum(c["gen_ai.usage.output_tokens"] for c in chats) == total["lab.run.tokens.output"] == r.tokens_out
    entrada = sum(c["gen_ai.usage.input_tokens"] for c in chats)
    assert entrada == total["lab.run.tokens.input"] + total["lab.run.tokens.cache_read"] + total["lab.run.tokens.cache_creation"]
    assert (total["lab.run.tokens.input"], total["lab.run.tokens.cache_read"], total["lab.run.tokens.cache_creation"]) == (
        r.tokens_in, 800 + 800, 800)
    assert sum(c["gen_ai.usage.cache_read.input_tokens"] for c in chats if "gen_ai.usage.cache_read.input_tokens" in c) == 1600
    costo = sum(c["lab.cost.usd"] for c in chats)
    assert costo == pytest.approx(total["lab.run.cost_usd"], abs=1e-7) == pytest.approx(r.costo_usd, abs=1e-7)
    assert costo == pytest.approx((1980 * 0.1 + 310 * 0.5) / 1e6, abs=1e-9)           # semana-07/prices.json: haiku 0.10 / 0.50
    assert (total["lab.run.steps"], total["lab.run.tool_calls"], total["lab.run.tool_errors"]) == (3, 3, 0)  # 2 tools + responder
    # the model calls are the only spans with usage: the agent span does not double count for Langfuse
    assert not [s for s in spans if not s["name"].startswith("chat ") and any(k.startswith("gen_ai.usage.") for k in s["attrs"])]


def test_el_tiempo_de_las_llamadas_cabe_dentro_de_la_corrida(banco):
    spans = tarea_de(de(banco, "principal")["spans"])
    raiz = raiz_de(spans)
    for s in spans:
        assert raiz["inicio"] <= s["inicio"] <= s["fin"] <= raiz["fin"], s["name"]


# ---------- plan bullet: nothing private in any attribute with content capture off ----------

def _texto(spans) -> str:
    partes = []
    for s in spans:
        partes += [s["name"], s["descripcion_estado"] or "", s["alcance"], json.dumps(s["recurso"], default=str)]
        partes += [json.dumps(s["attrs"], default=str), json.dumps(s["eventos"], default=str)]
    return "\n".join(partes)


def _celdas(banco) -> set[str]:
    celdas = set()
    for e in banco["escenarios"].values():
        for ll in e["cliente"].llamadas:
            for fila in json.loads(ll["salida"]).get("filas", []):
                celdas |= {str(c) for c in fila if isinstance(c, str) and len(c) >= 4}
    return celdas


def test_con_la_captura_de_contenido_apagada_no_hay_nada_privado_en_ningun_span(banco):
    estandar = {n: e for n, e in banco["escenarios"].items() if n != "captura_span_only"}
    texto = "\n".join(_texto(e["spans"]) for e in estandar.values())
    from psycopg.conninfo import conninfo_to_dict
    clave_db = conninfo_to_dict(os.environ["NLQ_LEGADO_DSN"]).get("password")
    privados = {**CANARIOS, "prompt_del_sistema": "You are a data analyst", "sujeto": "sub-analista", "sujeto2": "sub-almacenista",
                "sku_de_argumento": "SKU-0009", "clave_de_base": clave_db,
                **{f"token{i}": t for i, t in enumerate(banco["tokens"])}}
    assert clave_db and len(clave_db) >= 20 and len(banco["tokens"]) >= 2
    visto = {k: v for k, v in privados.items() if v in texto}
    assert not visto, sorted(visto)
    filas = _celdas(banco)
    assert filas, "the scripted SQL returned rows to look for"
    assert not [c for c in filas if c in texto], "a returned row value reached a span"
    # no list-valued attribute but the fixed-vocabulary finish reasons, and no exception text or events anywhere
    for e in estandar.values():
        for s in e["spans"]:
            assert [k for k, v in s["attrs"].items() if isinstance(v, (list, tuple))] in ([], ["gen_ai.response.finish_reasons"])
            assert not [ev for ev in s["eventos"] if ev["name"] == "exception"], s["name"]


def test_la_capa_del_laboratorio_tampoco_captura_contenido_con_span_only(banco):
    """`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY` is a switch of the util-genai handler: the lab layer never
    sets message content, and the MCP SDK spans do not read the switch (measured)."""
    texto = _texto(de(banco, "captura_span_only")["spans"])
    assert not [k for k, v in CANARIOS.items() if v in texto and k != "dsn" and k != "clave_api"], texto[:500]


# ---------- the failure paths ----------

def test_un_error_de_sql_marca_la_herramienta_y_el_sql_sin_el_texto_del_error(banco):
    d = de(banco, "error_sql")
    tarea = tarea_de(d["spans"])
    malo = next(s for s in tarea if s["name"] == "execute_tool legado__ejecutar_sql")
    assert malo["estado"] == "ERROR" and malo["attrs"]["lab.tool.status"] == "error" and malo["attrs"]["error.type"] == "error_sql"
    assert malo["descripcion_estado"] == "error_sql"
    sql = [s for s in tarea if s["name"] == "SELECT legado"]
    fallido = next(s for s in sql if s["estado"] == "ERROR")
    assert fallido["attrs"]["error.type"] == "error_sql" and "db.response.returned_rows" not in fallido["attrs"]
    assert any(s["estado"] == "UNSET" and s["attrs"]["db.response.returned_rows"] == 5 for s in sql)
    assert "no_existe" not in _texto(d["spans"])                  # the column name of the SQL error stays in the tool result
    a = raiz_de(d["spans"])["attrs"]
    assert (a["lab.outcome.status"], a["lab.run.tool_errors"]) == ("respondida", 1)


def test_sin_el_scope_la_frontera_responde_403_y_queda_en_la_misma_traza(banco):
    d = de(banco, "sin_permiso")
    tarea = tarea_de(d["spans"])
    denegado = next(s for s in tarea if s["name"] == "authorize")
    a = denegado["attrs"]
    assert a["lab.authz.decision"] == "deny_insufficient_scope" and a["error.type"] == "insufficient_scope"
    assert a["lab.authz.scopes.missing"] == "legado:compras:proponer" and a["lab.tool.name"] == "proponer_orden_compra"
    assert a["lab.authz.scopes.granted"] == "legado:leer" and a["user.id"] == E.seudonimo("sub-almacenista")
    assert denegado["estado"] == "ERROR" and denegado["descripcion_estado"] == "deny_insufficient_scope"
    cliente = next(s for s in tarea if s["name"] == "MCP send tools/call proponer_orden_compra")
    assert denegado["parent"] == cliente["span"] and cliente["estado"] == "ERROR"
    # the SDK client turns the HTTP 403 into JSON-RPC -32603 (internal error): only `authorize` says why it was refused
    assert cliente["attrs"]["rpc.response.status_code"] == cliente["attrs"]["error.type"] == "-32603"
    assert cliente["descripcion_estado"] == "Server returned an error response"
    assert not [s for s in tarea if s["name"].startswith(("tools/call", "handle_tool", "SELECT"))]   # nothing ran
    herramienta = next(s for s in tarea if s["name"].startswith("execute_tool "))
    assert herramienta["estado"] == "ERROR" and herramienta["attrs"]["error.type"] == "error_mcp"
    assert cliente["parent"] == herramienta["span"]
    assert raiz_de(d["spans"])["attrs"]["lab.outcome.status"] == "abstenida"


def test_si_el_perfil_no_ve_la_herramienta_la_llamada_no_llega_al_servidor(banco):
    """The scope filters `tools/list`: a profile without `legado:compras:proponer` never gets the tool, so the call dies in the
    client as an unknown tool (`_unknown` in the span name) and no request reaches the boundary."""
    spans = tarea_de(de(banco, "sin_ver_la_herramienta")["spans"])
    herramientas = [s for s in spans if s["name"].startswith("execute_tool ")]
    assert [s["name"] for s in herramientas] == ["execute_tool _unknown"] and herramientas[0]["estado"] == "ERROR"
    assert not [s for s in spans if s["name"].startswith(("MCP send", "authorize", "tools/call", "handle_tool"))]


def test_si_falla_la_api_el_span_de_chat_lleva_solo_la_clase_del_error(banco):
    d = de(banco, "api_falla")
    spans = tarea_de(d["spans"])
    chats = sorted((s for s in spans if s["name"].startswith("chat ")), key=lambda s: s["inicio"])
    fallido = chats[-1]
    assert fallido["estado"] == "ERROR" and fallido["attrs"]["error.type"] == "RuntimeError"
    assert not fallido["eventos"] and fallido["descripcion_estado"] == "RuntimeError"
    a = raiz_de(d["spans"])["attrs"]
    assert (a["lab.outcome.status"], a["lab.outcome.reason"], a["error.type"]) == ("error", "api_error", "error")
    assert raiz_de(d["spans"])["estado"] == "ERROR"
    texto = _texto(d["spans"])
    assert CANARIOS["dsn"] not in texto and CANARIOS["clave_api"] not in texto and "boom" not in texto


def test_el_nombre_de_una_herramienta_inventada_por_el_modelo_nunca_llega_al_nombre_de_un_span(banco):
    d = de(banco, "inventada")
    herramientas = [s for s in tarea_de(d["spans"]) if s["name"].startswith("execute_tool ")]
    assert [s["name"] for s in herramientas] == ["execute_tool _unknown"]
    assert herramientas[0]["attrs"]["lab.tool.known"] is False and herramientas[0]["estado"] == "ERROR"
    assert CANARIOS["email"] not in _texto(d["spans"])


# ---------- the locked shape ----------

def test_ningun_atributo_ni_span_queda_fuera_de_la_forma_fijada(banco):
    sin_clasificar, violaciones, sdk = [], [], {"mcp_cliente": set(), "mcp_servidor": set()}
    for e in banco["escenarios"].values():
        for s in e["spans"]:
            tipo = categoria(s["name"])
            if tipo is None:
                sin_clasificar.append(s["name"])
            elif tipo in sdk:
                sdk[tipo] |= set(s["attrs"])
            else:
                violaciones += E.violaciones(s, tipo)
    assert not sin_clasificar, sorted(set(sin_clasificar))
    assert not violaciones, violaciones[:5]
    assert sdk["mcp_cliente"] <= E.ATRIBUTOS_SDK["mcp_cliente"], sdk["mcp_cliente"] - E.ATRIBUTOS_SDK["mcp_cliente"]
    assert sdk["mcp_servidor"] <= E.ATRIBUTOS_SDK["mcp_servidor"], sdk["mcp_servidor"] - E.ATRIBUTOS_SDK["mcp_servidor"]
    # the pinned SDK keys are what the SDK really emits (a key listed but never seen would be a hole in the allowlist)
    assert sdk["mcp_cliente"] >= {"mcp.method.name", "jsonrpc.request.id"}
    assert sdk["mcp_servidor"] >= {"mcp.method.name", "mcp.protocol.version", "jsonrpc.request.id",
                                   "gen_ai.operation.name", "gen_ai.tool.name"}


def test_la_forma_fijada_no_admite_listas_ni_texto_libre():
    for tipo, claves in E.ATRIBUTOS.items():
        for clave, regla in claves.items():
            assert not regla("ana.garcia@example.com"), (tipo, clave)
            assert not regla("SELECT * FROM artmst WHERE x = 'y'"), (tipo, clave)
            assert not regla(["a@b.com", "postgresql://u:p@h/d"]), (tipo, clave)


def test_fijar_rechaza_en_modo_estricto_y_descarta_y_cuenta_en_produccion():
    class Fake:
        def __init__(self):
            self.attrs = {}

        def set_attribute(self, k, v):
            self.attrs[k] = v

    previo = E.ESTRICTO
    try:
        E.ESTRICTO = True
        with pytest.raises(E.ErrorEsquema):
            E.fijar(Fake(), "execute_tool", {"lab.tool.args.hmac": "ana.garcia@example.com"})
        with pytest.raises(E.ErrorEsquema):
            E.fijar(Fake(), "execute_tool", {"atributo.nuevo": "x"})
        E.ESTRICTO = False
        E.OMITIDOS.clear()
        f = Fake()
        E.fijar(f, "execute_tool", {"lab.tool.status": "ok", "lab.tool.args.hmac": "ana.garcia@example.com", "atributo.nuevo": 1,
                                    "lab.tool.args.chars": None})
        assert f.attrs == {"lab.tool.status": "ok"}
        assert E.OMITIDOS == {"execute_tool:lab.tool.args.hmac": 1, "execute_tool:atributo.nuevo": 1}
    finally:
        E.ESTRICTO = previo
        E.OMITIDOS.clear()


def test_el_seudonimo_depende_de_la_sal_y_no_es_un_hash_simple(monkeypatch):
    import hashlib
    monkeypatch.setenv("LAB_OBS_SALT", "sal-a")
    a = E.seudonimo("sub-analista")
    assert a == E.seudonimo("sub-analista") and E.HEX16(a)
    assert a != hashlib.sha256(b"sub-analista").hexdigest()[:16]        # not reversible by a dictionary of plain hashes
    monkeypatch.setenv("LAB_OBS_SALT", "sal-b")
    assert E.seudonimo("sub-analista") != a


def test_el_motivo_de_parada_libre_se_reduce_al_vocabulario_fijo():
    assert E.clasificar_motivo("api: HTTP 400 ana.garcia@example.com") == "api_error"
    assert E.clasificar_motivo("max_pasos") == "max_pasos" and E.clasificar_motivo("algo raro con a@b.co") == "otro"


# ---------- the locked shape through the Collector's real processors ----------

def _modulo_de_pruebas_del_stack():
    spec = importlib.util.spec_from_file_location("test_stack_helpers17", S17 / "tests" / "test_stack.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _valor_otlp(v: dict):
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        return int(v["intValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    if "arrayValue" in v:
        return tuple(_valor_otlp(x) for x in v["arrayValue"].get("values", []))
    raise AssertionError(v)


def _pasar_por_el_collector(tmp_path, crudos, editar=None) -> dict:
    """Export the spans through OTLP to the real Collector processors and read what its file exporter wrote."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    ts = _modulo_de_pruebas_del_stack()
    with ts.collector_con_la_config_real(tmp_path, editar) as (puerto, archivo):
        OTLPSpanExporter(endpoint=f"http://127.0.0.1:{puerto}/v1/traces", timeout=20).export(crudos)
        for _ in range(80):
            if archivo.exists() and archivo.read_text().count("\n") >= 1:
                time.sleep(0.6)
                break
            time.sleep(0.25)
        lineas = [json.loads(x) for x in archivo.read_text().splitlines()]
    salida = {}
    for d in lineas:
        for rs in d["resourceSpans"]:
            for ss in rs["scopeSpans"]:
                for sp in ss["spans"]:
                    salida[sp["spanId"]] = {"name": sp["name"], "status": sp.get("status", {}),
                                            "attrs": {a["key"]: _valor_otlp(a["value"]) for a in sp.get("attributes", [])}}
    return salida


def test_la_forma_fijada_pasa_por_el_collector_sin_que_se_enmascare_ni_se_pierda_nada(tmp_path, banco):
    crudos = de(banco, "principal")["crudos"]
    salida = _pasar_por_el_collector(tmp_path, crudos)
    assert len(salida) == len(crudos)
    for s in crudos:
        despues = salida[format(s.context.span_id, "016x")]
        assert despues["name"] == s.name and "****" not in json.dumps(despues), s.name        # no false positive
        antes = {k: (tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in s.attributes.items()}
        assert despues["attrs"] == antes, s.name


def test_la_lista_blanca_hecha_con_la_forma_fijada_conserva_todos_los_atributos(tmp_path, banco):
    """Preparation for activity 9: `allow_all_keys: false` with the keys of the locked shape drops nothing the shape allows
    (and, activity 2, it also drops lists: here only the fixed-vocabulary finish reasons are lists)."""
    crudos = de(banco, "principal")["crudos"] + de(banco, "sin_permiso")["crudos"]
    permitidas = sorted(E.claves_permitidas() | {"service.name", "service.version", "telemetry.sdk.name", "telemetry.sdk.language",
                                                 "telemetry.sdk.version"})

    def lista_blanca(cfg):
        cfg["processors"]["redaction"]["allow_all_keys"] = False
        cfg["processors"]["redaction"]["allowed_keys"] = permitidas
    salida = _pasar_por_el_collector(tmp_path, crudos, lista_blanca)
    perdidos = []
    for s in crudos:
        despues = salida[format(s.context.span_id, "016x")]["attrs"]
        for k, v in s.attributes.items():
            if despues.get(k) != (tuple(v) if isinstance(v, (list, tuple)) else v):
                perdidos.append((s.name, k))
    assert not perdidos, perdidos[:5]


# ---------- committed evidence (resultados/instrumentacion.json, written on the Mac by verificar_langfuse.py) ----------

EVIDENCIA = S17 / "resultados" / "instrumentacion.json"


def test_evidencia_de_langfuse_de_punta_a_punta():
    d = json.loads(EVIDENCIA.read_text(encoding="utf-8"))
    assert d["ok"] is True and d["modelo"].startswith("guionado")
    assert set(d["escenarios"]) == {"principal", "error_sql", "sin_permiso", "api_falla"}
    for nombre, e in d["escenarios"].items():
        assert e["spans"] == e["observaciones"] > 0, nombre
        llaves = ("ids_iguales", "tipos_correctos", "nombres_correctos", "jerarquia_igual", "niveles_error_correctos",
                  "uso_igual_al_del_agente", "costo_igual_al_del_agente", "usuario_seudonimo_en_el_agente",
                  "usuario_seudonimo_en_el_servidor", "sin_input_ni_output", "latencia_de_langfuse_igual_a_la_del_span", "ok")
        assert all(e[k] is True for k in llaves), (nombre, {k: e[k] for k in llaves if e[k] is not True})
    p = d["escenarios"]["principal"]
    assert (p["spans"], p["tipos"], p["observaciones_con_error"]) == (15, ["AGENT", "GENERATION", "SPAN", "TOOL"], [])
    assert [g["uso"] for g in p["generaciones"]] == [
        {"input": 1180, "output": 64, "input_cache_creation": 800, "total": 2044},
        {"input": 420, "output": 96, "input_cached_tokens": 800, "total": 1316},
        {"input": 380, "output": 150, "input_cached_tokens": 800, "total": 1330}]
    assert d["escenarios"]["sin_permiso"]["observaciones_con_error"] == [
        "SPAN MCP send tools/call proponer_orden_compra", "SPAN authorize", "TOOL _unknown"]
    assert d["escenarios"]["api_falla"]["observaciones_con_error"] == ["AGENT invoke_agent legacybridge", "GENERATION chat claude-haiku-5-5"]
    assert d["privacidad"] == {"canarios_en_langfuse_o_archivo": [], "asteriscos_en_langfuse_o_archivo": False,
                               "trazas_en_el_archivo": 4, "trazas_de_la_corrida": 4, "ok": True}
    # the two attribute names for cache creation: Langfuse 4.72.0 reads both (the semconv one is locked)
    assert d["sondas"]["conclusion"] == {"semconv_cache_creation_se_entiende": True, "util_genai_cache_write_se_entiende": True}


def test_evidencia_sin_secretos_ni_rutas_locales_ni_canarios():
    import re
    texto = EVIDENCIA.read_text(encoding="utf-8")
    assert not re.search(r"/Users/|/home/|C:\\|sk-lf-|pk-lf-|sk-ant-|postgres(ql)?://|eyJ[A-Za-z0-9_-]{10,}\.", texto)
    for valor in ("ana.garcia", "XAXX0101", "CANARIO", "sub-analista", "sub-almacenista", "secreto-canario"):
        assert valor not in texto, valor
    assert "LAB_OBS_SALT" not in texto
