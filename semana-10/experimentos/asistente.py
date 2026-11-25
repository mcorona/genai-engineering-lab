"""Activity 7: the integrated assistant (NLQ + document RAG) with citations.

Configurations, over the integrated gold set (102 questions):
- integrado: activity 6 routing (Haiku low) with a fallback: if the route is sql and the query fails, returns 0 rows or the
  NLQ tool abstains (NO_SQL: the data is not in the schema), the documents are also queried. Mixed route:
  both tools.
  The abstention applies only on the sql route (and in solo_sql); on the mixed route the NLQ always generates a query.
- integrado_sin_abstencion: the same, but the NLQ tool cannot abstain (the activity 6 fallback as it was).
  It measures what the abstention contributes; it was added after the pilot, where int-imagen-11 was routed to sql and
  the query invented a "service level" with rows, without triggering the fallback.
- solo_sql: always the NLQ tool.
- solo_docs: always the document tool.
Tools:
- NLQ: Haiku 5.5 low with the legacy DDL + the dictionary (activity 2); it runs over the legacy schema with the read-only
  role (NLQ_DSN, search_path = legado).
- Document: the pgvector index semana10.chunks with tenant_id and roles (the filter inside the query), top 20 with bge-m3,
  reranking with Haiku (week 8) and top 5. Content: the week 8 text corpus + PDF tables via pdfplumber
  (activity 3) + the inventory record and delivery note via Haiku (activity 4) + image descriptions via Haiku (activity 5).
Answer: Haiku 5.5 medium, using only the context, citing [SQL] and [D1]..[D5]. Judge: Sonnet 5.5 low against the reference.
Metrics, fixed before the run, per configuration, type and language: the judge's accuracy; document citation precision
(cited passages with evidence / cited passages); correct SQL citation (it cites [SQL] and its result matches the
reference's); cost and latency per question (without the judge, which is reported separately).
Cache per question and configuration (resultados/asistente_cache.json); --limite N for a pilot.
Requires PG_ADMIN_DSN (to build the index), NLQ_DSN (the copilot_ro role), LM Studio with bge-m3, and ANTHROPIC_API_KEY.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[0]
REPO = RAIZ.parent
RES = RAIZ / "resultados"
CORPUS = REPO / "semana-08" / "corpus"
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(REPO / "semana-08" / "experimentos"))
import ruteo  # noqa: E402
import sql_legado as sl  # noqa: E402
from chunking_pasajes import ESTRATEGIAS  # noqa: E402
from embeddings_comparacion import emb_bge  # noqa: E402
from reranking import llamar_haiku  # noqa: E402

trocear = ESTRATEGIAS["fijo_400_solape_80"]
PRECIOS = sl.PRECIOS
HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
TOP_CAND, TOP_DOCS, MAX_FILAS = 20, 5, 40
ROLES = {**json.loads((REPO / "semana-09" / "datasets" / "permisos.json").read_text(encoding="utf-8"))["roles_por_documento"]}
ROLES = {Path(k).stem: v for k, v in ROLES.items()}
ROLES.update(json.loads((RAIZ / "datasets" / "permisos_semana10.json").read_text(encoding="utf-8"))["roles_por_documento"])
USUARIO = {"tenant": "alfa", "roles": sorted({r for rs in ROLES.values() for r in rs})}
CONFIGS = ("integrado", "integrado_sin_abstencion", "solo_sql", "solo_docs")

SIS_RESP = ("Eres el asistente de una distribuidora industrial. Responde la pregunta usando SOLO el contexto dado, en el "
            "idioma de la pregunta, de forma breve y completa. Cita la fuente de cada dato: [SQL] para el resultado de la "
            "consulta y [D1], [D2], … para los pasajes de documentos. Si el contexto no alcanza para responder, dilo y no "
            "inventes datos.")
SIS_JUEZ = ("Eres un evaluador estricto. Recibes una pregunta, la referencia correcta y la respuesta de un asistente. La "
            "respuesta es correcta si contiene la información esencial de la referencia sin contradecirla (puede agregar "
            "detalles o citas). Si la referencia es una lista o un conjunto de filas, la respuesta debe incluir esos "
            "elementos. Responde SOLO con JSON: {\"correcta\": true} o {\"correcta\": false}.")


def anthropic(modelo, esfuerzo, sistema, contenido, max_tokens=4000):
    cuerpo = {"model": modelo, "max_tokens": max_tokens, "system": sistema, "output_config": {"effort": esfuerzo},
              "messages": [{"role": "user", "content": contenido}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                          "x-api-key": os.environ["ANTHROPIC_API_KEY"]})
    for intento in range(4):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and intento < 3:
                time.sleep(2 ** (intento + 1))
                continue
            raise SystemExit(f"API HTTP {e.code} ({modelo}): {e.read().decode()[:300]}")
    if d.get("stop_reason") == "max_tokens":
        raise SystemExit(f"Output truncated by max_tokens ({modelo}).")
    u, p = d["usage"], PRECIOS[f"anthropic:{modelo}"]
    return ("".join(b.get("text", "") for b in d["content"] if b.get("type") == "text"),
            (u["input_tokens"] * p["in"] + u["output_tokens"] * p["out"]) / 1e6, time.perf_counter() - t0)


# ---------- document index ----------

def documentos():
    docs = {p.stem: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
    ext = RAIZ / "resultados"
    for stem in ("tarifas_flete", "matriz_proveedores"):
        docs[stem] = (ext / "pdf_extracciones" / f"pdfplumber__{stem}.txt").read_text(encoding="utf-8")
    ocr = json.loads((ext / "ocr_extracciones" / "claude_claude-haiku-5-5_low.json").read_text(encoding="utf-8"))
    for stem in ("acta_inventario_norte", "remision_r4471"):
        docs[stem] = ocr[stem]["texto"]
    img = json.loads((ext / "imagenes_extracciones" / "claude_claude-haiku-5-5_low.json").read_text(encoding="utf-8"))
    for stem in ("grafica_nivel_servicio", "plano_cedis_occidente"):
        docs[stem] = img[f"desc::{stem}"]["texto"]
    faltan = set(docs) - set(ROLES)
    if faltan:
        raise SystemExit(f"Documents without roles: {sorted(faltan)}")
    return docs


def indexar():
    docs = documentos()
    filas = [(s, c) for s, t in docs.items() for c in trocear(t, s)]
    vecs, _ = emb_bge([c for _, c in filas], "doc")
    with psycopg.connect(os.environ["PG_ADMIN_DSN"], autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS semana10")
        conn.execute("DROP TABLE IF EXISTS semana10.chunks")
        conn.execute(f"CREATE TABLE semana10.chunks (id int PRIMARY KEY, tenant_id text NOT NULL, roles text[] NOT NULL, "
                     f"source text NOT NULL, content text NOT NULL, embedding vector({len(vecs[0])}) NOT NULL)")
        conn.execute("CREATE INDEX ON semana10.chunks USING hnsw (embedding vector_cosine_ops)")
        with conn.cursor() as cur:
            for i, ((s, c), v) in enumerate(zip(filas, vecs)):
                cur.execute("INSERT INTO semana10.chunks VALUES (%s,%s,%s,%s,%s,%s::vector)",
                            (i, "alfa", ROLES[s], s, c, "[" + ",".join(map(str, v)) + "]"))
        conn.execute("GRANT USAGE ON SCHEMA semana10 TO copilot_ro")
        conn.execute("GRANT SELECT ON semana10.chunks TO copilot_ro")
    print(f"index: {len(docs)} documents, {len(filas)} chunks in semana10.chunks", file=sys.stderr)


# ---------- tools ----------

ABSTENCION = ("\n\nIf the schema and dictionary do not contain the data the question asks for (for example service "
              "levels, freight rates, policies, approvals, warehouse layouts or documents), do not approximate it with "
              "other columns: output exactly NO_SQL instead of a query.")


def ejecutar_lectura(conn, sql):
    """Activity 8: every NLQ query runs in a READ ONLY transaction that is always rolled back. psycopg does not apply
    read_only in autocommit mode, and without this `SELECT lo_create(0)` wrote to the database."""
    filas = None
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        filas = conn.execute(sql).fetchall()
        raise psycopg.Rollback()
    return filas


class Herramientas:
    def __init__(self):
        self.conn_ref = sl.re7.conectar(os.environ["NLQ_DSN"])
        # NLQ_LEGADO_DSN: the copilot_nlq role (only SELECT on the legacy views; activity 8). Without it, copilot_ro.
        self.conn_leg = sl.re7.conectar(os.environ.get("NLQ_LEGADO_DSN") or os.environ["NLQ_DSN"])
        self.conn_leg.execute("SET search_path = legado")
        self.conn_doc = sl.re7.conectar(os.environ["NLQ_DSN"])
        self.conn_doc.execute("SET hnsw.ef_search = 100")
        self.conn_doc.execute("SET hnsw.iterative_scan = strict_order")
        self.sis_sql_base = sl.sistema("\n".join(sl.DDL_LEGADO[t] for t in sl.DICCIONARIO), sl.texto_diccionario(list(sl.DICCIONARIO)))
        self.sis_sql = self.sis_sql_base + ABSTENCION

    def sql(self, pregunta, abstener=True):
        texto, costo, lat = anthropic(HAIKU, "low", self.sis_sql if abstener else self.sis_sql_base, pregunta, max_tokens=8000)
        if abstener and texto.strip().upper().startswith("NO_SQL"):
            return {"sql": None, "filas": None, "error": "abstencion", "costo": costo, "lat": lat, "texto": texto}
        consulta = sl.re7.extraer_sql(texto)
        filas, error = None, None
        if consulta is None:
            error = "no_es_select"
        else:
            try:
                filas = ejecutar_lectura(self.conn_leg, consulta)
            except Exception as e:  # noqa: BLE001
                error = type(e).__name__
        return {"sql": consulta, "filas": filas, "error": error, "costo": costo, "lat": lat, "texto": texto}

    def docs(self, pregunta, usuario=USUARIO):
        t0 = time.perf_counter()
        v, _ = emb_bge([pregunta], "query")
        cands = self.conn_doc.execute(
            "SELECT id, source, content FROM semana10.chunks WHERE tenant_id = %s AND roles && %s::text[] "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (usuario["tenant"], usuario["roles"], "[" + ",".join(map(str, v[0])) + "]", TOP_CAND)).fetchall()
        ids = [c[0] for c in cands]
        cands = [(c[1], c[2]) for c in cands]
        orden, tin, tout = llamar_haiku(pregunta, cands)
        p = PRECIOS[f"anthropic:{HAIKU}"]
        ordenados = list(dict.fromkeys(orden or [])) + [i for i in range(len(cands)) if i not in (orden or [])]
        return {"chunks": [cands[i] for i in ordenados[:TOP_DOCS]], "ids": [ids[i] for i in ordenados[:TOP_DOCS]], "costo": (tin * p["in"] + tout * p["out"]) / 1e6,
                "lat": time.perf_counter() - t0, "rerank_fallo": orden is None}


def contexto(res_sql, res_docs):
    partes = []
    if res_sql:
        if res_sql["error"] == "abstencion":
            partes.append("[SQL] La base de datos no contiene este dato; no se ejecutó consulta.")
        elif res_sql["error"]:
            partes.append(f"[SQL] La consulta falló ({res_sql['error']}).")
        else:
            filas = res_sql["filas"]
            muestra = "\n".join(str(tuple(f)) for f in filas[:MAX_FILAS])
            extra = f"\n… ({len(filas) - MAX_FILAS} filas más)" if len(filas) > MAX_FILAS else ""
            partes.append(f"[SQL] Consulta ejecutada:\n{res_sql['sql']}\nResultado ({len(filas)} filas):\n{muestra or '(sin filas)'}{extra}")
    if res_docs:
        for i, (s, c) in enumerate(res_docs["chunks"], 1):
            partes.append(f"[D{i}] (documento: {s})\n{c}")
    return "\n\n".join(partes)


def correr(h, x, config):
    t0 = time.perf_counter()
    costo, ruta, res_sql, res_docs, respaldo = 0.0, None, None, None, False
    if config.startswith("integrado"):
        r = ruteo.clasificar(HAIKU, "low", x["question"])
        costo += r["costo_usd"]
        ruta = r["ruta"] or "mixta"
    else:
        ruta = {"solo_sql": "sql", "solo_docs": "documental"}[config]
    if ruta in ("sql", "mixta"):
        # The abstention applies only to the integrated assistant's sql route (where there is a fallback); on the mixed route the question
        # also carries the document part, and the NLQ tool abstained from the whole question (run 1: mixed 0/6 ES).
        res_sql = h.sql(x["question"], abstener=config == "solo_sql" or (config == "integrado" and ruta == "sql"))
        costo += res_sql["costo"]
        if config.startswith("integrado") and ruta == "sql" and (res_sql["error"] or not res_sql["filas"]):
            respaldo = True
    if ruta in ("documental", "mixta") or respaldo:
        res_docs = h.docs(x["question"])
        costo += res_docs["costo"]
    texto, c, _ = anthropic(HAIKU, "medium", SIS_RESP, f"Pregunta: {x['question']}\n\nContexto:\n{contexto(res_sql, res_docs)}")
    costo += c
    return {"ruta": ruta, "respaldo": respaldo, "respuesta": texto, "costo": round(costo, 7),
            "latencia_s": round(time.perf_counter() - t0, 3),
            "sql": res_sql["sql"] if res_sql else None, "sql_error": res_sql["error"] if res_sql else None,
            "sql_filas": [list(map(str, f)) for f in res_sql["filas"][:MAX_FILAS]] if res_sql and res_sql["filas"] else [],
            "sql_n": len(res_sql["filas"]) if res_sql and res_sql["filas"] is not None else None,
            "docs": [[s, c] for s, c in res_docs["chunks"]] if res_docs else [],
            "rerank_fallo": res_docs["rerank_fallo"] if res_docs else None}


def referencia(x, gold_filas):
    partes = []
    if "sql" in x:
        filas = gold_filas[(x["id"], x["lang"])]
        partes.append(f"Resultado correcto de la base de datos ({len(filas)} filas): " + "; ".join(str(tuple(f)) for f in filas[:MAX_FILAS]))
    if x.get("gold"):
        partes += [f"Pasaje del documento {g['source']}: {g['passage']}" for g in x["gold"]]
    if x.get("respuesta"):
        partes.append(f"Respuesta correcta (del documento {x['fuente']}): {x['respuesta']}")
    return "\n".join(partes)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("**", "")).strip().lower()


def evidencia(x, s, c):
    if x.get("gold"):
        return any(Path(g["source"]).stem == s and norm(g["passage"]) in norm(c) for g in x["gold"])
    if x.get("respuesta"):
        return Path(x["fuente"]).stem == s and norm(x["respuesta"]) in norm(c)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", "--limit", type=int, default=0, help="the first N questions of each type (and non-text format) per language (pilot)", metavar="LIMIT")
    ap.add_argument("--sin-indexar", "--no-index", action="store_true")
    args = ap.parse_args()
    if not args.sin_indexar:
        indexar()
    items = [json.loads(l) for lang in ("es", "en") for l in (RAIZ / "datasets" / f"integrado_{lang}.jsonl").read_text(encoding="utf-8").splitlines()]
    if args.limite:
        vistos, sel = {}, []
        for x in items:
            k = (x["lang"], x["tipo"], x.get("formato"))
            if vistos.get(k, 0) < args.limite:
                vistos[k] = vistos.get(k, 0) + 1
                sel.append(x)
        items = sel
    h = Herramientas()
    gold_filas = {(x["id"], x["lang"]): sl.re7.ejecutar(h.conn_ref, x["sql"]) for x in items if "sql" in x}
    ruta_cache = RES / ("asistente_cache_prueba.json" if args.limite else "asistente_cache.json")
    cache = json.loads(ruta_cache.read_text(encoding="utf-8")) if ruta_cache.exists() else {}
    detalle = []
    for x in items:
        for config in CONFIGS:
            clave = f"{config}::{x['id']}::{x['lang']}"
            if clave not in cache:
                r = correr(h, x, config)
                juicio, cj, _ = anthropic(SONNET, "low", SIS_JUEZ,
                                          f"Pregunta: {x['question']}\n\nReferencia correcta:\n{referencia(x, gold_filas)}\n\nRespuesta del asistente:\n{r['respuesta']}",
                                          max_tokens=2000)
                m = re.search(r"\{.*?\}", juicio, re.S)
                try:
                    r["correcta"] = bool(json.loads(m.group(0))["correcta"]) if m else None
                except (json.JSONDecodeError, KeyError):
                    r["correcta"] = None
                r["costo_juez"] = round(cj, 7)
                cache[clave] = r
                ruta_cache.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            r = cache[clave]
            citadas = sorted({int(n) for n in re.findall(r"\[D(\d+)\]", r["respuesta"]) if 0 < int(n) <= len(r["docs"])})
            con_ev = [n for n in citadas if evidencia(x, *r["docs"][n - 1])]
            sql_ok = None
            if "sql" in x:
                sql_ok = int(bool(r["sql"]) and not r["sql_error"] and "[SQL]" in r["respuesta"] and r["sql_n"] is not None
                             and sl.re7.results_match(gold_filas[(x["id"], x["lang"])], sl.re7.ejecutar(h.conn_leg, r["sql"]), x["order_matters"]))
            tipo = x["tipo"] + (f"/{x['formato']}" if "formato" in x else "")
            detalle.append({"config": config, "id": x["id"], "lang": x["lang"], "tipo": tipo, "ruta": r["ruta"],
                            "respaldo": int(r["respaldo"]), "correcta": "" if r["correcta"] is None else int(r["correcta"]),
                            "citas_doc": len(citadas), "citas_doc_con_evidencia": len(con_ev),
                            "cita_sql_correcta": "" if sql_ok is None else sql_ok,
                            "costo_usd": r["costo"], "costo_juez_usd": r["costo_juez"], "latencia_s": r["latencia_s"]})
        print(f"{x['id']} {x['lang']}: " + " ".join(f"{d['config']}={d['correcta']}" for d in detalle[-len(CONFIGS):]), file=sys.stderr)

    print("| Configuration | Type | Language | Accuracy (judge) | Document citation precision | Correct SQL citation | Cost per question (USD) | p50 latency (s) |")
    print("|---|---|---|---|---|---|---|---|")
    grupos = [("sql", lambda t: t == "sql"), ("documental", lambda t: t == "documental"),
              ("no textual", lambda t: t.startswith("no_textual")), ("mixta", lambda t: t == "mixta"), ("TOTAL", lambda t: True)]
    for config in CONFIGS:
        for nombre, pred in grupos:
            for lang in ("es", "en"):
                f = [d for d in detalle if d["config"] == config and d["lang"] == lang and pred(d["tipo"])]
                if not f:
                    continue
                jz = [d["correcta"] for d in f if d["correcta"] != ""]
                cd = sum(d["citas_doc"] for d in f)
                prec = f"{sum(d['citas_doc_con_evidencia'] for d in f) / cd:.3f} ({cd})" if cd else "-"
                cs = [d["cita_sql_correcta"] for d in f if d["cita_sql_correcta"] != ""]
                print(f"| {config} | {nombre} | {lang} | {sum(jz) / len(jz):.3f} ({sum(jz)}/{len(jz)}) | {prec} | "
                      f"{f'{sum(cs)}/{len(cs)}' if cs else '-'} | {statistics.mean(d['costo_usd'] for d in f):.5f} | "
                      f"{statistics.median(d['latencia_s'] for d in f):.1f} |")
    for cf in ("integrado", "integrado_sin_abstencion"):
        integ = [d for d in detalle if d["config"] == cf]
        print(f"\nDocument fallback triggered in {cf}: {sum(d['respaldo'] for d in integ)} of {len(integ)} questions.")
    print(f"Total cost without the judge: ${sum(d['costo_usd'] for d in detalle):.4f}; judge: ${sum(d['costo_juez_usd'] for d in detalle):.4f}; "
          f"judgments without valid JSON: {sum(1 for d in detalle if d['correcta'] == '')}")
    with (RES / ("asistente_detalle_prueba.csv" if args.limite else "asistente_detalle.csv")).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detalle[0].keys()))
        w.writeheader()
        w.writerows(detalle)


if __name__ == "__main__":
    main()
