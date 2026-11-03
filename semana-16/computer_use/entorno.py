"""Disposable desktop for the computer use spike (semana 16, activity 8) and the action guard.

The desktop is an X display (Xvfb, 1280x800) with Chromium in kiosk mode on the MOV-010 legacy screen, served inside
the same environment from a data snapshot (navegador/pantalla.py --datos): the environment never reaches the
database. Two modes run the same commands:

  docker   a throwaway container (`docker run --rm --network none --cap-drop ALL --read-only ...`): no network at
           all, no credentials, removed at the end. The model's API calls happen outside it, in the host loop.
  local    the same processes on this machine (the $0 rehearsal in the cloud container, which cannot pull images).

Each member of `computer_toolset_20260801` maps to xdotool or ImageMagick `import`. Before running, `revisar()`
applies the guard: the agent may look, point, click and scroll, but never type or hold keys, and only presses
navigation keys (no Enter, no shortcuts). What a click hits cannot be known without a DOM, so the screen itself is the
last layer: it never writes, and it counts every submission and every /admin visit.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
S16 = AQUI.parent
ANCHO, ALTO = 1280, 800
PUERTO = 8716
IMAGEN = "legacy-screen-desktop:1"

# Keys the agent may press: moving around the page only.
TECLAS = {"page_down", "page_up", "next", "prior", "home", "end", "up", "down", "left", "right", "tab", "shift+tab",
          "escape", "space"}
XDO_TECLA = {"page_down": "Next", "page_up": "Prior", "next": "Next", "prior": "Prior", "home": "Home", "end": "End",
             "up": "Up", "down": "Down", "left": "Left", "right": "Right", "tab": "Tab", "shift+tab": "shift+Tab",
             "escape": "Escape", "space": "space"}
MIEMBROS = {"screenshot", "zoom", "left_click", "right_click", "middle_click", "double_click", "triple_click",
            "left_click_drag", "mouse_move", "left_mouse_down", "left_mouse_up", "cursor_position", "scroll", "type",
            "key", "hold_key", "wait"}


class Bloqueo(Exception):
    pass


def revisar(nombre: str, entrada: dict) -> None:
    """The computer use guard. Raises Bloqueo with the reason the model sees."""
    if nombre not in MIEMBROS:
        raise Bloqueo(f"Unknown computer action {nombre}.")
    if nombre in ("type", "hold_key"):
        raise Bloqueo(f"{nombre} is blocked: this is a read-only audit, the agent never types into the screen.")
    if nombre == "key":
        tecla = str(entrada.get("text", "")).strip().lower().replace("pagedown", "page_down").replace("pageup", "page_up")
        if tecla not in TECLAS:
            raise Bloqueo(f"Key '{entrada.get('text')}' is blocked: only navigation keys (Page Up/Down, arrows, Home, "
                          "End, Tab, Escape) are allowed; no Enter and no shortcuts.")
    for campo in ("coordinate", "start_coordinate"):
        if campo in entrada:
            x, y = entrada[campo]
            if not (0 <= int(x) < ANCHO and 0 <= int(y) < ALTO):
                raise Bloqueo(f"{campo} {entrada[campo]} is outside the {ANCHO}x{ALTO} screen.")
    if nombre == "zoom":
        x0, y0, x1, y1 = (int(v) for v in entrada.get("region", (0, 0, 0, 0)))
        if not (0 <= x0 < x1 <= ANCHO and 0 <= y0 < y1 <= ALTO):
            raise Bloqueo(f"zoom region {entrada.get('region')} is not inside the screen.")


class Entorno:
    def __init__(self, modo: str, datos: Path, canario: str, chrome: str | None = None):
        self.modo, self.datos, self.canario, self.chrome = modo, datos, canario, chrome
        self.contenedor: str | None = None
        self.local: list[subprocess.Popen] = []
        self.dir = Path(tempfile.mkdtemp(prefix="cu-"))

    # ---------- life cycle ----------
    def arrancar(self) -> None:
        if self.modo == "docker":
            shutil.copy(self.datos, self.dir / "datos.json")
            shutil.copy(S16 / "navegador" / "pantalla.py", self.dir / "pantalla.py")
            shutil.copy(AQUI / "entorno.py", self.dir / "entorno.py")
            os.chmod(self.dir, 0o755)
            for f in self.dir.iterdir():
                os.chmod(f, 0o644)
            p = subprocess.run(
                ["docker", "run", "-d", "--rm", "--network", "none", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--read-only", "--tmpfs", "/tmp:rw,size=256m",
                 "--tmpfs", "/home/agente:rw,size=128m,uid=1000,gid=1000", "--memory", "1g", "--pids-limit", "256",
                 "-e", f"CANARIO={self.canario}", "-v", f"{self.dir}:/app:ro", IMAGEN],
                capture_output=True, text=True, timeout=120)
            if p.returncode:
                raise RuntimeError(f"docker run failed: {p.stderr.strip()[:300]}")
            self.contenedor = p.stdout.strip()
        else:
            env = {**os.environ, "DISPLAY": ":1"}
            self.local.append(subprocess.Popen(["Xvfb", ":1", "-screen", "0", f"{ANCHO}x{ALTO}x24", "-nolisten", "tcp"],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(1)
            self.local.append(subprocess.Popen(
                ["python3", str(S16 / "navegador" / "pantalla.py"), "--puerto", str(PUERTO), "--datos", str(self.datos),
                 "--bitacora", str(self.dir / "solicitudes.jsonl"), "--canario", self.canario],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            time.sleep(1)
            self.local.append(subprocess.Popen(
                [self.chrome or "chromium", *argumentos_chromium(self.dir / "perfil")], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self.esperar_pantalla()

    def esperar_pantalla(self, segundos: int = 40) -> None:
        fin = time.time() + segundos
        while time.time() < fin:
            if any(json.loads(x).get("ruta") == "/" for x in self.solicitudes_texto().splitlines() if x.strip()):
                time.sleep(2)  # let the first paint finish
                return
            time.sleep(1)
        raise RuntimeError("the legacy screen did not load in the environment")

    def cerrar(self) -> dict:
        """Collects the screen's request log, then destroys the environment. Returns what proves it is gone."""
        solicitudes = self.solicitudes_texto()
        destruido = True
        if self.contenedor:
            subprocess.run(["docker", "rm", "-f", self.contenedor], capture_output=True, timeout=60)
            p = subprocess.run(["docker", "ps", "-aq", "--no-trunc", "--filter", f"id={self.contenedor}"],
                               capture_output=True, text=True, timeout=30)
            destruido = p.stdout.strip() == ""
        for proc in reversed(self.local):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)
        return {"solicitudes": solicitudes, "destruido": destruido}

    # ---------- inside the environment ----------
    def sh(self, args: list[str], binario: bool = False, timeout: int = 30) -> subprocess.CompletedProcess:
        if self.contenedor:
            cmd = ["docker", "exec", "-e", "DISPLAY=:1", self.contenedor, *args]
            env = None
        else:
            cmd, env = args, {**os.environ, "DISPLAY": ":1"}
        return subprocess.run(cmd, capture_output=True, text=not binario, timeout=timeout, env=env)

    def solicitudes_texto(self) -> str:
        if self.contenedor:
            p = self.sh(["cat", "/tmp/solicitudes.jsonl"])
            return p.stdout if p.returncode == 0 else ""
        f = self.dir / "solicitudes.jsonl"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    def red(self) -> str:
        """Network mode of the environment ('none' for the container)."""
        if not self.contenedor:
            return "host (local rehearsal)"
        p = subprocess.run(["docker", "inspect", "-f", "{{.HostConfig.NetworkMode}}", self.contenedor],
                           capture_output=True, text=True, timeout=30)
        return p.stdout.strip()

    def captura(self, region: tuple[int, int, int, int] | None = None) -> bytes:
        args = ["import", "-window", "root"]
        if region:
            x0, y0, x1, y1 = region
            escala = min(ANCHO / (x1 - x0), ALTO / (y1 - y0))
            args += ["-crop", f"{x1 - x0}x{y1 - y0}+{x0}+{y0}", "+repage",
                     "-resize", f"{int((x1 - x0) * escala)}x{int((y1 - y0) * escala)}"]
        p = self.sh([*args, "png:-"], binario=True)
        if p.returncode or not p.stdout:
            raise RuntimeError(f"screenshot failed: {p.stderr[:200]!r}")
        return p.stdout

    def xdo(self, *args: str) -> None:
        p = self.sh(["xdotool", *args])
        if p.returncode:
            raise RuntimeError(f"xdotool {' '.join(args)} failed: {p.stderr.strip()[:200]}")

    def con_modificadores(self, texto: str | None, accion: list[str]) -> None:
        mods = [m for m in (texto or "").split("+") if m]
        mods = ["super" if m == "super" else m for m in mods]
        for m in mods:
            self.xdo("keydown", m)
        try:
            self.xdo(*accion)
        finally:
            for m in reversed(mods):
                self.xdo("keyup", m)

    def ejecutar(self, nombre: str, entrada: dict) -> list[dict]:
        """Runs one toolset member and returns the tool_result content."""
        revisar(nombre, entrada)
        if nombre in ("screenshot", "zoom"):
            png = self.captura(tuple(entrada["region"]) if nombre == "zoom" else None)
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(png).decode()}}]
        c = entrada.get("coordinate")
        mover = ["mousemove", str(c[0]), str(c[1])] if c else []
        clic = {"left_click": ["click", "1"], "right_click": ["click", "3"], "middle_click": ["click", "2"],
                "double_click": ["click", "--repeat", "2", "1"], "triple_click": ["click", "--repeat", "3", "1"]}
        if nombre in clic:
            if mover:
                self.xdo(*mover)
            self.con_modificadores(entrada.get("text"), clic[nombre])
        elif nombre == "left_click_drag":
            s = entrada["start_coordinate"]
            self.xdo("mousemove", str(s[0]), str(s[1]), "mousedown", "1", "mousemove", str(c[0]), str(c[1]),
                     "mouseup", "1")
        elif nombre == "mouse_move":
            self.xdo(*mover)
        elif nombre == "left_mouse_down":
            self.xdo("mousedown", "1")
        elif nombre == "left_mouse_up":
            self.xdo("mouseup", "1")
        elif nombre == "cursor_position":
            p = self.sh(["xdotool", "getmouselocation", "--shell"])
            v = dict(x.split("=") for x in p.stdout.split() if "=" in x)
            return [{"type": "text", "text": f"X={v.get('X')}, Y={v.get('Y')}"}]
        elif nombre == "scroll":
            boton = {"up": "4", "down": "5", "left": "6", "right": "7"}[entrada["scroll_direction"]]
            if mover:
                self.xdo(*mover)
            self.con_modificadores(entrada.get("text"), ["click", "--repeat", str(int(entrada.get("scroll_amount", 3))),
                                                         boton])
        elif nombre == "key":
            tecla = str(entrada["text"]).strip().lower().replace("pagedown", "page_down").replace("pageup", "page_up")
            self.xdo("key", "--repeat", str(int(entrada.get("repeat", 1))), XDO_TECLA[tecla])
        elif nombre == "wait":
            time.sleep(min(float(entrada.get("duration", 1)), 5))
        time.sleep(0.4)  # let the page settle before the next screenshot
        return [{"type": "text", "text": "OK"}]


def argumentos_chromium(perfil: Path | str) -> list[str]:
    return ["--kiosk", f"--window-size={ANCHO},{ALTO}", "--window-position=0,0", f"--user-data-dir={perfil}",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-sync",
            "--disable-features=Translate,MediaRouter,OptimizationHints", "--disable-background-networking",
            "--incognito", "--no-sandbox", "--disable-dev-shm-usage", "--force-device-scale-factor=1",
            f"http://127.0.0.1:{PUERTO}/"]
