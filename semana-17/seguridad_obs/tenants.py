"""Week 17, activity 9: one Langfuse project per tenant, and proof that one tenant's keys cannot see another's traces ($0, stack up).

    cd semana-17 && uv run --group semana17 python -m seguridad_obs.tenants

Langfuse OSS has no admin API for projects ("not available on your current plan": the `/api/admin` routes and organization keys are
Enterprise). The project and its keys are created the way an administrator does it in the UI, through the UI's own API (login with the
admin user of `.secretos.env`, `projects.create`, `projectApiKeys.create`), once: the keys are appended to `.secretos.env`
(`LANGFUSE_B_*`, mode 600) and never printed. Then:

1. one trace is exported straight to each project's OTLP endpoint with that project's keys (in production: one exporter per tenant,
   chosen by the tenant of the run, never by the payload);
2. each project's keys read its own trace and do NOT see the other's (`v2/observations?traceId=` returns nothing), and neither key can
   delete the other's trace.
"""
from __future__ import annotations

import base64
import http.cookiejar
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

LANGFUSE = "http://127.0.0.1:3100"
PROYECTO_B = "legacybridge-tenant-b"
RESULTADOS = S17 / "resultados"


def _vs():
    spec = importlib.util.spec_from_file_location("verificar_stack_s17_t9", S17 / "observabilidad" / "verificar_stack.py")
    vs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vs)
    return vs


class SesionUI:
    """The admin's browser session, without a browser."""

    def __init__(self, email: str, clave: str):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        csrf = json.loads(self.op.open(f"{LANGFUSE}/api/auth/csrf").read())["csrfToken"]
        datos = urllib.parse.urlencode({"csrfToken": csrf, "email": email, "password": clave, "json": "true", "callbackUrl": LANGFUSE}).encode()
        self.op.open(urllib.request.Request(f"{LANGFUSE}/api/auth/callback/credentials", data=datos,
                                            headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if json.loads(self.op.open(f"{LANGFUSE}/api/auth/session").read()).get("user", {}).get("email") != email:
            raise RuntimeError("login failed")

    def mutacion(self, procedimiento: str, entrada: dict) -> dict:
        req = urllib.request.Request(f"{LANGFUSE}/api/trpc/{procedimiento}", data=json.dumps({"json": entrada}).encode(),
                                     headers={"Content-Type": "application/json"})
        with self.op.open(req) as r:
            return json.loads(r.read())["result"]["data"]["json"]


def asegurar_proyecto_b() -> dict:
    """The tenant B project and its keys, created once. Returns the secrets dict (never printed)."""
    vs = _vs()
    s = vs.leer_secretos()
    if s.get("LANGFUSE_B_PUBLIC_KEY") and s.get("LANGFUSE_B_SECRET_KEY"):
        return s
    ui = SesionUI("admin@lab.example", s["LANGFUSE_USER_PASSWORD"])
    p = ui.mutacion("projects.create", {"name": PROYECTO_B, "orgId": "lab-org"})
    k = ui.mutacion("projectApiKeys.create", {"projectId": p["id"], "note": "tenant B, week 17 activity 9"})
    with open(vs.SECRETOS, "a", encoding="utf-8") as f:
        f.write(f"LANGFUSE_B_PROJECT_ID={p['id']}\nLANGFUSE_B_PUBLIC_KEY={k['publicKey']}\nLANGFUSE_B_SECRET_KEY={k['secretKey']}\n")
    os.chmod(vs.SECRETOS, 0o600)
    return vs.leer_secretos()


def _auth(pk: str, sk: str) -> str:
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()


def exportar_traza(auth: str, tenant: str) -> str:
    """One span straight to a project's OTLP endpoint, with that project's keys. Returns the trace id."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    prov = TracerProvider(resource=Resource.create({"service.name": "legacybridge"}))
    prov.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{LANGFUSE}/api/public/otel/v1/traces",
                                                                 headers={"Authorization": f"Basic {auth}"})))
    with prov.get_tracer("aislamiento").start_as_current_span("invoke_agent legacybridge") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("lab.tenant.id", tenant)
        traza = format(span.get_span_context().trace_id, "032x")
    prov.shutdown()
    return traza


def ve(auth: str, traza: str, espera_s: int = 0) -> int:
    peticion = _vs().peticion
    t0 = time.time()
    while True:
        c, b = peticion(f"{LANGFUSE}/api/public/v2/observations?traceId={traza}&fields=core&limit=10", auth)
        n = len(b.get("data") or []) if c == 200 else 0
        if n or time.time() - t0 >= espera_s:
            return n
        time.sleep(3)


def borra(auth: str, traza: str) -> int:
    req = urllib.request.Request(f"{LANGFUSE}/api/public/traces/{traza}", method="DELETE", headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> int:
    s = asegurar_proyecto_b()
    a = _auth(s["LANGFUSE_PUBLIC_KEY"], s["LANGFUSE_SECRET_KEY"])
    b = _auth(s["LANGFUSE_B_PUBLIC_KEY"], s["LANGFUSE_B_SECRET_KEY"])
    peticion = _vs().peticion
    proyectos = {nombre: [p["id"] for p in (peticion(f"{LANGFUSE}/api/public/projects", auth)[1].get("data") or [])]
                 for nombre, auth in (("a", a), ("b", b))}
    ta, tb = exportar_traza(a, "lab"), exportar_traza(b, "tenant-b")
    visto = {"a_ve_a": ve(a, ta, 90), "b_ve_b": ve(b, tb, 90), "a_ve_b": ve(a, tb), "b_ve_a": ve(b, ta)}
    # a delete with the other project's keys must not remove anything: the trace is still visible to its owner after it
    borrado_cruzado = {"a_borra_b": borra(a, tb), "b_borra_a": borra(b, ta)}
    time.sleep(180)                 # deletion is asynchronous (1 to 2 minutes measured by retencion.py): wait it out before judging
    sigue = {"b_sigue_viendo_b": ve(b, tb), "a_sigue_viendo_a": ve(a, ta)}
    informe = {"fecha": time.strftime("%Y-%m-%d"), "proyectos_que_ve_cada_llave": {k: len(v) for k, v in proyectos.items()},
               "las_llaves_ven_un_solo_proyecto_y_distinto": len(proyectos["a"]) == len(proyectos["b"]) == 1 and proyectos["a"] != proyectos["b"],
               "observaciones": visto, "borrado_con_la_llave_ajena_http": borrado_cruzado, "despues_del_borrado_ajeno": sigue}
    informe["ok"] = (informe["las_llaves_ven_un_solo_proyecto_y_distinto"] and visto["a_ve_a"] > 0 and visto["b_ve_b"] > 0
                     and visto["a_ve_b"] == 0 and visto["b_ve_a"] == 0 and sigue["b_sigue_viendo_b"] > 0 and sigue["a_sigue_viendo_a"] > 0)
    (RESULTADOS / "seguridad_obs_tenants.json").write_text(json.dumps(informe, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(informe, indent=1))
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
