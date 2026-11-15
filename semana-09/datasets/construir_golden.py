"""Builds the week 9 gold set from the week 8 one.

Output: avanzado_es.jsonl, avanzado_en.jsonl and permisos.json.
Each reference passage is validated as literal text within its document.
The roles per document are a synthetic test model (not a real permission system).
"""
import json
import pathlib

R = pathlib.Path(__file__).resolve().parents[2]
DS = R / "semana-09" / "datasets"

base = {
    lang: {d["id"]: d for d in map(json.loads, open(R / "semana-08/datasets" / f"recuperacion_{lang}.jsonl", encoding="utf-8"))}
    for lang in ("es", "en")
}
corpus = {p.name: p.read_text(encoding="utf-8") for p in (R / "semana-08/corpus").glob("*.md")}

ROLES = {
    "auditoria_interna.md": ["finanzas", "calidad"],
    "capacitacion_almacen.md": ["operaciones", "almacen"],
    "cedis_monterrey.md": ["operaciones"],
    "cierre_mensual_inventario.md": ["finanzas"],
    "contratos_marco_proveedores.md": ["compras", "finanzas"],
    "descuentos_clientes.md": ["ventas", "finanzas"],
    "devoluciones.md": ["ventas", "almacen"],
    "embalaje_etiquetado.md": ["almacen", "operaciones"],
    "flota_reparto.md": ["operaciones", "finanzas"],
    "glosario_inventario.md": ["operaciones", "almacen", "compras", "ventas", "finanzas", "calidad"],
    "indicadores_operacion.md": ["operaciones", "finanzas"],
    "inventario_ciclico.md": ["almacen", "finanzas"],
    "mermas_caducidad.md": ["almacen", "calidad"],
    "onboarding_compradores.md": ["compras"],
    "ordenes_de_compra.md": ["compras", "finanzas"],
    "politica_reorden.md": ["compras", "almacen"],
    "proveedores.md": ["compras", "calidad"],
    "reclamaciones_clientes.md": ["ventas", "calidad"],
    "recepcion_almacen.md": ["almacen"],
    "seguridad_instalaciones.md": ["operaciones"],
    "skus_criticos.md": ["compras", "almacen"],
    "transferencias_cedis.md": ["almacen", "operaciones"],
    "uso_copiloto.md": ["operaciones", "almacen", "compras", "ventas", "finanzas", "calidad"],
    "wms_respaldos.md": ["operaciones"],
}

# (base id of the previous question, base id of the reference passage, ES question, EN question)
SEGUIMIENTO = [
    ("rec-01", "rec-03", "¿Y el plazo si el producto tiene defecto de calidad y lo devuelvo a un proveedor?", "And what is the deadline if the product has a quality defect and I return it to a supplier?"),
    ("rec-04", "rec-06", "¿Y cada cuánto se cuentan los SKUs de clase A para llegar a esa meta?", "And how often are class A SKUs counted to reach that target?"),
    ("rec-05", "rec-07", "¿Y quién aprueba una orden de compra de 120 mil pesos?", "And who approves a purchase order for 120,000 pesos?"),
    ("rec-07", "rec-09", "¿Y cuántas cotizaciones necesita esa misma orden?", "And how many quotes does that same order need?"),
    ("rec-08", "rec-07", "Entonces, ¿quién la aprueba en una compra de 120 mil pesos?", "So who approves it for a 120,000 peso purchase?"),
    ("rec-10", "rec-11", "¿Y qué factor de seguridad usan los SKUs críticos en ese cálculo?", "And what safety factor do critical SKUs use in that calculation?"),
    ("rec-11", "rec-14", "¿Y para cuántos días de demanda se piden esos mismos SKUs?", "And for how many days of demand are those same SKUs ordered?"),
    ("rec-15", "rec-17", "¿Y qué pasa si incumple dos de esas metas?", "And what happens if it misses two of those targets?"),
    ("rec-16", "rec-15", "¿Y cuál es la meta de OTIF de ese mismo proveedor?", "And what is the OTIF target for that same supplier?"),
    ("rec-21", "rec-22", "¿Y quién aprueba una compra urgente de ese SKU?", "And who approves an urgent purchase of that SKU?"),
    ("rec-22", "rec-23", "¿Y desde cuántos días de cobertura hay que escalarla al gerente?", "And from how many days of coverage does it have to be escalated to the manager?"),
    ("rec-24", "rec-26", "¿Y cuándo un CEDIS se considera con excedente para esa transferencia?", "And when is a CEDIS considered to have a surplus for that transfer?"),
    ("rec-27", "rec-28", "¿Y puede modificar precios?", "And can it change prices?"),
    ("rec-28", "rec-29", "¿Y qué hago si me da una respuesta incorrecta?", "And what should I do if it gives me a wrong answer?"),
    ("rec-41", "rec-42", "¿Y cuál es la penalización por entrega tardía en ese contrato?", "And what is the late-delivery penalty in that contract?"),
]

# (base id of the question, the user's role, does it have permission over the reference document?)
PERMISO = [
    ("rec-01", "ventas", True),
    ("rec-07", "compras", True),
    ("rec-21", "almacen", True),
    ("rec-33", "operaciones", True),
    ("rec-40", "finanzas", True),
    ("rec-05", "ventas", False),
    ("rec-41", "almacen", False),
    ("rec-30", "ventas", False),
    ("rec-36", "almacen", False),
    ("rec-38", "ventas", False),
]

out = {"es": [], "en": []}
for lang in ("es", "en"):
    for d in base[lang].values():
        out[lang].append({"id": d["id"], "lang": lang, "tipo": "base", "question": d["question"], "gold": d["gold"]})
    for i, (prev, gold_id, es, en) in enumerate(SEGUIMIENTO, 1):
        out[lang].append({
            "id": f"seg-{i:02d}", "lang": lang, "tipo": "seguimiento",
            "pregunta_previa": base[lang][prev]["question"],
            "question": es if lang == "es" else en,
            "gold": base[lang][gold_id]["gold"],
        })
    for i, (bid, rol, permitido) in enumerate(PERMISO, 1):
        item = base[lang][bid]
        out[lang].append({
            "id": f"perm-{i:02d}", "lang": lang, "tipo": "permiso",
            "usuario": {"tenant": "alfa", "roles": [rol]},
            "permitido": permitido,
            "question": item["question"],
            "gold": item["gold"],
        })

# Validation
errores = []
for lang, items in out.items():
    ids = [x["id"] for x in items]
    if len(ids) != len(set(ids)):
        errores.append(f"ids duplicados en {lang}")
    for x in items:
        for g in x["gold"]:
            if g["passage"] not in corpus.get(g["source"], ""):
                errores.append(f"{x['id']} ({lang}): pasaje no literal en {g['source']}")
        if x["tipo"] == "permiso":
            doc = x["gold"][0]["source"]
            rol = x["usuario"]["roles"][0]
            visible = rol in ROLES[doc]
            if visible != x["permitido"]:
                errores.append(f"{x['id']} ({lang}): permitido={x['permitido']} no coincide con roles de {doc}")
if errores:
    raise SystemExit("\n".join(errores))

for lang, items in out.items():
    with open(DS / f"avanzado_{lang}.jsonl", "w", encoding="utf-8") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

(DS / "permisos.json").write_text(json.dumps({
    "tenants": {"alfa": "tenant de prueba 1; por ahora contiene todos los documentos"},
    "roles_por_documento": ROLES,
    "nota": "Modelo sintético de prueba. Los roles son asignaciones de este experimento, no permisos reales de inventory-copilot.",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for lang, items in out.items():
    conteo = {}
    for x in items:
        conteo[x["tipo"]] = conteo.get(x["tipo"], 0) + 1
    print(lang, conteo, "total", len(items))
print("validation: OK")
