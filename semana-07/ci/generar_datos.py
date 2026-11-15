# Copia de inventory-copilot/scripts/generate_data.py (semana 7, CI).
# Synthetic data with a fixed seed: same seed, same data.
"""Reproducible synthetic data generator for the inventory database.

Usage:
    python -m scripts.generate_data               # seed 42, inserts through PG_ADMIN_DSN
    python -m scripts.generate_data --dry-run     # only prints the counts
    python -m scripts.generate_data --seed 7

The anchor date is fixed (ANCHOR_DATE, defined in src/tools/sql_tool.py) so that the eval gold set stays stable:
sales_daily covers the 180 days that end on ANCHOR_DATE (inclusive).
"""
from __future__ import annotations

import argparse
import math
import os
import random
from datetime import date, timedelta

# Fixed anchor date, copied from src/tools/sql_tool.py (ANCHOR_DATE).
# It is copied here so that CI does not depend on inventory-copilot's src/ package.
ANCHOR_DATE = date(2026, 9, 26)

SEED = 42
N_PRODUCTS = 200
CRITICAL_RATIO = 0.15
N_DAYS = 180
N_BELOW_REORDER = 25

SUPPLIERS = [
    ("Aceros del Norte", "MX", 7), ("Plasticos Bajio", "MX", 5),
    ("Electronica Pacifico", "MX", 10), ("Global Parts Inc", "US", 14),
    ("Midwest Supply Co", "US", 12), ("Shenzhen Components", "CN", 40),
    ("Ningbo Hardware", "CN", 35), ("Rhein Industrietechnik", "DE", 28),
    ("Bavaria Precision", "DE", 30), ("Andes Distribuciones", "CO", 18),
    ("Iberia Suministros", "ES", 25), ("Maple Industrial", "CA", 15),
]

WAREHOUSES = [("CEDIS Centro", "Ciudad de Mexico"),
              ("CEDIS Occidente", "Guadalajara"),
              ("CEDIS Norte", "Monterrey")]

# category -> (base names, unit cost range)
CATEGORIES = {
    "Tornilleria": (["Tornillo hexagonal", "Tuerca de seguridad", "Arandela plana", "Perno de anclaje"], (0.5, 8)),
    "Electrico": (["Cable THHN", "Interruptor termomagnetico", "Contactor", "Relevador"], (15, 450)),
    "Hidraulico": (["Valvula de bola", "Manguera hidraulica", "Conector rapido", "Bomba de engranes"], (20, 1800)),
    "Neumatico": (["Cilindro neumatico", "Electrovalvula", "Regulador de presion", "Racor push-in"], (10, 900)),
    "Rodamientos": (["Rodamiento de bolas", "Chumacera", "Rodamiento conico", "Buje de bronce"], (8, 600)),
    "Seguridad": (["Guante de nitrilo", "Casco industrial", "Lentes de seguridad", "Arnes"], (3, 1200)),
    "Herramientas": (["Llave combinada", "Broca de cobalto", "Disco de corte", "Dado de impacto"], (5, 350)),
    "Empaque": (["Caja de carton", "Pelicula estirable", "Cinta canela", "Tarima de madera"], (1, 250)),
}
VARIANTS = ["M6", "M8", "M10", "1/2\"", "3/4\"", "1\"", "Chico", "Mediano", "Grande", "Pro", "HD", "XL"]


def build_dataset(seed: int = SEED) -> dict[str, list[tuple]]:
    """Builds all the rows in memory. A pure function: same seed -> same data."""
    rng = random.Random(seed)

    suppliers = [(i + 1, n, c, lt) for i, (n, c, lt) in enumerate(SUPPLIERS)]
    warehouses = [(i + 1, n, c) for i, (n, c) in enumerate(WAREHOUSES)]

    n_critical = round(N_PRODUCTS * CRITICAL_RATIO)
    critical_idx = set(rng.sample(range(N_PRODUCTS), n_critical))
    cat_names = list(CATEGORIES)

    products, base_demand = [], {}
    used_names: set[str] = set()
    for i in range(N_PRODUCTS):
        sku = f"SKU-{i + 1:04d}"
        cat = cat_names[i % len(cat_names)]
        bases, (lo, hi) = CATEGORIES[cat]
        name = f"{rng.choice(bases)} {rng.choice(VARIANTS)}"
        while name in used_names:
            name = f"{rng.choice(bases)} {rng.choice(VARIANTS)}"
        used_names.add(name)
        unit_cost = round(math.exp(rng.uniform(math.log(lo), math.log(hi))), 2)
        demand = rng.uniform(0.5, 30.0) * (1.5 if i in critical_idx else 1.0)
        supplier_id = rng.randint(1, len(suppliers))
        lead_time = suppliers[supplier_id - 1][3]
        # reorder point ~ demand during the lead time + safety stock
        reorder_point = max(5, round(demand * lead_time * rng.uniform(1.1, 1.5)))
        products.append((sku, name, cat, unit_cost, reorder_point, i in critical_idx, supplier_id))
        base_demand[sku] = demand

    # SKUs below reorder_point: biased toward critical ones (about half are critical)
    crit_skus = [p[0] for p in products if p[5]]
    other_skus = [p[0] for p in products if not p[5]]
    n_crit_below = min(len(crit_skus), N_BELOW_REORDER // 2)
    below = set(rng.sample(crit_skus, n_crit_below)) | set(
        rng.sample(other_skus, N_BELOW_REORDER - n_crit_below))

    stock = []
    for sku, _, _, _, rop, _, _ in products:
        total = (rng.randint(0, max(0, rop - 1)) if sku in below
                 else rng.randint(rop + 1, rop * 3))
        # split the total across 3 warehouses
        w = [rng.random() for _ in warehouses]
        parts = [int(total * x / sum(w)) for x in w]
        parts[0] += total - sum(parts)
        for (wid, _, _), qty in zip(warehouses, parts):
            stock.append((sku, wid, qty))

    start = ANCHOR_DATE - timedelta(days=N_DAYS - 1)
    weekday_factor = [1.1, 1.05, 1.0, 1.0, 1.15, 0.7, 0.4]  # lun..dom
    sales = []
    for sku, *_ in products:
        base = base_demand[sku]
        trend = rng.uniform(-0.3, 0.3)  # linear trend over the period
        for d in range(N_DAYS):
            day = start + timedelta(days=d)
            lam = base * weekday_factor[day.weekday()] * (1 + trend * (d / N_DAYS - 0.5))
            sales.append((sku, day, _poisson(rng, max(lam, 0.01))))

    return {"suppliers": suppliers, "warehouses": warehouses, "products": products,
            "stock": stock, "sales_daily": sales}


def _poisson(rng: random.Random, lam: float) -> int:
    """Poisson via Knuth for a small lam; normal approximation for a large lam."""
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


COLUMNS = {
    "suppliers": ("supplier_id", "name", "country", "lead_time_days"),
    "warehouses": ("warehouse_id", "name", "city"),
    "products": ("sku", "name", "category", "unit_cost", "reorder_point", "critical", "supplier_id"),
    "stock": ("sku", "warehouse_id", "on_hand"),
    "sales_daily": ("sku", "day", "units"),
}
LOAD_ORDER = ["suppliers", "warehouses", "products", "stock", "sales_daily"]


def load(dsn: str, data: dict[str, list[tuple]]) -> None:
    """Replaces the business data in a single transaction (idempotent)."""
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE purchase_orders, sales_daily, stock, products, "
                    "warehouses, suppliers RESTART IDENTITY CASCADE")
        for table in LOAD_ORDER:
            cols = ", ".join(COLUMNS[table])
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
                for row in data[table]:
                    copy.write_row(row)
        # the SERIAL columns were inserted with explicit ids: sync the sequences
        for table, pk in (("suppliers", "supplier_id"), ("warehouses", "warehouse_id")):
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
                        f"(SELECT MAX({pk}) FROM {table}))")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    data = build_dataset(args.seed)
    for t in LOAD_ORDER:
        print(f"  {t:<12} {len(data[t]):>6} rows")
    if args.dry_run:
        return
    load(os.environ["PG_ADMIN_DSN"], data)
    print(f"Loaded into PG_ADMIN_DSN (seed={args.seed}, anchor={ANCHOR_DATE})")


if __name__ == "__main__":
    main()
