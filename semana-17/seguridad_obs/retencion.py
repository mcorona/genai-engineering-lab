"""Week 17, activity 9: the retention policy of the traces, as a job ($0, stack up).

    cd semana-17
    uv run --group semana17 python -m seguridad_obs.retencion --dias 30                 # dry run on the main project: what would go
    uv run --group semana17 python -m seguridad_obs.retencion --dias 30 --borrar        # delete it
    uv run --group semana17 python -m seguridad_obs.retencion --demostrar               # proof on the tenant B project only

Langfuse OSS cannot set a retention per project (the `data-retention` entitlement is Enterprise; measured in activity 9). So the policy
is a job: list the observations that started before `now - dias` (`v2/observations?toStartTime=`), take their trace ids, and delete those
traces in batches (`DELETE /api/public/traces`). Dry run by default. Run it daily (cron, or the CI of the environment that hosts Langfuse).

The policy (resultados/seguridad_obs.md): traces 30 days in Langfuse; the Collector's raw file 7 days of rotated backups (and at most
5 x 20 MB); nothing with message content is kept, because the Collector drops it (allowlist).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from seguridad_obs.tenants import LANGFUSE, _auth, _vs, asegurar_proyecto_b, ve  # noqa: E402

RESULTADOS = S17 / "resultados"
DIAS_POR_OMISION = 30
LOTE = 100


def trazas_viejas(auth: str, dias: float, ahora: datetime | None = None, tope: int = 50_000) -> list[str]:
    import urllib.parse
    corte = (ahora or datetime.now(timezone.utc)) - timedelta(days=dias)
    peticion = _vs().peticion
    vistas, cursor = [], None
    while len(vistas) < tope:
        url = f"{LANGFUSE}/api/public/v2/observations?toStartTime={corte.strftime('%Y-%m-%dT%H:%M:%SZ')}&fields=core&limit=1000"
        c, b = peticion(url + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else ""), auth)
        if c != 200:
            raise RuntimeError(f"listing observations failed: HTTP {c}")
        vistas += [o["traceId"] for o in b.get("data") or [] if o.get("traceId")]
        cursor = (b.get("meta") or {}).get("cursor")
        if not cursor or not b.get("data"):
            break
    return sorted(set(vistas))


def borrar(auth: str, trazas: list[str]) -> int:
    borradas = 0
    for i in range(0, len(trazas), LOTE):
        lote = trazas[i:i + LOTE]
        req = urllib.request.Request(f"{LANGFUSE}/api/public/traces", data=json.dumps({"traceIds": lote}).encode(), method="DELETE",
                                     headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            borradas += len(lote) if r.status == 200 else 0
    return borradas


def _traza_con_fecha(auth: str, hace_dias: float) -> str:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    prov = TracerProvider(resource=Resource.create({"service.name": "legacybridge"}))
    prov.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{LANGFUSE}/api/public/otel/v1/traces",
                                                                 headers={"Authorization": f"Basic {auth}"})))
    inicio = int((time.time() - hace_dias * 86400) * 1e9)
    span = prov.get_tracer("retencion").start_span("invoke_agent legacybridge", start_time=inicio)
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    traza = format(span.get_span_context().trace_id, "032x")
    span.end(end_time=inicio + 1_000_000)
    prov.shutdown()
    return traza


def demostrar() -> dict:
    """On tenant B's project only: a trace from 10 days ago and one from now; the job with 7 days deletes the old one and only it."""
    s = asegurar_proyecto_b()
    b = base64.b64encode(f"{s['LANGFUSE_B_PUBLIC_KEY']}:{s['LANGFUSE_B_SECRET_KEY']}".encode()).decode()
    vieja, nueva = _traza_con_fecha(b, 10), _traza_con_fecha(b, 0)
    antes = {"vieja": ve(b, vieja, 90), "nueva": ve(b, nueva, 90)}
    candidatas = trazas_viejas(b, 7)
    borradas = borrar(b, candidatas)
    despues, t0 = {}, time.time()
    while time.time() - t0 < 300:                 # Langfuse deletes asynchronously (its worker): measured 1 to 2 minutes
        despues = {"vieja": ve(b, vieja), "nueva": ve(b, nueva)}
        if despues["vieja"] == 0:
            break
        time.sleep(5)
    despues["segundos_hasta_desaparecer"] = round(time.time() - t0)
    informe = {"fecha": time.strftime("%Y-%m-%d"), "proyecto": "tenant B", "dias": 7, "antes": antes, "candidatas": len(candidatas),
               "la_vieja_era_candidata": vieja in candidatas, "la_nueva_era_candidata": nueva in candidatas, "borradas": borradas,
               "despues": despues}
    informe["ok"] = (antes["vieja"] > 0 and antes["nueva"] > 0 and informe["la_vieja_era_candidata"] and not informe["la_nueva_era_candidata"]
                     and despues["vieja"] == 0 and despues["nueva"] > 0)
    return informe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=float, default=DIAS_POR_OMISION)
    ap.add_argument("--borrar", action="store_true", help="delete (default: dry run)")
    ap.add_argument("--demostrar", action="store_true", help="the proof on tenant B's project")
    a = ap.parse_args(argv)
    if a.demostrar:
        informe = demostrar()
        (RESULTADOS / "seguridad_obs_retencion.json").write_text(json.dumps(informe, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(informe, indent=1))
        return 0 if informe["ok"] else 1
    s = _vs().leer_secretos()
    auth = _auth(s["LANGFUSE_PUBLIC_KEY"], s["LANGFUSE_SECRET_KEY"])
    viejas = trazas_viejas(auth, a.dias)
    borradas = borrar(auth, viejas) if a.borrar else 0
    print(json.dumps({"dias": a.dias, "trazas_mas_viejas": len(viejas), "borradas": borradas, "modo": "borrar" if a.borrar else "prueba"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
