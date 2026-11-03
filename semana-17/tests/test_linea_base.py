"""Activity 1 (baseline), no API: the probes that need neither Docker nor the model run here and in CI; the
throwaway Langfuse stack and the Collector configs are checked for pins, localhost-only ports and no secrets; the
committed reports carry no secret and the matrix covers every capability of the plan."""
import importlib.util
import json
import re
from pathlib import Path

import yaml

S17 = Path(__file__).resolve().parents[1]
LB = S17 / "linea_base"
spec = importlib.util.spec_from_file_location("verificar_lb17", LB / "verificar.py")
vb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vb)


def test_sondas_sin_docker_ni_modelo(tmp_path):
    salida = tmp_path / "lb.json"
    codigo = vb.main(["--solo", "paquetes,semconv,util_genai,collector,mcp,frameworks,repo", "--salida", str(salida)])
    r = json.loads(salida.read_text())["sondas"]
    assert codigo == 0, {k: v for k, v in r.items() if not v.get("ok")}
    assert r["collector"]["canarios_filtrados"] == [] and r["collector"]["enmascarado"]
    assert r["util_genai"]["por_omision"]["contenido"] is False and r["util_genai"]["SPAN_ONLY"]["contenido"] is True
    assert r["mcp"]["cliente_a_servidor"] and not r["mcp"]["agente_a_cliente"]   # activity 3 fixes the thread


def test_compose_de_prueba_por_digest_solo_localhost_y_sin_secretos():
    texto = (LB / "langfuse_prueba.compose.yml").read_text()
    c = yaml.safe_load(texto)
    for nombre, s in c["services"].items():
        assert re.fullmatch(r"\$\{IMG_[A-Z_]+\}", s["image"]), nombre
        for p in s.get("ports", []):
            assert p.startswith("127.0.0.1:"), (nombre, p)
    assert sorted(p for s in c["services"].values() for p in s.get("ports", [])) == [
        "127.0.0.1:3100:3000", "127.0.0.1:4318:4318"]
    for linea in texto.splitlines():
        if re.search(r"[A-Z0-9_]*(PASSWORD|SECRET|SALT|KEY|AUTH):\s", linea) or "postgresql://" in linea:
            assert "${" in linea, linea
    variables = set(re.findall(r"\$\{([A-Z_]+)\}", texto))
    fuente = (LB / "verificar.py").read_text()
    for v in variables:
        assert f'"{v}"' in fuente, v                      # verificar.py writes every variable the compose reads


def test_collector_redacta_antes_de_exportar():
    for archivo in ("collector_prueba.yaml", "collector_langfuse.yaml"):
        c = yaml.safe_load((LB / archivo).read_text())
        traces = c["service"]["pipelines"]["traces"]
        assert traces["processors"][0] == "redaction", archivo
        bloqueados = " ".join(c["processors"]["redaction"]["blocked_values"])
        for patron in ("postgres", "bearer", "sk-ant", "@"):
            assert patron in bloqueados, (archivo, patron)
    lf = yaml.safe_load((LB / "collector_langfuse.yaml").read_text())
    exp = lf["exporters"]["otlp_http/langfuse"]
    assert exp["headers"]["Authorization"] == "Basic ${env:LANGFUSE_AUTH}"
    assert exp["endpoint"].endswith("/api/public/otel")


def test_reportes_sin_secretos_ni_rutas_locales():
    reportes = sorted((S17 / "resultados").glob("linea_base_*.json"))
    assert reportes
    for r in reportes:
        t = r.read_text()
        for prohibido in ("sk-lf-", "pk-lf-", "postgresql://", "Basic ", "/Users/", "/home/", "canario-dsn"):
            assert prohibido not in t, (r.name, prohibido)


# ---- the M/D/N matrix of resultados/linea_base.md -------------------------------------------------------------
MD = S17 / "resultados" / "linea_base.md"

# Every capability the plan asks activity 1 to verify (plan, "1. Baseline"), as a regex over the first column.
CAPACIDADES_DEL_PLAN = {
    "semconv: current names and status": [r"semantic conventions: status", r"semantic conventions: names"],
    "content capture variables of the chosen instrumentation": [r"content capture of the instrumentation"],
    "Python SDK": [r"python sdk"],
    "Collector (otelcol-contrib)": [r"collector contrib"],
    "Langfuse v4 images": [r"langfuse images"],
    "Langfuse minimum versions of its dependencies": [r"langfuse dependencies"],
    "Langfuse OTLP endpoint and auth": [r"otlp endpoint and auth"],
    "Langfuse gen_ai.* to observations": [r"mapping of `gen_ai"],
    "Langfuse scores": [r"langfuse scores"],
    "Langfuse dashboards API": [r"dashboards api"],
    "Langfuse data retention": [r"data retention"],
    "Claude Agent SDK native OpenTelemetry": [r"claude agent sdk"],
    "Claude Code telemetry": [r"claude code .* telemetry"],
    "LangGraph": [r"langgraph"],
    "Strands": [r"strands"],
    "W3C propagation over Streamable HTTP in the MCP SDK": [r"mcp sdk .*w3c propagation"],
    "semana-17/** in the evals-semana-06 paths": [r"evals-semana-06"],
    "pins replaced and images by digest": [r"pins and digests replaced"],
}


def _filas_matriz() -> list[list[str]]:
    texto = MD.read_text()
    cuerpo = texto.split("## Capability matrix", 1)[1].split("## Findings", 1)[0]
    filas = []
    for linea in cuerpo.splitlines():
        if linea.startswith("|") and not linea.startswith("|---") and not linea.startswith("| Capability"):
            filas.append([c.strip() for c in linea.strip().strip("|").split("|")])
    return filas


def test_matriz_cubre_cada_capacidad_del_plan():
    filas = _filas_matriz()
    assert filas
    primeras = [f[0].lower() for f in filas]
    faltan = [nombre for nombre, patrones in CAPACIDADES_DEL_PLAN.items()
              if not all(any(re.search(p, c) for c in primeras) for p in patrones)]
    assert not faltan, f"capabilities of the plan missing from the matrix: {faltan}"


def test_matriz_cada_fila_tiene_estado_m_d_n():
    for fila in _filas_matriz():
        assert len(fila) == 3, fila
        estado = re.sub(r"\([^)]*\)", "", fila[2])             # drop notes such as "(week 15)"
        marcas = [m.strip() for m in estado.split("·")]
        assert marcas and all(m in {"M", "D", "N"} for m in marcas), (fila[0], fila[2])
        assert fila[1], fila[0]


def test_matriz_cifras_coinciden_con_los_json_y_las_versiones():
    texto = MD.read_text()
    v = json.loads((S17 / "preparar" / "versiones.json").read_text())
    for valor in (v["python"]["opentelemetry-api"], v["python"]["opentelemetry-semantic-conventions"],
                  v["python"]["opentelemetry-util-genai"], v["imagenes"]["langfuse-web"].rsplit(":", 1)[1],
                  v["imagenes"]["clickhouse"].rsplit(":", 1)[1], v["imagenes"]["otel-collector"].rsplit(":", 1)[1],
                  v["semconv_genai"]["commit"], v["claude_code"]["cli_contenedor"]):
        assert valor in texto, valor
    assert re.search(r"all (\d+) entries", v["semconv_genai"]["estabilidad"]).group(1) in texto
    # probes: the totals written in the text are the ones in the committed reports
    mac = json.loads((S17 / "resultados" / "linea_base_mac.json").read_text())["sondas"]
    cont = json.loads((S17 / "resultados" / "linea_base_contenedor.json").read_text())["sondas"]
    assert all(s["ok"] for s in mac.values()) and f"**{len(mac)}/{len(mac)} OK**" in texto
    assert all(s["ok"] for s in cont.values()) and f"**{len(cont)}/{len(cont)} OK**" in texto
    # Langfuse usage accounting: what the report says is what the probe measured
    uso = mac["langfuse"]["generacion"]["usage"]
    assert (uso["input"], uso["input_cached_tokens"], uso["total"]) == (120, 900, 1050)
    for n in (uso["input"], uso["input_cached_tokens"], uso["output"], uso["total"]):
        assert str(n) in texto, n
    assert mac["langfuse"]["otlp_auth"] == {"sin_auth": 401, "con_auth": 200}
    assert mac["mcp"]["cliente_a_servidor"] and not mac["mcp"]["agente_a_cliente"]
    assert len(mac["semconv"]["atributos"]) == 16 and len(mac["semconv"]["operaciones"]) == 9


def test_matriz_enlaces_de_evidencia_existen_y_sin_rutas_locales():
    texto = MD.read_text()
    enlaces = re.findall(r"\]\((?!https?:)([^)#]+)\)", texto)
    assert enlaces
    for e in enlaces:
        assert (MD.parent / e).resolve().exists(), e
    for prohibido in ("/Users/", "/home/", "postgresql://", "sk-lf-", "pk-lf-", "sk-ant-"):
        assert prohibido not in texto, prohibido
