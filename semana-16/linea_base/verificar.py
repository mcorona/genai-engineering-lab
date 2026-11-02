"""Semana 16, actividad 1: verifica con la CLI instalada lo que la línea base afirma de Claude Code.

    cd semana-16 && python linea_base/verificar.py                 # $0: sin modelo
    python linea_base/verificar.py --con-modelo                    # + 2 corridas headless (suscripción, no API)

Sin modelo:
1. Versión de Claude Code y subcomandos de `claude plugin`.
2. `claude plugin validate --strict` del plugin mínimo y del marketplace local; dos negativos: nombre reservado y ruta
   con `..` (el validador debe rechazarlos).
3. Marketplace local → instalación → `claude plugin details` (inventario y costo en tokens) → `configure` (userConfig
   sensible) en un CLAUDE_CONFIG_DIR temporal: no toca tu configuración.
4. `claude plugin eval init --bare` en una copia: estructura de casos y graders.
5. El hook PreToolUse con entradas guionadas (exit 0 / 2) y el PostToolUse (bitácora JSONL).

Con modelo (`--con-modelo`, cuenta contra tu plan de Claude Code; `claude -p --plugin-dir`):
6. Una petición natural ("documenta este esquema legado...") debe disparar la skill y ejecutar `lb-version` (bin/).
7. Una petición de escribir fuera de `auditoria/` debe quedar bloqueada por el hook: el archivo no existe al final.
Escribe resultados/linea_base.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S16 = AQUI.parent
PLUGIN = AQUI / "plugin_minimo"
RES = S16 / "resultados"


def sh(*cmd, entorno=None, cwd=None, entrada=None, timeout=120):
    p = subprocess.run(list(cmd), capture_output=True, text=True, env={**os.environ, **(entorno or {})}, cwd=cwd,
                       input=entrada, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def check(nombre, ok, detalle=""):
    print(f"{'✅' if ok else '❌'} {nombre}{' · ' + detalle if detalle else ''}", flush=True)
    return {"check": nombre, "ok": bool(ok), "detalle": detalle}


def guardia(evento: dict) -> tuple[int, str]:
    c, _, err = sh(sys.executable, str(PLUGIN / "scripts" / "guardia.py"), entrada=json.dumps(evento))
    return c, err.strip()


def sin_modelo() -> list[dict]:
    r = []
    c, out, _ = sh("claude", "--version")
    r.append(check("Claude Code instalado", c == 0, out.strip()))
    _, out, _ = sh("claude", "plugin", "--help")
    faltan = [s for s in ("validate", "eval", "details", "configure", "marketplace", "install") if s not in out]
    r.append(check("Subcomandos de claude plugin", not faltan, "faltan " + ", ".join(faltan) if faltan else "validate, eval, details, configure, marketplace, install"))
    c, out, _ = sh("claude", "plugin", "validate", "--strict", "--json", str(PLUGIN))
    v = json.loads(out)
    r.append(check("validate --strict del plugin", c == 0 and v["success"] and not v["manifest"]["errors"],
                   f"{len(v['manifest']['warnings'])} advertencias"))
    c, out, _ = sh("claude", "plugin", "validate", "--strict", "--json", str(AQUI))
    r.append(check("validate --strict del marketplace", c == 0, "marketplace lb-local"))
    with tempfile.TemporaryDirectory() as t:
        malo = Path(t) / "malo"
        shutil.copytree(PLUGIN, malo)
        m = json.loads((malo / ".claude-plugin" / "plugin.json").read_text())
        (malo / ".claude-plugin" / "plugin.json").write_text(json.dumps({**m, "name": "claude-legacy-audit"}))
        c, out, err = sh("claude", "plugin", "validate", str(malo))
        r.append(check("Negativo: nombre reservado rechazado", c != 0 and "reserved" in (out + err), "claude-legacy-audit"))
        (malo / ".claude-plugin" / "plugin.json").write_text(json.dumps({**m, "agents": ["../fuera.md"]}))
        c, out, err = sh("claude", "plugin", "validate", str(malo))
        r.append(check("Negativo: ruta con .. rechazada", c != 0 and ".." in (out + err), "agents: ../fuera.md"))
    with tempfile.TemporaryDirectory() as cfg:
        e = {"CLAUDE_CONFIG_DIR": cfg}
        c1, _, _ = sh("claude", "plugin", "marketplace", "add", str(AQUI), entorno=e)
        c2, _, _ = sh("claude", "plugin", "install", "lb-spike@lb-local", entorno=e)
        _, det, _ = sh("claude", "plugin", "details", "lb-spike", entorno=e)
        r.append(check("Marketplace local + install + details", c1 == 0 and c2 == 0 and "hola-auditoria" in det
                       and "perfilador" in det and "PreToolUse" in det,
                       " ".join(l.strip() for l in det.splitlines() if "Always-on" in l)))
        _, conf, _ = sh("claude", "plugin", "configure", "lb-spike@lb-local", entorno=e)
        r.append(check("userConfig sensible visible sin exponer valor", "dsn_lectura" in conf and "sensitive" in conf, "dsn_lectura (sensitive)"))
    with tempfile.TemporaryDirectory() as t:
        copia = Path(t) / "p"
        shutil.copytree(PLUGIN, copia)
        c, _, _ = sh("claude", "plugin", "eval", "init", "--bare", "caso-disparo", cwd=copia)
        prompt = (copia / "evals" / "caso-disparo" / "prompt.md")
        grader = (copia / "evals" / "caso-disparo" / "graders" / "criteria.md")
        r.append(check("plugin eval init --bare", c == 0 and prompt.exists() and grader.exists(),
                       "prompt.md (max_turns, allowed_tools) + graders/criteria.md (type: llm)"))
    with tempfile.TemporaryDirectory() as proy:
        casos = [("Write fuera de auditoria/", {"tool_name": "Write", "tool_input": {"file_path": "notas.txt"}, "cwd": proy}, 2),
                 ("Write dentro de auditoria/", {"tool_name": "Write", "tool_input": {"file_path": "auditoria/x.md"}, "cwd": proy}, 0),
                 ("Edit con ../ para escapar", {"tool_name": "Edit", "tool_input": {"file_path": "auditoria/../x.py"}, "cwd": proy}, 2),
                 ("Bash con DELETE", {"tool_name": "Bash", "tool_input": {"command": "psql -c 'DELETE FROM exidet'"}, "cwd": proy}, 2),
                 ("Bash con SELECT", {"tool_name": "Bash", "tool_input": {"command": "psql -c 'SELECT 1'"}, "cwd": proy}, 0),
                 ("Bash con lo_import", {"tool_name": "Bash", "tool_input": {"command": "psql -c \"select lo_import('/etc/passwd')\""}, "cwd": proy}, 2)]
        c, _, err = sh(sys.executable, str(PLUGIN / "scripts" / "guardia.py"), entrada="no es json")
        r.append(check("Hook PreToolUse: entrada ilegible falla cerrada", c == 2, f"exit {c}"))
        h = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
        r.append(check("Hook PreToolUse en forma exec con onFailure: block", "args" in h and h.get("onFailure") == "block",
                       "si el hook no arranca o se vence, la herramienta no corre"))
        for nombre, ev, esperado in casos:
            c, err = guardia(ev)
            r.append(check(f"Hook PreToolUse: {nombre}", c == esperado, f"exit {c}" + (f" · {err}" if err else "")))
        c, _, _ = sh(sys.executable, str(PLUGIN / "scripts" / "bitacora.py"),
                     entrada=json.dumps({"tool_name": "Bash", "tool_input": {"command": "lb-version"}, "cwd": proy}))
        lineas = (Path(proy) / "auditoria" / "bitacora.jsonl").read_text().splitlines()
        r.append(check("Hook PostToolUse: bitácora JSONL", c == 0 and json.loads(lineas[-1])["comando"] == "lb-version"))
    return r


def eventos_headless(*extra, prompt: str, cwd: str, entorno=None, nombre="") -> tuple[int, list[dict], str]:
    """Runs claude -p with the spike plugin. The prompt goes through stdin: --allowedTools is variadic and
    would swallow a positional prompt. Returns exit code, stream-json events and stderr."""
    cmd = ["claude", "-p", "--plugin-dir", str(PLUGIN), "--output-format", "stream-json", "--verbose",
           "--model", "haiku", "--max-turns", "8", *extra]
    c, out, err = sh(*cmd, cwd=cwd, entrada=prompt, entorno=entorno, timeout=300)
    if nombre:
        RES.mkdir(exist_ok=True)
        (RES / f"headless_{nombre}.jsonl").write_text(out)
    ev = []
    for linea in out.splitlines():
        try:
            ev.append(json.loads(linea))
        except json.JSONDecodeError:
            pass
    return c, ev, err


def usos(ev: list[dict]) -> list[dict]:
    return [b for e in ev if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or []) if b.get("type") == "tool_use"]


def resultados_texto(ev: list[dict]) -> str:
    partes = []
    for e in ev:
        if e.get("type") != "user":
            continue
        for b in e.get("message", {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                partes.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return "\n".join(partes)


def final(ev: list[dict]) -> dict:
    return next((e for e in reversed(ev) if e.get("type") == "result"), {})


def con_modelo() -> list[dict]:
    r = []
    with tempfile.TemporaryDirectory() as proy:
        t = time.time()
        c, ev, err = eventos_headless("--allowedTools", "Bash(lb-version),Skill,Read", cwd=proy, nombre="skill",
                                      prompt="I need to audit a legacy database schema and build a data dictionary. "
                                             "First confirm the audit tooling is available and report its version. "
                                             "No schema files exist yet, so do not search for them.")
        u = usos(ev)
        skill = any(x["name"] == "Skill" and "hola-auditoria" in json.dumps(x.get("input", {})) for x in u)
        version = "lb-spike 0.1.0" in resultados_texto(ev)
        fin = final(ev)
        ok = bool(fin) and skill and version
        det = (f"{round(time.time() - t)} s · skill {'sí' if skill else 'no'} · lb-version {'sí' if version else 'no'}"
               f" · exit {c} · {fin.get('subtype', 'sin result')} · ${fin.get('total_cost_usd', 0):.4f} equiv."
               if ev else f"exit {c} · {err.strip()[:120]!r}")
        r.append(check("Headless: la skill se dispara con frase natural y bin/ está en el PATH", ok, det))

        # Only Write is available (Bash denied) and permissions accept edits: if notas.txt is not created and the
        # tool result carries the guard's message, the block came from the hook, not from permissions. The
        # SessionStart context is switched off so the model does not decline on its own.
        t = time.time()
        c, ev, err = eventos_headless("--permission-mode", "acceptEdits", "--allowedTools", "Write",
                                      "--disallowedTools", "Bash", cwd=proy, nombre="hook",
                                      entorno={"LB_SIN_CONTEXTO": "1"},
                                      prompt="Create a file named notas.txt in the current directory containing "
                                             "the word hola. Use the Write tool.")
        creado = (Path(proy) / "notas.txt").exists()
        intento = any(x["name"] == "Write" for x in usos(ev))
        bloqueo = "lb-spike: escritura bloqueada" in resultados_texto(ev)
        ok = intento and bloqueo and not creado
        det = (f"{round(time.time() - t)} s · Write intentado {'sí' if intento else 'no'} · mensaje del hook "
               f"{'sí' if bloqueo else 'no'} · notas.txt {'EXISTE' if creado else 'no existe'}"
               if ev else f"exit {c} · {err.strip()[:120]!r}")
        r.append(check("Headless: el hook bloquea Write fuera de auditoria/ aunque los permisos lo acepten", ok, det))
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--con-modelo", action="store_true")
    a = ap.parse_args(argv)
    r = sin_modelo() + (con_modelo() if a.con_modelo else [])
    RES.mkdir(exist_ok=True)
    (RES / "linea_base.json").write_text(json.dumps({"fecha": time.strftime("%Y-%m-%d"), "checks": r}, indent=1,
                                                    ensure_ascii=False) + "\n")
    malos = [x for x in r if not x["ok"]]
    print(f"\n{len(r) - len(malos)}/{len(r)} checks en verde")
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
