#!/usr/bin/env python3
"""Builds the bilingual NLQ-Inventory evaluation set (semana 7).

Each unique question has a reference SQL and two wording variants: Spanish (es)
and English (en). Templates are filled from the synthetic inventory data
(inventory-copilot, scripts/generate_data.py, seed 42). The reference SQL is
validated against the database in run_eval.py, which drops any item whose
reference returns no rows.

Output: datasets/nlq_bilingual.jsonl, one line per (question, language).
"""
import json
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "datasets" / "nlq_bilingual.jsonl"

CATEGORIAS = ["Tornilleria", "Electrico", "Hidraulico", "Neumatico",
              "Rodamientos", "Seguridad", "Herramientas", "Empaque"]
PAISES = [("CN", "China", "China"), ("DE", "Alemania", "Germany"),
          ("US", "Estados Unidos", "the United States"), ("CO", "Colombia", "Colombia"),
          ("ES", "España", "Spain"), ("CA", "Canadá", "Canada")]
CIUDADES = [("Ciudad de Mexico", "Ciudad de México", "Mexico City"),
            ("Guadalajara", "Guadalajara", "Guadalajara"),
            ("Monterrey", "Monterrey", "Monterrey")]
ESTADOS = ["PENDING_APPROVAL", "APPROVED", "REJECTED"]

items = []


def add(tags, sql, es, en):
    items.append({"tags": tags, "sql": sql, "es": es, "en": en})


for c in CATEGORIAS:
    add(["category", "count"], f"SELECT COUNT(*) FROM products WHERE category = '{c}'",
        f"¿Cuántos productos hay en la categoría {c}?",
        f"How many products are in the {c} category?")
    add(["category", "aggregate"],
        f"SELECT ROUND(AVG(unit_cost), 2) FROM products WHERE category = '{c}'",
        f"¿Cuál es el costo unitario promedio de los productos de la categoría {c}?",
        f"What is the average unit cost of products in the {c} category?")
    add(["category", "count", "critical"],
        f"SELECT COUNT(*) FROM products WHERE category = '{c}' AND critical",
        f"¿Cuántos productos críticos hay en la categoría {c}?",
        f"How many critical products are in the {c} category?")
    add(["category", "join", "sales"],
        f"SELECT COALESCE(SUM(d.units), 0) FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE p.category = '{c}'",
        f"¿Cuántas unidades se han vendido de la categoría {c}?",
        f"How many units have been sold in the {c} category?")
    add(["category", "aggregate"],
        f"SELECT MAX(unit_cost) FROM products WHERE category = '{c}'",
        f"¿Cuál es el costo unitario máximo en la categoría {c}?",
        f"What is the maximum unit cost in the {c} category?")

for cc, es, en in PAISES:
    add(["supplier", "count"], f"SELECT COUNT(*) FROM suppliers WHERE country = '{cc}'",
        f"¿Cuántos proveedores tenemos en {es}?",
        f"How many suppliers do we have in {en}?")
    add(["supplier", "list"], f"SELECT name FROM suppliers WHERE country = '{cc}'",
        f"¿Cuáles son los nombres de los proveedores en {es}?",
        f"What are the names of the suppliers in {en}?")

for city, esc, enc in CIUDADES:
    add(["warehouse", "join", "aggregate"],
        f"SELECT COALESCE(SUM(s.on_hand), 0) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = '{city}'",
        f"¿Cuántas unidades hay en existencia en el almacén de {esc}?",
        f"How many units are on hand at the {enc} warehouse?")
    add(["warehouse", "join", "count"],
        f"SELECT COUNT(DISTINCT s.sku) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = '{city}'",
        f"¿Cuántos SKU distintos tienen registro de existencias en {esc}?",
        f"How many distinct SKUs have a stock record in {enc}?")
    add(["warehouse", "reorder", "join"],
        f"SELECT s.sku FROM stock s JOIN products p ON p.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = '{city}' AND s.on_hand < p.reorder_point",
        f"¿Qué SKU están por debajo de su punto de reorden en {esc}?",
        f"Which SKUs are below their reorder point at the {enc} warehouse?")
    add(["warehouse", "aggregate", "join"],
        f"SELECT ROUND(SUM(s.on_hand * p.unit_cost), 2) FROM stock s JOIN products p ON p.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = '{city}'",
        f"¿Cuál es el valor a costo del inventario en {esc}?",
        f"What is the inventory value at cost in {enc}?")

for st in ESTADOS:
    add(["purchase_order", "count"],
        f"SELECT COUNT(*) FROM purchase_orders WHERE status = '{st}'",
        f"¿Cuántas órdenes de compra están en estado {st}?",
        f"How many purchase orders are in status {st}?")
    add(["purchase_order", "aggregate"],
        f"SELECT COALESCE(SUM(qty), 0) FROM purchase_orders WHERE status = '{st}'",
        f"¿Cuál es la cantidad total de piezas en órdenes de compra con estado {st}?",
        f"What is the total quantity across purchase orders with status {st}?")

for n in [10, 20, 30]:
    add(["supplier", "threshold"], f"SELECT name FROM suppliers WHERE lead_time_days > {n}",
        f"¿Qué proveedores tienen un tiempo de entrega mayor a {n} días?",
        f"Which suppliers have a lead time greater than {n} days?")
for n in [100, 500, 1000]:
    add(["product", "threshold"], f"SELECT sku FROM products WHERE unit_cost > {n}",
        f"¿Qué productos tienen un costo unitario mayor a {n}?",
        f"Which products have a unit cost greater than {n}?")
for n in [1, 3, 5]:
    # The question asks for SKUs only; the reference returns just the SKU column.
    sql_rank = f"SELECT p.sku FROM sales_daily d JOIN products p ON p.sku = d.sku GROUP BY p.sku ORDER BY SUM(d.units) DESC, p.sku LIMIT {n}"
    add(["sales", "ranking"], sql_rank,
        f"¿Cuáles son los {n} SKU más vendidos en unidades?" if n > 1 else "¿Cuál es el SKU más vendido en unidades?",
        f"What are the top {n} best-selling SKUs by units?" if n > 1 else "What is the best-selling SKU by units?")
for n in [5, 20]:
    add(["product", "threshold"], f"SELECT COUNT(*) FROM products WHERE reorder_point > {n}",
        f"¿Cuántos productos tienen un punto de reorden mayor a {n}?",
        f"How many products have a reorder point greater than {n}?")
for cc, es, en in PAISES:
    add(["supplier", "join", "count"],
        f"SELECT COUNT(*) FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE s.country = '{cc}'",
        f"¿Cuántos productos surten proveedores de {es}?",
        f"How many products are supplied by suppliers in {en}?")
add(["warehouse", "ranking"],
    "SELECT w.name FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id GROUP BY w.name ORDER BY SUM(s.on_hand) DESC LIMIT 1",
    "¿Qué almacén tiene más unidades en existencia?",
    "Which warehouse has the most units on hand?")
add(["warehouse", "ranking"],
    "SELECT w.name FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id GROUP BY w.name ORDER BY SUM(s.on_hand) ASC LIMIT 1",
    "¿Qué almacén tiene menos unidades en existencia?",
    "Which warehouse has the fewest units on hand?")
# Count questions always return one row, so the reference is never empty.
# (The earlier anti-join questions returned no rows in this data and were dropped.)
add(["sales", "count", "distinct"], "SELECT COUNT(DISTINCT sku) FROM sales_daily",
    "¿Cuántos productos tienen al menos una venta registrada?",
    "How many products have at least one sale recorded?")
add(["stock", "count", "anti_join"],
    "SELECT COUNT(*) FROM products p WHERE p.critical AND NOT EXISTS (SELECT 1 FROM stock s WHERE s.sku = p.sku)",
    "¿Cuántos productos críticos no tienen existencias en ningún almacén?",
    "How many critical products have no stock in any warehouse?")
add(["supplier", "aggregate"],
    "SELECT country, AVG(lead_time_days) FROM suppliers GROUP BY country",
    "¿Cuál es el tiempo de entrega promedio por país de proveedor?",
    "What is the average lead time by supplier country?")
add(["product", "aggregate"],
    "SELECT category, MAX(unit_cost) FROM products GROUP BY category",
    "¿Cuál es el costo unitario más alto de cada categoría?",
    "What is the highest unit cost in each category?")
add(["stock", "aggregate", "join"],
    "SELECT ROUND(SUM(s.on_hand * p.unit_cost), 2) FROM stock s JOIN products p ON p.sku = s.sku",
    "¿Cuál es el valor total del inventario a costo?",
    "What is the total inventory value at cost?")
for cc, es, en in PAISES[:3]:
    add(["supplier", "join", "critical"],
        f"SELECT COUNT(*) FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE p.critical AND s.country = '{cc}'",
        f"¿Cuántos productos críticos surte un proveedor de {es}?",
        f"How many critical products are supplied by a supplier in {en}?")
add(["supplier", "count", "distinct"], "SELECT COUNT(DISTINCT supplier_id) FROM products",
    "¿Cuántos proveedores surten al menos un producto?",
    "How many suppliers supply at least one product?")
add(["sales", "count"], "SELECT COUNT(DISTINCT day) FROM sales_daily",
    "¿En cuántos días distintos hay ventas registradas?",
    "On how many distinct days are sales recorded?")
add(["sales", "aggregate"], "SELECT SUM(units) FROM sales_daily",
    "¿Cuántas unidades se han vendido en total?",
    "How many units have been sold in total?")

assert len(items) == 100, len(items)

SALIDA.parent.mkdir(exist_ok=True)
with SALIDA.open("w", encoding="utf-8") as archivo:
    for i, it in enumerate(items, start=1):
        base = {"tags": it["tags"], "sql": it["sql"], "order_matters": False}
        for lang in ("es", "en"):
            registro = {"id": f"nlq-{i:03d}-{lang}", "lang": lang, "question": it[lang], **base}
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

print(f"{len(items)} unique questions, {2 * len(items)} lines in {SALIDA}")
