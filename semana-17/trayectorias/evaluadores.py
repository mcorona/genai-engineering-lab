"""Week 17, activity 7 (part 1): the deterministic trajectory graders. Pure functions: no I/O, no model, no clock, no network.

They take an ABSTRACT trajectory (`Trayectoria`: the tool calls in order plus the number of model steps) and a `Referencia`, so the same
code can later read the calls from the week 13 loop's trace lines (`adaptadores.py`), from the OTLP file the Collector writes or from
Langfuse. The definitions and the pass rules are in `criterios.py`, which was written before any recorded run was scored.

    from trayectorias.evaluadores import Llamada, Trayectoria, Referencia, evaluar
    resultado = evaluar(referencia, Trayectoria((Llamada("describir_esquema", True, 1), ...), pasos=3))
    resultado["ok"], resultado["puntaje"], resultado["notas"]["orden"]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

S17 = Path(__file__).resolve().parents[1]
if str(S17) not in sys.path:
    sys.path.insert(0, str(S17))

from trayectorias import criterios as C  # noqa: E402


def normalizar(nombre: str) -> str:
    """The tool name without the prefix the week 14 MCP client adds (`legado__ejecutar_sql` -> `ejecutar_sql`)."""
    nombre = str(nombre)
    return nombre[len(C.PREFIJO_MCP):] if nombre.startswith(C.PREFIJO_MCP) else nombre


@dataclass(frozen=True)
class Llamada:
    """One tool call. `turno` is the model step that issued it (from 1); calls of one turn were issued together. `args` is an opaque
    identifier of the exact arguments (a hash): equal arguments, equal value. None means unknown and never counts as a repeat."""
    herramienta: str
    ok: bool
    turno: int
    args: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Trayectoria:
    llamadas: tuple
    pasos: int                  # model steps (calls to the model), the final `responder` turn included

    def __post_init__(self):
        if self.pasos < 1:
            raise ValueError("a trajectory has at least one model step")
        turnos = [c.turno for c in self.llamadas]
        if any(t < 1 for t in turnos) or turnos != sorted(turnos):
            raise ValueError("calls must be in order, with turns counted from 1")


@dataclass(frozen=True)
class Referencia:
    id: str
    tipo: str
    estado_esperado: str
    requeridas: tuple
    permitidas: tuple
    prohibidas: tuple
    orden: tuple                # pairs (before, after)
    pasos_min: int
    pasos_max: int

    def a_dict(self) -> dict:
        return {"id": self.id, "tipo": self.tipo, "estado_esperado": self.estado_esperado, "requeridas": list(self.requeridas),
                "permitidas": list(self.permitidas), "prohibidas": list(self.prohibidas), "orden": [list(p) for p in self.orden],
                "pasos_min": self.pasos_min, "pasos_max": self.pasos_max}

    @classmethod
    def de_dict(cls, d: dict) -> "Referencia":
        return cls(d["id"], d["tipo"], d["estado_esperado"], tuple(d["requeridas"]), tuple(d["permitidas"]), tuple(d["prohibidas"]),
                   tuple((a, b) for a, b in d["orden"]), int(d["pasos_min"]), int(d["pasos_max"]))


@dataclass(frozen=True)
class Nota:
    nombre: str
    puntaje: float              # 0..1
    ok: bool | None             # None: reported, with no pass rule
    detalle: dict


def _r(x: float) -> float:
    return round(float(x), 6)


def _llamadas(t: Trayectoria) -> list[Llamada]:
    return [Llamada(normalizar(c.herramienta), c.ok, c.turno, c.args, c.error) for c in t.llamadas]


def recall_herramientas(ref: Referencia, t: Trayectoria) -> Nota:
    req = set(ref.requeridas)
    usadas_ok = {c.herramienta for c in _llamadas(t) if c.ok}
    faltan = sorted(req - usadas_ok)
    p = 1.0 if not req else (len(req) - len(faltan)) / len(req)
    return Nota("recall_herramientas", _r(p), not faltan, {"requeridas": sorted(req), "faltan": faltan})


def precision_herramientas(ref: Referencia, t: Trayectoria) -> Nota:
    usadas = {c.herramienta for c in _llamadas(t)} - {C.HERRAMIENTA_DE_ENTREGA}
    aceptables = set(ref.requeridas) | set(ref.permitidas)
    inesperadas = sorted(usadas - aceptables)
    p = 1.0 if not usadas else (len(usadas) - len(inesperadas)) / len(usadas)
    return Nota("precision_herramientas", _r(p), not inesperadas, {"usadas": sorted(usadas), "inesperadas": inesperadas})


def orden(ref: Referencia, t: Trayectoria) -> Nota:
    llamadas = _llamadas(t)
    evaluados, cumplidos, incumplidos = 0, 0, []
    for antes, despues in ref.orden:
        primero_despues = next((c.turno for c in llamadas if c.herramienta == despues), None)
        primero_antes = next((c.turno for c in llamadas if c.herramienta == antes and c.ok), None)
        if primero_despues is None or primero_antes is None:
            continue                                          # a missing tool is the recall's finding
        evaluados += 1
        if primero_antes < primero_despues:
            cumplidos += 1
        else:
            incumplidos.append([antes, despues])
    p = 1.0 if not evaluados else cumplidos / evaluados
    return Nota("orden", _r(p), not incumplidos, {"evaluados": evaluados, "incumplidos": incumplidos})


def llamadas_redundantes(ref: Referencia, t: Trayectoria) -> Nota:
    vistas_ok: set = set()
    repetidas = []
    llamadas = _llamadas(t)
    for c in llamadas:
        clave = (c.herramienta, c.args)
        if c.args is not None and clave in vistas_ok:
            repetidas.append(c.herramienta)
        if c.ok and c.args is not None:
            vistas_ok.add(clave)
    n = len(llamadas)
    p = 1.0 - min(1.0, len(repetidas) / max(1, n))
    return Nota("llamadas_redundantes", _r(p), len(repetidas) <= C.REDUNDANTES_MAX, {"redundantes": len(repetidas), "herramientas": sorted(repetidas), "llamadas": n})


def llamadas_fallidas(ref: Referencia, t: Trayectoria) -> Nota:
    llamadas = _llamadas(t)
    fallidas = [c for c in llamadas if not c.ok]
    p = 1.0 - len(fallidas) / max(1, len(llamadas))
    return Nota("llamadas_fallidas", _r(p), None, {"fallidas": len(fallidas), "llamadas": len(llamadas),
                                                    "errores": sorted({c.error for c in fallidas if c.error})})


def recuperacion(ref: Referencia, t: Trayectoria) -> Nota:
    llamadas = _llamadas(t)
    estado = []
    for i, c in enumerate(llamadas):
        if not c.ok:
            estado.append((c.herramienta, any(d.herramienta == c.herramienta and d.ok for d in llamadas[i + 1:])))
    sin = [h for h, rec in estado if not rec]
    p = 1.0 if not estado else (len(estado) - len(sin)) / len(estado)
    return Nota("recuperacion", _r(p), not sin, {"fallidas": len(estado), "sin_recuperar": len(sin), "herramientas_sin_recuperar": sorted(set(sin))})


def pasos(ref: Referencia, t: Trayectoria) -> Nota:
    p = min(1.0, ref.pasos_min / t.pasos)
    return Nota("pasos", _r(p), t.pasos <= ref.pasos_max, {"pasos": t.pasos, "pasos_min": ref.pasos_min, "pasos_max": ref.pasos_max})


def herramientas_prohibidas(ref: Referencia, t: Trayectoria) -> Nota:
    usadas = [c.herramienta for c in _llamadas(t) if c.herramienta in set(ref.prohibidas)]
    return Nota("herramientas_prohibidas", 0.0 if usadas else 1.0, not usadas, {"intentos": len(usadas), "herramientas": sorted(set(usadas))})


_EVALUADORES = {"recall_herramientas": recall_herramientas, "precision_herramientas": precision_herramientas, "orden": orden,
                "llamadas_redundantes": llamadas_redundantes, "llamadas_fallidas": llamadas_fallidas, "recuperacion": recuperacion,
                "pasos": pasos, "herramientas_prohibidas": herramientas_prohibidas}
assert tuple(_EVALUADORES) == tuple(n for n, _ in C.EVALUADORES)


def evaluar(ref: Referencia, t: Trayectoria) -> dict:
    """All the graders on one trajectory. `ok` is true when every pass rule holds; `puntaje` is the mean of the scores that have a rule."""
    notas = {n: f(ref, t) for n, f in _EVALUADORES.items()}
    con_regla = [notas[n] for n in C.EVALUADORES_CON_REGLA]
    return {"id": ref.id, "ok": all(x.ok for x in con_regla), "puntaje": _r(sum(x.puntaje for x in con_regla) / len(con_regla)),
            "fallan": [x.nombre for x in con_regla if not x.ok],
            "notas": {n: {"puntaje": x.puntaje, "ok": x.ok, "detalle": x.detalle} for n, x in notas.items()}}
