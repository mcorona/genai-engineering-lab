"""Week 15, activity 1: a spike without the API. Each framework lists and calls the tools of the week 14 MCP server.

    cd semana-15 && python linea_base/orquestar.py                 # Mac: Keycloak (semana-14/auth/arrancar.sh) and copilot-db
    python linea_base/orquestar.py --emisor prueba                # without Keycloak: a lab issuer (the same JWT validation)

The server (Streamable HTTP + OAuth, permissions by scope, a DB role per profile) runs in this process with `mcp` 2.3.0.
Each spike runs in its own virtual environment (the frameworks pin mutually incompatible versions of `mcp` and `a2a-sdk`)
and receives only the URL and the token of the `analista` user (Keycloak: authorization code + PKCE + resource). No spike calls
a model: the "model" is scripted (it asks for `describir_esquema` and `ejecutar_sql`, then answers) or, if the framework does not
allow injecting it without the API, the tools are invoked through the framework's tool API. Cost: $0.

The evidence comes from the server's traces (not from what each framework says about itself): protocol version,
methods, the token's subject and scopes, HTTP status. Writes resultados/spike_mcp.json.
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
            # negative: an invalid token. It must end in a 401 from the server and a visible error in the framework (not in an empty result)
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
            print(f"{fw:<14} ok={res['ok']} protocols={res['servidor']['protocolos']} "
                  f"methods={res['servidor']['metodos']} rejections={res['servidor']['rechazos'][:3]}", flush=True)
    finally:
        ent.cerrar()
    destino = S15 / "resultados" / "spike_mcp.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0 if all(r.get("ok") for r in salida["frameworks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
