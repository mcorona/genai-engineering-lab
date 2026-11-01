"""Semana 15, actividad 8: la misma mini eval contra el agente Strands desplegado en AgentCore Runtime.

    cd semana-15 && python eval/agentcore.py --destino local --simular        # $0: main.py local + modelo simulado
    python eval/agentcore.py --destino agentcore --tope-usd 0.30              # AgentCore real (se autoriza antes)

1. **Arranque:** 3 sesiones nuevas con `ping` (sin modelo) = arranque en frío; 3 pings más en la última sesión =
   en caliente. Cada respuesta dice cuánto lleva vivo el proceso y cuántas invocaciones atendió.
2. **Identity:** una tarea invocada sin `runtimeUserId`: ¿entrega Runtime el token de carga de trabajo con el que el
   agente pide la llave a AgentCore Identity?
3. **Mini eval:** las 10 tareas por idioma de la CI de la semana 13 (las de la actividad 6), k = 1, una sesión nueva
   por tarea (como un usuario por petición), con el mismo verificador que en local.

Las herramientas son las del servidor MCP de la semana 14, que corre en la Mac. Con `--destino agentcore` se publica
**solo durante la corrida** por un túnel temporal de Cloudflare (`cloudflared`, sin cuenta): el servidor sigue exigiendo
el token OAuth de Keycloak, con su audiencia y sus scopes; Keycloak y Postgres no se publican. El encabezado Host se
reescribe a 127.0.0.1 para que la protección contra DNS rebinding del servidor siga igual.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
if str(S15) not in sys.path:
    sys.path.insert(0, str(S15))
from eval import correr as base  # noqa: E402
from eval.spikes import tareas_ci  # noqa: E402

from arnes.contrato import resultado_de_dict  # noqa: E402

RES = S15 / "resultados"
TOPE_USD = 0.30
USUARIO = "analista"


def _sesion() -> str:
    return f"semana15-{uuid.uuid4().hex}"           # AgentCore exige al menos 33 caracteres


class Local:
    """main.py servido en local (entorno `st`), con el mismo protocolo HTTP que Runtime (/invocations, /ping)."""

    nombre = "local"

    def __init__(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.puerto = s.getsockname()[1]
        py = Path(os.environ.get("VENVS_S15", S15 / ".venvs")) / "st" / "bin" / "python"
        entorno = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # como en la nube: sin llave en el entorno
        self.p = subprocess.Popen([str(py), str(S15 / "agentcore" / "main.py")], cwd=S15,
                                  env={**entorno, "PUERTO": str(self.puerto), "PYTHONPATH": str(S15)},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f"http://127.0.0.1:{self.puerto}"
        for _ in range(150):
            try:
                urllib.request.urlopen(self.url + "/ping", timeout=1)
                return
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        raise RuntimeError("main.py no arrancó")

    def invocar(self, payload: dict, sesion: str, usuario: str | None = USUARIO) -> dict:
        h = {"content-type": "application/json", "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sesion}
        req = urllib.request.Request(self.url + "/invocations", data=json.dumps(payload).encode(), headers=h)
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)

    def cerrar(self):
        self.p.terminate()
        self.p.wait(timeout=10)


class AgentCore:
    """El runtime desplegado por agentcore/infra.py, invocado con IAM (SigV4) y `runtimeUserId`."""

    nombre = "agentcore"

    def __init__(self):
        import boto3
        e = json.loads((S15 / "agentcore" / "estado.json").read_text())
        self.arn, self.region = e["runtime_arn"], e["region"]
        # Una sesión de boto3 por hilo: crear clientes desde la sesión por omisión en varios hilos no es seguro
        # (primera corrida: NoRegionError en una de 20 invocaciones concurrentes).
        self._sesion, self._local = boto3.Session(region_name=self.region), threading.local()
        self._candado = threading.Lock()

    def _cliente(self):
        if not hasattr(self._local, "c"):
            import boto3
            from botocore.config import Config
            with self._candado:
                self._local.c = boto3.Session(region_name=self.region).client(
                    "bedrock-agentcore", config=Config(region_name=self.region, read_timeout=600, retries={"max_attempts": 1}))
        return self._local.c

    def invocar(self, payload: dict, sesion: str, usuario: str | None = USUARIO) -> dict:
        kw = {"runtimeUserId": usuario} if usuario else {}
        r = self._cliente().invoke_agent_runtime(agentRuntimeArn=self.arn, runtimeSessionId=sesion, qualifier="DEFAULT",
                                        contentType="application/json", accept="application/json",
                                        payload=json.dumps(payload).encode(), **kw)
        return json.loads(r["response"].read())

    def cerrar(self):
        pass


class Tunel:
    """Túnel rápido de Cloudflare hacia el servidor MCP local, solo mientras dura la corrida."""

    def __init__(self, url_local: str):
        hostport = url_local.split("//", 1)[1].split("/", 1)[0]
        self.p = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://{hostport}",
                                   "--http-host-header", hostport], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  text=True)
        self.publica = None
        fin = time.time() + 60
        while time.time() < fin and self.publica is None:
            linea = self.p.stderr.readline()
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linea or "")
            if m:
                self.publica = m.group(0)
        if not self.publica:
            self.cerrar()
            raise RuntimeError("cloudflared no entregó una URL en 60 s")
        threading.Thread(target=lambda: [None for _ in self.p.stderr], daemon=True).start()   # vaciar stderr
        for _ in range(60):                       # la URL tarda unos segundos en resolverse
            try:
                urllib.request.urlopen(self.publica + "/.well-known/oauth-protected-resource/mcp", timeout=5)
                return
            except urllib.error.HTTPError:
                return
            except Exception:  # noqa: BLE001
                time.sleep(2)
        self.cerrar()
        raise RuntimeError("el túnel no respondió")

    def cerrar(self):
        self.p.terminate()
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", choices=["local", "agentcore"], default="agentcore")
    ap.add_argument("--emisor", choices=["auto", "keycloak", "prueba"], default="auto")
    ap.add_argument("--tope-usd", type=float, default=TOPE_USD)
    ap.add_argument("--hilos", type=int, default=2)
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--solo-reporte", action="store_true")
    a = ap.parse_args(argv)
    if a.solo_reporte:
        return reporte(json.loads((RES / "agentcore_meta.json").read_text()))
    if a.simular and a.destino == "agentcore":
        print("El modelo simulado corre en la Mac; AgentCore no lo alcanza. Usa --destino local para simular.")
        return 2
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
    adm = seg.admin()
    antes = seg.huella(adm)
    from herramientas.conexion import conectar
    from agente.verificar import verificar
    conn = conectar()[0]
    doble, base_url, tunel = None, None, None
    if a.simular:
        from arnes.simulado import DobleAnthropic
        doble = DobleAnthropic(base.GuionFijo()).__enter__()
        base_url = doble.base_url
    det, trazas = RES / "agentcore_detalle.jsonl", RES / "trazas" / "agentcore.jsonl"
    for p in (det, trazas):
        p.unlink(missing_ok=True)
    trazas.parent.mkdir(parents=True, exist_ok=True)
    total, candado, sin_lanzar, filas_arranque = [0.0], threading.Lock(), [0], []
    destino = Local() if a.destino == "local" else AgentCore()
    t0 = time.time()
    try:
        mcp_url = ent.servidores["normal"].url
        if a.destino == "agentcore":
            tunel = Tunel(mcp_url)
            mcp_url = tunel.publica + "/" + mcp_url.split("//", 1)[1].split("/", 1)[1]
            print(f"túnel temporal: {tunel.publica} → servidor MCP local (OAuth exigido)", flush=True)

        # 1. Arranque en frío y en caliente (ping, sin modelo)
        sesion = None
        for i in range(3):
            sesion = _sesion()
            t = time.perf_counter()
            r = destino.invocar({"ping": True}, sesion)
            filas_arranque.append({"tipo": "frio", "ms": round(1000 * (time.perf_counter() - t)), **r["arranque"]})
        for i in range(3):
            t = time.perf_counter()
            r = destino.invocar({"ping": True}, sesion)
            filas_arranque.append({"tipo": "caliente", "ms": round(1000 * (time.perf_counter() - t)), **r["arranque"]})
        for f in filas_arranque:
            print(f"arranque {f['tipo']:<8} {f['ms']:>6} ms  proceso vivo {f['proceso_s']:>7.1f} s  "
                  f"importación {f['importacion_s']} s  invocación #{f['invocacion']}", flush=True)

        ts = tareas_ci()

        def pedido(t):
            return {"tarea": {**t, "rep": 0}, "mcp_url": mcp_url, "token": token(), "base_url": base_url}

        # 2. Identity: sin runtimeUserId
        t = time.perf_counter()
        sin_usuario = destino.invocar(pedido(ts[0]), _sesion(), usuario=None)
        identidad = {"ms": round(1000 * (time.perf_counter() - t)), "error": sin_usuario.get("error"),
                     "respondio": "resultado" in sin_usuario}
        if "resultado" in sin_usuario:
            total[0] += sin_usuario["resultado"]["costo_usd"]
        print(f"identity sin runtimeUserId: {identidad['error'] or 'el agente obtuvo la llave'}", flush=True)

        # 3. Mini eval
        def una(t):
            with candado:
                if total[0] >= a.tope_usd:
                    sin_lanzar[0] += 1
                    return
            inicio = time.perf_counter()
            try:
                out = destino.invocar(pedido(t), _sesion())
            except Exception as e:  # noqa: BLE001
                out = {"error": f"invocación: {type(e).__name__}: {e}"[:300]}
            cliente_s = round(time.perf_counter() - inicio, 2)
            arr = out.get("arranque", {})
            if "error" in out:
                fila = {"id": t["id"], "tipo": t["tipo"], "estado": "error", "exito": False, "pasos": 0, "herramientas": 0,
                        "tokens_in": 0, "tokens_out": 0, "costo_usd": 0.0, "segundos": 0.0, "cliente_s": cliente_s,
                        "motivo": out["error"][:300], "arranque": arr}
                eventos = []
            else:
                r = resultado_de_dict(out["resultado"])
                v = verificar(t, r.final, conn, r.estado)
                fila = {"id": t["id"], "tipo": t["tipo"], "estado": r.estado, "exito": v["exito"], "pasos": r.pasos,
                        "herramientas": r.herramientas, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                        "costo_usd": round(r.costo_usd, 6), "segundos": r.segundos, "cliente_s": cliente_s,
                        "motivo": r.motivo, "arranque": arr, "respuesta": (r.final or {}).get("respuesta", "")[:300]}
                eventos = out.get("eventos", [])
            with candado:
                total[0] += fila["costo_usd"]
                with open(det, "a", encoding="utf-8") as f:
                    f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
                with open(trazas, "a", encoding="utf-8") as f:
                    f.writelines(json.dumps({**e, "framework": f"strands@{destino.nombre}"}, ensure_ascii=False,
                                            default=str) + "\n" for e in eventos)
            print(f"{t['id']:<7} {fila['estado']:<19} éxito={'sí' if fila['exito'] else 'NO':<3} ${fila['costo_usd']:.4f} "
                  f"agente {fila['segundos']:5.1f}s cliente {cliente_s:5.1f}s "
                  f"{'(proceso nuevo)' if arr.get('invocacion') == 1 else ''} {fila['motivo'][:70] if fila['estado'] == 'error' else ''}"
                  f"[acumulado ${total[0]:.3f}]", flush=True)

        print(f"{len(ts)} tareas · destino {destino.nombre} · emisor {a.emisor} · "
              f"{'SIMULACIÓN ($0)' if a.simular else 'Haiku 5.5 low'} · tope ${a.tope_usd:.2f}", flush=True)
        with ThreadPoolExecutor(a.hilos) as ex:
            for f in as_completed([ex.submit(una, t) for t in ts]):
                f.result()
    finally:
        if tunel:
            tunel.cerrar()
        destino.cerrar()
        ent.cerrar()
        if doble:
            doble.__exit__()
    despues = seg.huella(adm)
    meta = {"destino": destino.nombre, "emisor": a.emisor, "simulacion": a.simular, "costo_usd": round(total[0], 4),
            "sin_lanzar": sin_lanzar[0], "minutos": round((time.time() - t0) / 60, 1), "tope_usd": a.tope_usd,
            "arranque": filas_arranque, "identidad_sin_usuario": identidad,
            "tablas_modificadas": [t for t in antes if antes[t] != despues[t]]}
    (RES / "agentcore_meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    return reporte(meta)


def reporte(meta) -> int:
    filas = [json.loads(x) for x in open(RES / "agentcore_detalle.jsonl", encoding="utf-8")]
    ids = {f["id"] for f in filas}
    local = [json.loads(x) for x in open(RES / "frameworks_detalle.jsonl", encoding="utf-8")] \
        if (RES / "frameworks_detalle.jsonl").exists() else []
    local = [f for f in local if f["framework"] == "strands" and f["id"] in ids]

    def fila(nombre, fs, cliente=True):
        ok = sum(bool(f["exito"]) for f in fs)
        lo, hi = base.wilson(ok, len(fs))
        s = [f["segundos"] for f in fs]
        c = [f.get("cliente_s", f["segundos"]) for f in fs]
        return (f"| {nombre} | {len(fs)} | **{ok / len(fs):.3f}** | {lo + 0.0:.3f} to {hi:.3f} | "
                f"${sum(f['costo_usd'] for f in fs) / len(fs):.4f} | {base.percentil(s, .5)} / {base.percentil(s, .95)} | "
                + (f"{base.percentil(c, .5)} / {base.percentil(c, .95)} |" if cliente else "same |"))
    fr = [f["ms"] for f in meta["arranque"] if f["tipo"] == "frio"]
    ca = [f["ms"] for f in meta["arranque"] if f["tipo"] == "caliente"]
    nuevos = sum(1 for f in filas if f.get("arranque", {}).get("invocacion") == 1)
    L = ["# Activity 8: Strands on AgentCore Runtime, generated tables (analysis in [agentcore.md](agentcore.md))", "",
         f"Generated by [`eval/agentcore.py`](../eval/agentcore.py). Target **{meta['destino']}**, issuer `{meta['emisor']}`"
         + (", **SIMULATED MODEL**" if meta["simulacion"] else ", Haiku 5.5 `low`") + f". Model cost: **${meta['costo_usd']:.4f}** "
         f"(cap ${meta['tope_usd']:.2f}); {meta['minutos']} min. Database fingerprint: "
         f"**{'unchanged' if not meta['tablas_modificadas'] else 'CHANGED'}**.", "",
         "## Start-up (ping, no model)", "", "| | Runs | Client latency (ms) |", "|---|---|---|",
         f"| Cold: new session | {len(fr)} | {', '.join(map(str, fr))} |",
         f"| Warm: same session | {len(ca)} | {', '.join(map(str, ca))} |", "",
         f"Import time inside the process: {meta['arranque'][0]['importacion_s']} s. Tasks served by a fresh process: "
         f"{nuevos} of {len(filas)}.", "",
         "## Mini eval (week 13 CI tasks, 10 × ES/EN, k = 1, one session per task)", "",
         "| Agent | Runs | Success | 95% CI | Cost / task | Agent p50 / p95 (s) | Client p50 / p95 (s) |",
         "|---|---|---|---|---|---|---|", fila(f"Strands on {meta['destino']}", filas)]
    if local:
        L.append(fila("Strands local (activity 5, k = 3)", local, cliente=False))
    i = meta["identidad_sin_usuario"]
    sin_usuario = ("skipped: the simulated model needs no key" if meta["simulacion"] else
                   f"error `{i['error']}`" if i.get("error") else "the agent got the key and answered")
    L += ["", "## AgentCore Identity", "", f"Invocation without `runtimeUserId`: {sin_usuario}."]
    fallas = [f for f in filas if not f["exito"]]
    if fallas:
        L += ["", "Failures: " + ", ".join(f"{f['id']} ({f['estado']}{': ' + f['motivo'][:80] if f['estado'] == 'error' else ''})"
                                           for f in fallas)]
    (RES / "agentcore_tablas.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 1 if meta["tablas_modificadas"] and not meta["simulacion"] else 0


if __name__ == "__main__":
    sys.exit(main())
