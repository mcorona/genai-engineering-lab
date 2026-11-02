"""Verdad de referencia de la auditoría de esquema legado (semana 16, actividad 2).

Calcula, desde la base y no a mano:
- diccionario.json: cada columna del esquema `legado` con su tabla y columna originales (vistas de la semana 10,
  resueltas con sqlglot sobre semana-10/legado/legado.sql), significado (diccionarios de las semanas 10 y 13 más
  etiquetas.json), tipo (catálogo), llave primaria y foránea (restricciones de las tablas base, traducidas a nombres
  legados; en tablas nativas, las llaves foráneas lógicas de etiquetas.json), unidad y si es dato personal.
- riesgos.json: los riesgos sembrados de etiquetas.json con el resultado de su consulta de evidencia, más las
  reglas de negocio que viven fuera de la base y las notas con instrucciones inyectadas (con hash de su texto).

Uso:
    PG_DSN=... python construir.py              # recalcula y compara con lo congelado (sale 1 si difiere)
    PG_DSN=... python construir.py --escribir   # regenera diccionario.json, riesgos.json y manifiesto.json

Requiere la base preparada como en CI: semana-07/ci/preparar_base.py, semana-10/legado/legado.sql,
semana-13/seguridad/artnot.sql y semana-16/verdad/riesgos.sql. Basta un rol de solo lectura.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

import psycopg
import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)  # legado.sql trae SET y GRANT que sqlglot no modela

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
VISTAS_SQL = RAIZ / "semana-10" / "legado" / "legado.sql"
DICC_10 = RAIZ / "semana-10" / "legado" / "diccionario.json"
DICC_13 = RAIZ / "semana-13" / "herramientas" / "diccionario_extra.json"
REGLAS = RAIZ / "semana-13" / "golden" / "reglas_negocio.json"
ETIQUETAS = AQUI / "etiquetas.json"
CONGELADOS = ("diccionario.json", "riesgos.json")
HASHEADOS = CONGELADOS + ("etiquetas.json", "riesgos.sql", "construir.py")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def mapa_vistas() -> dict[str, dict]:
    """vista legada -> {"base": tabla, "columnas": {col_legada: col_base}} desde los CREATE VIEW de la semana 10."""
    vistas = {}
    for st in sqlglot.parse(VISTAS_SQL.read_text(encoding="utf-8"), read="postgres"):
        if not (isinstance(st, exp.Create) and (st.args.get("kind") or "").upper() == "VIEW"):
            continue
        sel = st.expression
        cols = {}
        for e in sel.expressions:
            assert isinstance(e, exp.Alias) and isinstance(e.this, exp.Column), e.sql()
            cols[e.alias] = e.this.name
        vistas[st.this.name] = {"base": sel.args["from_"].this.name, "columnas": cols}
    return vistas


def catalogo(conn) -> dict:
    esquema_base = conn.execute(
        "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relname = 'stock' AND c.relkind = 'r' AND n.nspname <> 'legado' ORDER BY 1 LIMIT 1").fetchone()[0]
    cols = conn.execute(
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), c.relkind::text, a.attnotnull "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'legado' AND a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r', 'v') "
        "ORDER BY c.relname, a.attnum").fetchall()

    def restricciones(esquema):
        filas = conn.execute(
            "SELECT r.relname, c.contype::text, "
            "ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n, o) "
            "      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.n ORDER BY k.o)::text[], "
            "f.relname, ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n, o) "
            "      JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.n ORDER BY k.o)::text[] "
            "FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid JOIN pg_namespace n ON n.oid = r.relnamespace "
            "LEFT JOIN pg_class f ON f.oid = c.confrelid WHERE n.nspname = %s AND c.contype IN ('p', 'f')",
            (esquema,)).fetchall()
        pk, fk = {}, {}
        for tabla, tipo, columnas, ref, refcols in filas:
            if tipo == "p":
                pk[tabla] = list(columnas)
            else:
                for c, rc in zip(columnas, refcols or []):
                    fk[(tabla, c)] = (ref, rc)
        return pk, fk

    return {"esquema_base": esquema_base, "columnas": cols, "base": restricciones(esquema_base),
            "legado": restricciones("legado")}


def diccionario(conn) -> list[dict]:
    vistas = mapa_vistas()
    cat = catalogo(conn)
    etq = json.loads(ETIQUETAS.read_text(encoding="utf-8"))
    signif = {**json.loads(DICC_10.read_text(encoding="utf-8")), **json.loads(DICC_13.read_text(encoding="utf-8")),
              **etq["significados_nativos"]}
    base_a_legado = {v["base"]: k for k, v in vistas.items()}
    pk_base, fk_base = cat["base"]
    pk_leg, fk_leg = cat["legado"]
    filas = []
    for tabla, col, tipo, kind, no_nulo in cat["columnas"]:
        clave = f"{tabla}.{col}"
        if kind == "v":
            v = vistas[tabla]
            base, col_base = v["base"], v["columnas"][col]
            inverso = {b: l for l, b in v["columnas"].items()}
            pk = col_base in pk_base.get(base, [])
            ref = fk_base.get((base, col_base))
            fk = None
            if ref:
                vista_ref = base_a_legado[ref[0]]
                fk = f"{vista_ref}.{({b: l for l, b in vistas[vista_ref]['columnas'].items()})[ref[1]]}"
            fuente_fk = "restriccion_tabla_base" if fk else None
            original = {"tabla": base, "columna": col_base}
            assert inverso[col_base] == col
        else:
            pk = col in pk_leg.get(tabla, [])
            ref = fk_leg.get((tabla, col))
            fk = f"{ref[0]}.{ref[1]}" if ref else etq["fk_logicas"].get(clave)
            fuente_fk = ("restriccion_legado" if ref else "etiqueta") if fk else None
            original = None
        filas.append({
            "tabla": tabla, "columna": col, "original": original,
            "significado": signif[tabla]["columnas"][col], "tipo": tipo, "llave_primaria": pk,
            "llave_foranea": fk, "fuente_llave_foranea": fuente_fk, "unidad": etq["unidades"].get(clave),
            "datos_personales": clave in etq["datos_personales"],
        })
    return filas


def riesgos(conn) -> dict:
    etq = json.loads(ETIQUETAS.read_text(encoding="utf-8"))
    salida = []
    for r in etq["riesgos"]:
        evidencia = [list(f) if len(f) > 1 else f[0] for f in conn.execute(r["sql"]).fetchall()]
        salida.append({**{k: r[k] for k in ("id", "categoria", "tabla", "descripcion", "sql")},
                       "evidencia": [str(x) if not isinstance(x, list) else [str(y) for y in x] for x in evidencia]})
    reglas = json.loads(REGLAS.read_text(encoding="utf-8"))["reglas"]
    nombres = {c for t in json.loads(DICC_10.read_text(encoding="utf-8")).values() for c in t["columnas"]}
    fuera = [{"id": r["id"], "nombre": r["nombre_en"], "fuente": r["fuente"],
              "columnas_citadas": sorted(set(re.findall(r"\b([a-z]{3}_[a-z]{2,4})\b", r["es"] + " " + r["en"])) & nombres)} for r in reglas]
    notas = conn.execute("SELECT not_id, not_art, not_txt FROM legado.artnot ORDER BY not_id").fetchall()
    inyectadas = [{"not_id": i, "not_art": a, "tipo": etq["inyecciones"][str(i)],
                   "sha256_texto": hashlib.sha256(t.encode()).hexdigest()}
                  for i, a, t in notas if str(i) in etq["inyecciones"]]
    return {"riesgos": salida, "reglas_fuera_de_la_base": fuera, "notas_inyectadas": inyectadas,
            "notas_limpias": [i for i, _, _ in notas if str(i) not in etq["inyecciones"]]}


def calcular(dsn: str) -> dict[str, str]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")  # aun con PG_ADMIN_DSN, no escribe
        d, r = diccionario(conn), riesgos(conn)
    dump = lambda x: json.dumps(x, ensure_ascii=False, indent=1) + "\n"  # noqa: E731
    return {"diccionario.json": dump(d), "riesgos.json": dump(r)}


def manifiesto(contenidos: dict[str, str]) -> dict:
    d = json.loads(contenidos["diccionario.json"])
    r = json.loads(contenidos["riesgos.json"])
    por_cat = {}
    for x in r["riesgos"]:
        por_cat[x["categoria"]] = por_cat.get(x["categoria"], 0) + 1
    return {
        "descripcion": "Verdad de referencia de la auditoría de esquema legado, semana 16. Congelada: cualquier cambio "
                       "exige regenerar con construir.py --escribir y revisar en PR.",
        "tablas": len({x["tabla"] for x in d}), "columnas": len(d),
        "llaves_primarias": sum(x["llave_primaria"] for x in d),
        "llaves_foraneas": sum(bool(x["llave_foranea"]) for x in d),
        "datos_personales": sum(x["datos_personales"] for x in d),
        "riesgos_por_categoria": por_cat, "reglas_fuera_de_la_base": len(r["reglas_fuera_de_la_base"]),
        "notas_inyectadas": len(r["notas_inyectadas"]),
        "sha256": {p: sha(AQUI / p) for p in HASHEADOS},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--escribir", action="store_true")
    a = ap.parse_args(argv)
    dsn = os.environ.get("PG_DSN") or os.environ["PG_ADMIN_DSN"]
    nuevos = calcular(dsn)
    if a.escribir:
        for nombre, texto in nuevos.items():
            (AQUI / nombre).write_text(texto, encoding="utf-8")
        m = manifiesto(nuevos)
        (AQUI / "manifiesto.json").write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in m.items() if k not in ("sha256", "descripcion")}, ensure_ascii=False))
        return 0
    distintos = [n for n, t in nuevos.items() if (AQUI / n).read_text(encoding="utf-8") != t]
    print("verdad recalculada = congelada" if not distintos else f"DIFIERE: {distintos}")
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
