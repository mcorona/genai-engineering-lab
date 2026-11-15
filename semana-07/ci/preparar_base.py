"""Prepares the CI database: the full schema, a read-only role and synthetic data (seed 42)."""
import importlib.util
import os
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent
admin = os.environ["PG_ADMIN_DSN"]

with psycopg.connect(admin, autocommit=True) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute((RAIZ.parent / "schema_completo.sql").read_text(encoding="utf-8"))
    # The same scope as the production copilot_ro role: business tables only, no audit_log.
    conn.execute("CREATE ROLE copilot_ro LOGIN PASSWORD 'ci-ro'")
    conn.execute("GRANT CONNECT ON DATABASE inventory TO copilot_ro")
    conn.execute("GRANT USAGE ON SCHEMA public TO copilot_ro")
    conn.execute("GRANT SELECT ON suppliers, products, warehouses, stock, sales_daily, purchase_orders, doc_chunks TO copilot_ro")

spec = importlib.util.spec_from_file_location("gen", RAIZ / "generar_datos.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
gen.load(admin, gen.build_dataset(gen.SEED))
print(f"database ready (seed={gen.SEED})")
