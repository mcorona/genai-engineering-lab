"""Installs legacy-schema-audit from its marketplace in a clean Claude Code configuration, and checks it (semana 16,
activity 9). No model call: $0.

A new empty CLAUDE_CONFIG_DIR and an empty project folder stand in for a client machine that has never seen the
plugin. The script adds the marketplace (this checkout, or GitHub), installs the plugin, and checks:

  - both manifests pass `claude plugin validate --strict` (the plugin also with `--profile directory`);
  - the installed version matches plugin.json, marketplace.json and the top CHANGELOG entry;
  - the installed copy has every component (4 skills, 3 agents, 3 hooks, 1 MCP server) and the client README;
  - the installed guard works from the installed path: it blocks a write SQL and a Bash `psql`, and allows a SELECT;
  - the installed SessionStart check reports a role that can write as unsafe and the read-only role as safe
    (only when PG_ADMIN_DSN / PG_DSN are set);
  - uninstalling and removing the marketplace leave no plugin behind.

    python empaquetado/instalar_desde_cero.py                         # marketplace from this checkout
    python empaquetado/instalar_desde_cero.py --github mcorona/genai-engineering-lab     # after the merge, as a client
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S16 = AQUI.parent
RAIZ = S16.parent
PLUGIN = S16 / "legacy-schema-audit"
NOMBRE = "legacy-schema-audit@genai-engineering-lab"


def claude(args: list[str], env: dict, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(["claude", *args], capture_output=True, text=True, env=env, cwd=cwd, timeout=timeout)


def fuga_de_dsn(dsn: str, texto: str) -> bool:
    """A printed DSN shows up whole or as its `user:password@` part. The password alone is not searched: it can be a
    common word (on the Mac the admin role is postgres with password postgres, and the hook's message names the role)."""
    m = re.search(r"://([^:@/]+:[^@]*@)", dsn)
    return dsn in texto or bool(m and m.group(1) in texto)


def evento(herramienta: str, entrada: dict, proyecto: Path, sesion: str = "s") -> str:
    return json.dumps({"session_id": sesion, "cwd": str(proyecto), "hook_event_name": "PreToolUse",
                       "tool_name": herramienta, "tool_input": entrada})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--github", help="owner/repo (optionally with #ref): add the marketplace from GitHub")
    ap.add_argument("--salida", help="where to write the JSON report (default resultados/empaquetado/...)")
    a = ap.parse_args(argv)
    fuente = a.github or str(RAIZ)
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    mercado = json.loads((RAIZ / ".claude-plugin" / "marketplace.json").read_text())
    entrada_mercado = next(p for p in mercado["plugins"] if p["name"] == "legacy-schema-audit")
    changelog = re.search(r"^## \[?(\d+\.\d+\.\d+)\]?", (PLUGIN / "CHANGELOG.md").read_text(), re.M).group(1)
    r: dict = {"fuente": "github:" + a.github if a.github else "checkout", "version": version, "checks": {}}
    c = r["checks"]
    c["versions_coinciden"] = version == entrada_mercado["version"] == mercado["metadata"]["version"] == changelog
    c["semver"] = bool(re.fullmatch(r"\d+\.\d+\.\d+", version))
    raiz = Path(tempfile.mkdtemp(prefix="cliente-"))
    try:
        config, proyecto = raiz / "config", raiz / "proyecto"
        proyecto.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_"))}
        env.update({"CLAUDE_CONFIG_DIR": str(config), "DISABLE_AUTOUPDATER": "1"})
        c["config_vacia_al_inicio"] = not config.exists()
        p = claude(["plugin", "validate", "--strict", str(RAIZ)], env, proyecto)
        c["marketplace_valida_strict"] = p.returncode == 0
        p = claude(["plugin", "validate", "--strict", "--profile", "directory", str(PLUGIN)], env, proyecto)
        c["plugin_valida_strict_directory"] = p.returncode == 0
        # From GitHub, as the README tells clients: a sparse checkout of the marketplace file and the plugin only.
        disperso = ["--sparse", ".claude-plugin", "semana-16/legacy-schema-audit"] if a.github else []
        p = claude(["plugin", "marketplace", "add", fuente, *disperso, "--json"], env, proyecto, timeout=300)
        c["marketplace_agregada"] = p.returncode == 0
        r["marketplace_add"] = p.stdout.strip().splitlines()[-1][:400] if p.stdout.strip() else p.stderr[-400:]
        p = claude(["plugin", "install", NOMBRE], env, proyecto, timeout=300)
        c["instalado"] = p.returncode == 0 and "Successfully installed" in p.stdout
        r["install"] = p.stdout.strip()[-400:]
        registro = json.loads((config / "plugins" / "installed_plugins.json").read_text())["plugins"][NOMBRE][0]
        instalado = Path(registro["installPath"])
        c["version_instalada"] = registro["version"] == version
        c["copia_instalada_fuera_del_checkout"] = RAIZ not in instalado.parents
        p = claude(["plugin", "list"], env, proyecto)
        c["habilitado"] = "legacy-schema-audit@genai-engineering-lab" in p.stdout and "enabled" in p.stdout
        p = claude(["plugin", "details", "legacy-schema-audit"], env, proyecto)
        r["details"] = p.stdout.strip()
        c["componentes"] = all(x in p.stdout for x in ("Skills (4)", "Agents (3)", "Hooks (3)", "MCP servers (1)"))
        c["readme_y_changelog_instalados"] = (instalado / "README.md").exists() and (instalado / "CHANGELOG.md").exists()
        c["ejemplo_instalado"] = all((instalado / "ejemplo" / f).exists()
                                     for f in ("resumen.md", "riesgos.md", "relaciones.mmd", "diccionario.yaml"))
        # The installed hooks, run from the installed path as Claude Code would run them.
        estado = raiz / "estado"
        spec = importlib.util.spec_from_file_location("comun_instalado", instalado / "scripts" / "comun.py")
        comun = importlib.util.module_from_spec(spec)  # the installed copy, not this checkout's
        spec.loader.exec_module(comun)
        comun.escribir_estado(estado, "s", {"modo": "dsn", "lectura_segura": True, "motivo": "role x is read-only"})
        guardia = [sys.executable, str(instalado / "scripts" / "guardia.py"), "--estado", str(estado)]
        servidor = "mcp__plugin_legacy-schema-audit_legacy-sql__run_select"
        casos = {"bloquea_delete": (servidor, {"sql": "DELETE FROM movinv"}, 2),
                 "bloquea_psql": ("Bash", {"command": "psql -c 'select 1'"}, 2),
                 "permite_select": (servidor, {"sql": "SELECT count(*) FROM movinv"}, 0)}
        for k, (h, e, esperado) in casos.items():
            p = subprocess.run(guardia, input=evento(h, e, proyecto), capture_output=True, text=True, timeout=30)
            c[f"guardia_instalada_{k}"] = p.returncode == esperado
        for k, var, esperado in (("rol_admin_inseguro", "PG_ADMIN_DSN", False), ("rol_lectura_seguro", "PG_DSN", True)):
            if os.environ.get(var):
                p = subprocess.run([sys.executable, str(instalado / "scripts" / "verificar_rol.py"), "--estado",
                                    str(estado)], input=json.dumps({"session_id": k, "cwd": str(proyecto)}),
                                   capture_output=True, text=True, timeout=60,
                                   env={**env, "CLAUDE_PLUGIN_OPTION_PG_DSN": os.environ[var],
                                        "LEGACY_AUDIT_DSN": os.environ[var]})
                leido = comun.leer_estado(estado, k) or {}
                c[f"sessionstart_instalado_{k}"] = leido.get("lectura_segura") is esperado
                if fuga_de_dsn(os.environ[var], p.stdout + p.stderr):
                    c[f"sessionstart_instalado_{k}"] = False  # it must never print the DSN
        p = claude(["plugin", "uninstall", NOMBRE], env, proyecto)
        c["desinstalado"] = p.returncode == 0
        p = claude(["plugin", "marketplace", "remove", "genai-engineering-lab"], env, proyecto)
        p2 = claude(["plugin", "list"], env, proyecto)
        c["sin_rastro_al_final"] = p.returncode == 0 and "legacy-schema-audit" not in p2.stdout
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    r["aprobado"] = all(c.values())
    destino = Path(a.salida) if a.salida else S16 / "resultados" / "empaquetado" / \
        f"instalacion_{'github' if a.github else 'checkout'}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(r, ensure_ascii=False, indent=1)
    texto = texto.replace(str(raiz), "<tmp>").replace(str(RAIZ), "<repo>").replace(str(Path.home()), "~")
    destino.write_text(texto + "\n", encoding="utf-8")
    for k, v in c.items():
        print(f"  {'OK' if v else 'FAIL'}  {k}")
    return 0 if r["aprobado"] else 1


if __name__ == "__main__":
    sys.exit(main())
