"""Builds the two sets of multi-hop questions of activity 7 (GraphRAG).

- compound (multisalto_*.jsonl): two documents per question, with the passages of base questions from the
  gold set. The question names both topics. It is the control: ordinary two-document questions.
- bridge (multisalto_puente_*.jsonl): the most favorable case for GraphRAG. The entity that links the two
  documents does NOT appear in the question; the first passage identifies it and the second gives the answer.

Every passage is validated as literal text in its document and complete within a chunk
(fixed 400/80 chunking), and each question uses two different documents.
"""
import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[2]
DS = R / "semana-09" / "datasets"
CORPUS = R / "semana-08" / "corpus"
sys.path.insert(0, str(R / "semana-08" / "experimentos"))
from chunking_pasajes import ESTRATEGIAS  # noqa: E402
trocear = ESTRATEGIAS["fijo_400_solape_80"]

# (base id of the first passage, base id of the second, ES question, EN question)
PREGUNTAS = [
    ("rec-22", "rec-11",
     "¿Quién aprueba la compra urgente de un SKU en riesgo y qué factor de seguridad usa ese tipo de SKU en el punto de reorden?",
     "Who approves the urgent purchase of an at-risk SKU, and what safety factor does that type of SKU use in the reorder point?"),
    ("rec-23", "rec-14",
     "¿Desde cuántos días de cobertura se escala un SKU crítico al gerente de compras, y para cuántos días de demanda se pide ese tipo de SKU?",
     "From how many days of coverage is a critical SKU escalated to the purchasing manager, and for how many days of demand is that type of SKU ordered?"),
    ("rec-05", "rec-07",
     "¿Quién aprueba un ajuste de inventario de 15 mil pesos, y quién aprueba una orden de compra de 120 mil pesos?",
     "Who approves an inventory adjustment of 15,000 pesos, and who approves a purchase order of 120,000 pesos?"),
    ("rec-16", "rec-42",
     "¿Cuánto tarda en entregar un proveedor de China, y qué penalización se le aplica por cada semana de entrega tardía según su contrato marco?",
     "How long does a supplier from China take to deliver, and what penalty applies for each week of late delivery under its framework contract?"),
    ("rec-15", "rec-41",
     "¿Qué meta de OTIF debe cumplir un proveedor, y cuánto dura la vigencia de su contrato marco?",
     "What OTIF target must a supplier meet, and how long is its framework contract valid?"),
    ("rec-18", "rec-25",
     "¿Cuál es el horario de recepción del CEDIS de Guadalajara, y cuánto tarda en tránsito una transferencia de ese CEDIS a Monterrey?",
     "What are the receiving hours of the Guadalajara distribution center, and how long does a transfer from that center to Monterrey take in transit?"),
    ("rec-37", "rec-26",
     "¿Cuántas posiciones de tarima tiene el CEDIS de Monterrey, y cuándo se considera que un CEDIS tiene excedente para transferir?",
     "How many pallet positions does the Monterrey distribution center have, and when is a distribution center considered to have a surplus to transfer?"),
    ("rec-46", "rec-34",
     "¿Qué es una merma, y qué SKUs perecederos se revisan cada semana para evitarla?",
     "What is shrinkage, and which perishable SKUs are reviewed every week to prevent it?"),
    ("rec-36", "rec-01",
     "¿Cuánto tiene un cliente para reclamar una entrega, y cuál es el plazo para devolver el producto?",
     "How long does a customer have to file a delivery claim, and what is the deadline to return the product?"),
    ("rec-44", "rec-09",
     "Durante su primer mes, ¿qué límite de compra tiene un comprador nuevo, y cuántas cotizaciones necesita una orden mayor a 100 mil pesos?",
     "During their first month, what purchase limit does a new buyer have, and how many quotes does an order over 100,000 pesos need?"),
]

# (hop 1 document, passage that identifies the bridge entity, hop 2 document, passage with the answer, ES, EN)
PUENTE = [
    ("cedis_monterrey.md", "El CEDIS Norte (Monterrey) tiene capacidad para **12,000 posiciones** de tarima.",
     "transferencias_cedis.md", "Ciudad de México ↔ Monterrey: 2 días.",
     "¿Cuántos días de tránsito hay desde Ciudad de México hasta el CEDIS que tiene capacidad para 12,000 posiciones de tarima?",
     "How many days of transit are there from Mexico City to the distribution center with capacity for 12,000 pallet positions?"),
    ("recepcion_almacen.md", "CEDIS Occidente (Guadalajara): lunes a viernes de 8:00 a 16:00.",
     "transferencias_cedis.md", "Ciudad de México ↔ Guadalajara: 1 día.",
     "¿Cuánto tarda en tránsito una transferencia desde Ciudad de México al CEDIS que recibe mercancía de lunes a viernes de 8:00 a 16:00?",
     "How long does a transfer from Mexico City take in transit to the distribution center that receives goods Monday to Friday from 8:00 to 16:00?"),
    ("recepcion_almacen.md", "CEDIS Norte (Monterrey): lunes a sábado de 6:00 a 14:00.",
     "cedis_monterrey.md", "El CEDIS Norte (Monterrey) tiene capacidad para **12,000 posiciones** de tarima.",
     "¿Cuántas posiciones de tarima tiene el CEDIS que recibe mercancía de lunes a sábado?",
     "How many pallet positions does the distribution center that receives goods Monday to Saturday have?"),
    ("ordenes_de_compra.md", "De $50,000 a $250,000 MXN | Gerente de compras",
     "skus_criticos.md", "**Nivel 2 (gerente de compras):** SKU crítico con menos de **7 días** de cobertura.",
     "¿Con menos de cuántos días de cobertura se escala un SKU crítico al puesto que aprueba las órdenes de compra de 50,000 a 250,000 MXN?",
     "Below how many days of coverage is a critical SKU escalated to the role that approves purchase orders from 50,000 to 250,000 MXN?"),
    ("skus_criticos.md", "**Nivel 3 (director de operaciones):** SKU crítico con existencia total en cero",
     "ordenes_de_compra.md", "Más de $250,000 MXN | Director de operaciones",
     "¿Desde qué monto aprueba órdenes de compra el puesto al que se escala un SKU crítico con existencia total en cero?",
     "From what amount does the role to which a critical SKU with zero total stock is escalated approve purchase orders?"),
    ("inventario_ciclico.md", "Ajustes mayores a **$10,000 MXN**: requieren aprobación de **contraloría**.",
     "mermas_caducidad.md", "Una merma mensual mayor a **2%** del valor del inventario se reporta a contraloría.",
     "¿A partir de qué porcentaje de merma mensual se reporta al área que aprueba los ajustes de inventario mayores a $10,000 MXN?",
     "Above what monthly shrinkage percentage is it reported to the area that approves inventory adjustments over $10,000 MXN?"),
    ("inventario_ciclico.md", "Ajustes mayores a **$10,000 MXN**: requieren aprobación de **contraloría**.",
     "devoluciones.md", "El producto dañado se da de baja con aprobación de contraloría.",
     "¿Qué producto devuelto se da de baja con aprobación del área que autoriza los ajustes de inventario mayores a $10,000 MXN?",
     "Which returned product is written off with approval from the area that authorizes inventory adjustments over $10,000 MXN?"),
    ("proveedores.md", "Proveedores de Asia (CN): de 35 a 40 días.",
     "skus_criticos.md", "Todo SKU crítico cuyo proveedor tenga un tiempo de entrega mayor a **20 días**",
     "Por su tiempo de entrega de referencia, ¿qué debe tener un SKU crítico surtido por un proveedor de China?",
     "Given its reference lead time, what must a critical SKU supplied by a vendor from China have?"),
    ("devoluciones.md", "**no se aceptan** si el empaque fue abierto, por razones de higiene.",
     "descuentos_clientes.md", "Los descuentos no aplican a productos de la categoría Seguridad.",
     "¿Se pueden dar descuentos a la categoría de productos cuyas devoluciones no se aceptan si el empaque fue abierto?",
     "Can discounts be given on the product category whose returns are not accepted if the package was opened?"),
    ("politica_reorden.md", "la categoría Empaque se revisa **semanalmente** (los lunes)",
     "devoluciones.md", "Productos de Empaque cortados a la medida no tienen devolución.",
     "¿Tienen devolución los productos cortados a la medida de la categoría que se revisa contra su punto de reorden solo los lunes?",
     "Do custom-cut products have returns in the category that is checked against its reorder point only on Mondays?"),
]

base = {lang: {d["id"]: d for d in map(json.loads, open(DS / f"avanzado_{lang}.jsonl", encoding="utf-8")) if d["tipo"] == "base"}
        for lang in ("es", "en")}
corpus = {p.name: p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md")}
chunks = {n: trocear(t, n) for n, t in corpus.items()}


def validar(qid, golds, errores):
    if golds[0]["source"] == golds[1]["source"]:
        errores.append(f"{qid}: los dos pasajes son del mismo documento ({golds[0]['source']})")
    for g in golds:
        if g["passage"] not in corpus[g["source"]]:
            errores.append(f"{qid}: pasaje no literal en {g['source']}: {g['passage'][:50]}")
        elif not any(g["passage"] in c for c in chunks[g["source"]]):
            errores.append(f"{qid}: pasaje partido por el chunking en {g['source']}: {g['passage'][:50]}")


errores = []
compuestas, puente = {"es": [], "en": []}, {"es": [], "en": []}
for i, (a, b, es, en) in enumerate(PREGUNTAS, 1):
    golds = [base["es"][a]["gold"][0], base["es"][b]["gold"][0]]
    validar(f"ms-{i:02d}", golds, errores)
    for lang, q in (("es", es), ("en", en)):
        compuestas[lang].append({"id": f"ms-{i:02d}", "lang": lang, "set": "compuestas", "question": q, "gold": golds, "base": [a, b]})
for i, (s1, p1, s2, p2, es, en) in enumerate(PUENTE, 1):
    golds = [{"source": s1, "passage": p1}, {"source": s2, "passage": p2}]
    validar(f"pt-{i:02d}", golds, errores)
    for lang, q in (("es", es), ("en", en)):
        puente[lang].append({"id": f"pt-{i:02d}", "lang": lang, "set": "puente", "question": q, "gold": golds})
if errores:
    raise SystemExit("\n".join(errores))
for nombre, conjunto in (("multisalto", compuestas), ("multisalto_puente", puente)):
    for lang, items in conjunto.items():
        with open(DS / f"{nombre}_{lang}.jsonl", "w", encoding="utf-8") as f:
            for x in items:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
print(f"compound: {len(PREGUNTAS)} per language; bridge: {len(PUENTE)} per language; validation OK "
      "(literal passages, complete within a chunk, two documents per question)")
