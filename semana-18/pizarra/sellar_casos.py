"""Week 18, activity 6: the whiteboard briefs, generated and SEALED before any rehearsal.

    cd semana-18/pizarra && python3 sellar_casos.py              # once: writes .sellados/ (git-ignored) and sellos.json (versioned)
    python3 sellar_casos.py --revelar caso-3                      # the day it is used: prints it and checks it against its seal

Each brief combines, at random, one option of each dimension below with a random seed that is never printed nor versioned. The text of
the briefs lives only in `.sellados/` (ignored by git); the repo keeps their sha256 (`sellos.json`), so a brief revealed later can be shown
to be the one sealed today. Nobody sees a brief before it is used: not the person drawing, not the one scoring.

Every brief needs more than one agent and at least one MCP server: it has two jobs of different risk, a consequential action and data
that cannot leave its system of record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SELLADOS = AQUI / ".sellados"
SELLOS = AQUI / "sellos.json"
USOS = {"caso-1": "rehearsal 1", "caso-2": "rehearsal 2", "caso-3": "rehearsal 3", "caso-4": "final", "caso-5": "spare", "caso-6": "spare"}

SISTEMAS = [
    "an AS/400 (IBM i) order-management system with DB2 tables named in 6-letter codes, used by 300 branch offices",
    "a COBOL policy-administration system for an insurer, batch jobs at night and a DB2 copy for reporting",
    "a 2004 hospital admissions database (SQL Server) with patient records and free-text clinical notes",
    "a municipal water utility's billing system on Oracle 9 with meter readings and payment plans",
    "a logistics company's warehouse system on Informix with cryptic column names and no documentation",
    "a university's student-records system (PeopleSoft era) with grades, tuition and scholarship rules",
    "a credit union's core banking on a mainframe, exposed only through a nightly flat-file extract and a read replica",
    "a manufacturer's MRP on Progress OpenEdge with bills of materials, suppliers and production orders",
    "a pharmacy chain's inventory system with controlled-substance logs and supplier contracts",
    "a government permits system (Access front end, SQL Server back end) with applicants' personal data",
    "a telecom's provisioning database with customer lines, plans and network inventory",
    "an airline's maintenance-records system with parts, technicians and regulatory sign-offs",
]
OBJETIVOS = [
    "let operations managers ask questions in natural language and get answers with the evidence behind them",
    "find and explain anomalies (duplicates, impossible values, broken rules) and propose corrections",
    "prepare the monthly regulatory report and flag every figure that cannot be traced to source data",
    "draft replenishment or purchase proposals from stock and demand, ready for a human to approve",
    "answer customer-service agents' questions about one customer's history in under ten seconds",
    "document the schema (dictionary, relationships, business rules) to plan a migration to the cloud",
    "detect fraud signals across two systems and open a case for an investigator",
    "reconcile the legacy system against a new SaaS system during a phased migration and list every mismatch",
]
RESTRICCIONES = [
    "the data must not leave the client's network; no SaaS model may see personal values",
    "two business units (tenants) share the system and must never see each other's data",
    "the database is fragile: no query may run longer than 5 seconds and nothing may write to it",
    "the budget is fixed per month and a runaway agent must not exceed it",
    "auditors require a full trace of every answer and every action, kept for 5 years",
    "the client's identity provider is Microsoft Entra ID; every user acts with their own permissions",
    "some table and column comments were written by contractors and may contain instructions",
    "a third-party MCP server from a vendor must be used for one data source and is not fully trusted",
]
ACCIONES = [
    "registering a purchase order above a monetary threshold",
    "changing a customer's credit limit",
    "sending an email or a letter to a customer",
    "closing or merging duplicated records",
    "submitting the regulatory report",
    "creating a ticket that triggers field work",
    "approving a refund",
    "publishing a migration plan that other teams will execute",
]
SENSIBILIDAD = [
    "personal data (names, national IDs, phone numbers)",
    "health data",
    "financial account data",
    "trade secrets (supplier prices and margins)",
    "data of minors",
    "no personal data, but business-critical figures",
]


def generar(rng: secrets.SystemRandom) -> list[dict]:
    combos, out = set(), []
    while len(out) < len(USOS):
        c = (rng.randrange(len(SISTEMAS)), rng.randrange(len(OBJETIVOS)), rng.randrange(len(RESTRICCIONES)),
             rng.randrange(len(ACCIONES)), rng.randrange(len(SENSIBILIDAD)))
        if c[0] in {x[0] for x in combos} or c in combos:     # six different legacy systems
            continue
        combos.add(c)
        s, o, r, a, d = c
        out.append({"sistema": SISTEMAS[s], "objetivo": OBJETIVOS[o], "restriccion": RESTRICCIONES[r], "accion": ACCIONES[a],
                    "datos": SENSIBILIDAD[d]})
    return out


def texto(nombre: str, b: dict, sal: str) -> str:
    return (f"# Whiteboard brief {nombre}\n\n"
            f"**Client system.** {b['sistema'][0].upper() + b['sistema'][1:]}.\n\n"
            f"**Goal.** The client wants to {b['objetivo']}.\n\n"
            f"**Constraint.** {b['restriccion'][0].upper() + b['restriccion'][1:]}.\n\n"
            f"**Consequential action in scope.** {b['accion'][0].upper() + b['accion'][1:]}.\n\n"
            f"**Sensitive data involved.** {b['datos'][0].upper() + b['datos'][1:]}.\n\n"
            "**Your task (30 minutes).** Design a multi-agent system that uses MCP to reach the goal. On the board: (1) context and goal; "
            "(2) the agents and why each exists (or why fewer agents would be better); (3) the MCP servers, their tools, data and "
            "authentication; (4) the security boundaries; (5) how you will evaluate it before and after go-live. State the trade-offs and "
            "a rough cost.\n\n"
            f"<!-- salt: {sal} -->\n")


def sellar() -> int:
    if SELLOS.exists():
        print("already sealed: sellos.json exists (delete both files only to start over before any rehearsal)", file=sys.stderr)
        return 1
    rng = secrets.SystemRandom()
    SELLADOS.mkdir(exist_ok=True)
    sellos = {"fecha": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "metodo": "sha256 of the brief file (a random salt inside)",
              "casos": {}}
    for (nombre, uso), b in zip(USOS.items(), generar(rng)):
        contenido = texto(nombre, b, secrets.token_hex(16))
        (SELLADOS / f"{nombre}.md").write_text(contenido, encoding="utf-8")
        sellos["casos"][nombre] = {"uso": uso, "sha256": hashlib.sha256(contenido.encode()).hexdigest(), "revelado": None}
    SELLOS.write_text(json.dumps(sellos, indent=1) + "\n", encoding="utf-8")
    for n, v in sellos["casos"].items():
        print(f"{n}  {v['uso']:<12} {v['sha256'][:16]}…")
    return 0


def revelar(nombre: str) -> int:
    sellos = json.loads(SELLOS.read_text(encoding="utf-8"))
    contenido = (SELLADOS / f"{nombre}.md").read_text(encoding="utf-8")
    if hashlib.sha256(contenido.encode()).hexdigest() != sellos["casos"][nombre]["sha256"]:
        print(f"{nombre} DOES NOT match its seal", file=sys.stderr)
        return 1
    sellos["casos"][nombre]["revelado"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    SELLOS.write_text(json.dumps(sellos, indent=1) + "\n", encoding="utf-8")
    print(contenido)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revelar")
    a = ap.parse_args()
    raise SystemExit(revelar(a.revelar) if a.revelar else sellar())
