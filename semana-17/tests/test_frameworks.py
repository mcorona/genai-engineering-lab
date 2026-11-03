"""Optional of activity 3 (the same task through Strands and LangGraph), no API ($0).

The measurement needs the framework venvs of week 15, the lab's server and, for the Langfuse part, the stack of activity 2, so it
runs on the Mac (`comparacion/comparar_frameworks.py --langfuse`) and writes `resultados/frameworks.json`. CI has none of that, so
these tests check the committed evidence against the code that is in the repository (the locked span shape, the scripted turns) and
check the scripts statically; the write-up's numbers are checked against the evidence."""
import json
import re
import sys
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.modelo_guionado import turnos_principal  # noqa: E402

RUTA = S17 / "resultados" / "frameworks.json"
TEXTO = RUTA.read_text(encoding="utf-8")
R = json.loads(TEXTO)
MD = (S17 / "resultados" / "frameworks.md").read_text(encoding="utf-8")
COMPARAR = (S17 / "comparacion" / "comparar_frameworks.py").read_text(encoding="utf-8")
STRANDS = (S17 / "comparacion" / "agente_strands.py").read_text(encoding="utf-8")
LANGGRAPH = (S17 / "comparacion" / "agente_langgraph.py").read_text(encoding="utf-8")
CANARIOS = ("email", "rfc", "telefono", "literal_sql", "prompt")


def _entradas_totales():
    """Input tokens per chat call as the semantic conventions define them: uncached + cache read + cache creation."""
    return [t["usage"]["input_tokens"] + t["usage"].get("cache_read_input_tokens", 0)
            + t["usage"].get("cache_creation_input_tokens", 0) for t in turnos_principal()]


# ---------- the evidence itself ----------

def test_la_evidencia_esta_completa_y_no_tiene_secretos_ni_rutas():
    assert R["completo"] is True and R["modelo_guionado"] is True and R["sin_token_en_el_informe"] is True
    for prohibido in ("/Users/", "127.0.0.1", "localhost", "eyJ", "postgresql://", "sk-ant", "Bearer ", "LAB_OBS_SALT"):
        assert prohibido not in TEXTO, prohibido
    assert not re.search(r"[0-9a-f]{64}", TEXTO)                                   # no key-like blobs
    assert R["strands"]["versiones"] == {"strands-agents": "1.63.0", "mcp": "2.3.0"}
    assert R["langgraph"]["versiones"]["langgraph"] == "1.2.19" and R["langgraph"]["versiones"]["mcp"] == "1.30.0"


def test_strands_continua_la_traza_del_agente_dentro_del_servidor():
    c = R["strands"]["continuidad"]
    assert c["llamadas_a_herramientas_en_el_servidor"] == c["de_ellas_en_la_traza_del_agente"] == 2
    assert c["una_sola_traza_hasta_el_sql"] is True
    assert c["padre_de_authorize"] == ["MCP send tools/call describir_esquema", "MCP send tools/call ejecutar_sql"]
    assert all(x["en_la_traza_del_agente"] and x["padre"].startswith("execute_tool ") for x in
               c["spans_mcp_del_sdk_en_el_proceso_del_framework"])
    assert c["spans_del_servidor_en_la_traza"] == {"SELECT": 1, "authorize": 2, "handle_tool": 2, "tools/call": 2}
    # the discovery requests before the agent starts are traces of their own
    assert c["spans_del_servidor_en_otras_trazas"].get("tools/list") and "tools/call" not in c["spans_del_servidor_en_otras_trazas"]
    assert R["strands"]["spans"] == 13 and R["strands"]["spans_en_la_traza_del_agente"] == 11
    assert len([x for x in c["arbol"] if not x.startswith("0 MCP send")]) == 18        # 11 from Strands + 7 from the server
    assert c["arbol"].index("0 invoke_agent Strands Agents") < c["arbol"].index("6 SELECT legado")


def test_strands_cuenta_los_tokens_como_el_laboratorio():
    esperados = _entradas_totales()
    assert esperados == [1980, 1220, 1180]
    for lado in (R["laboratorio"]["tokens"], R["strands"]["tokens"]):
        assert [t["gen_ai.usage.input_tokens"] for t in lado] == esperados
        assert [t["gen_ai.usage.output_tokens"] for t in lado] == [64, 96, 150]
        assert [t.get("gen_ai.usage.cache_creation.input_tokens", 0) for t in lado] == [800, 0, 0]
        assert [t.get("gen_ai.usage.cache_read.input_tokens", 0) for t in lado] == [0, 800, 800]
    extra = R["strands"]["tokens"][0]
    # the legacy aliases: same numbers under old names, and a sum
    assert extra["gen_ai.usage.prompt_tokens"] == extra["gen_ai.usage.input_tokens"]
    assert extra["gen_ai.usage.completion_tokens"] == extra["gen_ai.usage.output_tokens"]
    assert extra["gen_ai.usage.cache_write_input_tokens"] == extra["gen_ai.usage.cache_creation.input_tokens"]
    assert extra["gen_ai.usage.total_tokens"] == 2044


def test_la_cobertura_es_la_del_esquema_de_hoy():
    """Recomputed with the shape in the repository: if `esquema.py` changes, the evidence must be measured again."""
    todas = E.claves_permitidas()
    for op, c in R["strands"]["cobertura"].items():
        nativas = set(R["strands"]["operaciones"][op]["claves"])
        propias = set(E.ATRIBUTOS.get(op, {}))
        assert set(c["aceptadas_por_el_esquema"]) == nativas & propias
        assert set(c["fuera_del_esquema"]) == nativas - propias
        assert set(c["fuera_de_toda_la_lista"]) == nativas - todas
        if propias:
            assert set(c["del_esquema_que_no_emite"]) == propias - nativas
    ag, ch, he = (R["strands"]["cobertura"][o] for o in ("invoke_agent", "chat", "execute_tool"))
    assert (len(ag["aceptadas_por_el_esquema"]), ag["emite"], len(ag["del_esquema_que_no_emite"]), len(E.ATRIBUTOS["invoke_agent"])) \
        == (3, 16, 23, 26)
    assert (len(ch["aceptadas_por_el_esquema"]), ch["emite"], len(ch["del_esquema_que_no_emite"]), len(E.ATRIBUTOS["chat"])) \
        == (6, 16, 13, 19)
    assert (len(he["aceptadas_por_el_esquema"]), he["emite"], len(he["del_esquema_que_no_emite"]), len(E.ATRIBUTOS["execute_tool"])) \
        == (3, 9, 8, 11)
    for faltante in ("user.id", "lab.tenant.id", "lab.outcome.status", "lab.budget.max_steps", "lab.run.cost_usd"):
        assert faltante in ag["del_esquema_que_no_emite"]
    distintas = {k for o in R["strands"]["operaciones"].values() for k in o["claves"]}
    assert (len(distintas), len(distintas - todas)) == (27, 16)
    assert "gen_ai.system" in distintas - todas and "gen_ai.usage.prompt_tokens" in distintas - todas


# ---------- content: the default and the switch ----------

def test_strands_por_omision_registra_el_contenido_y_con_su_interruptor_no():
    por_omision, con_interruptor = R["strands"], R["strands_redactado"]
    assert con_interruptor["configuracion"] == "OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_unredacted_attributes="
    for k in (*CANARIOS, "sql_completo", "tarea", "filas_devueltas"):
        assert por_omision["fugas"][k] is True, k
        assert con_interruptor["fugas"][k] is False, k
    assert por_omision["fugas"]["token"] is False and con_interruptor["fugas"]["token"] is False
    # the switch costs nothing else: same spans, same continuity, same events (their content is what changes)
    assert con_interruptor["spans"] == por_omision["spans"] == 13
    assert con_interruptor["continuidad"]["arbol"] == por_omision["continuidad"]["arbol"]
    assert con_interruptor["continuidad"]["una_sola_traza_hasta_el_sql"] is True
    usos = lambda r: [{k: v for k, v in t.items() if "usage" in k} for t in r["tokens"]]   # noqa: E731  (timings differ run to run)
    assert usos(con_interruptor) == usos(por_omision)
    assert "gen_ai.user.message" in por_omision["operaciones"]["chat"]["eventos"]


def test_langfuse_recibe_el_mismo_arbol_y_el_colector_solo_enmascara_patrones():
    a, b = R["langfuse_strands"], R["langfuse_strands_redactado"]
    for lf in (a, b):
        assert lf["observaciones"] == lf["esperadas"] == 18
        assert lf["tipos"] == {"AGENT": 1, "GENERATION": 3, "SPAN": 10, "TOOL": 4}
        assert lf["usuario_en_el_agente"] is False                                  # Strands knows no user
    # default: the Collector masks the email, tax id and phone (patterns), but not a marker or a SQL literal
    assert a["canarios_en_langfuse"] == {"email": False, "rfc": False, "telefono": False, "literal_sql": True, "prompt": True}
    assert a["mascaras"] > 0
    # with Strands' switch there is nothing to mask and nothing to leak
    assert not any(b["canarios_en_langfuse"].values()) and b["mascaras"] == 0


def test_langfuse_guarda_los_tokens_de_strands_y_los_cobra_con_su_tabla():
    esperados = _entradas_totales()
    gen = R["langfuse_strands"]["generaciones"]
    assert [g["usageDetails"]["input"] for g in gen] == [e - c for e, c in zip(esperados, (800, 800, 800))]   # Langfuse subtracts the cache
    assert [g["usageDetails"]["total"] for g in gen] == [2044, 1316, 1330]
    assert gen[0]["usageDetails"]["input_cache_creation"] == 800 == gen[0]["usageDetails"]["cache_write_input_tokens"]   # the duplicate name
    assert all(g["usageDetails"]["input_cached_tokens"] == 800 for g in gen[1:])
    assert all(g["modelo"] == "claude-haiku-5-5" for g in gen)
    cobrado = sum(g["costDetails"]["total"] for g in gen)
    assert 0.00046 < cobrado < 0.00048                                              # $0.000469 with the cache priced
    assert "0.000469" in MD and "0.000353" in MD


# ---------- LangGraph ----------

def test_langgraph_no_emite_opentelemetry_y_el_servidor_no_puede_enlazar_sus_llamadas():
    lg = R["langgraph"]
    assert lg["spans_otel"] == 0 and lg["nombres_otel"] == [] and lg["atributos_gen_ai_otel"] == []

    def contar(n):
        return 1 + sum(contar(h) for h in n["hijos"])
    assert lg["runs"] == sum(contar(a) for a in lg["arboles"]) == 23
    assert lg["tipos"] == ["chain", "llm", "tool"] and lg["usage_en_el_rastro"] is True
    assert lg["servidor_real"] is True and lg["motivo_sin_servidor"] is None
    srv = lg["servidor"]
    assert srv["llamadas_a_herramientas"] == srv["trazas_de_las_llamadas"] == 2 and srv["authorize_con_padre"] == 0
    assert srv["trazas"] == 22 and srv["spans"] == 25                                # one MCP session per call, no context
    assert all(lg["fugas"][k] is True for k in (*CANARIOS, "sql_completo", "tarea", "filas_devueltas")) and lg["fugas"]["token"] is False


def test_el_laboratorio_tiene_los_15_spans_de_la_actividad_3():
    assert R["laboratorio"]["estado"] == "respondida" and R["laboratorio"]["spans_en_la_traza"] == 15
    assert set(R["laboratorio"]["operaciones"]) == {"invoke_agent", "chat", "execute_tool"}


# ---------- the scripts ----------

def test_el_token_viaja_por_el_entorno_y_nunca_por_los_argumentos():
    assert 'os.environ["LAB_TOKEN"]' in STRANDS and 'os.environ["LAB_TOKEN"]' in LANGGRAPH
    assert "sys.argv" not in STRANDS and "sys.argv" not in LANGGRAPH
    assert '"LAB_TOKEN": token' in COMPARAR and "[str(py), str(S17 / " in COMPARAR      # the argv has the interpreter and the script
    assert ".replace(token," in COMPARAR                                               # a failure message never prints it
    assert "_API_KEY" not in COMPARAR and "os.environ.get(\"HOME\"" in COMPARAR        # a minimal environment, no key inherited


def test_los_dos_frameworks_corren_el_mismo_guion_y_el_modelo_es_guionado():
    assert 'GUION["turnos"]' in STRANDS and 'GUION["turnos"]' in LANGGRAPH
    assert "turnos_principal(prefijo=\"\"" in COMPARAR                                  # the lab's own scripted turns
    for texto in (STRANDS, LANGGRAPH):
        assert not re.search(r"^\s*(import|from)\s+(anthropic|langchain_anthropic|strands\.models\.anthropic)", texto, re.M)   # no real model
    assert 'os.environ["LANGSMITH_TRACING"] = "false"' in LANGGRAPH                    # nothing is sent anywhere


def test_la_redaccion_de_strands_se_pide_con_la_lista_vacia():
    assert 'REDACCION_STRANDS = "gen_ai_unredacted_attributes="' in COMPARAR


def test_el_texto_cita_los_numeros_de_la_evidencia():
    for dato in (R["strands"]["spans"], R["strands"]["spans_en_la_traza_del_agente"], R["langgraph"]["runs"],
                 R["langgraph"]["servidor"]["spans"], R["langgraph"]["servidor"]["trazas"], R["langfuse_strands"]["observaciones"],
                 R["langfuse_strands"]["mascaras"], R["laboratorio"]["spans_en_la_traza"]):
        assert str(dato) in MD, dato
    for linea in ("agent 3 of 16", "chat 6 of 16", "tool 3 of 9", "16 of its 27 distinct keys", "agent 23 of 26", "chat 13 of 19",
                  "tool 8 of 11", "1980, 1220 and 1180"):
        assert linea in MD, linea
