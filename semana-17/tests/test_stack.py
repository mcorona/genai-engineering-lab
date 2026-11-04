"""Activity 2 (observability stack), no API and no Docker daemon needed in CI.

Static checks of docker-compose.yml, arrancar.sh and collector.yaml (pins by digest, localhost-only ports, no secrets
in the repo, secrets never printed, redaction before every exporter), a functional run of the REAL redaction
processors in the Collector (binary in CI, Docker image on the Mac) and a check of the committed end-to-end evidence
(resultados/stack.json, produced by observabilidad/verificar_stack.py, which needs Docker and runs on the Mac)."""
import contextlib
import copy
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import yaml

S17 = Path(__file__).resolve().parents[1]
RAIZ = S17.parent
OBS = S17 / "observabilidad"
V = json.loads((S17 / "preparar" / "versiones.json").read_text(encoding="utf-8"))

spec = importlib.util.spec_from_file_location("verificar_stack17", OBS / "verificar_stack.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

COMPOSE_TEXTO = (OBS / "docker-compose.yml").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load(COMPOSE_TEXTO)
ARRANCAR = (OBS / "arrancar.sh").read_text(encoding="utf-8")
COLECTOR = yaml.safe_load((OBS / "collector.yaml").read_text(encoding="utf-8"))
INTERNOS = {"postgres", "clickhouse", "redis", "minio", "langfuse-worker"}


# ---- docker-compose.yml ---------------------------------------------------------------------------------------
def test_compose_servicios_por_digest_y_solo_localhost():
    assert set(COMPOSE["services"]) == INTERNOS | {"langfuse-web", "collector"}
    for nombre, s in COMPOSE["services"].items():
        assert re.fullmatch(r"\$\{IMG_[A-Z_]+\}", s["image"]), nombre          # the digest is resolved by arrancar.sh
        assert s.get("restart") == "unless-stopped", nombre
        for p in s.get("ports", []):
            assert p.startswith("127.0.0.1:"), (nombre, p)
    publicados = sorted(p for s in COMPOSE["services"].values() for p in s.get("ports", []))
    assert publicados == ["127.0.0.1:13133:13133", "127.0.0.1:3100:3000", "127.0.0.1:4317:4317",
                          "127.0.0.1:4318:4318"]
    for nombre in INTERNOS:
        assert "ports" not in COMPOSE["services"][nombre], nombre            # Compose network only
    puertos_plan = V["puertos"]
    assert (puertos_plan["langfuse-web"], puertos_plan["otlp-grpc"], puertos_plan["otlp-http"],
            puertos_plan["collector-salud"]) == (3100, 4317, 4318, 13133)


def test_compose_sin_secretos_y_con_volumenes_con_nombre():
    for linea in COMPOSE_TEXTO.splitlines():
        if re.search(r"[A-Z0-9_]*(PASSWORD|SECRET|SALT|KEY|AUTH):\s", linea) or "postgresql://" in linea:
            assert "${" in linea, linea
    assert set(COMPOSE["volumes"]) == {"clickhouse", "minio", "postgres"}
    col = COMPOSE["services"]["collector"]
    assert "./collector.yaml:/etc/otelcol/config.yaml:ro" in col["volumes"]
    assert col["user"] == "${HOST_UID}:${HOST_GID}" and col["mem_limit"]
    assert COMPOSE["services"]["collector"]["depends_on"]["langfuse-web"]["condition"] == "service_started"
    assert "healthcheck" in COMPOSE["services"]["langfuse-web"]


def test_compose_variables_las_escribe_arrancar_sh():
    usadas = set(re.findall(r"(?<!\$)\$\{([A-Z_]+)\}", COMPOSE_TEXTO))
    secretos = set(re.findall(r'echo "([A-Z_]+)=', ARRANCAR))
    imagenes = set(re.findall(r'"(IMG_[A-Z_]+)"', ARRANCAR))
    assert usadas <= secretos | imagenes | {"HOST_UID", "HOST_GID"}, usadas - secretos - imagenes
    assert {v for v in usadas if v.startswith("IMG_")} == imagenes
    claves = set(re.findall(r'^mapa = \{(.*?)\}', ARRANCAR, re.S | re.M)[0].split('"')[1::2]) - imagenes
    for nombre in claves:                                                      # every image has repo and digest
        assert nombre in V["imagenes"] and V["digests"][nombre].startswith("sha256:"), nombre


# ---- arrancar.sh ----------------------------------------------------------------------------------------------
def test_arrancar_sh_sintaxis_opciones_y_secretos():
    ruta = OBS / "arrancar.sh"
    assert os.access(ruta, os.X_OK)
    assert subprocess.run(["bash", "-n", str(ruta)], capture_output=True).returncode == 0
    for opcion in ("--estado", "--detener", "--reiniciar", "--borrar", "--secretos"):
        assert opcion in ARRANCAR, opcion
    assert "umask 077" in ARRANCAR and "chmod 600" in ARRANCAR
    assert "set -x" not in ARRANCAR and "bash -x" not in ARRANCAR
    assert not re.search(r"\bsource\b|^\s*\. ", ARRANCAR, re.M)               # the secrets file is passed to Compose, not read
    assert 'cat "$SECRETOS"' not in ARRANCAR
    # no line prints a secret value: the only prints of the secrets file are counts and its name
    for linea in ARRANCAR.splitlines():
        if re.match(r"\s*(echo|printf)\b", linea) and "aleatorio" not in linea and "LANGFUSE_AUTH=" not in linea:
            assert not re.search(r"\$\{?(POSTGRES_PASSWORD|CLICKHOUSE_PASSWORD|MINIO_ROOT_PASSWORD|REDIS_AUTH|SALT|"
                                 r"ENCRYPTION_KEY|NEXTAUTH_SECRET|LANGFUSE_[A-Z_]*)\}?", linea), linea


def test_secretos_y_trazas_crudas_ignorados_por_git():
    for ruta in ("semana-17/observabilidad/.secretos.env", "semana-17/observabilidad/datos/trazas.jsonl"):
        p = subprocess.run(["git", "check-ignore", "-q", ruta], cwd=RAIZ)
        assert p.returncode == 0, f"{ruta} is not git-ignored"


# ---- collector.yaml -------------------------------------------------------------------------------------------
REGEX_DE_TRANSFORM = re.compile(r', "(\(postgres\(ql\)\?://.*)", "\*\*\*\*"\)$')


def test_collector_pipeline_redacta_antes_de_exportar():
    assert COLECTOR["extensions"]["health_check"]["endpoint"] == "0.0.0.0:13133"
    http, grpc = (COLECTOR["receivers"]["otlp"]["protocols"][k]["endpoint"] for k in ("http", "grpc"))
    assert (http, grpc) == ("0.0.0.0:4318", "0.0.0.0:4317")
    tuberia = COLECTOR["service"]["pipelines"]["traces"]
    assert tuberia["processors"] == ["memory_limiter", "redaction", "transform/redaccion", "batch"]
    assert tuberia["exporters"] == ["file", "otlp_http/langfuse"]
    assert COLECTOR["service"]["extensions"] == ["health_check"]
    lf = COLECTOR["exporters"]["otlp_http/langfuse"]
    assert lf["endpoint"] == "http://langfuse-web:3000/api/public/otel"
    assert lf["headers"]["Authorization"] == "Basic ${env:LANGFUSE_AUTH}"
    assert lf["sending_queue"]["enabled"] and lf["retry_on_failure"]["enabled"]
    rot = COLECTOR["exporters"]["file"]["rotation"]
    assert rot["max_megabytes"] and rot["max_backups"] and rot["max_days"]      # the raw file is bounded


def test_collector_los_siete_patrones_estan_en_redaction_y_en_cada_regla_transform():
    red = COLECTOR["processors"]["redaction"]
    assert red["allow_all_keys"] is False and len(red["blocked_values"]) == 7          # allowlist since activity 9
    fragmentos = ["postgres(ql)?://", "bearer", "eyJ", "sk-ant-", "@", "[A-ZÑ&]{3,4}", "\\d{2} \\d{4} \\d{4}"]
    for f in fragmentos:
        assert any(f in b for b in red["blocked_values"]), f
    reglas = []
    contextos = {}
    for bloque in COLECTOR["processors"]["transform/redaccion"]["trace_statements"]:
        contextos[bloque["context"]] = bloque["statements"]
        reglas += bloque["statements"]
    assert set(contextos) == {"span", "spanevent"}
    assert [s.split("(")[0] + ":" + s.split(",")[0].split("(")[1] for s in contextos["span"]] == [
        "replace_pattern:name", "replace_pattern:status.message", "replace_all_patterns:attributes"]
    assert [s.split("(")[0] + ":" + s.split(",")[0].split("(")[1] for s in contextos["spanevent"]] == [
        "replace_pattern:name", "replace_all_patterns:attributes"]
    regex = {REGEX_DE_TRANSFORM.search(s).group(1) for s in reglas}
    assert len(regex) == 1, "every transform statement must carry the same pattern list"
    for f in fragmentos:
        # in the transform statements YAML keeps the backslashes doubled (OTTL unescapes them) and bearer is scoped
        assert f.replace("bearer", "(?i:bearer)").replace("\\", "\\\\") in next(iter(regex)), f


def _binario() -> str | None:
    return os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")


def _imagen() -> str:
    return f"{V['imagenes']['otel-collector'].rsplit(':', 1)[0]}@{V['digests']['otel-collector']}"


def test_collector_config_real_valida(tmp_path):
    binario = _binario()
    if binario:
        cmd = [binario, "validate", f"--config={OBS / 'collector.yaml'}"]
    else:
        assert shutil.which("docker"), "needs OTELCOL_BIN, otelcol-contrib on PATH or Docker"
        cmd = ["docker", "run", "--rm", "-e", "LANGFUSE_AUTH=x", "-v", f"{OBS / 'collector.yaml'}:/etc/otelcol/config.yaml:ro",
               _imagen(), "validate", "--config=/etc/otelcol/config.yaml"]
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "LANGFUSE_AUTH": "x"})
    assert p.returncode == 0, p.stderr[-500:]


@contextlib.contextmanager
def collector_con_la_config_real(tmp_path, editar=None):
    """The real processors and receivers' shape, with only the file exporter (no Langfuse) on a free port.
    `editar(cfg)` may change the derived config (used to characterize variants of the redaction processors)."""
    binario = _binario()
    assert binario or shutil.which("docker"), "needs OTELCOL_BIN, otelcol-contrib on PATH or Docker"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    salida = tmp_path / "salida"
    salida.mkdir()
    os.chmod(salida, 0o777)
    cfg = copy.deepcopy(COLECTOR)
    del cfg["extensions"], cfg["service"]["extensions"]
    cfg["exporters"] = {"file": {"path": str(salida / "t.jsonl") if binario else "/salida/t.jsonl",
                                 "flush_interval": "200ms"}}
    cfg["service"]["pipelines"]["traces"]["exporters"] = ["file"]
    cfg["receivers"]["otlp"]["protocols"] = {"http": {"endpoint": f"127.0.0.1:{puerto}" if binario else "0.0.0.0:4318"}}
    if editar:
        editar(cfg)
    ruta = tmp_path / "config.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True))
    if binario:
        proc = subprocess.Popen([binario, f"--config={ruta}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parar = proc.terminate
    else:
        cid = subprocess.run(["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{puerto}:4318", "-v", f"{ruta}:/etc/otelcol/config.yaml:ro",
                              "-v", f"{salida}:/salida", _imagen(), "--config=/etc/otelcol/config.yaml"],
                             capture_output=True, text=True).stdout.strip()
        parar = lambda: subprocess.run(["docker", "rm", "-f", cid], capture_output=True)  # noqa: E731
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        yield puerto, salida / "t.jsonl"
    finally:
        parar()


def _traza_por_el_collector(tmp_path, editar=None) -> list[dict]:
    with collector_con_la_config_real(tmp_path, editar) as (puerto, archivo):
        vs.OTLP_HTTP = f"http://127.0.0.1:{puerto}/v1/traces"
        traza = vs.enviar_traza()
        lineas = []
        for _ in range(60):
            if archivo.exists() and traza in archivo.read_text():
                lineas = [json.loads(x) for x in archivo.read_text().splitlines() if traza in x]
                break
            time.sleep(0.25)
    assert lineas, "the trace never reached the file"
    return lineas


def test_collector_config_real_enmascara_cada_zona(tmp_path):
    lineas = _traza_por_el_collector(tmp_path)
    texto = json.dumps(lineas)
    zonas = vs.zonas_archivo(lineas)
    assert not vs.filtrados(texto, vs.CANARIOS), {z: vs.filtrados(t, vs.CANARIOS) for z, t in zonas.items()}
    assert all(not vs.filtrados(t, vs.CANARIOS) for t in zonas.values())
    assert "****" in texto
    # The gap measured in activity 2 (list-valued attributes were not redacted) is closed by the allowlist of activity 9:
    # the list attribute is not in the locked shape, so it is dropped whole.
    assert vs.filtrados(texto, vs.CANARIOS_LISTA) == []


def test_redaction_sola_no_cubre_nombre_estado_ni_eventos(tmp_path):
    """Why `transform/redaccion` exists: with `redaction` alone (the activity 1 pipeline) three string zones leak."""
    def solo_redaction(cfg):
        cfg["service"]["pipelines"]["traces"]["processors"] = ["memory_limiter", "redaction", "batch"]
        del cfg["processors"]["transform/redaccion"]
    lineas = _traza_por_el_collector(tmp_path, solo_redaction)
    zonas = vs.zonas_archivo(lineas)
    con_fuga = {z for z, t in zonas.items() if vs.filtrados(t, vs.CANARIOS)}
    assert con_fuga == {"span.name", "span.status.message", "span.event.name"}, con_fuga
    # what `redaction` does cover: resource, span and span-event attributes (strings), exception text included
    assert not vs.filtrados(zonas["resource.attributes"], vs.CANARIOS)
    assert not vs.filtrados(zonas["span.attributes"], vs.CANARIOS)
    assert not vs.filtrados(zonas["span.event.attributes"], vs.CANARIOS)


def test_redaction_en_lista_blanca_elimina_hasta_las_listas(tmp_path):
    """The way to close the list gap once the span shape is locked (activity 3): `allow_all_keys: false`."""
    permitidas = ["service.name", "gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.tool.name"]

    def lista_blanca(cfg):
        cfg["processors"]["redaction"]["allow_all_keys"] = False
        cfg["processors"]["redaction"]["allowed_keys"] = permitidas
    lineas = _traza_por_el_collector(tmp_path, lista_blanca)
    texto = json.dumps(lineas)
    assert vs.filtrados(texto, vs.CANARIOS_LISTA) == []
    assert not vs.filtrados(texto, vs.CANARIOS)
    claves = {a["key"] for rs in lineas[0]["resourceSpans"] for ss in rs["scopeSpans"] for sp in ss["spans"]
              for a in sp.get("attributes", [])}
    assert "prueba.lista" not in claves and claves <= set(permitidas) | {"redaction.redacted.keys", "redaction.redacted.count"}


# ---- the committed end-to-end evidence ------------------------------------------------------------------------
def test_evidencia_del_stack_de_punta_a_punta():
    r = json.loads((S17 / "resultados" / "stack.json").read_text(encoding="utf-8"))
    assert r["ok"] is True
    a = r["arranque"]
    assert a["codigo"] == 0 and a["langfuse_salud"] == 200 and a["collector_salud"] == 200
    assert a["secretos"]["permisos_600"] is True and a["version_langfuse"] == V["imagenes"]["langfuse-web"].rsplit(":", 1)[1]
    assert r["exposicion"]["ok"] and r["exposicion"]["por_digest"]
    assert r["exposicion"]["publicados"] == ["127.0.0.1:13133", "127.0.0.1:3100", "127.0.0.1:4317", "127.0.0.1:4318"]
    assert r["arranque"]["langfuse_web_healthy"] is True                              # the Docker healthcheck works
    assert r["arranque"]["secretos"]["longitud_clave_publica"] > 20 and r["arranque"]["secretos"]["longitud_clave_secreta"] > 30
    assert r["otlp"]["http_4318_acepta"] and r["otlp"]["grpc_4317_escucha"]
    assert 0 < r["memoria_mib_con_carga"] < 8192
    t = r["traza_1"]
    assert t["ok"] and t["en_archivo"] and t["observaciones"]["tipos"] == ["AGENT", "GENERATION", "TOOL"]
    assert t["canarios_en_archivo"] == [] and t["canarios_en_langfuse"] == []
    assert t["zonas_archivo_con_fuga"] == {} and t["campos_langfuse_con_fuga"] == {}
    assert t["enmascarado_en_archivo"] and t["enmascarado_en_langfuse"]
    assert t["hueco_listas"]["archivo"] == ["dsn_en_lista", "email_en_lista"]       # the known gap, measured
    assert r["reinicio"]["ok"] and r["reinicio"]["traza_previa_sigue_en_langfuse"] and r["reinicio"]["traza_previa_sigue_en_archivo"]
    assert r["caida_de_langfuse"]["ok"] and r["caida_de_langfuse"]["canarios_en_langfuse"] == []
    b = r["borrado"]
    assert b["ok"] and (b["contenedores"], b["volumenes"], b["redes"]) == (0, 0, 0) and b["datos_borrado"]


def test_evidencia_del_stack_sin_secretos_ni_rutas_locales():
    texto = (S17 / "resultados" / "stack.json").read_text(encoding="utf-8")
    for prohibido in ("/Users/", "/home/", "postgresql://", "Basic ", "sk-lf-", "canario-dsn-1234", "juan.perez"):
        assert prohibido not in texto, prohibido
    for valor in vs.leer_secretos().values() if vs.SECRETOS.exists() else []:
        if len(valor) >= 16:
            assert valor not in texto
