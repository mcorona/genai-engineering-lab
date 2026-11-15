"""Week 13, activity 4: deterministic equivalence between the native tools and the MCP server.

No model (cost $0). It compares complete JSON responses, field by field:
A. Catalog: the server's tools/list against definiciones() (name, description and JSON Schema).
B. Trace replay: each tool call the agent made in the pilots (resultados/trazas/piloto*.jsonl),
   in its task's language, through both paths.
C. Gold set: the SQL of each key the agent reported in pilot 2 runs through both paths; it is also
   checked against the gold set's expected result.
D. Permissions and errors: a matrix of cases for the three users (analista, almacenista, vendedor).

    python servidor_mcp/equivalencia.py     # writes resultados/mcp_equivalencia.{json,md}
"""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
from agente.verificar import verificar  # noqa: E402
from herramientas import Contexto, Herramientas, definiciones  # noqa: E402
from herramientas.conexion import conectar  # noqa: E402
from servidor_mcp.cliente import HerramientasMCP  # noqa: E402

CASOS_D = [
    ("describir_esquema", {}),
    ("describir_esquema", {"tablas": ["vtadia", "ocpcab"]}),
    ("muestrear_valores", {"tabla": "artmst", "columna": "art_cst"}),
    ("muestrear_valores", {"tabla": "prvmst", "columna": "prv_pais"}),
    ("ejecutar_sql", {"sql": "SELECT vta_art, SUM(vta_und) FROM vtadia GROUP BY 1 ORDER BY 2 DESC LIMIT 5"}),
    ("ejecutar_sql", {"sql": "SELECT * FROM artmst LIMIT 3"}),
    ("ejecutar_sql", {"sql": "SELECT art_cd, art_cst FROM artmst LIMIT 3"}),
    ("ejecutar_sql", {"sql": "SELECT ocp_id, ocp_sts FROM ocpcab"}),
    ("ejecutar_sql", {"sql": "DELETE FROM exidet"}),
    ("ejecutar_sql", {"sql": "SELECT set_config('default_transaction_read_only', 'off', false)"}),
    ("ejecutar_sql", {"sql": "SELECT content FROM semana10.chunks"}),
    ("ejecutar_sql", {"sql": "SELECT 1", "roles": ["finanzas"]}),
    ("validar_sql", {"sql": "SELECT art_precio FROM artmst"}),
]


def normal(r):
    return json.loads(json.dumps(r, ensure_ascii=False, default=str))


def main():
    conn, rol = conectar()
    out = {"rol_nativo": rol}
    mcp = {lang: HerramientasMCP("analista", lang) for lang in ("es", "en")}
    nat = {lang: Herramientas(Contexto.de_usuario("analista", conexion=conn, idioma=lang)) for lang in ("es", "en")}
    try:
        # A
        out["A_catalogo_igual"] = mcp["es"].definiciones() == definiciones()
        # B
        b = {"llamadas": 0, "iguales": 0, "diferentes": []}
        for traza in sorted((AQUI / "resultados" / "trazas").glob("piloto*.jsonl")):
            for linea in open(traza, encoding="utf-8"):
                e = json.loads(linea)
                if e["tipo"] != "herramienta" or e["herramienta"] == "responder":
                    continue
                lang = e["tarea"].rsplit("-", 1)[1]
                rn = normal(nat[lang].llamar(e["herramienta"], e["argumentos"] or {}))
                rm = normal(mcp[lang].llamar(e["herramienta"], e["argumentos"] or {}))
                b["llamadas"] += 1
                if rn == rm:
                    b["iguales"] += 1
                else:
                    b["diferentes"].append({"traza": traza.name, "tarea": e["tarea"], "herramienta": e["herramienta"]})
        out["B_trazas"] = b
        # C
        tareas = {}
        for lang in ("es", "en"):
            for linea in open(AQUI / "golden" / f"tareas_{lang}.jsonl", encoding="utf-8"):
                t = json.loads(linea)
                tareas[t["id"]] = t
        c = {"claves": 0, "iguales": 0, "exactas": 0, "tareas_exito": 0, "tareas": 0}
        for linea in open(AQUI / "resultados" / "piloto2_detalle.jsonl", encoding="utf-8"):
            d = json.loads(linea)
            c["tareas"] += 1
            c["tareas_exito"] += verificar(tareas[d["id"]], d["final"], conn, d["estado"])["exito"]
            for x in (d["final"] or {}).get("resultados", []):
                args = {"sql": x["sql"], "max_filas": 200}
                lang = d["id"].rsplit("-", 1)[1]
                rn, rm = normal(nat[lang].llamar("ejecutar_sql", args)), normal(mcp[lang].llamar("ejecutar_sql", args))
                c["claves"] += 1
                c["iguales"] += rn == rm
                c["exactas"] += verificar({**tareas[d["id"]], "salida": {x["clave"]: tareas[d["id"]]["salida"][x["clave"]]}},
                                          {"resultados": [x]}, conn, "respondida")["claves"][x["clave"]]["exacta"]
        out["C_golden"] = c
        # D
        d_res = []
        for usuario in ("analista", "almacenista", "vendedor"):
            hn = Herramientas(Contexto.de_usuario(usuario, conexion=conn))
            with HerramientasMCP(usuario) as hm:
                for nombre, args in CASOS_D:
                    rn, rm = normal(hn.llamar(nombre, args)), normal(hm.llamar(nombre, args))
                    d_res.append({"usuario": usuario, "herramienta": nombre, "args": args, "igual": rn == rm,
                                  "resultado": "ok" if rn["ok"] else rn["error"]["tipo"]})
        out["D_permisos"] = d_res
    finally:
        for m in mcp.values():
            m.cerrar()
    res = AQUI / "resultados"
    (res / "mcp_equivalencia.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    b, c = out["B_trazas"], out["C_golden"]
    filas = ["| User | Tool | Arguments | Result | Identical |", "|---|---|---|---|---|"]
    for x in out["D_permisos"]:
        filas.append(f"| {x['usuario']} | {x['herramienta']} | `{json.dumps(x['args'], ensure_ascii=False)[:90]}` | {x['resultado']} | "
                     f"{'yes' if x['igual'] else '**NO**'} |")
    md = [
        "# Activity 4: native tools vs MCP server",
        "",
        f"Generated by [`servidor_mcp/equivalencia.py`](../servidor_mcp/equivalencia.py). No model calls. Native role: `{rol}`.",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| A. `tools/list` equals `definiciones()` (names, descriptions, JSON Schema) | {'yes' if out['A_catalogo_igual'] else '**NO**'} |",
        f"| B. Replay of every tool call in the pilot traces | {b['iguales']}/{b['llamadas']} identical |",
        f"| C. Gold keys from pilot 2, run through both paths | {c['iguales']}/{c['claves']} identical; {c['exactas']}/{c['claves']} exact against the gold set; {c['tareas_exito']}/{c['tareas']} tasks successful |",
        f"| D. Permissions and errors, 3 users × {len(CASOS_D)} cases | {sum(x['igual'] for x in out['D_permisos'])}/{len(out['D_permisos'])} identical |",
        "",
        "## D. Permissions and errors",
        "",
        *filas,
        "",
    ]
    (res / "mcp_equivalencia.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[4:10]))
    ok = out["A_catalogo_igual"] and b["iguales"] == b["llamadas"] and c["iguales"] == c["claves"] and all(x["igual"] for x in out["D_permisos"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
