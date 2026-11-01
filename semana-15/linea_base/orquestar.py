"""Semana 15, actividad 1: spike sin API. Cada framework lista y llama las herramientas del servidor MCP de la semana 14.

    cd semana-15 && python linea_base/orquestar.py                 # Mac: Keycloak (semana-14/auth/arrancar.sh) y copilot-db
    python linea_base/orquestar.py --emisor prueba                # sin Keycloak: emisor de laboratorio (misma validación JWT)

El servidor (Streamable HTTP + OAuth, permisos por scope, rol de BD por perfil) corre en este proceso con `mcp` 2.3.0.
Cada spike corre en su propio entorno virtual (los frameworks fijan versiones de `mcp` y `a2a-sdk` incompatibles entre sí)
y recibe solo la URL y el token del usuario `analista` (Keycloak: authorization code + PKCE + resource). Ningún spike llama
a un modelo: el "modelo" está guionado (pide `describir_esquema` y `ejecutar_sql`, luego responde) o, si el framework no
permite inyectarlo sin API, las herramientas se invocan por la API de herramientas del framework. Costo: $0.

La evidencia sale de las trazas del servidor (no de lo que cada framework dice de sí mismo): versión de protocolo,
métodos, sujeto y scopes del token, estado HTTP. Escribe resultados/spike_mcp.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
S14 = S15.parent / "semana-14"
sys.path.insert(0, str(S14))
VENVS = Path(os.environ.get("VENVS_S15", S15 / ".venvs"))
SPIKES = {
    "langgraph": "spike_langgraph.py",
    "strands": "spike_strands.py",
    "openai_agents": "spike_openai.py",
    "google_adk": "spike_adk.py",
}
VENV_DE = {"langgraph": "lg", "strands": "st", "openai_agents": "oa", "google_adk": "adk"}


def entorno(emisor: str):
    spec = importlib.util.spec_from_file_location("seguridad14", S14 / "seguridad" / "correr.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Entorno(emisor, con_base=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emisor", choices=["keycloak", "prueba"], default="keycloak")
    ap.add_argument("--solo", default=",".join(SPIKES))
    a = ap.parse_args(argv)
    ent = entorno(a.emisor)
    srv = ent.servidores["normal"]
    salida = {"emisor": a.emisor, "url": srv.url, "frameworks": {}}
    try:
        for fw in a.solo.split(","):
            py = VENVS / VENV_DE[fw] / "bin" / "python"
            antes = len(srv.trazas.ultimas)
            env = {**os.environ, "MCP_URL": srv.url, "MCP_TOKEN": ent.token("analista")}
            p = subprocess.run([str(py), str(Path(__file__).with_name(SPIKES[fw]))], env=env, capture_output=True,
                               text=True, timeout=180)
            linea = next((x for x in reversed(p.stdout.splitlines()) if x.startswith("RESULTADO ")), None)
            res = json.loads(linea[len("RESULTADO "):]) if linea else {"error": (p.stderr or p.stdout)[-1500:]}
            tr = srv.trazas.ultimas[antes:]
            res["servidor"] = {
                "peticiones": len(tr),
                "por_estado": dict(Counter(str(x["estado"]) for x in tr)),
                "metodos": dict(Counter(f"{x.get('metodo')}{'/' + x['nombre'] if x.get('nombre') else ''}" for x in tr
                                        if x.get("http") == "POST")),
                "protocolos": sorted({x["protocolo"] for x in tr if x.get("protocolo")}),
                "sujetos": sorted({x["sujeto"] for x in tr if x.get("sujeto")}),
                "scopes": sorted({s for x in tr for s in (x.get("scopes") or [])}),
                "clientes": sorted({x["cliente"] for x in tr if x.get("cliente")}),
                "rechazos": [f"{x['estado']} {x.get('motivo_auth') or x.get('error')}" for x in tr if x["estado"] >= 400],
            }
            res["ok"] = bool(res.get("herramientas")) and bool((res.get("llamada") or {}).get("ok")) \
                and res["servidor"]["por_estado"].get("200", 0) > 0
            # negativo: token inválido. Debe terminar en 401 del servidor y en error visible del framework (no en vacío)
            antes = len(srv.trazas.ultimas)
            q = subprocess.run([str(py), str(Path(__file__).with_name(SPIKES[fw]))], text=True, capture_output=True,
                               env={**env, "MCP_TOKEN": "token.invalido.x"}, timeout=180)
            tr = srv.trazas.ultimas[antes:]
            res["token_invalido"] = {"codigo_salida": q.returncode,
                                     "estados": dict(Counter(str(x["estado"]) for x in tr)),
                                     "llamadas_ejecutadas": sum(1 for x in tr if x.get("metodo") == "tools/call" and x["estado"] == 200),
                                     "error_visible": next((x.strip() for x in reversed(q.stderr.splitlines())
                                                          if "401" in x or "Error" in x), "")[:200]}
            res["ok"] = res["ok"] and q.returncode != 0 and res["token_invalido"]["llamadas_ejecutadas"] == 0 \
                and res["token_invalido"]["estados"].get("401", 0) > 0
            salida["frameworks"][fw] = res
            print(f"{fw:<14} ok={res['ok']} protocolos={res['servidor']['protocolos']} "
                  f"metodos={res['servidor']['metodos']} rechazos={res['servidor']['rechazos'][:3]}", flush=True)
    finally:
        ent.cerrar()
    destino = S15 / "resultados" / "spike_mcp.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0 if all(r.get("ok") for r in salida["frameworks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
