"""Quality evaluator of the legacy-schema-audit outputs (semana 16, activity 5). `claude plugin eval` has no code graders,
so this is where quality is scored against the activity 2 ground truth, deterministically and without the API.

For each run directory (resultados/<run>/ with auditoria/ and corrida.json):
- Dictionary (auditoria/diccionario.yaml, read flexibly so a no-plugin run that invents its own layout still scores):
  meaning accuracy per column (the concept of eval/conceptos.json named in the meaning), precision and recall of
  primary keys, foreign keys and personal-data columns.
- Risks (auditoria/riesgos.md): every SQL block is RE-EXECUTED in a read-only transaction; a seeded risk of
  verdad/riesgos.json counts as found when a finding of its category (inferred from the header or the text) names its
  table and its re-executed SQL returns the evidence: the same ids or SKUs (or, for U-MOVINV, the affected rows), or
  for personal data, which must not be shown, their count.
- Cost, tokens, turns and time from corrida.json.

    PG_ADMIN_DSN=... python eval/calidad.py corrida_manual corrida_subagentes ...   # runs under resultados/
    python eval/calidad.py --sin-base corrida_manual                                # no re-execution (counts only)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

S16 = Path(__file__).resolve().parents[1]
RES = S16 / "resultados"
VERDAD = S16 / "verdad"
CONCEPTOS = {k: v for k, v in json.loads((Path(__file__).parent / "conceptos.json").read_text(encoding="utf-8")).items()
             if k != "descripcion"}
CATEGORIAS = ("datos_personales", "huerfanos", "duplicados", "nulos_en_clave", "unidades_inconsistentes",
              "reglas_fuera_de_la_base", "instrucciones_inyectadas")
PALABRAS = {  # to classify findings of a run that does not use the plugin's category names
    "datos_personales": r"personal|pii|privacy|privacidad|datos personales|gdpr|lfpdppp",
    "huerfanos": r"orphan|hu[eé]rfan|referential|integridad referencial|dangling|no (matching )?parent|no existe|"
                 r"inexistente|does not exist|non-?existent|missing parent",
    "duplicados": r"duplicad|duplicat|repetid|repeated|twice",
    "nulos_en_clave": r"null|nulo|vac[ií]o|empty|missing (item|warehouse|supplier)",
    "unidades_inconsistentes": r"\bunit|unidad|uom",
    "reglas_fuera_de_la_base": r"constraint|restricci|business rule|regla|not enforced|no se aplica|check",
    "instrucciones_inyectadas": r"inject|inyec|instruction|instrucci|prompt",
}
# Evidence that proves the same risk at another grain: the rows instead of the items they belong to.
EQUIVALENTES = {"U-MOVINV": {"31", "32", "33"}}
ALIAS = {"meaning": ("meaning", "description", "significado", "descripcion", "descripción", "definition"),
         "pk": ("primary_key", "pk", "llave_primaria", "clave_primaria", "is_primary_key"),
         "fk": ("foreign_key", "fk", "references", "llave_foranea", "clave_foranea", "referencia", "ref"),
         "pii": ("personal_data", "pii", "datos_personales", "dato_personal", "is_pii", "sensitive")}
NOMBRE = ("name", "nombre", "column", "columna", "table", "tabla")
COLUMNAS = ("columns", "columnas")

def _campo(d: dict, clave: str):
    for a in ALIAS[clave]:
        if a in d:
            return d[a]
    return None


def _bool(v) -> bool:
    """true/yes/sí, and the 'declared' or 'inferred' a dictionary may write for a key ("inferida", "declarada")."""
    return v is True or (isinstance(v, str) and v.strip().lower().split(" ")[0].strip("(),") in (
        "true", "yes", "sí", "si", "inferida", "inferido", "inferred", "declarada", "declarado", "declared"))


def _fk(v, tabla_de: dict[str, str]) -> str | None:
    """'artmst.art_cd', 'artmst(art_cd)', 'legado.artmst.art_cd' or {table, column} -> 'artmst.art_cd'."""
    if isinstance(v, dict):
        v = f"{v.get('table') or v.get('tabla')}.{v.get('column') or v.get('columna')}"
    if not isinstance(v, str) or not v.strip() or v.strip().lower() in ("null", "none", "~", "no", "n/a", "-"):
        return None
    texto = v.strip().lower().replace("legado.", "")
    m = re.search(r"\b([a-z]{3,6})\s*[.(]\s*([a-z]{3}_[a-z0-9]{2,4})\b", texto)   # it may carry a note around it
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    col = v.strip().lower()
    return f"{tabla_de[col]}.{col}" if col in tabla_de else None


def columnas_del_yaml(y) -> dict[str, dict]:
    """{'tabla.columna': attrs} from the plugin's layout (tables: [{name, columns: [{name, ...}]}]) or from mappings
    {table: {columns: {col: attrs}}} / {table: [{name, ...}]}."""
    out: dict[str, dict] = {}

    def nombre_de(d: dict):
        return next((d[k] for k in NOMBRE if isinstance(d.get(k), str)), None)

    def columnas(tabla, cols):
        if isinstance(cols, list):
            for c in cols:
                if isinstance(c, dict) and nombre_de(c):
                    out[f"{tabla}.{nombre_de(c)}".lower()] = c
        elif isinstance(cols, dict):
            for nombre, c in cols.items():
                out[f"{tabla}.{nombre}".lower()] = c if isinstance(c, dict) else {"meaning": c}

    def andar(nodo):
        if isinstance(nodo, dict):
            cols = next((nodo[k] for k in COLUMNAS if k in nodo), None)
            if nombre_de(nodo) and cols is not None:
                columnas(nombre_de(nodo).split(".")[-1], cols)
                return
            for k, v in nodo.items():
                sub = next((v[c] for c in COLUMNAS if isinstance(v, dict) and c in v), None)
                if sub is not None and not nombre_de(v):
                    columnas(str(k).split(".")[-1], sub)
                else:
                    andar(v)
        elif isinstance(nodo, list):
            for x in nodo:
                andar(x)

    andar(y)
    return out


def prf(pred: set, real: set) -> dict:
    tp = len(pred & real)
    return {"precision": round(tp / len(pred), 3) if pred else 0.0, "recall": round(tp / len(real), 3) if real else None,
            "aciertos": tp, "predichas": len(pred), "reales": len(real)}


def evaluar_diccionario(texto: str) -> dict:
    import yaml
    verdad = {f"{x['tabla']}.{x['columna']}": x for x in json.loads((VERDAD / "diccionario.json").read_text("utf-8"))}
    tabla_de = {k.split(".")[1]: k.split(".")[0] for k in verdad}
    try:
        cols = columnas_del_yaml(yaml.safe_load(texto) or {})
        valido = True
    except Exception:  # noqa: BLE001
        cols, valido = {}, False
    exactas = [k for k, rx in CONCEPTOS.items() if k in cols and re.search(rx, str(_campo(cols[k], "meaning") or ""), re.I)]
    return {
        "yaml_valido": valido, "columnas_cubiertas": len(set(cols) & set(verdad)), "columnas_reales": len(verdad),
        "significado_exacto": round(len(exactas) / len(verdad), 3),
        "significado_fallido": sorted(set(verdad) - set(exactas)),
        "llave_primaria": prf({k for k, c in cols.items() if _bool(_campo(c, "pk"))},
                              {k for k, x in verdad.items() if x["llave_primaria"]}),
        "llave_foranea": prf({f"{k}->{_fk(_campo(c, 'fk'), tabla_de)}" for k, c in cols.items() if _fk(_campo(c, "fk"), tabla_de)},
                             {f"{k}->{x['llave_foranea']}" for k, x in verdad.items() if x["llave_foranea"]}),
        "datos_personales": prf({k for k, c in cols.items() if _bool(_campo(c, "pii"))},
                                {k for k, x in verdad.items() if x["datos_personales"]}),
    }


def hallazgos(texto: str) -> list[dict]:
    """Sections of riesgos.md (### or ## headers) with their category, the tables they name and their SQL blocks."""
    partes = re.split(r"^(#{2,4} .+)$", texto, flags=re.M)
    out = []
    for i in range(1, len(partes), 2):
        cabecera, cuerpo = partes[i].strip("# ").strip(), partes[i + 1]
        if re.match(r"(?i)(not verified|no verificado|scope|alcance|summary|resumen|contents)", cabecera):
            continue
        # The plugin names one category; a free-form report may cover several in one finding
        # ("orphan and duplicated supplier contacts"), so every category its header names counts.
        cats = {c for c in CATEGORIAS if c in cabecera} or {c for c, rx in PALABRAS.items() if re.search(rx, cabecera, re.I)} \
            or {c for c, rx in PALABRAS.items() if re.search(rx, cuerpo[:600], re.I)}
        sqls = [q.strip() for q in re.findall(r"```sql\s*\n(.*?)```", cuerpo, re.S)]
        if sqls or cats:
            out.append({"cabecera": cabecera, "categorias": cats, "categoria": next(iter(sorted(cats)), None),
                        "texto": (cabecera + "\n" + cuerpo).lower(), "sql": sqls})
    return out


def tokens(x) -> set[str]:
    return set(re.findall(r"SKU-\d{4}|[A-Za-z_]+|\d+", json.dumps(x, ensure_ascii=False, default=str)))


def reejecutar(sql: str, dsn: str) -> tuple[bool, set[str], str]:
    sys.path.insert(0, str(S16 / "legacy-schema-audit" / "scripts"))
    import comun
    import psycopg
    import sqlglot
    try:   # a free-form report may put several SELECTs in one block: each one is checked and run on its own
        sentencias = [x.sql(dialect="postgres") for x in sqlglot.parse(sql, read="postgres") if x is not None]
    except sqlglot.errors.SqlglotError as e:
        return False, set(), f"no se pudo interpretar: {str(e).splitlines()[0][:120]}"
    toks: set[str] = set()
    if not sentencias:
        return True, set(), ""   # a block with only comments proves nothing and fails nothing
    for q in sentencias:
        try:
            comun.check_read_only(q)
        except ValueError as e:
            return False, set(), f"rechazada: {e}"
        try:
            with psycopg.connect(dsn, autocommit=False, options="-c statement_timeout=10000 -c search_path=legado") as c:
                c.read_only = True
                toks |= tokens(c.execute(q).fetchmany(5000))
                c.rollback()
        except Exception as e:  # noqa: BLE001
            return False, set(), str(e).splitlines()[0][:160]
    return True, toks, ""


TABLAS = ("almmst", "artmst", "artnot", "exidet", "movinv", "ocpcab", "prvcto", "prvmst", "vtadia")


def nombra(h: dict, tabla: str) -> bool:
    """The finding is about `tabla`: named in its header or, if the header names no table, in its text."""
    cab = h["cabecera"].lower()
    return tabla in cab if any(t in cab for t in TABLAS) else tabla in h["texto"]


def evaluar_riesgos(texto: str, dsn: str | None) -> dict:
    verdad = json.loads((VERDAD / "riesgos.json").read_text("utf-8"))["riesgos"]
    hs = hallazgos(texto)
    for h in hs:
        h["resultados"] = [reejecutar(q, dsn) for q in h["sql"]] if dsn else []
    detalle = []
    for r in verdad:
        esperado = tokens(r["evidencia"]) - {"trigger"}
        cand = [h for h in hs if r["categoria"] in h["categorias"] and (r["tabla"] is None or nombra(h, r["tabla"]))]
        encontrado, como = False, None
        for h in cand:
            if r["id"] == "R-FUERA":
                encontrado, como = True, h["cabecera"]
                break
            for ok, toks, _ in h["resultados"]:
                # Counts prove only personal-data findings, whose evidence must not show values; the rest need the ids.
                por_conteo = r["categoria"] == "datos_personales" and str(len(esperado)) in toks
                if ok and (esperado <= toks or EQUIVALENTES.get(r["id"], {"-"}) <= toks or por_conteo):
                    encontrado, como = True, h["cabecera"]
                    break
            if not dsn and not encontrado:   # without a database: the ids written in the finding
                if esperado <= tokens(h["texto"].upper().replace("SKU-", "SKU-")) or esperado <= tokens(h["texto"]):
                    encontrado, como = True, h["cabecera"] + " (sin re-ejecutar)"
            if encontrado:
                break
        detalle.append({"id": r["id"], "categoria": r["categoria"], "encontrado": encontrado, "hallazgo": como})
    sql_total = sum(len(h["sql"]) for h in hs)
    sql_ok = sum(ok for h in hs for ok, _, _ in h["resultados"])
    return {"hallazgos": len(hs), "sql": sql_total, "sql_reejecutado_ok": sql_ok if dsn else None,
            "sql_fallidos": [f"{h['cabecera'][:50]}: {e}" for h in hs for ok, _, e in h["resultados"] if not ok][:10],
            "recall_riesgos": round(sum(d["encontrado"] for d in detalle) / len(detalle), 3),
            "encontrados": sum(d["encontrado"] for d in detalle), "sembrados": len(detalle), "detalle": detalle}


def evaluar(corrida: str, dsn: str | None) -> dict:
    d = RES / corrida
    a = d / "auditoria"
    leer = lambda n: (a / n).read_text(encoding="utf-8") if (a / n).exists() else ""  # noqa: E731
    meta = json.loads((d / "corrida.json").read_text(encoding="utf-8")).get("corrida", {}) if (d / "corrida.json").exists() else {}
    uso = meta.get("uso") or {}
    return {
        "corrida": corrida, "modelo": meta.get("modelo"), "modo": meta.get("modo", "plugin"),
        "archivos": {n: (a / n).exists() for n in ("diccionario.yaml", "relaciones.mmd", "riesgos.md", "resumen.md")},
        "diccionario": evaluar_diccionario(leer("diccionario.yaml")),
        "riesgos": evaluar_riesgos(leer("riesgos.md"), dsn),
        "costo_equivalente_usd": meta.get("costo_equivalente_usd"), "segundos": meta.get("segundos"),
        "turnos": meta.get("turnos"),
        "tokens": {"entrada": (uso.get("input_tokens") or 0) + (uso.get("cache_creation_input_tokens") or 0),
                   "cache_leido": uso.get("cache_read_input_tokens"), "salida": uso.get("output_tokens")},
        "llamadas_bd": sum(v for k, v in (meta.get("herramientas") or {}).items()
                           if k in ("list_objects", "describe_object", "profile_table", "run_select")),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corridas", nargs="+")
    ap.add_argument("--sin-base", action="store_true")
    ap.add_argument("--salida", default=str(RES / "calidad.json"))
    a = ap.parse_args(argv)
    dsn = None if a.sin_base else (os.environ.get("PG_ADMIN_DSN") or os.environ.get("PG_DSN"))
    res = [evaluar(c, dsn) for c in a.corridas]
    Path(a.salida).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'corrida':<22} {'modelo':<7} {'signif':>6} {'PK P/R':>9} {'FK P/R':>9} {'PII P/R':>9} {'riesgos':>7} "
          f"{'SQL ok':>7} {'$eq':>6} {'s':>5} {'tok sal':>8}")
    for r in res:
        d, k = r["diccionario"], r["riesgos"]
        pr = lambda x: f"{x['precision']:.2f}/{(x['recall'] or 0):.2f}"  # noqa: E731
        print(f"{r['corrida']:<22} {str(r['modelo']):<7} {d['significado_exacto']:>6.2f} {pr(d['llave_primaria']):>9} "
              f"{pr(d['llave_foranea']):>9} {pr(d['datos_personales']):>9} {k['encontrados']:>3}/{k['sembrados']:<3} "
              f"{str(k['sql_reejecutado_ok']) + '/' + str(k['sql']):>7} {r['costo_equivalente_usd'] or 0:>6.2f} "
              f"{r['segundos'] or 0:>5} {r['tokens']['salida'] or 0:>8}")
    print(f"\nDetalle en {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
