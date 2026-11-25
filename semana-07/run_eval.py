#!/usr/bin/env python3
"""NLQ-Inventory bilingual evaluation (semana 7).

For each question (Spanish and English) and each model:
1. The model writes one PostgreSQL SELECT from the question and schema.schema.sql.
2. The reference SQL and the predicted SQL run in a read-only session (role copilot_ro).
3. Result sets are compared as multisets, allowing extra predicted columns (execution accuracy).

Usage (from the repo root, with the project venv):
    NLQ_DSN=... python semana-07/run_eval.py --validar          # keep only questions whose reference returns rows
    NLQ_DSN=... python semana-07/run_eval.py --modelos anthropic:claude-haiku-5-5 openai:gpt-5.6-luna

API keys come from the environment or semana-05/.env. NLQ_DSN must use the read-only role.
"""
import argparse
import http.client
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import permutations
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ROOT = RAIZ.parent
DATASET = RAIZ / "datasets" / "nlq_bilingual.jsonl"
VALIDADO = RAIZ / "datasets" / "nlq_validado.jsonl"
SETS = {
    "facil": (RAIZ / "datasets" / "nlq_bilingual.jsonl", RAIZ / "datasets" / "nlq_validado.jsonl"),
    "dificil": (RAIZ / "datasets" / "nlq_hard_bilingual.jsonl", RAIZ / "datasets" / "nlq_hard_validado.jsonl"),
    "seguimiento": (RAIZ / "datasets" / "nlq_seguimiento.jsonl", RAIZ / "datasets" / "nlq_seguimiento_validado.jsonl"),
    "cadenas": (RAIZ / "datasets" / "nlq_cadenas.jsonl", RAIZ / "datasets" / "nlq_cadenas_validado.jsonl"),
}
SCHEMA = RAIZ / "schema.sql"
SCHEMAS = {"corto": SCHEMA, "completo": RAIZ / "schema_completo.sql"}
TABLAS = {"suppliers", "products", "warehouses", "stock", "sales_daily", "purchase_orders", "doc_chunks"}
PRECIOS = RAIZ / "prices.json"
RESULTADOS = RAIZ / "resultados"
FLOAT_DIGITS = 2
MAX_EXTRA_COLS = 8
TIMEOUT_SQL = "5s"
MAX_TOKENS_SQL = 4096  # headroom for reasoning tokens (Gemini counts reasoning as output)

_spec = importlib.util.spec_from_file_location("run_prompts", ROOT / "semana-05" / "run_prompts.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)


# --- Result comparison (adapted from inventory-copilot/evals/run_sql_eval.py) ---

def normalize_value(v):
    # SUM without COALESCE returns NULL when there are no rows: it is treated as 0 on both sides.
    if v is None:
        return 0
    if isinstance(v, bool):
        return v
    if isinstance(v, (Decimal, float, int)):
        return round(float(v), FLOAT_DIGITS)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def normalize_rows(rows):
    return [tuple(normalize_value(v) for v in r) for r in rows]


def _same_rows(a, b, order_matters):
    return a == b if order_matters else Counter(a) == Counter(b)


def results_match(gold_rows, pred_rows, order_matters=False):
    gold, pred = normalize_rows(gold_rows), normalize_rows(pred_rows)
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    k, n = len(gold[0]), len(pred[0])
    if n < k or n > MAX_EXTRA_COLS:
        return n == k and _same_rows(gold, pred, order_matters)
    for idx in permutations(range(n), k):
        if _same_rows(gold, [tuple(r[i] for i in idx) for r in pred], order_matters):
            return True
    return False


# --- SQL ---

def extraer_sql(texto):
    limpio = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", texto.strip()).strip().rstrip(";").strip()
    if ";" in limpio or not re.match(r"^(SELECT|WITH)\b", limpio, re.IGNORECASE):
        return None
    return limpio


def sistema_sql(esquema=SCHEMA, citas=False):
    texto_esquema = esquema.read_text(encoding="utf-8")
    instruccion = ("Output the SQL, then on a final line by itself write TABLES: followed by the comma-separated "
                   "names of the tables your SQL reads from. No markdown, no comments, no explanation." if citas
                   else "Output only the SQL: no markdown, no comments, no explanation.")
    return ("You translate questions about an inventory database into one PostgreSQL SELECT statement. "
            + instruccion + " Use only the tables and columns in the schema. "
            "Never write anything other than a single SELECT or WITH ... SELECT.\n\n"
            "Schema:\n" + texto_esquema)


def ejecutar(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def conectar(dsn):
    import psycopg
    conn = psycopg.connect(dsn, autocommit=True)
    conn.read_only = True
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = '{TIMEOUT_SQL}'")
    return conn


# --- Models ---

def llamar_modelo(spec, pregunta, intentos=3, sistema=None, ejemplos=()):
    """Calls the model, retrying on network or server failures.

    If every attempt fails, it returns a record with the error instead of stopping the run.
    """
    proveedor, modelo = spec.split(":", 1)
    plantilla = {"nombre": "nlq_inventario", "version": "1.0.0", "sistema": sistema or sistema_sql(),
                 "usuario": "{pregunta}", "ejemplos": list(ejemplos)}
    cuerpo = rp.construir(proveedor, plantilla, {"pregunta": pregunta}, modelo, MAX_TOKENS_SQL)
    clave = os.environ.get(rp.PROVEEDORES[proveedor]["clave"], "")
    ultimo_error = None
    for intento in range(1, intentos + 1):
        inicio = time.perf_counter()
        try:
            crudo = rp.llamar(proveedor, cuerpo, clave, modelo)
            latencia = time.perf_counter() - inicio
            r = rp.interpretar(proveedor, crudo, modelo)
            return {"texto": r["texto"], "tokens_in": r["tokens_entrada"] or 0,
                    "tokens_out": r["tokens_salida"] or 0, "latencia_s": round(latencia, 3),
                    "error": None}
        except (SystemExit, OSError, http.client.HTTPException) as error:
            ultimo_error = str(error)[:200] or type(error).__name__
            # 4xx errors other than 429 (balance, quota, key, model) are not retried.
            if ultimo_error.startswith("Error HTTP 4") and not ultimo_error.startswith("Error HTTP 429"):
                break
            time.sleep(2 ** intento)
    return {"texto": "", "tokens_in": 0, "tokens_out": 0, "latencia_s": None, "error": ultimo_error}


def costo_usd(spec, tokens_in, tokens_out):
    precio = json.loads(PRECIOS.read_text(encoding="utf-8")).get(spec, {})
    if precio.get("in") is None or precio.get("out") is None:
        return None
    return (tokens_in * precio["in"] + tokens_out * precio["out"]) / 1_000_000


def separar_citas(texto):
    lineas = texto.strip().splitlines()
    if lineas and lineas[-1].strip().upper().startswith("TABLES:"):
        tablas = [t.strip().strip("`\"'").lower() for t in lineas[-1].split(":", 1)[1].split(",") if t.strip()]
        return "\n".join(lineas[:-1]), tablas
    return texto, []


def tablas_del_sql(sql):
    return sorted({t.lower() for t in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_]+)", sql, re.IGNORECASE)} & TABLAS)


def metricas_citas(citadas, referencia):
    citadas, referencia = set(citadas), set(referencia)
    interseccion = len(citadas & referencia)
    precision = interseccion / len(citadas) if citadas else 0.0
    exhaustividad = interseccion / len(referencia) if referencia else 1.0
    return citadas == referencia, round(precision, 3), round(exhaustividad, 3)


def citas_resumen(filas, activo):
    if not activo:
        return {}
    medibles = [f for f in filas if f.get("tablas_citadas") is not None and f["sql_predicho"] is not None]
    if not medibles:
        return {"citas_exactas": None, "citas_precision": None, "citas_exhaustividad": None}
    m = [metricas_citas(f["tablas_citadas"], f["tablas_referencia"]) for f in medibles]
    n = len(m)
    return {"citas_exactas": round(sum(x[0] for x in m) / n, 3),
            "citas_precision": round(sum(x[1] for x in m) / n, 3),
            "citas_exhaustividad": round(sum(x[2] for x in m) / n, 3)}


# --- Flow ---

def cargar(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def validar(conn):
    """Keeps only questions (per language) whose reference SQL runs and returns rows."""
    lineas = cargar(DATASET)
    descartadas = []
    buenas = []
    for linea in lineas:
        try:
            filas = ejecutar(conn, linea["sql"])
        except Exception as error:
            descartadas.append((linea["id"], f"error: {str(error)[:120]}"))
            continue
        if not filas:
            descartadas.append((linea["id"], "sin filas"))
            continue
        buenas.append(linea)
    VALIDADO.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in buenas), encoding="utf-8")
    print(f"Valid: {len(buenas)} of {len(lineas)}. Discarded: {len(descartadas)}")
    for id_, motivo in descartadas:
        print(f"  {id_}: {motivo}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--validar", "--validate", action="store_true")
    parser.add_argument("--modelos", "--models", nargs="+", default=[], metavar="MODELS")
    parser.add_argument("--limite", "--limit", type=int, default=None, metavar="LIMIT")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--set", choices=sorted(SETS), default="facil", help="facil (100 cases), dificil (50 x 2 languages), seguimiento (previous turn) or cadenas (3 turns)")
    parser.add_argument("--esquema", "--schema", choices=sorted(SCHEMAS), default="corto", help="corto (schema.sql) or completo (schema_completo.sql)")
    parser.add_argument("--sin-historial", "--no-history", action="store_true", help="control: omit the previous turn of the follow-up questions")
    parser.add_argument("--citas", "--citations", action="store_true", help="ask the model to list its tables and measure precision and recall")
    args = parser.parse_args()

    global DATASET, VALIDADO
    DATASET, VALIDADO = SETS[args.set]
    print(f"Set: {args.set} ({DATASET.name})")
    sistema = sistema_sql(SCHEMAS[args.esquema], args.citas)
    print(f"Schema: {args.esquema}  citations: {args.citas}")

    rp.cargar_env_local()
    dsn = os.environ.get("NLQ_DSN", "")
    if not dsn:
        sys.exit("NLQ_DSN is missing (the copilot_ro read-only role).")
    conn = conectar(dsn)

    if args.validar:
        validar(conn)
        return

    if not VALIDADO.exists():
        sys.exit("Run --validar first to generate datasets/nlq_validado.jsonl.")
    if not args.modelos:
        sys.exit("Pass --modelos, for example anthropic:claude-haiku-5-5 openai:gpt-5.6-luna")

    items = cargar(VALIDADO)
    if args.limite:
        items = items[:args.limite]
    gold = {it["id"]: ejecutar(conn, it["sql"]) for it in items}

    detalle = []
    for spec in args.modelos:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            respuestas = list(pool.map(lambda it: (it, llamar_modelo(spec, it["question"], sistema=sistema, ejemplos=[] if args.sin_historial else it.get("ejemplos", []))), items))
        for it, resp in respuestas:
            if resp.get("error"):
                detalle.append({"modelo": spec, "id": it["id"], "lang": it["lang"], "ok": False,
                                "categoria": "error_api", "sql_predicho": None, "tokens_in": 0,
                                "tokens_out": 0, "latencia_s": None, "detalle_error": resp["error"]})
                continue
            texto, citadas = separar_citas(resp["texto"]) if args.citas else (resp["texto"], None)
            sql = extraer_sql(texto)
            if sql is None:
                ok, categoria = False, "sin_sql"
            else:
                try:
                    pred = ejecutar(conn, sql)
                    ok = results_match(gold[it["id"]], pred, it["order_matters"])
                    categoria = "correcta" if ok else "resultado_distinto"
                except Exception:
                    conn.rollback() if not conn.autocommit else None
                    ok, categoria = False, "error_ejecucion"
            detalle.append({"modelo": spec, "id": it["id"], "lang": it["lang"], "ok": ok,
                            "categoria": categoria, "sql_predicho": sql,
                            "tokens_in": resp["tokens_in"], "tokens_out": resp["tokens_out"],
                            "latencia_s": resp["latencia_s"],
                            "tablas_citadas": citadas, "tablas_referencia": tablas_del_sql(it["sql"])})
        print(f"Done: {spec}")

    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTADOS.mkdir(exist_ok=True)
    (RESULTADOS / f"detalle_{marca}.jsonl").write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in detalle), encoding="utf-8")

    resumen = []
    grupos = defaultdict(list)
    for d in detalle:
        grupos[(d["modelo"], d["lang"])].append(d)
    for (spec, lang), filas in sorted(grupos.items()):
        correctas = sum(f["ok"] for f in filas)
        costo = sum(costo_usd(spec, f["tokens_in"], f["tokens_out"]) or 0 for f in filas)
        precio_verificado = costo_usd(spec, 1, 1) is not None
        resumen.append({"modelo": spec, "idioma": lang, "n": len(filas), "correctas": correctas,
                        "exactitud": round(correctas / len(filas), 3),
                        "costo_usd": round(costo, 4) if precio_verificado else None,
                        "costo_por_respuesta_correcta": (round(costo / correctas, 6)
                                                         if precio_verificado and correctas else None),
                        "errores": dict(Counter(f["categoria"] for f in filas if not f["ok"])),
                        "set": args.set, "esquema": args.esquema, "citas": args.citas, "sin_historial": args.sin_historial,
                        **citas_resumen(filas, args.citas)})
    (RESULTADOS / f"resumen_{marca}.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    for fila in resumen:
        print(f"{fila['modelo']:<32} {fila['idioma']}  accuracy {fila['exactitud']:.3f}  "
              f"correct {fila['correctas']}/{fila['n']}  errors {fila['errores']}")


if __name__ == "__main__":
    main()
