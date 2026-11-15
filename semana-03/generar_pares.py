"""Unit 3: generates and validates question -> SQL pairs over the LegacyBridge legacy schema.

1. Templates per business rule (docs/legacy-defects.md): each with several ways of
   asking in Spanish and real values sampled from the database.
2. Each SQL statement runs with the lb_reader role (read-only, with a timeout). It is discarded
   if it fails or returns no rows.
3. Questions and SQL that match the LegacyBridge evaluation set are discarded.
4. The rest is split 80/20 by template (fixed seed) into training and evaluation.

Usage (from the repository root; needs LB_READER_DSN in the environment):
    uv run python semana-03/generar_pares.py
Optional: LEGACYBRIDGE_DIR points to the legacybridge-v2 folder (default ~/legacybridge-v2).
"""
import json
import os
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
import yaml

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "data"
DATOS.mkdir(exist_ok=True)
DSN = os.environ["LB_READER_DSN"]
GOLDEN = Path(os.environ.get("LEGACYBRIDGE_DIR", Path.home() / "legacybridge-v2")) / "evals" / "golden_set.yaml"
SEMILLA = 42
POR_PLANTILLA = 6  # values of each template

ESQUEMA = """Base PostgreSQL legacy de facturación e inventario (sintética, con defectos documentados).
clientes(clave CHAR(10), nombre, rfc, estado CHAR(3), telefono, email, status A|I|B, falta CHAR(8) YYYYMMDD)
productos(clave CHAR(8), descripcion, linea CHAR(2), precio NUMERIC, status A|B)
faccab(serie CHAR(2), numfac CHAR(10), cliente CHAR(10), rfc, fecha CHAR(8) YYYYMMDD, subtotal/iva/total CHAR(15) texto con $ y comas, ref1 VARCHAR(12), status V|C|B, fcaptura CHAR(14))
facdet(serie, numfac CHAR(10) a veces con espacios, renglon, producto CHAR(8), cantidad NUMERIC, precio/importe VARCHAR texto, status A|B)
invart(clave CHAR(12), descr, unimed CHAR(3), factor INT, costo VARCHAR texto con coma decimal, activo S|N|NULL, alta CHAR(8))
invalm(clave CHAR(3), nombre, tipo P|T|C)
invexi(alm CHAR(3), art CHAR(12), cant NUMERIC, corte CHAR(6) YYYYMM)
invprv(clave CHAR(6), nombre, rfc, activo)
invmov(fol INT, fecha CHAR(8), alm, art CHAR(12), tipo E|S|T|A|I|O, cant NUMERIC, uni CHAR(3) CJA|PZA, prov, ref VARCHAR(20), cancel CHAR(1) C, obs)
Responde solo con una consulta SQL de PostgreSQL de solo lectura, sin explicación."""

# Current invoices: the latest capture per (series, folio) (FAC-09). The status filter is applied afterwards.
VIG = """WITH vigentes AS (
  SELECT DISTINCT ON (serie, LPAD(TRIM(numfac), 10, '0'))
         serie, LPAD(TRIM(numfac), 10, '0') AS folio, cliente, rfc, fecha, total, ref1, status
  FROM faccab
  ORDER BY serie, LPAD(TRIM(numfac), 10, '0'), fcaptura DESC
)"""

def monto(col):
    return f"REPLACE(REPLACE(TRIM({col}), '$', ''), ',', '')::numeric"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# Each template: SQL with placeholders for the values, questions in Spanish and the possible values.
PLANTILLAS = [
    dict(id="cliente_datos", vig=False,
         sql="SELECT nombre, estado FROM clientes WHERE clave = '{clave}' AND status <> 'B'",
         preguntas=["¿Quién es el cliente {clave} y de qué estado es?",
                    "Dame el nombre y el estado del cliente con clave {clave}.",
                    "¿Cómo se llama el cliente {clave} y dónde está registrado?"],
         valores=lambda S: [dict(clave=c.strip()) for c in S["clave"]]),
    dict(id="clientes_activos_estado", vig=False,
         sql="SELECT COUNT(*) FROM clientes WHERE status = 'A' AND estado = '{estado}'",
         preguntas=["¿Cuántos clientes activos hay en {estado}?",
                    "Cuenta los clientes activos del estado {estado}.",
                    "¿Cuál es el número de clientes activos en {estado}?"],
         valores=lambda S: [dict(estado=e.strip()) for e in S["estado"]]),
    dict(id="facturas_vigentes_cliente", vig=True,
         sql="SELECT COUNT(*) FROM vigentes WHERE status = 'V' AND cliente = '{clave}'",
         preguntas=["¿Cuántas facturas vigentes tiene el cliente {clave}?",
                    "¿Cuántas facturas válidas se le han emitido al cliente {clave}?",
                    "¿Cuál es el número de facturas vigentes del cliente {clave}?"],
         valores=lambda S: [dict(clave=c.strip()) for c in S["cliente_fact"]]),
    dict(id="total_factura", vig=True,
         sql="SELECT {monto_total} AS total FROM vigentes WHERE status = 'V' AND serie = '{serie}' AND folio = '{folio}'",
         preguntas=["¿Cuál fue el total de la factura {folio} de la serie {serie}?",
                    "¿Cuánto suma la factura {folio}, serie {serie}?",
                    "Dame el total con IVA de la factura {folio} de la serie {serie}."],
         valores=lambda S: [dict(serie=s.strip(), folio=f) for s, f in S["factura"]]),
    dict(id="ventas_moneda_anio", vig=True,
         sql="SELECT ref1, SUM({monto_total}) AS total FROM vigentes WHERE status = 'V' AND fecha BETWEEN '{ini}' AND '{fin}' GROUP BY ref1 ORDER BY ref1",
         preguntas=["¿Cuánto se facturó en {y} separado por moneda?",
                    "Ventas de {y} por moneda.",
                    "¿Cuál fue el total facturado en {y}, desglosado por moneda?"],
         valores=lambda S: [dict(y=y, ini=f"{y}0101", fin=f"{y}1231") for y in (2001, 2002, 2003)]),
    dict(id="facturas_usd_anio", vig=True,
         sql="SELECT COUNT(*) FROM vigentes WHERE status = 'V' AND ref1 = 'USD' AND fecha BETWEEN '{ini}' AND '{fin}'",
         preguntas=["¿Cuántas facturas en dólares se emitieron en {y}?",
                    "¿Cuántas facturas vigentes en USD hay en {y}?",
                    "Cuenta las facturas en USD del año {y}."],
         valores=lambda S: [dict(y=y, ini=f"{y}0101", fin=f"{y}1231") for y in (2001, 2002, 2003)]),
    dict(id="ventas_mes_mxn", vig=True,
         sql="SELECT COUNT(*) AS facturas, SUM({monto_total}) AS total FROM vigentes WHERE status = 'V' AND fecha BETWEEN '{ini}' AND '{fin}'",
         preguntas=["¿Cuántas facturas vigentes hubo en {mes} de {y} y cuánto suman?",
                    "Dame el número de facturas y el monto total de {mes} de {y}.",
                    "¿Cuánto se vendió en {mes} de {y}?"],
         valores=lambda S: [dict(y=y, mes=MESES[m - 1], ini=f"{y}{m:02d}01", fin=f"{y}{m:02d}31")
                            for y in (2004, 2005, 2006) for m in (1, 4, 7, 10)]),
    dict(id="facturas_fecha_invalida", vig=True,
         sql="SELECT COUNT(*) FROM vigentes WHERE status = 'V' AND (fecha = '00000000' OR TRIM(fecha) = '')",
         preguntas=["¿Cuántas facturas vigentes no tienen una fecha válida?",
                    "¿Cuántas facturas válidas tienen la fecha en cero o vacía?",
                    "Cuenta las facturas vigentes con fecha inválida."],
         valores=lambda S: [dict()]),
    dict(id="lineas_factura", vig=True,
         sql=("SELECT d.renglon, d.producto, d.cantidad, {monto_importe} AS importe FROM facdet d "
              "JOIN vigentes f ON d.serie = f.serie AND LPAD(TRIM(d.numfac), 10, '0') = f.folio "
              "WHERE f.status = 'V' AND d.status = 'A' AND f.serie = '{serie}' AND f.folio = '{folio}' ORDER BY d.renglon"),
         preguntas=["¿Qué renglones tiene la factura {folio} de la serie {serie}?",
                    "Muéstrame las líneas de la factura {folio}, serie {serie}.",
                    "¿Qué productos y cantidades incluye la factura {folio} de la serie {serie}?"],
         valores=lambda S: [dict(serie=s.strip(), folio=f) for s, f in S["factura"]]),
    dict(id="facturas_cliente_inexistente", vig=True,
         sql="SELECT COUNT(*) FROM vigentes f WHERE f.status = 'V' AND NOT EXISTS (SELECT 1 FROM clientes c WHERE c.clave = f.cliente)",
         preguntas=["¿Cuántas facturas vigentes apuntan a un cliente que no existe en el catálogo?",
                    "¿Cuántas facturas válidas tienen un cliente que no está en clientes?",
                    "Cuenta las facturas vigentes sin cliente registrado."],
         valores=lambda S: [dict()]),
    dict(id="productos_activos_linea", vig=False,
         sql="SELECT COUNT(*) FROM productos WHERE status = 'A' AND linea = '{linea}'",
         preguntas=["¿Cuántos productos activos hay en la línea {linea}?",
                    "Cuenta los productos activos de la línea {linea}.",
                    "¿Cuántos productos vigentes tiene la línea {linea}?"],
         valores=lambda S: [dict(linea=l.strip()) for l in S["linea"]]),
    dict(id="precio_promedio_linea", vig=False,
         sql="SELECT ROUND(AVG(precio), 2) AS precio_promedio FROM productos WHERE status = 'A' AND linea = '{linea}'",
         preguntas=["¿Cuál es el precio promedio de los productos activos de la línea {linea}?",
                    "¿Cuánto cuesta en promedio un producto activo de la línea {linea}?",
                    "Dame el precio de lista promedio de la línea {linea}, solo productos activos."],
         valores=lambda S: [dict(linea=l.strip()) for l in S["linea"]]),
    dict(id="existencia_almacen", vig=False,
         sql=("WITH ultimo AS (SELECT DISTINCT ON (alm, art) alm, art, cant FROM invexi ORDER BY alm, art, corte DESC) "
              "SELECT SUM(u.cant) AS existencia FROM ultimo u JOIN invalm a ON a.clave = u.alm "
              "WHERE a.tipo = 'P' AND u.cant >= 0 AND u.alm = '{alm}'"),
         preguntas=["¿Cuánta existencia actual tiene el almacén {alm}?",
                    "¿Cuál es el inventario vigente del almacén {alm}?",
                    "Dame las existencias actuales del almacén {alm}, sin cantidades negativas."],
         valores=lambda S: [dict(alm=a.strip()) for a in S["almacen"]]),
    dict(id="salidas_unidades_base", vig=False,
         sql=("SELECT m.art, SUM(ABS(m.cant) * CASE WHEN m.uni = 'CJA' THEN COALESCE(NULLIF(a.factor, 0), 1) ELSE 1 END) AS unidades_base "
              "FROM invmov m LEFT JOIN invart a ON a.clave = m.art "
              "WHERE m.tipo IN ('S', 'O') AND m.cancel IS DISTINCT FROM 'C' AND m.ref NOT LIKE 'CANC-%' "
              "AND m.fecha BETWEEN '{ini}' AND '{fin}' GROUP BY m.art ORDER BY unidades_base DESC LIMIT 5"),
         preguntas=["¿Cuáles son los 5 artículos con más salidas en {y}, en unidades base?",
                    "¿Qué artículos tuvieron más salidas en {y}, contando cajas como unidades base?",
                    "Top 5 de artículos por salidas en {y}, en piezas base."],
         valores=lambda S: [dict(y=y, ini=f"{y}0101", fin=f"{y}1231") for y in (2002, 2003, 2004)]),
    dict(id="proveedores_por_rfc", vig=False,
         sql="SELECT COUNT(DISTINCT rfc) FROM invprv WHERE rfc IS NOT NULL",
         preguntas=["¿Cuántos proveedores distintos hay si se cuentan por RFC?",
                    "¿Cuántos proveedores reales hay, agrupando por RFC?"],
         valores=lambda S: [dict()]),
    dict(id="costo_articulo", vig=False,
         sql="SELECT descr, REPLACE(TRIM(costo), ',', '.')::numeric AS costo FROM invart WHERE clave = '{clave}'",
         preguntas=["¿Cuál es el costo unitario del artículo {clave}?",
                    "¿Cuánto cuesta el artículo {clave}?",
                    "Dame el costo y la descripción del artículo {clave}."],
         valores=lambda S: [dict(clave=c.strip()) for c in S["articulo"]]),
    dict(id="articulos_en_piezas", vig=False,
         sql="SELECT COUNT(*) FROM invart WHERE UPPER(TRIM(unimed)) IN ('PZA', 'PZ') AND activo = 'S'",
         preguntas=["¿Cuántos artículos activos se miden en piezas?",
                    "¿Cuántos artículos activos tienen unidad de medida pieza?"],
         valores=lambda S: [dict()]),
    dict(id="facturas_canceladas_anio", vig=True,
         sql="SELECT COUNT(*) FROM vigentes WHERE status = 'C' AND fecha BETWEEN '{ini}' AND '{fin}'",
         preguntas=["¿Cuántas facturas canceladas hubo en {y}?",
                    "¿Cuántas facturas se cancelaron en {y}?",
                    "Cuenta las facturas canceladas del año {y}."],
         valores=lambda S: [dict(y=y, ini=f"{y}0101", fin=f"{y}1231") for y in (2001, 2002, 2003, 2004)]),
    dict(id="agentes_facturas_anio", vig=True,
         sql=("SELECT ref1, COUNT(*) AS facturas FROM vigentes WHERE status = 'V' AND ref1 LIKE 'AG%' "
              "AND fecha BETWEEN '{ini}' AND '{fin}' GROUP BY ref1 ORDER BY facturas DESC"),
         preguntas=["¿Cuántas facturas emitió cada agente en {y}?",
                    "Ranking de agentes por número de facturas vigentes en {y}.",
                    "¿Qué agente tuvo más facturas vigentes en {y}?"],
         valores=lambda S: [dict(y=y, ini=f"{y}0101", fin=f"{y}1231") for y in (2004, 2005, 2006, 2007)]),
]


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def muestras(conn):
    def q(sql):
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    return {
        "clave": [r[0] for r in q("SELECT clave FROM clientes WHERE status <> 'B' ORDER BY md5(clave) LIMIT 30")],
        "estado": [r[0] for r in q("SELECT DISTINCT estado FROM clientes WHERE estado IS NOT NULL ORDER BY 1")],
        "cliente_fact": [r[0] for r in q("SELECT cliente FROM faccab WHERE cliente IS NOT NULL GROUP BY cliente ORDER BY md5(cliente) LIMIT 30")],
        "factura": q(VIG + " SELECT serie, folio FROM vigentes WHERE status = 'V' ORDER BY md5(serie || folio) LIMIT 40"),
        "linea": [r[0] for r in q("SELECT DISTINCT linea FROM productos WHERE linea IS NOT NULL ORDER BY 1")],
        "almacen": [r[0] for r in q("SELECT clave FROM invalm WHERE tipo = 'P' ORDER BY clave")],
        "articulo": [r[0] for r in q("SELECT clave FROM invart WHERE clave IS NOT NULL ORDER BY md5(clave) LIMIT 30")],
    }


def construir_candidatos(S):
    candidatos = []
    rng = random.Random(SEMILLA)
    for p in PLANTILLAS:
        valores = p["valores"](S)
        rng.shuffle(valores)
        for v in valores[:POR_PLANTILLA]:
            sql_cuerpo = p["sql"].format(
                monto_total=monto("total"), monto_importe=monto("d.importe"), **v)
            sql = (VIG + " " + sql_cuerpo) if p["vig"] else sql_cuerpo
            for pregunta in p["preguntas"]:
                candidatos.append(dict(plantilla=p["id"], pregunta=pregunta.format(**v), sql=sql))
    return candidatos


def validar(conn, sql):
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute(sql)
            filas = cur.fetchall()
        conn.rollback()
    except psycopg.Error as e:
        conn.rollback()
        return None, type(e).__name__ + ": " + str(e).splitlines()[0][:120]
    if not filas or all(all(c is None for c in f) for f in filas):
        return 0, "sin filas útiles"
    return len(filas), None


def cargar_golden():
    if not GOLDEN.exists():
        print(f"WARNING: {GOLDEN} not found; no questions are excluded from the evaluation set")
        return set(), set()
    casos = yaml.safe_load(GOLDEN.read_text(encoding="utf-8")) or []
    preguntas = {normalizar(c["question"]) for c in casos if c.get("question")}
    sqls = {re.sub(r"\s+", " ", (c.get("expected_sql") or "")).strip().lower() for c in casos}
    return preguntas, sqls


def main():
    golden_preguntas, golden_sqls = cargar_golden()
    with psycopg.connect(DSN) as conn:
        S = muestras(conn)
        candidatos = construir_candidatos(S)
        print(f"candidates generated: {len(candidatos)}")

        vistos, aceptados, rechazados = set(), [], []
        motivos = Counter()
        for c in candidatos:
            clave = normalizar(c["pregunta"])
            sql_norm = re.sub(r"\s+", " ", c["sql"]).strip().lower()
            if clave in vistos:
                motivos["pregunta duplicada"] += 1
                continue
            vistos.add(clave)
            if clave in golden_preguntas or sql_norm in golden_sqls:
                motivos["coincide con conjunto de evaluación"] += 1
                continue
            filas, error = validar(conn, c["sql"])
            if error:
                motivos[error.split(":")[0]] += 1
                rechazados.append(dict(c, motivo=error))
                continue
            aceptados.append(dict(c, filas=filas))

    # 80/20 split by template, with a fixed seed
    rng = random.Random(SEMILLA)
    grupos = defaultdict(list)
    for a in aceptados:
        grupos[a["plantilla"]].append(a)
    train, evaluacion = [], []
    for plantilla, items in sorted(grupos.items()):
        rng.shuffle(items)
        corte = round(len(items) * 0.8)
        train += items[:corte]
        evaluacion += items[corte:]

    def formato(item):
        return {"messages": [
            {"role": "system", "content": ESQUEMA},
            {"role": "user", "content": item["pregunta"]},
            {"role": "assistant", "content": item["sql"].strip()},
        ]}

    for nombre, items in (("pares_train.jsonl", train), ("pares_eval.jsonl", evaluacion)):
        with open(DATOS / nombre, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(formato(it), ensure_ascii=False) + "\n")
    with open(DATOS / "rechazados.jsonl", "w", encoding="utf-8") as f:
        for r in rechazados:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    resumen = dict(candidatos=len(candidatos), aceptados=len(aceptados), train=len(train),
                   eval=len(evaluacion), rechazados=len(rechazados), motivos=dict(motivos),
                   por_plantilla={k: len(v) for k, v in sorted(grupos.items())})
    (DATOS / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
