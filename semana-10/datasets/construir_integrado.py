"""Builds the week 10 integrated gold set and the non-text sources.

Types (51 questions per language):
- sql (15): from the week 7 hard set (nlq_hard_validado), with their reference SQL.
- document (15): week 9 base questions, with a literal passage from the week 8 corpus.
- non_text (15): 5 PDF-table, 5 OCR and 5 image questions. The answer is ONLY in new documents
  (semana-10/fuentes/), which do not exist in the text corpus; activities 3 to 5 turn them into a PDF, a
  scan or an image without changing their content.
- mixed (6): they need SQL and a document; they carry a reference SQL and a literal passage. Includes the plan's
  example (critical SKUs at risk today and who approves their urgent purchase), with the risk definition in
  skus_criticos.md: days of coverage (total stock / average daily sales over the last 30 days) lower than the lead time.

Validation without a database: literal passages in the corpus, non-text answers contained in their source.
SQL validation (every sql and mixed query): python3 construir_integrado.py --validar-sql with PG_DSN;
each query must run and return at least one row with no nulls.
"""
import json
import os
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
DS = R / "semana-10" / "datasets"
FUENTES = R / "semana-10" / "fuentes"
CORPUS = R / "semana-08" / "corpus"

# ---------- new sources (frozen content; the format is generated later) ----------
DOCS = {
    "tarifas_flete.md": """# Tarifas de flete entre CEDIS

> Documento sintético de una empresa ficticia (Distribuidora Industrial Ficticia, DIF). Versión 1.0. Formato de entrega: PDF con tabla.

| Ruta | Tarifa de flete normal (MXN) | Tránsito |
|---|---|---|
| Ciudad de México → Guadalajara | $8,500 | 1 día |
| Ciudad de México → Monterrey | $12,300 | 2 días |
| Guadalajara → Monterrey | $10,900 | 2 días |

Recargo por flete exprés: 35% sobre la tarifa normal.
""",
    "matriz_proveedores.md": """# Matriz de proveedores por categoría

> Documento sintético de una empresa ficticia (Distribuidora Industrial Ficticia, DIF). Versión 1.0. Formato de entrega: PDF con tabla.

| Proveedor | País | Categoría | Clasificación | Tiempo de entrega pactado |
|---|---|---|---|---|
| Aceros del Norte | MX | Herramienta | A | 7 días |
| Shenzhen Industrial Parts | CN | Eléctrico | B | 38 días |
| Bavaria Werkzeuge | DE | Herramienta | A | 27 días |
| Seguridad Andina | CO | Seguridad | C | 15 días |
""",
    "acta_inventario_norte.md": """# Acta de inventario físico, CEDIS Norte (Monterrey)

> Documento sintético de una empresa ficticia (Distribuidora Industrial Ficticia, DIF). Formato de entrega: escaneo.

Fecha del conteo: 30 de septiembre de 2026
Ubicaciones contadas: 1,240
Exactitud obtenida: 96.4%
Diferencia total valorizada: $18,240 MXN
Responsable: Laura Méndez, jefa de almacén
""",
    "remision_r4471.md": """# Nota de remisión R-4471

> Documento sintético de una empresa ficticia (Distribuidora Industrial Ficticia, DIF). Formato de entrega: escaneo.

Proveedor: Aceros del Norte
SKU: SKU-0042
Cantidad remitida: 120 piezas
Observaciones: 3 piezas dañadas en el empaque; se rechazan en recepción.
""",
}
IMAGENES = {
    "grafica_nivel_servicio.json": {
        "tipo": "gráfica de barras",
        "titulo": "Nivel de servicio por CEDIS, septiembre 2026",
        "barras": {"CEDIS Centro": "97.8%", "CEDIS Occidente": "95.1%", "CEDIS Norte": "98.6%"},
        "nota": "Documento sintético de una empresa ficticia (DIF). Formato de entrega: imagen PNG.",
    },
    "plano_cedis_occidente.json": {
        "tipo": "plano",
        "titulo": "Plano del CEDIS Occidente (Guadalajara)",
        "zonas": ["Andenes de recepción: 1 a 4", "Andenes de embarque: 5 a 8",
                  "Zona de SKUs críticos: junto al andén 2", "Zona de cuarentena: pasillo 12"],
        "nota": "Documento sintético de una empresa ficticia (DIF). Formato de entrega: imagen PNG.",
    },
}

# (format, source, ES question, EN question, answer)
NO_TEXTUAL = [
    ("pdf", "tarifas_flete.md", "¿Cuánto cuesta el flete normal de Guadalajara a Monterrey?",
     "How much does standard freight from Guadalajara to Monterrey cost?", "$10,900"),
    ("pdf", "tarifas_flete.md", "¿Qué recargo tiene el flete exprés sobre la tarifa normal?",
     "What surcharge does express freight have over the standard rate?", "35%"),
    ("pdf", "tarifas_flete.md", "¿Cuál es la tarifa de flete normal de Ciudad de México a Monterrey?",
     "What is the standard freight rate from Mexico City to Monterrey?", "$12,300"),
    ("pdf", "matriz_proveedores.md", "¿Qué tiempo de entrega pactado tiene Shenzhen Industrial Parts?",
     "What is the agreed lead time for Shenzhen Industrial Parts?", "38 días"),
    ("pdf", "matriz_proveedores.md", "¿Qué proveedor de la categoría Seguridad tiene clasificación C?",
     "Which supplier in the Safety category has a C rating?", "Seguridad Andina"),
    ("ocr", "acta_inventario_norte.md", "¿Qué exactitud se obtuvo en el inventario físico de septiembre del CEDIS Norte?",
     "What accuracy was obtained in the September physical inventory at the North distribution center?", "96.4%"),
    ("ocr", "acta_inventario_norte.md", "¿Cuál fue la diferencia total valorizada en el acta de inventario del CEDIS Norte?",
     "What was the total valued difference in the North distribution center inventory record?", "$18,240"),
    ("ocr", "acta_inventario_norte.md", "¿Quién fue la responsable del inventario físico del CEDIS Norte?",
     "Who was responsible for the physical inventory at the North distribution center?", "Laura Méndez"),
    ("ocr", "remision_r4471.md", "¿Cuántas piezas llegaron dañadas en la remisión R-4471?",
     "How many pieces arrived damaged in delivery note R-4471?", "3 piezas"),
    ("ocr", "remision_r4471.md", "¿Cuántas piezas se remitieron en la nota R-4471?",
     "How many pieces were shipped in delivery note R-4471?", "120 piezas"),
    ("imagen", "grafica_nivel_servicio.json", "¿Cuál fue el nivel de servicio más bajo entre los CEDIS en septiembre de 2026?",
     "What was the lowest service level among the distribution centers in September 2026?", "95.1%"),
    ("imagen", "grafica_nivel_servicio.json", "¿Qué nivel de servicio tuvo el CEDIS Norte en septiembre de 2026?",
     "What service level did the North distribution center have in September 2026?", "98.6%"),
    ("imagen", "grafica_nivel_servicio.json", "¿Qué nivel de servicio tuvo el CEDIS Centro en septiembre de 2026?",
     "What service level did the Central distribution center have in September 2026?", "97.8%"),
    ("imagen", "plano_cedis_occidente.json", "¿En qué pasillo está la zona de cuarentena del CEDIS Occidente?",
     "In which aisle is the quarantine zone of the West distribution center?", "pasillo 12"),
    ("imagen", "plano_cedis_occidente.json", "¿Junto a qué andén está la zona de SKUs críticos del CEDIS Occidente?",
     "Next to which dock is the critical SKU zone of the West distribution center?", "andén 2"),
]

SQL_IDS = ["hard-001", "hard-002", "hard-003", "hard-004", "hard-005", "hard-006", "hard-007", "hard-008",
           "hard-009", "hard-010", "hard-011", "hard-012", "hard-014", "hard-015", "hard-016"]
DOC_IDS = ["rec-02", "rec-03", "rec-06", "rec-09", "rec-12", "rec-17", "rec-19", "rec-20", "rec-24",
           "rec-27", "rec-29", "rec-31", "rec-35", "rec-39", "rec-43"]

# (ES question, EN question, reference SQL, document, literal passage)
MIXTAS = [
    ("¿Cuántos SKUs críticos hay en el catálogo y qué factor de seguridad usan en el punto de reorden?",
     "How many critical SKUs are in the catalog, and what safety factor do they use in the reorder point?",
     "SELECT count(*) FROM products WHERE critical",
     "politica_reorden.md", "Factor de seguridad para SKUs críticos: **1.5**."),
    ("¿Cuántas unidades se vendieron en total en septiembre de 2026 y cuál es el nivel de servicio objetivo?",
     "How many units were sold in total in September 2026, and what is the target service level?",
     "SELECT SUM(units) FROM sales_daily WHERE day >= DATE '2026-09-01' AND day < DATE '2026-10-01'",
     "indicadores_operacion.md", "El nivel de servicio objetivo es de **97%** de pedidos completos."),
    ("¿Qué proveedores tienen un tiempo de entrega mayor a 20 días y qué deben tener los SKUs críticos que surten?",
     "Which suppliers have a lead time over 20 days, and what must the critical SKUs they supply have?",
     "SELECT name FROM suppliers WHERE lead_time_days > 20",
     "skus_criticos.md", "Todo SKU crítico cuyo proveedor tenga un tiempo de entrega mayor a **20 días**"),
    ("¿Cuántas unidades hay en existencia en el almacén de Monterrey y cuántas posiciones de tarima tiene ese CEDIS?",
     "How many units are on hand in the Monterrey warehouse, and how many pallet positions does that center have?",
     "SELECT SUM(s.on_hand) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Monterrey'",
     "cedis_monterrey.md", "El CEDIS Norte (Monterrey) tiene capacidad para **12,000 posiciones** de tarima."),
    ("¿Cuántos productos tiene la categoría Seguridad y se les pueden aplicar descuentos?",
     "How many products are in the Safety category, and can discounts be applied to them?",
     "SELECT count(*) FROM products WHERE category = 'Seguridad'",
     "descuentos_clientes.md", "Los descuentos no aplican a productos de la categoría Seguridad."),
    ("¿Qué SKUs críticos están en riesgo hoy y quién aprueba su compra urgente?",
     "Which critical SKUs are at risk today, and who approves their urgent purchase?",
     "SELECT p.sku FROM products p "
     "JOIN suppliers s ON s.supplier_id = p.supplier_id "
     "JOIN (SELECT sku, SUM(on_hand) AS total FROM stock GROUP BY sku) t ON t.sku = p.sku "
     "JOIN (SELECT sku, SUM(units) / 30.0 AS diaria FROM sales_daily "
     "WHERE day > (SELECT max(day) FROM sales_daily) - 30 GROUP BY sku) v ON v.sku = p.sku "
     "WHERE p.critical AND v.diaria > 0 AND t.total / v.diaria < s.lead_time_days",
     "skus_criticos.md", "Requiere aprobación del gerente de compras sin"),
]


def norm(s):
    return re.sub(r"\s+", " ", s.replace("**", "")).strip().lower()


def construir():
    corpus = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
    fuentes = {**DOCS, **{n: json.dumps(d, ensure_ascii=False) for n, d in IMAGENES.items()}}
    hard = {}
    for l in open(R / "semana-07" / "datasets" / "nlq_hard_validado.jsonl", encoding="utf-8"):
        d = json.loads(l)
        hard[(d["id"][:-3], d["lang"])] = d
    base = {lang: {d["id"]: d for d in map(json.loads, open(R / "semana-09" / "datasets" / f"avanzado_{lang}.jsonl",
                                                          encoding="utf-8")) if d["tipo"] == "base"}
            for lang in ("es", "en")}
    errores, out = [], {"es": [], "en": []}
    for lang in ("es", "en"):
        for i in SQL_IDS:
            if (i, lang) not in hard:
                errores.append(f"{i}-{lang} no está en nlq_hard_validado")
                continue
            h = hard[(i, lang)]
            out[lang].append({"id": f"int-sql-{i[5:]}", "lang": lang, "tipo": "sql", "question": h["question"],
                              "sql": h["sql"], "order_matters": h["order_matters"], "origen": h["id"]})
        for i in DOC_IDS:
            d = base[lang][i]
            for g in d["gold"]:
                if g["passage"] not in corpus.get(g["source"], ""):
                    errores.append(f"{i}: pasaje no literal")
            out[lang].append({"id": f"int-doc-{i[4:]}", "lang": lang, "tipo": "documental", "question": d["question"],
                              "gold": d["gold"], "origen": i})
        for n, (fmt, fuente, es, en, resp) in enumerate(NO_TEXTUAL, 1):
            if norm(resp) not in norm(fuentes[fuente]):
                errores.append(f"no textual {n}: '{resp}' no está en {fuente}")
            if norm(resp) in norm(" ".join(corpus.values())):
                errores.append(f"no textual {n}: '{resp}' ya aparece en el corpus de texto; no mediría {fmt}")
            out[lang].append({"id": f"int-{fmt}-{n:02d}", "lang": lang, "tipo": "no_textual", "formato": fmt,
                              "fuente": fuente, "question": es if lang == "es" else en, "respuesta": resp})
        for n, (es, en, sql, fuente, pasaje) in enumerate(MIXTAS, 1):
            if pasaje not in corpus[fuente]:
                errores.append(f"mixta {n}: pasaje no literal en {fuente}")
            out[lang].append({"id": f"int-mix-{n:02d}", "lang": lang, "tipo": "mixta",
                              "question": es if lang == "es" else en, "sql": sql, "order_matters": False,
                              "gold": [{"source": fuente, "passage": pasaje}]})
    if errores:
        raise SystemExit("\n".join(errores))
    FUENTES.mkdir(parents=True, exist_ok=True)
    for n, t in DOCS.items():
        (FUENTES / n).write_text(t, encoding="utf-8")
    for n, d in IMAGENES.items():
        (FUENTES / n).write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for lang, items in out.items():
        with open(DS / f"integrado_{lang}.jsonl", "w", encoding="utf-8") as f:
            for x in items:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    conteo = {}
    for x in out["es"]:
        k = x["tipo"] + (f"/{x['formato']}" if "formato" in x else "")
        conteo[k] = conteo.get(k, 0) + 1
    print(f"per language: {len(out['es'])} questions {conteo}; validation without a database OK")
    return out


def validar_sql(out):
    import psycopg
    malos = []
    with psycopg.connect(os.environ["PG_DSN"]) as conn:
        for x in out["es"] + out["en"]:
            if "sql" not in x:
                continue
            try:
                filas = conn.execute(x["sql"]).fetchall()
            except psycopg.Error as e:
                conn.rollback()
                malos.append(f"{x['id']}-{x['lang']}: error {e.__class__.__name__}")
                continue
            if not filas or any(v is None for v in filas[0]):
                malos.append(f"{x['id']}-{x['lang']}: sin filas o con nulos")
            elif x["tipo"] == "mixta" and x["lang"] == "es":
                print(f"  {x['id']}: {filas[:3]}{' ...' if len(filas) > 3 else ''}")
    if malos:
        raise SystemExit("Invalid SQL:\n" + "\n".join(malos))
    print("SQL validation OK: every query runs and returns rows with no nulls")


if __name__ == "__main__":
    salida = construir()
    if "--validar-sql" in sys.argv:
        validar_sql(salida)
