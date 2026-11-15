#!/usr/bin/env python3
"""A set of 3-turn chains (week 7, third iteration). Frozen before it was run.

Each chain has two previous turns (question, reference SQL) and a final question that
depends on them: corrections, filter changes, references to earlier turns.
Output: datasets/nlq_cadenas.jsonl (16 chains x 2 languages).
"""
import json
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "datasets" / "nlq_cadenas.jsonl"

TOP_CATEGORIA = ("(SELECT p.category FROM sales_daily d JOIN products p ON p.sku = d.sku "
                 "WHERE d.day >= '2026-04-01' AND d.day < '2026-05-01' "
                 "GROUP BY p.category ORDER BY SUM(d.units) DESC, p.category LIMIT 1)")
TOP_ALMACEN = ("(SELECT w.name FROM stock s JOIN products p ON p.sku = s.sku "
               "JOIN warehouses w ON w.warehouse_id = s.warehouse_id "
               "GROUP BY w.name ORDER BY SUM(s.on_hand * p.unit_cost) DESC, w.name LIMIT 1)")
TOP_SKU = "(SELECT sku FROM sales_daily GROUP BY sku ORDER BY SUM(units) DESC, sku LIMIT 1)"
CON_MONTERREY = ("EXISTS (SELECT 1 FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id "
                 "WHERE s.sku = d.sku AND w.city = 'Monterrey')")

# (id, (es_t1, es_t2, es_t3), (en_t1, en_t2, en_t3), (sql1, sql2, sql3), tags)
CADENAS = [
 ("cad-01",
  ("¿Qué productos están por debajo de su punto de reorden en Guadalajara?", "No, mejor solo los críticos.", "¿Y cuál es el costo unitario total de esos?"),
  ("Which products are below their reorder point in Guadalajara?", "No, only the critical ones instead.", "And what is the total unit cost of those?"),
  ("SELECT s.sku FROM stock s JOIN products p ON p.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Guadalajara' AND s.on_hand < p.reorder_point",
   "SELECT s.sku FROM stock s JOIN products p ON p.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Guadalajara' AND s.on_hand < p.reorder_point AND p.critical",
   "SELECT COALESCE(SUM(p.unit_cost), 0) FROM products p WHERE p.sku IN (SELECT s.sku FROM stock s JOIN products p2 ON p2.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Guadalajara' AND s.on_hand < p2.reorder_point AND p2.critical)"),
  ["correccion", "join"]),
 ("cad-02",
  ("¿Cuántas órdenes de compra hay por estado?", "Solo las de productos críticos.", "¿Y cuántas unidades suman las pendientes de aprobación?"),
  ("How many purchase orders are there per status?", "Only the ones for critical products.", "And how many units do the pending approval ones add up to?"),
  ("SELECT status, COUNT(*) FROM purchase_orders GROUP BY status",
   "SELECT po.status, COUNT(*) FROM purchase_orders po JOIN products p ON p.sku = po.sku WHERE p.critical GROUP BY po.status",
   "SELECT COALESCE(SUM(po.qty), 0) FROM purchase_orders po JOIN products p ON p.sku = po.sku WHERE p.critical AND po.status = 'PENDING_APPROVAL'"),
  ["filtro", "estado"]),
 ("cad-03",
  ("¿Qué categoría vendió más unidades en abril de 2026? Desempata por nombre ascendente.", "¿Cuántas unidades vendió esa categoría en abril?", "¿Y cuántos productos distintos tiene esa categoría?"),
  ("Which category sold the most units in April 2026? Break ties by category name ascending.", "How many units did that category sell in April?", "And how many distinct products does that category have?"),
  ("SELECT p.category FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE d.day >= '2026-04-01' AND d.day < '2026-05-01' GROUP BY p.category ORDER BY SUM(d.units) DESC, p.category LIMIT 1",
   f"SELECT SUM(d.units) FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE d.day >= '2026-04-01' AND d.day < '2026-05-01' AND p.category = {TOP_CATEGORIA}",
   f"SELECT COUNT(*) FROM products WHERE category = {TOP_CATEGORIA}"),
  ["referencia_lejana", "ranking"]),
 ("cad-04",
  ("¿Cuántos SKU tienen registro de existencias en el almacén de Monterrey?", "Cámbialo: que tengan menos de 5 unidades.", "De ésos, ¿cuántos son críticos?"),
  ("How many SKUs have a stock record at the Monterrey warehouse?", "Change it: only the ones with fewer than 5 units.", "Now of those, how many are critical?"),
  ("SELECT COUNT(*) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Monterrey'",
   "SELECT COUNT(*) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Monterrey' AND s.on_hand < 5",
   "SELECT COUNT(*) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id JOIN products p ON p.sku = s.sku WHERE w.city = 'Monterrey' AND s.on_hand < 5 AND p.critical"),
  ["correccion", "encadenado"]),
 ("cad-05",
  ("¿Qué proveedores tienen productos de la categoría Electrico?", "¿Cuál de ellos tiene el tiempo de entrega más largo? Desempata por nombre ascendente.", "¿Cuántos productos de la categoría Electrico surte ese proveedor?"),
  ("Which suppliers have products in the Electrico category?", "Which of them has the longest lead time? Break ties by name ascending.", "How many Electrico products does that supplier supply?"),
  ("SELECT DISTINCT s.name FROM products p JOIN suppliers s ON s.supplier_id = p.supplier_id WHERE p.category = 'Electrico'",
   "SELECT s.name FROM suppliers s WHERE s.supplier_id IN (SELECT p.supplier_id FROM products p WHERE p.category = 'Electrico') ORDER BY s.lead_time_days DESC, s.name LIMIT 1",
   "SELECT COUNT(*) FROM products p WHERE p.category = 'Electrico' AND p.supplier_id = (SELECT s.supplier_id FROM suppliers s WHERE s.supplier_id IN (SELECT p2.supplier_id FROM products p2 WHERE p2.category = 'Electrico') ORDER BY s.lead_time_days DESC, s.name LIMIT 1)"),
  ["encadenado", "ranking"]),
 ("cad-06",
  ("¿Cuántas unidades se vendieron en julio de 2026?", "Solo para los productos críticos.", "¿Y qué porcentaje de esas unidades fue de la categoría Electrico?"),
  ("How many units were sold in July 2026?", "Only for the critical products.", "And what percentage of those units was Electrico?"),
  ("SELECT SUM(units) FROM sales_daily WHERE day >= '2026-07-01' AND day < '2026-08-01'",
   "SELECT SUM(d.units) FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE d.day >= '2026-07-01' AND d.day < '2026-08-01' AND p.critical",
   "SELECT 100.0 * SUM(CASE WHEN p.category = 'Electrico' THEN d.units ELSE 0 END) / SUM(d.units) FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE d.day >= '2026-07-01' AND d.day < '2026-08-01' AND p.critical"),
  ["filtro", "porcentaje"]),
 ("cad-07",
  ("¿Qué almacén tiene el mayor valor de inventario a costo? Desempata por nombre ascendente.", "¿Cuántos SKU distintos tiene en existencia?", "¿Y cuántos de esos SKU tienen proveedor en China?"),
  ("Which warehouse has the highest inventory value at cost? Break ties by warehouse name ascending.", "How many distinct SKUs does it have on hand?", "And how many of those SKUs come from suppliers in China?"),
  ("SELECT w.name FROM stock s JOIN products p ON p.sku = s.sku JOIN warehouses w ON w.warehouse_id = s.warehouse_id GROUP BY w.name ORDER BY SUM(s.on_hand * p.unit_cost) DESC, w.name LIMIT 1",
   f"SELECT COUNT(DISTINCT s.sku) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.name = {TOP_ALMACEN} AND s.on_hand > 0",
   f"SELECT COUNT(DISTINCT s.sku) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id JOIN products p ON p.sku = s.sku JOIN suppliers su ON su.supplier_id = p.supplier_id WHERE w.name = {TOP_ALMACEN} AND s.on_hand > 0 AND su.country = 'CN'"),
  ["encadenado", "ranking"]),
 ("cad-08",
  ("¿Qué proveedores tienen más de 30 días de entrega?", "¿Cuáles de esos surten productos críticos?", "¿Y cuántas unidades vendieron en total los productos críticos de esos proveedores?"),
  ("Which suppliers have a lead time over 30 days?", "Which of those supply critical products?", "And how many units did the critical products of those suppliers sell in total?"),
  ("SELECT name FROM suppliers WHERE lead_time_days > 30",
   "SELECT DISTINCT su.name FROM suppliers su JOIN products p ON p.supplier_id = su.supplier_id WHERE su.lead_time_days > 30 AND p.critical",
   "SELECT COALESCE(SUM(d.units), 0) FROM sales_daily d JOIN products p ON p.sku = d.sku JOIN suppliers su ON su.supplier_id = p.supplier_id WHERE su.lead_time_days > 30 AND p.critical"),
  ["encadenado", "join"]),
 ("cad-09",
  ("¿Cuál es el costo unitario promedio de la categoría Hidraulico? Da el valor exacto, sin redondear.", "¿Y cuántos productos de esa categoría cuestan más que ese promedio?", "Ahora compara con la categoría Electrico: ¿cuántos cuestan más que el promedio de Hidraulico?"),
  ("What is the average unit cost of the Hidraulico category? Give the exact value, without rounding.", "And how many products in that category cost more than that average?", "Now compare with the Electrico category: how many cost more than the Hidraulico average?"),
  ("SELECT AVG(unit_cost) FROM products WHERE category = 'Hidraulico'",
   "SELECT COUNT(*) FROM products WHERE category = 'Hidraulico' AND unit_cost > (SELECT AVG(unit_cost) FROM products WHERE category = 'Hidraulico')",
   "SELECT COUNT(*) FROM products WHERE category = 'Electrico' AND unit_cost > (SELECT AVG(unit_cost) FROM products WHERE category = 'Hidraulico')"),
  ["referencia_lejana", "promedio"]),
 ("cad-10",
  ("¿Qué SKU vendieron más de 300 unidades entre el 2026-07-01 y el 2026-09-26?", "Quita los que no tienen registro de existencias en Monterrey.", "¿Y cuál de ésos vendió más en total? Desempata por SKU ascendente."),
  ("Which SKUs sold more than 300 units between 2026-07-01 and 2026-09-26?", "Remove the ones that have no stock record at the Monterrey warehouse.", "And which of those sold the most in total? Break ties by SKU ascending."),
  ("SELECT sku FROM sales_daily WHERE day BETWEEN '2026-07-01' AND '2026-09-26' GROUP BY sku HAVING SUM(units) > 300",
   f"SELECT d.sku FROM sales_daily d WHERE d.day BETWEEN '2026-07-01' AND '2026-09-26' AND {CON_MONTERREY} GROUP BY d.sku HAVING SUM(d.units) > 300",
   f"SELECT d.sku FROM sales_daily d WHERE d.day BETWEEN '2026-07-01' AND '2026-09-26' AND {CON_MONTERREY} GROUP BY d.sku HAVING SUM(d.units) > 300 ORDER BY SUM(d.units) DESC, d.sku LIMIT 1"),
  ["correccion", "ranking"]),
 ("cad-11",
  ("¿Cuántas órdenes de compra están pendientes de aprobación?", "¿Cuántas de esas son de la categoría Electrico?", "Y de esas, ¿cuántas unidades suman?"),
  ("How many purchase orders are pending approval?", "How many of those are for the Electrico category?", "And of those, how many units do they add up to?"),
  ("SELECT COUNT(*) FROM purchase_orders WHERE status = 'PENDING_APPROVAL'",
   "SELECT COUNT(*) FROM purchase_orders po JOIN products p ON p.sku = po.sku WHERE po.status = 'PENDING_APPROVAL' AND p.category = 'Electrico'",
   "SELECT COALESCE(SUM(po.qty), 0) FROM purchase_orders po JOIN products p ON p.sku = po.sku WHERE po.status = 'PENDING_APPROVAL' AND p.category = 'Electrico'"),
  ["encadenado", "filtro"]),
 ("cad-12",
  ("¿Qué porcentaje de los productos son críticos? Da el valor exacto, sin redondear.", "¿Y en la categoría Electrico?", "¿Cuántos productos hay en total en esa categoría?"),
  ("What percentage of products are critical? Give the exact value, without rounding.", "And in the Electrico category?", "How many products are there in total in that category?"),
  ("SELECT 100.0 * SUM(CASE WHEN critical THEN 1 ELSE 0 END) / COUNT(*) FROM products",
   "SELECT 100.0 * SUM(CASE WHEN critical THEN 1 ELSE 0 END) / COUNT(*) FROM products WHERE category = 'Electrico'",
   "SELECT COUNT(*) FROM products WHERE category = 'Electrico'"),
  ["mismo_metrica", "encadenado"]),
 ("cad-13",
  ("¿Cuántas unidades en existencia hay en el almacén de Guadalajara?", "Ahora lo mismo para Monterrey.", "¿Cuántas unidades de diferencia hay entre los dos?"),
  ("How many units are on hand at the Guadalajara warehouse?", "Now the same for Monterrey.", "How many units is the difference between the two?"),
  ("SELECT SUM(s.on_hand) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Guadalajara'",
   "SELECT SUM(s.on_hand) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Monterrey'",
   "SELECT ABS((SELECT SUM(s.on_hand) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Guadalajara') - (SELECT SUM(s.on_hand) FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE w.city = 'Monterrey'))"),
  ["elipsis", "resta"]),
 ("cad-14",
  ("¿Qué productos cuestan más de 500 por unidad?", "Solo los críticos.", "¿Y cuántas unidades de esos productos críticos se vendieron en total en agosto de 2026?"),
  ("Which products cost more than 500 per unit?", "Only the critical ones.", "And how many units of those critical products were sold in total in August 2026?"),
  ("SELECT sku FROM products WHERE unit_cost > 500",
   "SELECT sku FROM products WHERE unit_cost > 500 AND critical",
   "SELECT COALESCE(SUM(d.units), 0) FROM sales_daily d JOIN products p ON p.sku = d.sku WHERE p.unit_cost > 500 AND p.critical AND d.day >= '2026-08-01' AND d.day < '2026-09-01'"),
  ["filtro", "fecha"]),
 ("cad-15",
  ("¿Qué proveedores de México surten productos?", "¿Cuántos productos surte cada uno?", "¿Cuál surte más productos críticos? Desempata por nombre ascendente."),
  ("Which suppliers from Mexico supply products?", "How many products does each one supply?", "Which one supplies the most critical products? Break ties by name ascending."),
  ("SELECT DISTINCT s.name FROM suppliers s JOIN products p ON p.supplier_id = s.supplier_id WHERE s.country = 'MX'",
   "SELECT s.name, COUNT(*) FROM suppliers s JOIN products p ON p.supplier_id = s.supplier_id WHERE s.country = 'MX' GROUP BY s.name",
   "SELECT s.name FROM suppliers s JOIN products p ON p.supplier_id = s.supplier_id WHERE s.country = 'MX' AND p.critical GROUP BY s.name ORDER BY COUNT(*) DESC, s.name LIMIT 1"),
  ["encadenado", "ranking"]),
 ("cad-16",
  ("¿Cuál es el SKU más vendido en unidades totales? Desempata por SKU ascendente.", "¿En qué almacenes tiene existencias?", "¿Cuántas unidades tiene en total en esos almacenes?"),
  ("Which SKU is the best-selling by total units? Break ties by SKU ascending.", "Which warehouses does it have stock in?", "How many units does it have in total across those warehouses?"),
  ("SELECT sku FROM sales_daily GROUP BY sku ORDER BY SUM(units) DESC, sku LIMIT 1",
   f"SELECT w.name FROM stock s JOIN warehouses w ON w.warehouse_id = s.warehouse_id WHERE s.sku = {TOP_SKU}",
   f"SELECT COALESCE(SUM(s.on_hand), 0) FROM stock s WHERE s.sku = {TOP_SKU}"),
  ["encadenado", "ranking"]),
]

assert len(CADENAS) == 16
SALIDA.parent.mkdir(exist_ok=True)
with SALIDA.open("w", encoding="utf-8") as archivo:
    for cid, es, en, sqls, etiquetas in CADENAS:
        for lang, textos in (("es", es), ("en", en)):
            t1, t2, t3 = textos
            registro = {"id": f"{cid}-{lang}", "lang": lang, "question": t3,
                        "ejemplos": [{"entrada": t1, "salida": sqls[0]}, {"entrada": t2, "salida": sqls[1]}],
                        "tags": ["cadena_3_turnos"] + etiquetas, "sql": sqls[2], "order_matters": False}
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
print(f"{len(CADENAS)} chains, {2 * len(CADENAS)} lines in {SALIDA}")
