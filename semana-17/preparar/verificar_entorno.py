"""Readiness check for week 17 (no model, $0). Run it before activity 1, on the Mac and in the container.

It checks what activity 1 assumes is already there, and prints one line per check:
- Python 3.13 and the week 17 packages at the candidate pins (`uv sync --group semana17`);
- Docker running, with enough memory and disk for Langfuse v4 (ClickHouse is the heavy part);
- the pinned images pulled (`preparar/jalar_imagenes.sh`);
- the host ports of the plan free, and the lab's own services (PostgreSQL, Keycloak, the week 14 MCP server)
  not clashing with them;
- the lab database with the `legado` schema and the week 13 golden tasks and per-task results that activities 4
  and 7 start from;
- `semana-17/**` in the paths of the required `regresion` check, and the `eval-semana-17` workflow present.

Nothing is printed that could hold a secret: DSNs are only tried, never shown.

    uv run --group semana17 python semana-17/preparar/verificar_entorno.py [--sin-docker] [--json salida.json]
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S17 = AQUI.parent
RAIZ = S17.parent
V = json.loads((AQUI / "versiones.json").read_text(encoding="utf-8"))


def docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def puerto_libre(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def revisar(sin_docker: bool) -> list[tuple[str, bool, str]]:
    r: list[tuple[str, bool, str]] = []
    r.append(("python >= 3.13", sys.version_info >= (3, 13), sys.version.split()[0]))
    for paquete, version in V["python"].items():
        try:
            v = md.version(paquete)
        except md.PackageNotFoundError:
            v = None
        r.append((f"paquete {paquete}=={version}", v == version, v or "no instalado (uv sync --group semana17)"))
    if not sin_docker:
        if shutil.which("docker") is None:
            r.append(("docker instalado", False, "no está en PATH"))
        else:
            p = docker("info", "--format", "{{.MemTotal}} {{.NCPU}} {{.ServerVersion}}")
            ok = p.returncode == 0
            r.append(("docker corriendo", ok, p.stdout.strip().split(" ")[-1] if ok else p.stderr.strip()[:80]))
            if ok:
                mem, cpus, _ = p.stdout.split()
                gib = int(mem) / 2**30
                minimo = V["recursos_docker"]["memoria_gib_min"]
                r.append((f"memoria de Docker >= {minimo} GiB", gib >= minimo, f"{gib:.1f} GiB, {cpus} CPU"))
                for nombre, imagen in V["imagenes"].items():
                    q = docker("image", "inspect", "--format", "{{index .RepoDigests 0}}", imagen)
                    r.append((f"imagen {nombre}", q.returncode == 0,
                              q.stdout.strip().split("@")[-1][:19] if q.returncode == 0 else "falta (jalar_imagenes.sh)"))
    if not sin_docker:   # the disk is for the Langfuse stack's images and ClickHouse data
        libre = shutil.disk_usage(Path.home()).free / 1e9
        minimo = V["recursos_docker"]["disco_libre_gb_min"]
        r.append((f"disco libre >= {minimo} GB", libre >= minimo, f"{libre:.0f} GB"))
    propios = {"keycloak", "mcp-semana-14", "postgres-laboratorio"}   # lab services: in use is fine
    for nombre, puerto in V["puertos"].items():
        if nombre not in propios:
            r.append((f"puerto {puerto} libre ({nombre})", puerto_libre(puerto), "" if puerto_libre(puerto) else "en uso"))
    usados = list(V["puertos"].values())
    r.append(("puertos del plan sin repetir", len(usados) == len(set(usados)), ""))
    for var in ("PG_DSN", "PG_ADMIN_DSN"):
        dsn = os.environ.get(var)
        if not dsn:
            r.append((f"{var} definido", False, "no definido"))
            continue
        try:
            import psycopg
            with psycopg.connect(dsn, connect_timeout=5) as c:
                n = c.execute("SELECT count(*) FROM pg_views WHERE schemaname = 'legado'").fetchone()[0]
            r.append((f"{var}: base con esquema legado", n >= 6, f"{n} vistas en legado"))
        except Exception as e:  # noqa: BLE001
            r.append((f"{var}: base con esquema legado", False, type(e).__name__))
    tareas = sum(1 for lang in ("es", "en") for _ in open(RAIZ / "semana-13" / "golden" / f"tareas_{lang}.jsonl",
                                                            encoding="utf-8"))
    r.append(("84 tareas golden de la semana 13", tareas == 84, str(tareas)))
    detalle = RAIZ / "semana-13" / "resultados" / "eval_sdk_low_detalle.jsonl"
    filas = [json.loads(x) for x in detalle.read_text(encoding="utf-8").splitlines() if x.strip()]
    r.append(("resultados por tarea de la semana 13 (costo, pasos, herramientas)",
              len({f["id"] for f in filas}) == 84 and all("costo_usd" in f and "pasos" in f for f in filas),
              f"{len(filas)} corridas"))
    regresion = (RAIZ / ".github" / "workflows" / "evals-semana-06.yml").read_text(encoding="utf-8")
    r.append(("semana-17/** en el check requerido regresion", '"semana-17/**"' in regresion, ""))
    r.append(("workflow eval-semana-17", (RAIZ / ".github" / "workflows" / "eval-semana-17.yml").exists(), ""))
    r.append(("auth de Keycloak de la semana 14", (RAIZ / "semana-14" / "auth" / "arrancar.sh").exists(), ""))
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sin-docker", action="store_true", help="skip Docker checks (CI without the stack)")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    r = revisar(a.sin_docker)
    for nombre, ok, detalle in r:
        print(f"  {'OK' if ok else 'FALTA'}  {nombre}" + (f"  ({detalle})" if detalle else ""))
    faltan = [n for n, ok, _ in r if not ok]
    print(f"\n{len(r) - len(faltan)}/{len(r)} listos" + (f"; falta: {', '.join(faltan)}" if faltan else ""))
    if a.json:
        a.json.write_text(json.dumps([{"check": n, "ok": ok, "detalle": d} for n, ok, d in r], ensure_ascii=False,
                                     indent=1) + "\n", encoding="utf-8")
    return 0 if not faltan else 1


if __name__ == "__main__":
    sys.exit(main())
