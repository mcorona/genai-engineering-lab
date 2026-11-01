"""Semana 15, actividad 9: matriz de decisión de frameworks para clientes.

Los puntajes, su evidencia y los pesos por escenario viven aquí, no en el texto: el documento
`resultados/matriz_decision.md` se regenera desde este archivo y una prueba verifica que no se desfasen.

    python eval/matriz.py                          # regenera las tablas del documento ($0)
    python eval/matriz.py --pesos cliente.json     # ranking con los pesos de un cliente (sin tocar el documento)

`cliente.json` = {"proveedor": "anthropic|openai|gemini|multi", "nube": "aws|gcp|ninguna",
                  "pesos": {"modelo": 10, "nube": 5, ...}}   (los 10 criterios, suma 100)

Escala 1 a 5 (5 = mejor para el cliente). Estado de cada celda:
  M = medido en este laboratorio · D = documentado o verificado en el paquete, no ejercitado · N = no medido (juicio)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

S15 = Path(__file__).resolve().parents[1]
DOC = S15 / "resultados" / "matriz_decision.md"

# Evidencia: etiqueta → ruta relativa a resultados/
EV = {
    "A1": "linea_base.md", "A3": "langgraph.md", "A4": "strands.md", "A5": "frameworks.md", "A6": "spikes.md",
    "A7": "multiagente.md", "A8": "agentcore.md", "S13": "../../semana-13/resultados/seguridad.md",
    "S14": "../../semana-14/README.md", "L13": "../../semana-13/agente/loop.py",
    "COA": "../adaptadores/openai_agents.py", "CADK": "../adaptadores/google_adk.py",
}
OPCIONES = {"langgraph": "LangGraph", "strands": "Strands Agents", "openai": "OpenAI Agents SDK",
            "adk": "Google ADK", "propio": "No framework (own loop)"}
CRITERIOS = {
    "modelo": "Fit with the client's model provider",
    "nube": "Independence from one cloud or vendor",
    "protocolos": "MCP and A2A support",
    "seguridad": "Security and permission control",
    "estado": "State and human-in-the-loop",
    "observabilidad": "Observability",
    "despliegue": "Managed deployment on the client's platform",
    "madurez": "Maturity and license",
    "curva": "Team learning curve",
    "costo": "Measured cost per task",
}

# Costo medido por tarea, mismas 20 tareas (CI de la semana 13), mismo modelo (actividad 6, tabla de resultados).
COSTO_TAREA = {"propio": 0.0027, "strands": 0.0029, "langgraph": 0.0030, "openai": 0.0032, "adk": 0.0046}


def puntaje_costo(o: str) -> int:
    """5 si está a ≤10 % del más barato, 4 ≤25 %, 3 ≤50 %, 2 ≤100 %, 1 más."""
    extra = COSTO_TAREA[o] / min(COSTO_TAREA.values()) - 1
    return next(p for lim, p in ((0.10, 5), (0.25, 4), (0.50, 3), (1.00, 2), (9e9, 1)) if extra <= lim + 1e-9)


# (puntaje, estado, nota corta, evidencia). Dos criterios dependen del escenario: modelo (proveedor) y despliegue (nube).
P = {
    "modelo": {
        "langgraph": {"anthropic": (5, "M", "native `ChatAnthropic`", ["A1", "A5"]),
                      "openai": (5, "N", "native LangChain chat model integration (not exercised here)", []),
                      "gemini": (5, "N", "native LangChain chat model integration (not exercised here)", []),
                      "multi": (5, "N", "one chat model interface over the major providers (not exercised here)", [])},
        "strands": {"anthropic": (5, "M", "native `AnthropicModel`", ["A1", "A5"]),
                    "openai": (4, "N", "OpenAI model provider (not exercised here)", []),
                    "gemini": (3, "N", "through LiteLLM (not exercised here)", []),
                    "multi": (4, "N", "Bedrock by default; Anthropic, OpenAI and LiteLLM providers (only Anthropic exercised)", [])},
        "openai": {"anthropic": (3, "M", "Claude only through LiteLLM; 2 of 3 ways to pass a parameter misbehaved silently", ["A6"]),
                   "openai": (5, "N", "native (not exercised here)", []),
                   "gemini": (3, "N", "through LiteLLM, as Claude was", []),
                   "multi": (3, "M", "everything not OpenAI goes through LiteLLM", ["A6"])},
        "adk": {"anthropic": (3, "M", "Claude through LiteLLM; native `Claude` class only on Vertex AI", ["A1", "A6"]),
                "openai": (3, "N", "through LiteLLM, as Claude was", []),
                "gemini": (5, "N", "native (not exercised here)", []),
                "multi": (3, "M", "non-Google models through LiteLLM", ["A6"])},
        "propio": {"anthropic": (5, "M", "direct Messages API over HTTP", ["A5", "L13"]),
                   "openai": (1, "N", "client written for one API; switching = rewrite", []),
                   "gemini": (1, "N", "client written for one API; switching = rewrite", []),
                   "multi": (1, "N", "one client per provider to write and test", [])},
    },
    "nube": {
        "langgraph": (5, "D", "runs anywhere; managed on LangSmith, Vertex AI and AgentCore", ["A1"]),
        "strands": (4, "M", "ran locally and on AgentCore unchanged; its managed path is AWS", ["A5", "A8"]),
        "openai": (3, "D", "portable code, but its tracing exports to OpenAI by default", ["A1"]),
        "adk": (3, "D", "runs anywhere; native Claude and managed path lean on Google Cloud", ["A1"]),
        "propio": (5, "M", "plain Python and HTTP", ["A5"]),
    },
    "protocolos": {
        "langgraph": (3, "M", "MCP adapter on protocol 2025-11-25, one session per call unless kept open; no A2A in the library (A2A client written by us)", ["A1", "A7"]),
        "strands": (4, "M", "MCP 2026-07-28; A2A server v0.3 that enforces no auth (we added the middleware)", ["A1", "A7"]),
        "openai": (3, "M", "MCP 2026-07-28, tool results arrive as a Python repr; no A2A", ["A1", "A6"]),
        "adk": (4, "M", "the only one that keeps the MCP untrusted-data marker; A2A v1.0 that declares OAuth without enforcing it", ["A1"]),
        "propio": (3, "M", "MCP through our week 14 secure client; no A2A", ["S14"]),
    },
    "seguridad": {
        "langgraph": (4, "M", "38/38 poisoning cases with the MCP gateway; untrusted marker lost in the adapter", ["A5", "A1"]),
        "strands": (4, "M", "38/38 with the MCP gateway; A2A auth had to be added", ["A5", "A7"]),
        "openai": (3, "N", "poisoning suite not run; tracing sends data to OpenAI unless disabled", ["A1", "A6"]),
        "adk": (3, "N", "poisoning suite not run; A2A accepts calls without a token", ["A1"]),
        "propio": (5, "M", "140/140 security runs in week 13; secure MCP client native", ["S13", "S14"]),
    },
    "estado": {
        "langgraph": (5, "M", "checkpoints and `interrupt()` before purchase proposals, tested", ["A3"]),
        "strands": (4, "M", "interrupts tested; session managers documented, not exercised", ["A4", "A1"]),
        "openai": (3, "D", "MCP approval items and sessions in the package, not exercised", ["A1", "A6"]),
        "adk": (3, "D", "`require_confirmation` and session services in the package, not exercised", ["A1", "A6"]),
        "propio": (2, "M", "no checkpoints; approval only as `PENDING_APPROVAL` proposals", ["S13"]),
    },
    "observabilidad": {
        "langgraph": (2, "M", "0 OpenTelemetry spans from the library (LangSmith or external instrumentation)", ["A1"]),
        "strands": (5, "M", "OpenTelemetry GenAI spans (15 `gen_ai.*` attributes); CloudWatch on AgentCore", ["A1", "A8"]),
        "openai": (2, "M", "own tracing, exported to OpenAI by default; 0 OpenTelemetry spans", ["A1"]),
        "adk": (4, "M", "OpenTelemetry GenAI spans (9 attributes)", ["A1"]),
        "propio": (3, "M", "own JSONL traces per step; no OpenTelemetry", ["A5"]),
    },
    "despliegue": {
        "langgraph": {"aws": (4, "D", "AgentCore runs any framework", ["A1"]), "gcp": (4, "D", "Vertex AI Agent Engine", ["A1"]),
                      "ninguna": (4, "D", "LangSmith Deployment or any container", ["A1"])},
        "strands": {"aws": (5, "M", "AgentCore: READY in 35 s, same 1.000, cold start 5.7 s", ["A8"]),
                    "gcp": (2, "N", "no managed path; a container on Cloud Run", []),
                    "ninguna": (3, "N", "a container you run", [])},
        "openai": {"aws": (3, "D", "AgentCore runs any framework", ["A1"]), "gcp": (2, "N", "a container you run", []),
                   "ninguna": (3, "D", "self-hosted", ["A1"])},
        "adk": {"aws": (3, "D", "AgentCore runs any framework", ["A1"]), "gcp": (5, "D", "Vertex AI Agent Engine, Cloud Run", ["A1"]),
                "ninguna": (3, "N", "a container you run", [])},
        "propio": {"aws": (4, "M", "the AgentCore entry point is framework-agnostic (it wraps a plain function)", ["A8"]),
                   "gcp": (3, "N", "a container on Cloud Run", []), "ninguna": (3, "N", "a container you run", [])},
    },
    "madurez": {
        "langgraph": (5, "D", "MIT, 1.x Production/Stable, 65 installed packages", ["A1", "A5"]),
        "strands": (4, "D", "Apache-2.0, 1.x Production/Stable, 77 packages; A2A pinned to v0.3", ["A1", "A5"]),
        "openai": (3, "D", "MIT, 0.x (no stability classifier)", ["A1"]),
        "adk": (4, "D", "Apache-2.0, 2.x", ["A1"]),
        "propio": (3, "M", "your code, one dependency (pydantic); no community and you maintain it", ["L13"]),
    },
    "curva": {
        "langgraph": (4, "M", "145 lines, 12 min from request to merged PR; explicit state schema", ["A5", "A3"]),
        "strands": (3, "M", "166 lines, 17 min; needs its internals (metrics timing, concurrent tools by default)", ["A5", "A4"]),
        "openai": (3, "M", "about 119 lines, but LiteLLM pitfalls need a request-level test", ["A6", "COA"]),
        "adk": (3, "M", "about 133 lines; prompt quirks (appended identity line, `{...}` as state)", ["A6", "CADK"]),
        "propio": (4, "M", "about 209 lines of plain Python; nothing to learn, everything to own", ["L13"]),
    },
}
for o in OPCIONES:     # costo: derivado de los números medidos, no asignado a mano
    extra = round(100 * (COSTO_TAREA[o] / min(COSTO_TAREA.values()) - 1))
    P.setdefault("costo", {})[o] = (puntaje_costo(o), "M", f"${COSTO_TAREA[o]:.4f} per task (+{extra}% vs cheapest)", ["A6"])

ESCENARIOS = {
    "aws": {"nombre": "Client on AWS", "proveedor": "anthropic", "nube": "aws",
            "pesos": {"modelo": 10, "nube": 5, "protocolos": 10, "seguridad": 15, "estado": 10, "observabilidad": 10,
                      "despliegue": 20, "madurez": 8, "curva": 5, "costo": 7}},
    "gcp": {"nombre": "Client on Google Cloud", "proveedor": "gemini", "nube": "gcp",
            "pesos": {"modelo": 15, "nube": 5, "protocolos": 10, "seguridad": 15, "estado": 10, "observabilidad": 10,
                      "despliegue": 20, "madurez": 5, "curva": 5, "costo": 5}},
    "openai": {"nombre": "Client standardized on OpenAI", "proveedor": "openai", "nube": "ninguna",
               "pesos": {"modelo": 20, "nube": 5, "protocolos": 10, "seguridad": 15, "estado": 10, "observabilidad": 10,
                         "despliegue": 10, "madurez": 8, "curva": 7, "costo": 5}},
    "regulada": {"nombre": "Regulated multicloud enterprise", "proveedor": "multi", "nube": "ninguna",
                 "pesos": {"modelo": 10, "nube": 15, "protocolos": 10, "seguridad": 20, "estado": 10, "observabilidad": 15,
                           "despliegue": 5, "madurez": 10, "curva": 0, "costo": 5}},
    "startup": {"nombre": "Startup prototype", "proveedor": "anthropic", "nube": "ninguna",
                "pesos": {"modelo": 10, "nube": 5, "protocolos": 5, "seguridad": 10, "estado": 10, "observabilidad": 5,
                          "despliegue": 10, "madurez": 5, "curva": 25, "costo": 15}},
    "sin_framework": {"nombre": "Small team, one agent, strict dependency policy", "proveedor": "anthropic", "nube": "ninguna",
                      "pesos": {"modelo": 5, "nube": 10, "protocolos": 5, "seguridad": 20, "estado": 5, "observabilidad": 10,
                                "despliegue": 5, "madurez": 5, "curva": 15, "costo": 20}},
}


NOMBRES = {"anthropic": "Claude", "openai": "OpenAI", "gemini": "Gemini", "multi": "several providers", "aws": "AWS",
           "gcp": "Google Cloud", "ninguna": "no preference"}


def celda(c: str, o: str, proveedor: str = "anthropic", nube: str = "aws") -> tuple:
    v = P[c][o]
    if c == "modelo":
        return v[proveedor]
    if c == "despliegue":
        return v[nube]
    return v


def evaluar(pesos: dict, proveedor: str, nube: str) -> dict[str, float]:
    assert set(pesos) == set(CRITERIOS) and sum(pesos.values()) == 100, "10 criterios, suma 100"
    return {o: round(sum(pesos[c] * celda(c, o, proveedor, nube)[0] for c in CRITERIOS) / 100, 2) for o in OPCIONES}


def estabilidad(esc: dict, reps: int = 2000, ruido: float = 0.3, semilla: int = 15) -> float:
    """Fracción de perturbaciones aleatorias de los pesos (±30 % cada uno, renormalizados) en las que gana la misma opción."""
    rnd = random.Random(semilla)
    base = evaluar(esc["pesos"], esc["proveedor"], esc["nube"])
    ganador = max(base, key=base.get)
    iguales = 0
    for _ in range(reps):
        w = {c: p * rnd.uniform(1 - ruido, 1 + ruido) for c, p in esc["pesos"].items()}
        s = sum(w.values())
        r = {o: sum(w[c] / s * celda(c, o, esc["proveedor"], esc["nube"])[0] for c in CRITERIOS) for o in OPCIONES}
        iguales += max(r, key=r.get) == ganador
    return iguales / reps


# ---------- render ----------

def _ev(ids):
    return ", ".join(f"[{i}]({EV[i]})" for i in ids) if ids else "not measured"


def tabla_puntajes() -> str:
    filas = ["| Criterion | " + " | ".join(OPCIONES.values()) + " |", "|---|" + "---|" * len(OPCIONES)]
    for c, nombre in CRITERIOS.items():
        if c == "modelo":
            for prov, etiqueta in (("anthropic", "Claude"), ("openai", "OpenAI"), ("gemini", "Gemini"), ("multi", "several")):
                filas.append(f"| {nombre}: {etiqueta} | " + " | ".join(
                    f"**{celda(c, o, prov)[0]}** {celda(c, o, prov)[1]} · {_ev(celda(c, o, prov)[3])}" for o in OPCIONES) + " |")
        elif c == "despliegue":
            for nube, etiqueta in (("aws", "AWS"), ("gcp", "Google Cloud"), ("ninguna", "no preference")):
                filas.append(f"| {nombre}: {etiqueta} | " + " | ".join(
                    f"**{celda(c, o, nube=nube)[0]}** {celda(c, o, nube=nube)[1]} · {_ev(celda(c, o, nube=nube)[3])}"
                    for o in OPCIONES) + " |")
        else:
            filas.append(f"| {nombre} | " + " | ".join(f"**{celda(c, o)[0]}** {celda(c, o)[1]} · {_ev(celda(c, o)[3])}"
                                                      for o in OPCIONES) + " |")
    return "\n".join(filas)


def tabla_notas() -> str:
    filas = ["| Criterion | Option | Score | Why |", "|---|---|---|---|"]
    for c, nombre in CRITERIOS.items():
        for o, etiqueta in OPCIONES.items():
            if c in ("modelo", "despliegue"):
                for k, v in P[c][o].items():
                    filas.append(f"| {nombre} ({NOMBRES[k]}) | {etiqueta} | {v[0]} {v[1]} | {v[2]} |")
            else:
                v = P[c][o]
                filas.append(f"| {nombre} | {etiqueta} | {v[0]} {v[1]} | {v[2]} |")
    return "\n".join(filas)


def tabla_pesos() -> str:
    filas = ["| Criterion | " + " | ".join(e["nombre"] for e in ESCENARIOS.values()) + " |", "|---|" + "---|" * len(ESCENARIOS)]
    for c, nombre in CRITERIOS.items():
        filas.append(f"| {nombre} | " + " | ".join(str(e["pesos"][c]) for e in ESCENARIOS.values()) + " |")
    filas.append("| *Model provider / platform* | " + " | ".join(f"{NOMBRES[e['proveedor']]} / {NOMBRES[e['nube']]}"
                                                                  for e in ESCENARIOS.values()) + " |")
    return "\n".join(filas)


def tabla_resultados() -> str:
    filas = ["| Scenario | " + " | ".join(OPCIONES.values()) + " | Winner | Margin | Same winner under ±30% weights |",
             "|---|" + "---|" * (len(OPCIONES) + 3)]
    for e in ESCENARIOS.values():
        r = evaluar(e["pesos"], e["proveedor"], e["nube"])
        orden = sorted(r, key=r.get, reverse=True)
        filas.append(f"| {e['nombre']} | " + " | ".join(f"**{r[o]:.2f}**" if o == orden[0] else f"{r[o]:.2f}" for o in OPCIONES)
                     + f" | {OPCIONES[orden[0]]} | +{r[orden[0]] - r[orden[1]]:.2f} over {OPCIONES[orden[1]]} | "
                     f"{100 * estabilidad(e):.0f}% |")
    return "\n".join(filas)


BLOQUES = {"puntajes": tabla_puntajes, "pesos": tabla_pesos, "resultados": tabla_resultados, "notas": tabla_notas}


def renderizar(texto: str) -> str:
    for k, f in BLOQUES.items():
        texto = re.sub(rf"(<!-- tabla:{k} -->)\n.*?(<!-- /tabla:{k} -->)",
                       lambda m: m.group(1) + "\n" + f() + "\n" + m.group(2), texto, flags=re.S)
    return texto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pesos", type=Path, help="JSON de un cliente: proveedor, nube y pesos")
    a = ap.parse_args(argv)
    if a.pesos:
        cfg = json.loads(a.pesos.read_text())
        r = evaluar(cfg["pesos"], cfg.get("proveedor", "anthropic"), cfg.get("nube", "ninguna"))
        for o in sorted(r, key=r.get, reverse=True):
            print(f"{OPCIONES[o]:<26} {r[o]:.2f}")
        return 0
    DOC.write_text(renderizar(DOC.read_text(encoding="utf-8")), encoding="utf-8")
    print(tabla_resultados())
    return 0


if __name__ == "__main__":
    sys.exit(main())
