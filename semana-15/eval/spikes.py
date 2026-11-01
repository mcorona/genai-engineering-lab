"""Semana 15, actividad 6: spikes de OpenAI Agents SDK y Google ADK (mismo agente, Claude por LiteLLM, herramientas
por MCP) sobre las 10 tareas por idioma de la CI de la semana 13, k = 1.

    cd semana-15 && python eval/spikes.py --simular        # $0
    python eval/spikes.py --tope-usd 0.30                  # Haiku 5.5 low, ~$0.12 (se autoriza antes)

Escribe resultados/spikes_detalle.jsonl y resultados/spikes_tablas.md. Como referencia, en las mismas tareas: LangGraph
y Strands (actividad 5, k = 3), el loop propio y el Claude Agent SDK (semana 13, k = 3).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
if str(S15) not in sys.path:
    sys.path.insert(0, str(S15))
from eval import correr as base  # noqa: E402

from arnes.contrato import resultado_de_dict  # noqa: E402
from arnes.puente import Puente  # noqa: E402

RES = S15 / "resultados"
SPIKES = ("openai_agents", "google_adk")
TOPE_USD = 0.30


def tareas_ci() -> list[dict]:
    fuente = (base.S13 / "ci" / "eval_ci.py").read_text(encoding="utf-8")
    ids = eval(re.search(r"TAREAS_CI = (\[.*?\])", fuente).group(1))  # noqa: S307
    return [t for t in base.tareas() if t["id"].rsplit("-", 1)[0] in ids]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emisor", choices=["auto", "keycloak", "prueba"], default="auto")
    ap.add_argument("--tope-usd", type=float, default=TOPE_USD)
    ap.add_argument("--hilos", type=int, default=2)
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--solo-reporte", action="store_true")
    a = ap.parse_args(argv)
    if a.solo_reporte:
        return reporte(json.loads((RES / "spikes_meta.json").read_text()))
    if a.emisor == "auto":
        try:
            from auth import pkce
            pkce.descubrimiento()
            a.emisor = "keycloak" if pkce.SECRETOS.exists() else "prueba"
        except Exception:  # noqa: BLE001
            a.emisor = "prueba"
    seg = base.seguridad14()
    ent = seg.Entorno(a.emisor, con_base=True)
    token = base.Tokens(ent)
    from herramientas.conexion import conectar
    from agente.verificar import verificar
    doble, base_url = None, None
    if a.simular:
        from arnes.simulado import DobleAnthropic
        doble = DobleAnthropic(base.GuionFijo()).__enter__()
        base_url = doble.base_url
    det, trazas = RES / "spikes_detalle.jsonl", RES / "trazas" / "spikes.jsonl"
    for p in (det, trazas):
        p.unlink(missing_ok=True)
    trazas.parent.mkdir(parents=True, exist_ok=True)
    total, candado, sin_lanzar, locales = [0.0], threading.Lock(), [0], threading.local()
    import queue
    libres = {fw: queue.Queue() for fw in SPIKES}
    puentes = [Puente(fw, timeout_s=600) for fw in SPIKES for _ in range(a.hilos)]
    for p in puentes:
        libres[p.framework].put(p)

    def una(fw, t):
        with candado:
            if total[0] >= a.tope_usd:
                sin_lanzar[0] += 1
                return
        p = libres[fw].get()
        try:
            out = p.resolver(tarea={**t, "rep": 0}, mcp_url=ent.servidores["normal"].url, token=token(),
                             base_url=base_url, opciones={})
        finally:
            libres[fw].put(p)
        if "error" in out:
            fila = {"framework": fw, "id": t["id"], "rep": 0, "tipo": t["tipo"], "estado": "error", "exito": False,
                    "pasos": 0, "herramientas": 0, "errores_herramienta": 0, "tokens_in": 0, "tokens_out": 0,
                    "costo_usd": 0.0, "segundos": 0.0, "motivo": out["error"][:300], "respuesta": ""}
            eventos = []
        else:
            r = resultado_de_dict(out["resultado"])
            if not hasattr(locales, "conn"):
                locales.conn = conectar()[0]
            v = verificar(t, r.final, locales.conn, r.estado)
            fila = {"framework": fw, "id": t["id"], "rep": 0, "tipo": t["tipo"], "estado": r.estado, "exito": v["exito"],
                    "pasos": r.pasos, "herramientas": r.herramientas, "errores_herramienta": r.errores_herramienta,
                    "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "costo_usd": round(r.costo_usd, 6),
                    "segundos": r.segundos, "motivo": r.motivo, "respuesta": (r.final or {}).get("respuesta", "")[:300]}
            eventos = out.get("eventos", [])
        with candado:
            total[0] += fila["costo_usd"]
            with open(det, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
            with open(trazas, "a", encoding="utf-8") as f:
                f.writelines(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in eventos)
        print(f"{fw:<14} {t['id']:<7} {fila['estado']:<19} éxito={'sí' if fila['exito'] else 'NO':<3} "
              f"${fila['costo_usd']:.4f} {fila['segundos']:5.1f}s {fila['motivo'][:60] if fila['estado'] == 'error' else ''}"
              f"[acumulado ${total[0]:.3f}]", flush=True)

    ts = tareas_ci()
    print(f"{len(ts) * len(SPIKES)} corridas · emisor {a.emisor} · {'SIMULACIÓN ($0)' if a.simular else 'Haiku 5.5 low'} · "
          f"tope ${a.tope_usd:.2f}", flush=True)
    t0 = time.time()
    try:
        with ThreadPoolExecutor(a.hilos * len(SPIKES)) as ex:
            for f in as_completed([ex.submit(una, fw, t) for t in ts for fw in SPIKES]):
                f.result()
    finally:
        for p in puentes:
            p.cerrar()
        ent.cerrar()
        if doble:
            doble.__exit__()
    meta = {"emisor": a.emisor, "simulacion": a.simular, "costo_usd": round(total[0], 4), "sin_lanzar": sin_lanzar[0],
            "minutos": round((time.time() - t0) / 60, 1), "tope_usd": a.tope_usd}
    (RES / "spikes_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return reporte(meta)


def reporte(meta) -> int:
    filas = [json.loads(x) for x in open(RES / "spikes_detalle.jsonl", encoding="utf-8")]
    ids = {f["id"] for f in filas}
    grupos = {fw: [f for f in filas if f["framework"] == fw] for fw in SPIKES}
    previos = [json.loads(x) for x in open(RES / "frameworks_detalle.jsonl", encoding="utf-8")] \
        if (RES / "frameworks_detalle.jsonl").exists() else []
    for fw in ("langgraph", "strands"):
        grupos[f"{fw} (activity 5, k = 3)"] = [f for f in previos if f["framework"] == fw and f["id"] in ids]
    for nombre, archivo in (("own loop (week 13, k = 3)", "eval_haiku_low_detalle.jsonl"),
                            ("Claude Agent SDK (week 13, k = 3)", "eval_sdk_low_detalle.jsonl")):
        grupos[nombre] = [json.loads(x) for x in open(base.S13 / "resultados" / archivo, encoding="utf-8")
                          if json.loads(x)["id"] in ids]
    L = ["# Activity 6: spikes, generated tables (analysis in [spikes.md](spikes.md))", "",
         f"Generated by [`eval/spikes.py`](../eval/spikes.py). The week 13 CI tasks (10 × ES/EN), k = 1, Haiku 5.5 `low` "
         f"through LiteLLM, issuer `{meta['emisor']}`" + (", **SIMULATED MODEL**" if meta["simulacion"] else "")
         + f". Cost: **${meta['costo_usd']:.4f}** (cap ${meta['tope_usd']:.2f}); {meta['minutos']} min.", "",
         "| Agent | Runs | pass@1 | 95% CI (Wilson) | Cost / task | Tokens in / out | p50 / p95 (s) | Steps | Tool calls | Errors |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for g, fs in grupos.items():
        if not fs:
            continue
        ok = sum(bool(f["exito"]) for f in fs)
        lo, hi = base.wilson(ok, len(fs))
        seg = [f["segundos"] for f in fs]
        L.append(f"| {g} | {len(fs)} | **{ok / len(fs):.3f}** | {lo:.3f} to {hi:.3f} | "
                 f"${sum(f['costo_usd'] for f in fs) / len(fs):.4f} | {round(sum(f['tokens_in'] for f in fs) / len(fs)):,} / "
                 f"{round(sum(f['tokens_out'] for f in fs) / len(fs)):,} | {base.percentil(seg, .5)} / {base.percentil(seg, .95)} | "
                 f"{sum(f['pasos'] for f in fs) / len(fs):.2f} | {sum(f['herramientas'] for f in fs) / len(fs):.2f} | "
                 f"{sum(f['estado'] == 'error' for f in fs)} |")
    L += ["", "| Task | " + " | ".join(SPIKES) + " |", "|---|" + "---|" * len(SPIKES)]
    for i in sorted(ids):
        L.append(f"| {i} | " + " | ".join(next(("✓" if f["exito"] else f"✗ {f['estado']}") for f in grupos[fw] if f["id"] == i)
                                          if any(f["id"] == i for f in grupos[fw]) else "–" for fw in SPIKES) + " |")
    (RES / "spikes_tablas.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
