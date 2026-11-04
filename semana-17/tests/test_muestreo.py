"""Optional of activity 2 (tail sampling in the Collector), no API and no Langfuse: the overlay `observabilidad/muestreo.yaml`
is checked statically, merged with `collector.yaml` by the real Collector (binary in CI, Docker image on the Mac) and run
with a mix of traces to see what it keeps. The end-to-end run with Langfuse is `observabilidad/verificar_muestreo.py`."""
import copy
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import yaml

S17 = Path(__file__).resolve().parents[1]
OBS = S17 / "observabilidad"
V = json.loads((S17 / "preparar" / "versiones.json").read_text(encoding="utf-8"))
BASE = yaml.safe_load((OBS / "collector.yaml").read_text(encoding="utf-8"))
MUESTREO = yaml.safe_load((OBS / "muestreo.yaml").read_text(encoding="utf-8"))
SIN_MUESTREO = yaml.safe_load((OBS / "sin_muestreo.yaml").read_text(encoding="utf-8"))
COMPOSE = yaml.safe_load((OBS / "docker-compose.yml").read_text(encoding="utf-8"))
ARRANCAR = (OBS / "arrancar.sh").read_text(encoding="utf-8")
CANARIO = "ana.garcia@example.com"


# ---------- static ----------

def test_la_capa_de_muestreo_conserva_errores_no_respondidas_y_lentas_y_muestrea_el_resto():
    politicas = {p["name"]: p for p in MUESTREO["processors"]["tail_sampling"]["policies"]}
    assert list(politicas) == ["con-error", "tarea-no-respondida", "lentas", "muestra"]
    assert politicas["con-error"]["status_code"]["status_codes"] == ["ERROR"]
    sa = politicas["tarea-no-respondida"]["string_attribute"]
    assert sa["key"] == "lab.outcome.status" and sorted(sa["values"]) == sorted(
        ["abstenida", "requiere_aclaracion", "limite_alcanzado", "error"])        # everything but `respondida`
    assert politicas["lentas"]["latency"]["threshold_ms"] == 60000
    assert 0 < politicas["muestra"]["probabilistic"]["sampling_percentage"] <= 25
    ts = MUESTREO["processors"]["tail_sampling"]
    assert int(ts["decision_wait"].rstrip("s")) >= 30                              # longer than a normal task
    assert ts["num_traces"] >= 1000


def test_el_muestreo_corre_despues_de_la_redaccion_y_antes_del_batch():
    base = BASE["service"]["pipelines"]["traces"]["processors"]
    sobre = MUESTREO["service"]["pipelines"]["traces"]["processors"]
    assert sobre == ["memory_limiter", "redaction", "transform/redaccion", "tail_sampling", "batch"]
    assert [p for p in sobre if p != "tail_sampling"] == base                       # only one processor is added
    assert "service" not in SIN_MUESTREO or "pipelines" not in SIN_MUESTREO["service"]      # the no-op overlay keeps the default
    # the default stack keeps every trace: tail sampling is not in collector.yaml (activity 7 scores them all)
    assert "tail_sampling" not in BASE["processors"] and "tail_sampling" not in base


def test_compose_monta_las_dos_capas_y_arrancar_sh_elige_una():
    col = COMPOSE["services"]["collector"]
    assert col["command"] == ["--config=/etc/otelcol/config.yaml", "--config=/etc/otelcol/${COLLECTOR_CAPA:-sin_muestreo}.yaml"]
    assert "./muestreo.yaml:/etc/otelcol/muestreo.yaml:ro" in col["volumes"]
    assert "./sin_muestreo.yaml:/etc/otelcol/sin_muestreo.yaml:ro" in col["volumes"]
    assert "--muestreo" in ARRANCAR and "COLLECTOR_CAPA=muestreo" in ARRANCAR and "COLLECTOR_CAPA=sin_muestreo" in ARRANCAR
    assert "solo se usa al arrancar o reiniciar" in ARRANCAR                        # --muestreo with --detener or --borrar is refused
    p = subprocess.run(["bash", str(OBS / "arrancar.sh"), "--muestreo", "--detener"], capture_output=True, text=True,
                       env={**os.environ, "PATH": os.environ["PATH"]})
    assert p.returncode == 2 and "solo se usa al arrancar o reiniciar" in p.stderr


# ---------- the real Collector ----------

def _binario():
    return os.environ.get("OTELCOL_BIN") or shutil.which("otelcol-contrib")


def _imagen():
    return f"{V['imagenes']['otel-collector'].rsplit(':', 1)[0]}@{V['digests']['otel-collector']}"


def test_el_collector_real_mezcla_collector_y_capa_y_las_valida():
    binario = _binario()
    for capa in ("muestreo", "sin_muestreo"):
        if binario:
            cmd = [binario, "validate", f"--config={OBS / 'collector.yaml'}", f"--config={OBS / (capa + '.yaml')}"]
        else:
            assert shutil.which("docker"), "needs OTELCOL_BIN, otelcol-contrib on PATH or Docker"
            cmd = ["docker", "run", "--rm", "-e", "LANGFUSE_AUTH=x", "-v", f"{OBS}:/cfg:ro", _imagen(), "validate",
                   "--config=/cfg/collector.yaml", f"--config=/cfg/{capa}.yaml"]
        p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "LANGFUSE_AUTH": "x"})
        assert p.returncode == 0, (capa, p.stderr[-500:])


def _lanzar(tmp_path, overlay: dict):
    """The real two-file merge: derived base (file exporter, one HTTP port) plus the overlay as a second `--config`."""
    binario = _binario()
    assert binario or shutil.which("docker"), "needs OTELCOL_BIN, otelcol-contrib on PATH or Docker"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    salida = tmp_path / "salida"
    salida.mkdir()
    os.chmod(salida, 0o777)
    cfg = copy.deepcopy(BASE)
    del cfg["extensions"], cfg["service"]["extensions"]
    cfg["exporters"] = {"file": {"path": str(salida / "t.jsonl") if binario else "/salida/t.jsonl", "flush_interval": "200ms"}}
    cfg["service"]["pipelines"]["traces"]["exporters"] = ["file"]
    cfg["receivers"]["otlp"]["protocols"] = {"http": {"endpoint": f"127.0.0.1:{puerto}" if binario else "0.0.0.0:4318"}}
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
    (tmp_path / "capa.yaml").write_text(yaml.safe_dump(overlay, allow_unicode=True))
    if binario:
        proc = subprocess.Popen([binario, f"--config={tmp_path / 'base.yaml'}", f"--config={tmp_path / 'capa.yaml'}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parar = proc.terminate
    else:
        cid = subprocess.run(["docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{puerto}:4318", "-v", f"{tmp_path}:/cfg:ro",
                              "-v", f"{salida}:/salida", _imagen(), "--config=/cfg/base.yaml", "--config=/cfg/capa.yaml"],
                             capture_output=True, text=True).stdout.strip()
        parar = lambda: subprocess.run(["docker", "rm", "-f", cid], capture_output=True)  # noqa: E731
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", puerto), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.2)
    return puerto, salida / "t.jsonl", parar


def _enviar(puerto: int, mezcla: dict) -> dict[str, set[str]]:
    """Traces of each kind with the canary in an attribute. Returns the trace ids per kind."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    tp = TracerProvider(resource=Resource.create({"service.name": "muestreo-prueba"}))
    tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"http://127.0.0.1:{puerto}/v1/traces", timeout=20)))
    tr = tp.get_tracer("muestreo")
    ids = {k: set() for k in mezcla}
    ahora = time.time_ns()
    for clase, n in mezcla.items():
        for _ in range(n):
            estado = {"ok": "respondida", "con_error": "respondida", "abstenida": "abstenida", "limite": "limite_alcanzado",
                      "lenta": "respondida"}[clase]
            inicio = ahora - (90 * 10**9 if clase == "lenta" else 0)
            raiz = tr.start_span("invoke_agent legacybridge", start_time=inicio, attributes={
                "lab.outcome.status": estado, "gen_ai.operation.name": "invoke_agent", "prueba.canario": CANARIO})
            ids[clase].add(format(raiz.get_span_context().trace_id, "032x"))
            with trace.use_span(raiz, end_on_exit=False):
                hijo = tr.start_span("chat claude-haiku-5-5", start_time=inicio)
                if clase == "con_error":
                    hijo.set_status(Status(StatusCode.ERROR, "api_error"))
                hijo.end(end_time=ahora)
            raiz.end(end_time=ahora)
    tp.force_flush()
    return ids


def _conservadas(archivo: Path, espera_s: float = 25.0) -> tuple[set[str], str]:
    t0, anterior = time.time(), -1
    while time.time() - t0 < espera_s:
        texto = archivo.read_text() if archivo.exists() else ""
        if texto and len(texto) == anterior:
            break
        anterior = len(texto)
        time.sleep(2.5)
    texto = archivo.read_text() if archivo.exists() else ""
    ids = set()
    for linea in texto.splitlines():
        for rs in json.loads(linea)["resourceSpans"]:
            for ss in rs["scopeSpans"]:
                ids |= {sp["traceId"] for sp in ss["spans"]}
    return ids, texto


def test_el_muestreo_real_conserva_lo_que_importa_y_solo_muestrea_lo_demas(tmp_path):
    overlay = copy.deepcopy(MUESTREO)
    overlay["processors"]["tail_sampling"]["decision_wait"] = "3s"                 # timing only; the policies are the file's
    puerto, archivo, parar = _lanzar(tmp_path, overlay)
    try:
        mezcla = {"ok": 120, "con_error": 6, "abstenida": 5, "limite": 3, "lenta": 3}
        ids = _enviar(puerto, mezcla)
        conservadas, texto = _conservadas(archivo)
    finally:
        parar()
    for clase in ("con_error", "abstenida", "limite", "lenta"):
        assert ids[clase] <= conservadas, (clase, len(ids[clase] & conservadas), len(ids[clase]))     # kept 100 %
    ok = len(ids["ok"] & conservadas)
    assert 0 < ok < mezcla["ok"], ok                                               # a sample: not none, not all (10 % of 120)
    assert ok <= 0.3 * mezcla["ok"]
    # redaction ran before sampling: not even the kept traces carry the canary. Since activity 9 the key that carried it
    # (`prueba.canario`) is not in the allowlist, so it is dropped whole instead of masked.
    assert CANARIO not in texto and '"prueba.canario"' not in texto
    assert not (conservadas - set().union(*ids.values()))


def test_sin_la_capa_se_conservan_todas(tmp_path):
    """The default stack (no-op overlay) keeps everything: tail sampling is only there when asked for."""
    puerto, archivo, parar = _lanzar(tmp_path, SIN_MUESTREO)
    try:
        ids = _enviar(puerto, {"ok": 40, "con_error": 2})
        conservadas, texto = _conservadas(archivo, espera_s=12)
    finally:
        parar()
    assert set().union(*ids.values()) <= conservadas and CANARIO not in texto


# ---------- the evidence of the Mac run ----------

def test_la_evidencia_del_muestreo_con_langfuse():
    """`observabilidad/verificar_muestreo.py` needs the stack, so it runs on the Mac; its committed result is checked here."""
    texto = (S17 / "resultados" / "muestreo.json").read_text(encoding="utf-8")
    r = json.loads(texto)
    assert r["ok"] is True and r["capa_activa"] is True and r["capa_por_omision"] is True
    por_clase = r["con_muestreo"]["por_clase"]
    for clase in ("con_error", "abstenida", "limite", "lenta"):
        c = por_clase[clase]
        assert c["en_langfuse"] == c["enviadas"] == c["en_archivo"] > 0, clase       # every critical trace kept, in both places
    assert 0 < por_clase["ok"]["en_langfuse"] < por_clase["ok"]["enviadas"]          # a sample of the rest, not all, not none
    assert por_clase["ok"]["en_langfuse"] == por_clase["ok"]["en_archivo"]
    assert r["con_muestreo"]["langfuse_igual_al_archivo"] is True and r["con_muestreo"]["criticas_llegaron"] is True
    assert r["con_muestreo"]["canario_en_el_archivo"] is False
    assert r["sin_muestreo"] == {"enviadas": 10, "en_langfuse": 10, "todas": True}   # the default keeps everything
    assert r["mezcla"] == {k: v["enviadas"] for k, v in por_clase.items()}
    for prohibido in ("/Users/", "127.0.0.1", "ana.garcia"):
        assert prohibido not in texto
