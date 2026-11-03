"""Week 17, activity 2: measure the observability stack end to end ($0, no model call). Mac only (needs Docker).

    python semana-17/observabilidad/verificar_stack.py [--salida resultados/stack.json]

It runs ./arrancar.sh, sends synthetic traces with seeded canaries through the Collector and checks:
  1. the stack comes up, with only four host ports, all on 127.0.0.1, and every image pinned by digest;
  2. a trace arrives in Langfuse (3 observations: AGENT, GENERATION, TOOL) and in the Collector's JSONL file;
  3. the canaries (DSN, OAuth token, bearer token, API key, email, phone, tax ID) come out redacted in BOTH, zone by
     zone (resource, span name, attributes, status message, event names, event attributes);
  4. list-valued attributes are NOT redacted (a known gap, measured and reported apart, see collector.yaml);
  5. after `./arrancar.sh --reiniciar` the data is still in Langfuse and a new trace flows;
  6. while Langfuse is down the file keeps receiving traces, and Langfuse gets them once it is back;
  7. `./arrancar.sh --borrar` leaves 0 containers, 0 volumes, 0 networks and no datos/.
It never prints a secret and the report has no local path. The stack must not exist when it starts (it would be
deleted at the end); .secretos.env is kept so the keys stay the same.
"""
from __future__ import annotations

import argparse
import base64
import json
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S17 = AQUI.parent
ARRANCAR = AQUI / "arrancar.sh"
DATOS = AQUI / "datos"
SECRETOS = AQUI / ".secretos.env"
PROYECTO = "s17-observabilidad"
LANGFUSE = "http://127.0.0.1:3100"
OTLP_HTTP = "http://127.0.0.1:4318/v1/traces"
ETIQUETA = f"com.docker.compose.project={PROYECTO}"

# name -> (value written into the span, the core that must NOT survive redaction)
CANARIOS = {
    "dsn": ("postgresql://legacy_auditor:canario-dsn-1234@db:5432/inventory", "canario-dsn-1234"),
    "oauth": ("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJjYW5hcmlvIn0.firmacanario1234567", "firmacanario1234567"),
    "bearer": ("Bearer canariotoken1234567890abc", "canariotoken1234567890abc"),
    "clave_api": ("sk-ant-canario1234567890", "sk-ant-canario1234567890"),
    "email": ("juan.perez@correo.example", "juan.perez@correo.example"),
    "telefono": ("33 0000 1201", "33 0000 1201"),
    "rfc": ("PEJU800101AB1", "PEJU800101AB1"),
}
# The known gap: values inside a LIST attribute (neither `redaction` nor `transform` reads lists).
CANARIOS_LISTA = {
    "dsn_en_lista": ("postgresql://legacy_auditor:canario-lista-dsn-77@db:5432/inventory", "canario-lista-dsn-77"),
    "email_en_lista": ("lista.canario@correo.example", "lista.canario@correo.example"),
}
TODOS = " | ".join(v for v, _ in CANARIOS.values())
SERVICIOS_INTERNOS = {"postgres", "clickhouse", "redis", "minio", "langfuse-worker"}
PUBLICADOS_ESPERADOS = {("127.0.0.1", p) for p in (3100, 4317, 4318, 13133)}


def correr(args: list[str], timeout: int = 600) -> tuple[int, int, str]:
    t0 = time.time()
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, round(time.time() - t0), (p.stdout + p.stderr)[-600:]


def docker(*args: str, timeout: int = 120) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout).stdout.strip()


def contenedores() -> list[dict]:
    filas = docker("ps", "-a", "--filter", f"label={ETIQUETA}", "--format",
                   '{{.ID}}|{{.Label "com.docker.compose.service"}}|{{.State}}|{{.Status}}|{{.Ports}}|{{.Names}}')
    salida = []
    for f in filas.splitlines():
        i, s, e, st, pu, n = f.split("|")
        salida.append({"id": i, "servicio": s, "estado": e, "status": st, "puertos": pu, "nombre": n})
    return salida


def restos() -> dict:
    cuenta = lambda *a: len(docker(*a).split())  # noqa: E731
    return {"contenedores": cuenta("ps", "-aq", "--filter", f"label={ETIQUETA}"),
            "volumenes": cuenta("volume", "ls", "-q", "--filter", f"label={ETIQUETA}"),
            "redes": cuenta("network", "ls", "-q", "--filter", f"label={ETIQUETA}")}


def leer_secretos() -> dict:
    return dict(l.split("=", 1) for l in SECRETOS.read_text().splitlines() if "=" in l and not l.startswith("#"))


def peticion(url: str, auth: str | None = None, cuerpo: dict | None = None, timeout: int = 20):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json"})
    if auth:
        req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            texto = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(texto) if texto.strip().startswith(("{", "[")) else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, {}


def auth_langfuse() -> str:
    s = leer_secretos()
    return base64.b64encode(f"{s['LANGFUSE_PUBLIC_KEY']}:{s['LANGFUSE_SECRET_KEY']}".encode()).decode()


def enviar_traza() -> str:
    """One LegacyBridge-shaped trace (agent, model call, tool call) with the canaries in every zone."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Status, StatusCode
    c = {k: v for k, (v, _) in CANARIOS.items()}
    tp = TracerProvider(resource=Resource.create({"service.name": "legacybridge-stack", "prueba.recurso": TODOS}))
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_HTTP, timeout=10)))
    tr = tp.get_tracer("legacybridge")
    with tr.start_as_current_span("invoke_agent legacybridge", attributes={
            "gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": "legacybridge",
            "prueba.atributo": TODOS, "prueba.lista": [v for v, _ in CANARIOS_LISTA.values()]}) as raiz:
        traza = format(raiz.get_span_context().trace_id, "032x")
        with tr.start_as_current_span("chat claude-haiku-5-5", attributes={
                "gen_ai.operation.name": "chat", "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": "claude-haiku-5-5", "gen_ai.usage.input_tokens": 1020,
                "gen_ai.usage.output_tokens": 30, "gen_ai.usage.cache_read.input_tokens": 900}):
            pass
        with tr.start_as_current_span("execute_tool describir_esquema " + c["email"] + " " + c["rfc"], attributes={
                "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "describir_esquema",
                "gen_ai.tool.call.id": "toolu_1", "prueba.atributo": TODOS}) as herr:
            herr.add_event("evento " + c["email"], attributes={"prueba.evento": TODOS})
            try:
                raise RuntimeError("fallo con " + c["dsn"] + " y " + c["bearer"])
            except RuntimeError as e:
                herr.record_exception(e)
            herr.set_status(Status(StatusCode.ERROR, "estado " + c["clave_api"] + " " + c["telefono"]))
    tp.force_flush()
    tp.shutdown()
    return traza


def filtrados(texto: str, canarios: dict) -> list[str]:
    return [k for k, (_, nucleo) in canarios.items() if nucleo in texto]


def lineas_de_traza(traza: str, espera: int = 15) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < espera:
        if (DATOS / "trazas.jsonl").exists():
            ls = [json.loads(l) for l in (DATOS / "trazas.jsonl").read_text().splitlines() if traza in l]
            if ls:
                return ls
        time.sleep(0.5)
    return []


def zonas_archivo(lineas: list[dict]) -> dict:
    """Text of each OTLP zone in the Collector's file: what a reader of the file could see."""
    z = {k: [] for k in ("resource.attributes", "span.name", "span.attributes", "span.status.message",
                         "span.event.name", "span.event.attributes")}
    for d in lineas:
        for rs in d.get("resourceSpans", []):
            z["resource.attributes"].append(json.dumps(rs.get("resource", {})))
            for ss in rs.get("scopeSpans", []):
                for sp in ss.get("spans", []):
                    z["span.name"].append(sp.get("name", ""))
                    z["span.attributes"].append(json.dumps(sp.get("attributes", [])))
                    z["span.status.message"].append(json.dumps(sp.get("status", {})))
                    for e in sp.get("events", []):
                        z["span.event.name"].append(e.get("name", ""))
                        z["span.event.attributes"].append(json.dumps(e.get("attributes", [])))
    return {k: "\n".join(v) for k, v in z.items()}


def observaciones(traza: str, auth: str, espera: int = 120, minimo: int = 3) -> list[dict]:
    t0 = time.time()
    obs: list = []
    while time.time() - t0 < espera:
        e, c = peticion(f"{LANGFUSE}/api/public/v2/observations?traceId={traza}&fields=core,basic,io,metadata,model,usage",
                        auth)
        obs = c.get("data", []) if e == 200 else []
        if len(obs) >= minimo:
            break
        time.sleep(3)
    return obs


def esperar_salud(espera: int = 180) -> int:
    t0 = time.time()
    while time.time() - t0 < espera:
        if peticion(f"{LANGFUSE}/api/public/health")[0] == 200 and peticion("http://127.0.0.1:13133/")[0] == 200:
            return round(time.time() - t0)
        time.sleep(2)
    return -1


def esperar_healthy(servicio: str, espera: int = 90) -> bool:
    """The Docker healthcheck of a service reports (healthy)."""
    t0 = time.time()
    while time.time() - t0 < espera:
        if any(c["servicio"] == servicio and "(healthy)" in c["status"] for c in contenedores()):
            return True
        time.sleep(2)
    return False


def exposicion() -> dict:
    publicados, sin_puerto, malos = set(), [], []
    for c in contenedores():
        hallados = []
        for ip, desde, hasta in re.findall(r"(\d+\.\d+\.\d+\.\d+|\[::\]):(\d+)(?:-(\d+))?->", c["puertos"]):
            hallados += [(ip, p) for p in range(int(desde), int(hasta or desde) + 1)]
        publicados |= set(hallados)
        if c["servicio"] in SERVICIOS_INTERNOS and hallados:
            malos.append(c["servicio"])
        if c["servicio"] in SERVICIOS_INTERNOS and not hallados:
            sin_puerto.append(c["servicio"])
    imagenes = [docker("inspect", "--format", "{{.Config.Image}}", c["id"]) for c in contenedores()]
    return {"publicados": sorted(f"{ip}:{p}" for ip, p in publicados), "internos_sin_puerto": sorted(sin_puerto),
            "por_digest": all("@sha256:" in i for i in imagenes) and len(imagenes) == 7,
            "ok": publicados == PUBLICADOS_ESPERADOS and not malos and set(sin_puerto) == SERVICIOS_INTERNOS}


def memoria_mib() -> int:
    total = 0.0
    for fila in docker("stats", "--no-stream", "--format", "{{.Name}}|{{.MemUsage}}").splitlines():
        if not fila.startswith(PROYECTO):
            continue
        usado = fila.split("|")[1].split("/")[0].strip()
        n, unidad = float(re.sub(r"[^\d.]", "", usado)), re.sub(r"[\d.\s]", "", usado)
        total += n * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}.get(unidad, 0)
    return round(total)


def medir_traza(traza: str, auth: str) -> dict:
    lineas = lineas_de_traza(traza)
    zonas = zonas_archivo(lineas)
    texto_archivo = json.dumps(lineas)
    obs = observaciones(traza, auth)
    texto_lf = json.dumps(obs, ensure_ascii=False)
    por_zona_lf = {campo: "\n".join(json.dumps(o.get(campo), ensure_ascii=False) for o in obs)
                   for campo in ("name", "statusMessage", "metadata", "input", "output")}
    return {
        "en_archivo": bool(lineas),
        "observaciones": {"n": len(obs), "tipos": sorted(o.get("type") for o in obs)},
        "canarios_en_archivo": filtrados(texto_archivo, CANARIOS),
        "canarios_en_langfuse": filtrados(texto_lf, CANARIOS),
        "zonas_archivo_con_fuga": {z: filtrados(t, CANARIOS) for z, t in zonas.items() if filtrados(t, CANARIOS)},
        "campos_langfuse_con_fuga": {z: filtrados(t, CANARIOS) for z, t in por_zona_lf.items() if filtrados(t, CANARIOS)},
        "enmascarado_en_archivo": "****" in texto_archivo,
        "enmascarado_en_langfuse": "****" in texto_lf,
        "hueco_listas": {"archivo": filtrados(texto_archivo, CANARIOS_LISTA),
                         "langfuse": filtrados(texto_lf, CANARIOS_LISTA)},
    }


def traza_ok(m: dict) -> bool:
    return (m["en_archivo"] and m["observaciones"]["tipos"] == ["AGENT", "GENERATION", "TOOL"]
            and not m["canarios_en_archivo"] and not m["canarios_en_langfuse"]
            and not m["zonas_archivo_con_fuga"] and not m["campos_langfuse_con_fuga"]
            and m["enmascarado_en_archivo"] and m["enmascarado_en_langfuse"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", type=Path, default=S17 / "resultados" / "stack.json")
    a = ap.parse_args(argv)
    if not docker("version", "--format", "{{.Server.Version}}"):
        print("Docker is not running", file=sys.stderr)
        return 2
    if contenedores():
        print("The stack already exists: this check deletes it at the end. Run ./arrancar.sh --borrar first.",
              file=sys.stderr)
        return 2
    r: dict = {"fecha": time.strftime("%Y-%m-%d"), "donde": "mac" if platform.system() == "Darwin" else "linux",
               "python": platform.python_version(), "docker": docker("version", "--format", "{{.Server.Version}}")}

    rc, seg, cola = correr([str(ARRANCAR)])
    r["arranque"] = {"codigo": rc, "segundos_totales": seg}
    if rc:
        print(cola, file=sys.stderr)
        return 1
    s = leer_secretos()
    auth = auth_langfuse()
    r["arranque"]["version_langfuse"] = peticion(f"{LANGFUSE}/api/public/health")[1].get("version")
    r["arranque"]["secretos"] = {"permisos_600": oct(SECRETOS.stat().st_mode & 0o777) == "0o600",
                                 "variables": len(s),
                                 "longitud_clave_publica": len(s["LANGFUSE_PUBLIC_KEY"]),
                                 "longitud_clave_secreta": len(s["LANGFUSE_SECRET_KEY"])}
    r["exposicion"] = exposicion()
    r["arranque"]["langfuse_web_healthy"] = esperar_healthy("langfuse-web")
    r["arranque"]["langfuse_salud"] = peticion(f"{LANGFUSE}/api/public/health")[0]
    r["arranque"]["collector_salud"] = peticion("http://127.0.0.1:13133/")[0]
    r["arranque"]["ok"] = (rc == 0 and r["arranque"]["langfuse_web_healthy"] and r["arranque"]["langfuse_salud"] == 200
                           and r["arranque"]["collector_salud"] == 200 and r["arranque"]["secretos"]["permisos_600"])
    r["otlp"] = {"http_4318_acepta": peticion(OTLP_HTTP, cuerpo={"resourceSpans": []})[0] == 200}
    try:
        socket.create_connection(("127.0.0.1", 4317), timeout=3).close()
        r["otlp"]["grpc_4317_escucha"] = True   # TCP only: no gRPC client is installed in the lab (see stack.md)
    except OSError:
        r["otlp"]["grpc_4317_escucha"] = False

    # 2 and 3: a trace with canaries in every zone, in Langfuse and in the file
    traza1 = enviar_traza()
    r["traza_1"] = medir_traza(traza1, auth)
    r["traza_1"]["ok"] = traza_ok(r["traza_1"])
    r["memoria_mib_con_carga"] = memoria_mib()

    # 5: restart, data persists, a new trace flows
    rc, seg, cola = correr([str(ARRANCAR), "--reiniciar"])
    previa = observaciones(traza1, auth, espera=60)
    antes_en_archivo = bool(lineas_de_traza(traza1, espera=5))
    traza2 = enviar_traza()
    nueva = medir_traza(traza2, auth)
    r["reinicio"] = {"codigo": rc, "segundos": seg, "servicios_corriendo": sorted(
        c["servicio"] for c in contenedores() if c["estado"] == "running"),
        "traza_previa_sigue_en_langfuse": len(previa) == 3, "traza_previa_sigue_en_archivo": antes_en_archivo,
        "traza_nueva": {"observaciones": nueva["observaciones"]["n"], "en_archivo": nueva["en_archivo"],
                        "ok": traza_ok(nueva)}}
    r["reinicio"]["ok"] = (rc == 0 and len(r["reinicio"]["servicios_corriendo"]) == 7 and len(previa) == 3
                           and antes_en_archivo and r["reinicio"]["traza_nueva"]["ok"])

    # 6: Langfuse down: the file keeps receiving; Langfuse gets the trace when it is back
    web = next(c["id"] for c in contenedores() if c["servicio"] == "langfuse-web")
    docker("stop", web)
    caida_t0 = time.time()
    traza3 = enviar_traza()
    en_archivo = bool(lineas_de_traza(traza3, espera=15))
    docker("start", web)
    salud = esperar_salud()
    obs3 = observaciones(traza3, auth, espera=240)
    r["caida_de_langfuse"] = {"traza_en_archivo_mientras_caido": en_archivo, "segundos_hasta_salud": salud,
                              "observaciones_tras_volver": len(obs3),
                              "segundos_hasta_entrega": round(time.time() - caida_t0),
                              "entregada": len(obs3) == 3,
                              "canarios_en_langfuse": filtrados(json.dumps(obs3, ensure_ascii=False), CANARIOS)}
    r["caida_de_langfuse"]["ok"] = (en_archivo and len(obs3) == 3 and not r["caida_de_langfuse"]["canarios_en_langfuse"])

    # 7: remove everything
    rc, seg, cola = correr([str(ARRANCAR), "--borrar"])
    r["borrado"] = {"codigo": rc, "segundos": seg, **restos(), "datos_borrado": not DATOS.exists(),
                    "secretos_conservados": SECRETOS.exists()}
    r["borrado"]["ok"] = (rc == 0 and r["borrado"]["contenedores"] == r["borrado"]["volumenes"] == r["borrado"]["redes"] == 0
                          and r["borrado"]["datos_borrado"])
    r["ok"] = (r["arranque"]["langfuse_salud"] == 200 and r["arranque"]["collector_salud"] == 200
               and r["arranque"]["langfuse_web_healthy"]
               and r["arranque"]["secretos"]["permisos_600"] and r["exposicion"]["ok"] and r["exposicion"]["por_digest"]
               and r["otlp"]["http_4318_acepta"] and r["otlp"]["grpc_4317_escucha"]
               and r["traza_1"]["ok"] and r["reinicio"]["ok"] and r["caida_de_langfuse"]["ok"] and r["borrado"]["ok"])
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for nombre in ("arranque", "exposicion", "traza_1", "reinicio", "caida_de_langfuse", "borrado"):
        ok = r[nombre].get("ok", r[nombre].get("codigo") == 0)
        print(f"  {'OK' if ok else 'FALLA'}  {nombre}")
    print(f"\n{'stack OK' if r['ok'] else 'stack con fallas'}; evidence: {a.salida.name}")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
