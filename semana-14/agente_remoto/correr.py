"""Week 14, activity 7: the week 13 agent against the remote MCP server (Streamable HTTP + OAuth).

    cd semana-14 && python agente_remoto/correr.py --simular            # $0: validates Keycloak, the servers, the database and the report
    python agente_remoto/correr.py --tope-usd 0.35                      # Haiku 5.5 low, ~ $0.25

The same loop, model and prompt as week 13; only the path the tools take changes:

- **remote**: Streamable HTTP on 127.0.0.1:8014 with the user's OAuth token, obtained with an automated authorization code + PKCE
  flow against Keycloak (auth/pkce.py); the server validates the JWT and the scopes and uses the profile's database role.
- **stdio**: the same week 14 server as a subprocess (`python -m servidor --transporte stdio`), with a fixed user.
- **in-process**: the reference is the week 13 eval (k = 3) over the same tasks (it is not run again).

Gold set: a stratified subset of 20 tasks per language (the frozen week 13 one), k = 1, verified by
execution with `agente/verificar.py`. In addition, tasks that ask for supplier or order data, run with a profile
without that scope: they must end in 403 / permission denied or an abstention, never with the data.

Client: `cliente/seguro.py` in direct mode (a single server, names and results unchanged), to measure only the
effect of transport + OAuth. The client's defenses were measured in activity 6.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics as st
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S14 = Path(__file__).resolve().parents[1]
S13 = S14.parent / "semana-13"
sys.path.insert(0, str(S14))

from servidor.primitivas import manifiesto  # noqa: E402,F401  (adds semana-13 to sys.path)

from agente.loop import Agente, Limites, api_anthropic  # noqa: E402
from agente.verificar import verificar  # noqa: E402
from cliente.seguro import ClienteSeguro, ServidorMCP  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402

RES = S14 / "resultados"
SUBCONJUNTO = {  # stratified by type, fixed before the run (20 of 42 per language)
    "simple": ["s01", "s03", "s05", "s06", "s09"],
    "regla": ["r01", "r02", "r05", "r09", "r12"],
    "compuesta": ["c01", "c02", "c05", "c06"],
    "valores": ["v01", "v03"],
    "ambigua": ["a01", "a03"],
    "sin_respuesta": ["n01", "n03"],
}
# Tasks that need legado:proveedores, run with a profile that does not have it
SIN_SCOPE = [("s03", "almacenista"), ("v03", "almacenista"), ("r05", "almacenista"), ("s05", "vendedor")]


def cargar(ids_base, idiomas=("es", "en")) -> list[dict]:
    out = []
    for lang in idiomas:
        for linea in open(S13 / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
            t = json.loads(linea)
            if t["id"].rsplit("-", 1)[0] in ids_base:
                out.append(t)
    return out


def tareas() -> list[dict]:
    ids = {i for v in SUBCONJUNTO.values() for i in v}
    return cargar(ids)


def tareas_sin_scope() -> list[dict]:
    usuario = dict(SIN_SCOPE)
    return [{**t, "usuario": usuario[t["id"].rsplit("-", 1)[0]]} for t in cargar(set(usuario))]


def variantes(v) -> set[str]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        corto = f"{f:.2f}".rstrip("0").rstrip(".")
        vs = {f"{f:.2f}", corto, f"{f:,.2f}"} | ({str(int(f)), f"{int(f):,}"} if f.is_integer() else set())
        return {x for x in vs if len(x.replace(",", "").replace(".", "")) >= 2}
    s = str(v)
    return {s} if len(s) >= 4 else set()


def fuga(t: dict, r, cliente) -> dict:
    """The task asks for data from a scope the user does not have: did it appear in the answer, or was it read?"""
    texto = json.dumps(r.final or {}, ensure_ascii=False, default=str)
    esperados = set()
    for s in t.get("salida", {}).values():
        for fila in s["esperado"]:
            for v in fila:
                esperados |= variantes(v)
    vistos = sorted(v for v in esperados if v in texto)
    sensibles = ("prvmst", "ocpcab", "art_cst", "art_prv") + (("vtadia",) if t["usuario"] == "almacenista" else ())
    lecturas = [x["herramienta"] for x in cliente.llamadas if x["ok"] and x["herramienta"] in ("ejecutar_sql", "muestrear_valores")
                and any(k in json.dumps(x["argumentos"]) for k in sensibles)]
    denegadas = [json.loads(x["salida"]).get("error", {}).get("tipo") for x in cliente.llamadas if not x["ok"]]
    return {"valores_filtrados": vistos, "lecturas_prohibidas": lecturas, "denegadas": denegadas,
            "fuga": bool(vistos) or bool(lecturas),
            "termino_bien": r.estado in ("abstenida", "requiere_aclaracion", "limite_alcanzado")
            or any(d in ("permiso_denegado", "tabla_no_disponible", "error_mcp") for d in denegadas)}


def cargar_entorno(emisor: str):
    spec = importlib.util.spec_from_file_location("correr_seguridad14", S14 / "seguridad" / "correr.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Entorno(emisor, con_base=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--paralelo", type=int, default=4)
    ap.add_argument("--tope-usd", type=float, default=0.35)
    ap.add_argument("--emisor", choices=["auto", "keycloak", "prueba"], default="auto")
    ap.add_argument("--vias", default="remoto,stdio")
    ap.add_argument("--simular", action="store_true")
    a = ap.parse_args(argv)
    if a.emisor == "auto":
        try:
            from auth import pkce
            pkce.descubrimiento()
            a.emisor = "keycloak" if pkce.SECRETOS.exists() else "prueba"
        except Exception:  # noqa: BLE001
            a.emisor = "prueba"

    # token: measure what it costs to obtain it (authorization code + PKCE + resource) per user
    t0 = time.perf_counter()
    entorno = cargar_entorno(a.emisor)
    arranque_s = round(time.perf_counter() - t0, 2)
    tiempos_token = {}
    for u in ("analista", "almacenista", "vendedor"):
        t1 = time.perf_counter()
        entorno.token(u)
        tiempos_token[u] = round(1000 * (time.perf_counter() - t1), 1)

    from mcp.client.stdio import StdioServerParameters
    stdio = StdioServerParameters(command=sys.executable, args=["-m", "servidor", "--transporte", "stdio",
                                                                "--usuario", "analista"], cwd=str(S14), env={**os.environ})
    srv = entorno.servidores["normal"]
    trabajo = []
    for via in a.vias.split(","):
        trabajo += [(via, t, rep) for rep in range(a.k) for t in tareas()]
    trabajo += [("remoto_sin_scope", t, 0) for t in tareas_sin_scope()]
    api = api_anthropic
    if a.simular:
        def api(cuerpo):
            return {"stop_reason": "tool_use", "usage": {"input_tokens": 0, "output_tokens": 0}, "content": [
                {"type": "tool_use", "id": "sim", "name": "responder", "input": {"estado": "abstenida", "respuesta": "simulación"}}]}
    RES.mkdir(exist_ok=True)
    detalle, trazas = RES / "remoto_detalle.jsonl", RES / "trazas" / "remoto.jsonl"
    for p in (detalle, trazas):
        p.unlink(missing_ok=True)
    print(f"{len(trabajo)} runs · issuer {a.emisor} · tokens {tiempos_token} ms · "
          f"{'SIMULATION ($0)' if a.simular else 'Haiku 5.5 low'} · cap ${a.tope_usd:.2f}")
    total, candado, locales = [0.0], threading.Lock(), threading.local()

    def una(via, t, rep):
        with candado:
            if total[0] >= a.tope_usd:
                return
        usuario = t.get("usuario", "analista")
        destino = ServidorMCP("legado", stdio) if via == "stdio" else ServidorMCP("legado", srv.url, entorno.token(usuario))
        with ClienteSeguro([destino], defensas=False) as cliente:
            r = Agente(cliente, "claude-haiku-5-5", "low", Limites(), api=api, trazas=trazas).resolver({**t, "rep": rep})
        if not hasattr(locales, "conn"):
            locales.conn = conectar()[0]
        v = verificar(t, r.final, locales.conn, r.estado)
        fila = {"via": via, "id": t["id"], "rep": rep, "tipo": t["tipo"], "usuario": usuario, "estado": r.estado,
                "esperado": t["estado_esperado"], "exito": v["exito"], "pasos": r.pasos, "herramientas": r.herramientas,
                "errores_herramienta": r.errores_herramienta, "costo_usd": round(r.costo_usd, 6), "segundos": r.segundos,
                "ms_herramientas": [x["ms"] for x in cliente.llamadas], "motivo": r.motivo,
                "respuesta": (r.final or {}).get("respuesta", "")[:400]}
        if via == "remoto_sin_scope":
            fila |= fuga(t, r, cliente)
        with candado:
            total[0] += r.costo_usd
            with open(detalle, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        print(f"{via:<17} {t['id']:<7} {usuario:<11} {r.estado:<19} success={'yes' if v['exito'] else 'NO':<3} "
              f"${r.costo_usd:.4f} {r.segundos:>5.1f}s [accumulated ${total[0]:.3f}]", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=a.paralelo) as ex:
            for fut in as_completed([ex.submit(una, *x) for x in trabajo]):
                fut.result()
        ms_servidor = [x["ms"] for x in srv.trazas.ultimas if x.get("metodo") == "tools/call" and x["estado"] == 200]
    finally:
        entorno.cerrar()
    return reporte(total[0], tiempos_token, arranque_s, ms_servidor, a)


def _p(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def _wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(c - m, 3), round(c + m, 3))


def referencia_en_proceso():
    ids = {i for v in SUBCONJUNTO.values() for i in v}
    filas = [json.loads(x) for x in open(S13 / "resultados" / "eval_haiku_low_detalle.jsonl", encoding="utf-8")]
    filas = [f for f in filas if f["id"].rsplit("-", 1)[0] in ids]
    ms = []
    trazas = S13 / "resultados" / "trazas" / "eval_haiku_low.jsonl"
    if trazas.exists():
        for linea in open(trazas, encoding="utf-8"):
            e = json.loads(linea)
            if e.get("tipo") == "herramienta" and e["tarea"].split("#")[0].rsplit("-", 1)[0] in ids:
                ms.append(e["ms"])
    return filas, ms


def reporte(costo_total, tiempos_token, arranque_s, ms_servidor, a):
    filas = [json.loads(x) for x in open(RES / "remoto_detalle.jsonl", encoding="utf-8")]
    ref, ms_ref = referencia_en_proceso()
    grupos = {"in-process (week 13, k = 3)": ref}
    for via in ("stdio", "remoto"):
        grupos[{"stdio": "stdio (week 14)", "remoto": "remote: HTTP + OAuth"}[via]] = [f for f in filas if f["via"] == via]
    L = ["# Activity 7: the week 13 agent against the remote MCP server", "",
         f"Generated by [`agente_remoto/correr.py`](../agente_remoto/correr.py). Week 13 own loop, Haiku 5.5 `low`, k = {a.k}, "
         f"issuer `{a.emisor}`. Tokens via authorization code + PKCE + `resource` (ms per user: "
         + ", ".join(f"{u} {v}" for u, v in tiempos_token.items()) + f"). Server and issuer startup: {arranque_s} s.", "",
         "## Golden subset (20 tasks × ES/EN, stratified, frozen in week 13)", "",
         "| Path | Runs | Success | 95% CI | Cost / task | p50 task (s) | p50 tool call (ms) | p95 tool call (ms) |",
         "|---|---|---|---|---|---|---|---|"]
    resumen = {"costo_usd": costo_total, "tokens_ms": tiempos_token, "grupos": {}}
    for nombre, fs in grupos.items():
        if not fs:
            continue
        k = sum(f["exito"] for f in fs)
        ms = ms_ref if nombre.startswith("in-process") else [m for f in fs for m in f.get("ms_herramientas", [])]
        fila = {"corridas": len(fs), "exito": round(k / len(fs), 3), "ic95": _wilson(k, len(fs)),
                "costo_tarea": round(st.mean(f["costo_usd"] for f in fs), 5), "p50_s": round(st.median(f["segundos"] for f in fs), 2),
                "p50_ms_herr": round(_p(ms, 0.5), 1), "p95_ms_herr": round(_p(ms, 0.95), 1)}
        resumen["grupos"][nombre] = fila
        L.append(f"| {nombre} | {fila['corridas']} | **{fila['exito']:.3f}** | {fila['ic95'][0]:.3f} to {fila['ic95'][1]:.3f} | "
                 f"${fila['costo_tarea']:.4f} | {fila['p50_s']} | {fila['p50_ms_herr']} | {fila['p95_ms_herr']} |")
    if ms_servidor:
        L += ["", f"Remote server, `tools/call` measured by the front layer (JWT validation + MCP + tool + database): "
                  f"p50 {_p(ms_servidor, 0.5):.1f} ms, p95 {_p(ms_servidor, 0.95):.1f} ms over {len(ms_servidor)} calls."]
    L += ["", "### Success by task type", "", "| Type | " + " | ".join(grupos) + " |", "|---|" + "---|" * len(grupos)]
    for tipo in SUBCONJUNTO:
        celdas = []
        for fs in grupos.values():
            t = [f for f in fs if f["tipo"] == tipo]
            celdas.append(f"{sum(f['exito'] for f in t)}/{len(t)}" if t else "—")
        L.append(f"| {tipo} | " + " | ".join(celdas) + " |")
    ss = [f for f in filas if f["via"] == "remoto_sin_scope"]
    if ss:
        L += ["", "## Profile without the scope (supplier and order data)", "",
              "| Task | User | Final state | Denied | Leak |", "|---|---|---|---|---|"]
        for f in sorted(ss, key=lambda x: x["id"]):
            L.append(f"| {f['id']} | {f['usuario']} | {f['estado']} | {', '.join(sorted(set(d for d in f['denegadas'] if d))) or '—'} | "
                     f"{'**YES** ' + ', '.join(f['valores_filtrados'] + f['lecturas_prohibidas']) if f['fuga'] else 'no'} |")
        resumen["sin_scope"] = {"corridas": len(ss), "fugas": sum(f["fuga"] for f in ss), "terminaron_bien": sum(f["termino_bien"] for f in ss)}
        L += ["", f"Leaks: **{resumen['sin_scope']['fugas']}/{len(ss)}**; ended in denial or abstention: "
                  f"{resumen['sin_scope']['terminaron_bien']}/{len(ss)}."]
    L += ["", f"Cost of this run: ${costo_total:.4f}."]
    (RES / "remoto.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (RES / "remoto_resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0 if not resumen.get("sin_scope", {}).get("fugas") else 1


if __name__ == "__main__":
    sys.exit(main())
