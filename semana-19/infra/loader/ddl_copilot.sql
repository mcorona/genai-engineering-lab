CREATE EXTENSION IF NOT EXISTS vector;

-- Full inventory schema snapshot (inventory-copilot/db/init 01..03). Roles, grants and extensions omitted.
-- 01_schema.sql
-- Esquema de inventario sintetico + pgvector + rol de solo lectura (least privilege)

CREATE TABLE suppliers (
    supplier_id   SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    country       TEXT NOT NULL,  -- ISO 3166-1 alpha-2, e.g. 'CN', 'DE', 'US'
    lead_time_days INT NOT NULL CHECK (lead_time_days > 0)
);

CREATE TABLE products (
    sku           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,  -- e.g. 'Tornilleria', 'Electrico', 'Hidraulico'
    unit_cost     NUMERIC(12,2) NOT NULL,
    reorder_point INT NOT NULL,
    critical      BOOLEAN NOT NULL DEFAULT FALSE,
    supplier_id   INT REFERENCES suppliers(supplier_id)
);

CREATE TABLE warehouses (
    warehouse_id  SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    city          TEXT NOT NULL  -- 'Ciudad de Mexico', 'Guadalajara', 'Monterrey'
);

CREATE TABLE stock (
    sku           TEXT REFERENCES products(sku),
    warehouse_id  INT REFERENCES warehouses(warehouse_id),
    on_hand       INT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sku, warehouse_id)
);

CREATE TABLE sales_daily (
    sku           TEXT REFERENCES products(sku),
    day           DATE NOT NULL,
    units         INT NOT NULL,
    PRIMARY KEY (sku, day)
);

CREATE TABLE purchase_orders (
    po_id         SERIAL PRIMARY KEY,
    sku           TEXT REFERENCES products(sku),
    qty           INT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'PENDING_APPROVAL'
                  CHECK (status IN ('PENDING_APPROVAL','APPROVED','REJECTED')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunks de documentos (manuales, politicas) para RAG
CREATE TABLE doc_chunks (
    chunk_id      BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL,
    chunk_index   INT NOT NULL,
    content       TEXT NOT NULL,
    metadata      JSONB NOT NULL DEFAULT '{}',
    embedding     vector(1024)
);
CREATE INDEX ON doc_chunks USING hnsw (embedding vector_cosine_ops);

-- Rol de solo lectura para el agente: solo SELECT sobre tablas de negocio
-- 02_hitl_guardrails.sql
-- Semana 4: ordenes de compra con aprobacion humana + bitacora de auditoria.
-- Idempotente: corre sola en instalaciones nuevas (docker-entrypoint-initdb.d) y se aplica
-- a una DB existente con `python -m scripts.migrate`.

-- ---------------------------------------------------------------- purchase_orders
ALTER TABLE purchase_orders
    ADD COLUMN IF NOT EXISTS unit_cost      NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS amount         NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS required_level TEXT,
    ADD COLUMN IF NOT EXISTS reason         TEXT,
    ADD COLUMN IF NOT EXISTS requested_by   TEXT,
    ADD COLUMN IF NOT EXISTS confirmed_by   TEXT,
    ADD COLUMN IF NOT EXISTS decided_by     TEXT,
    ADD COLUMN IF NOT EXISTS decided_level  TEXT,
    ADD COLUMN IF NOT EXISTS decided_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS decision_note  TEXT;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'po_qty_positive') THEN
        ALTER TABLE purchase_orders ADD CONSTRAINT po_qty_positive CHECK (qty > 0);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'po_levels_valid') THEN
        ALTER TABLE purchase_orders ADD CONSTRAINT po_levels_valid CHECK (
            required_level IN ('comprador', 'gerente', 'director') AND
            (decided_level IS NULL OR decided_level IN ('comprador', 'gerente', 'director')));
    END IF;
END $$;

-- a lo mas una orden pendiente por SKU (politica_reorden.md: no duplicar ordenes abiertas)
CREATE UNIQUE INDEX IF NOT EXISTS po_one_pending_per_sku
    ON purchase_orders (sku) WHERE status = 'PENDING_APPROVAL';

CREATE OR REPLACE FUNCTION po_level_rank(level TEXT) RETURNS INT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE level WHEN 'comprador' THEN 1 WHEN 'gerente' THEN 2 WHEN 'director' THEN 3 END
$$;

-- Nivel de aprobacion por monto (ordenes_de_compra.md). Fuente de verdad: esta funcion;
-- src/tools/purchase_orders.py replica los umbrales solo para mostrar la vista previa.
CREATE OR REPLACE FUNCTION po_required_level(amount NUMERIC) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN amount < 50000 THEN 'comprador'
                WHEN amount <= 250000 THEN 'gerente'
                ELSE 'director' END
$$;

-- Al insertar, la DB (no el agente) fija costo, monto, nivel requerido y estado.
-- SECURITY DEFINER: copilot_po no necesita leer products para que el trigger lo haga.
CREATE OR REPLACE FUNCTION po_before_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    SELECT p.unit_cost INTO NEW.unit_cost FROM products p WHERE p.sku = NEW.sku;
    IF NEW.unit_cost IS NULL THEN
        RAISE EXCEPTION 'SKU inexistente: %', NEW.sku;
    END IF;
    NEW.amount := NEW.qty * NEW.unit_cost;
    NEW.required_level := po_required_level(NEW.amount);
    NEW.status := 'PENDING_APPROVAL';
    NEW.decided_by := NULL; NEW.decided_level := NULL; NEW.decided_at := NULL; NEW.decision_note := NULL;
    NEW.created_at := now();
    RETURN NEW;
END $$;

-- Al decidir: solo desde PENDING_APPROVAL, sin tocar la propuesta, y con autoridad suficiente.
CREATE OR REPLACE FUNCTION po_before_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'PENDING_APPROVAL' THEN
        RAISE EXCEPTION 'La orden % ya fue decidida (%)', OLD.po_id, OLD.status;
    END IF;
    IF NEW.status NOT IN ('APPROVED', 'REJECTED') THEN
        RAISE EXCEPTION 'Estado de decision invalido: %', NEW.status;
    END IF;
    IF (NEW.sku, NEW.qty, NEW.unit_cost, NEW.amount, NEW.required_level, NEW.reason,
        NEW.requested_by, NEW.confirmed_by, NEW.created_at)
       IS DISTINCT FROM
       (OLD.sku, OLD.qty, OLD.unit_cost, OLD.amount, OLD.required_level, OLD.reason,
        OLD.requested_by, OLD.confirmed_by, OLD.created_at) THEN
        RAISE EXCEPTION 'No se puede modificar la propuesta al decidir';
    END IF;
    IF NEW.decided_by IS NULL OR NEW.decided_level IS NULL THEN
        RAISE EXCEPTION 'La decision requiere decided_by y decided_level';
    END IF;
    IF NEW.status = 'APPROVED'
       AND po_level_rank(NEW.decided_level) < po_level_rank(OLD.required_level) THEN
        RAISE EXCEPTION 'Nivel insuficiente: la orden % requiere %, quien decide es %',
            OLD.po_id, OLD.required_level, NEW.decided_level;
    END IF;
    NEW.decided_at := now();
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS po_before_insert ON purchase_orders;
CREATE TRIGGER po_before_insert BEFORE INSERT ON purchase_orders
    FOR EACH ROW EXECUTE FUNCTION po_before_insert();
DROP TRIGGER IF EXISTS po_before_update ON purchase_orders;
CREATE TRIGGER po_before_update BEFORE UPDATE ON purchase_orders
    FOR EACH ROW EXECUTE FUNCTION po_before_update();

-- ---------------------------------------------------------------- audit_log (append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    event_id  BIGSERIAL PRIMARY KEY,
    ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor     TEXT NOT NULL,
    event     TEXT NOT NULL,
    details   JSONB NOT NULL DEFAULT '{}'
);

-- ---------------------------------------------------------------- roles de minimo privilegio


-- lectura: el agente revisa ordenes abiertas antes de proponer

-- el agente solo puede PROPONER: insertar columnas de la propuesta, nunca status ni decision

-- las personas aprobadoras solo pueden DECIDIR

-- bitacora: solo insercion (nadie de la app puede editar ni borrar eventos)
-- 03_po_delivery.sql
-- Ordenes de compra: CEDIS de entrega y fecha requerida (ordenes_de_compra.md, "Datos obligatorios
-- de una orden"). Idempotente: corre en instalaciones nuevas (docker-entrypoint-initdb.d) y se aplica
-- a una DB existente con `python -m scripts.migrate`. Las ordenes anteriores quedan con NULL.

ALTER TABLE purchase_orders
    ADD COLUMN IF NOT EXISTS delivery_warehouse_id INT REFERENCES warehouses (warehouse_id),
    ADD COLUMN IF NOT EXISTS required_date         DATE;

-- Obligatorios en ordenes nuevas. La fecha no se compara con now(): los datos sinteticos usan una
-- fecha "hoy" fija (ANCHOR_DATE) y esa validacion la hace la vista previa.
CREATE OR REPLACE FUNCTION po_require_delivery() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.delivery_warehouse_id IS NULL OR NEW.required_date IS NULL THEN
        RAISE EXCEPTION 'La orden requiere CEDIS de entrega y fecha requerida';
    END IF;
    RETURN NEW;
END $$;

-- Igual que el resto de la propuesta: nadie la cambia al decidir.
CREATE OR REPLACE FUNCTION po_delivery_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.delivery_warehouse_id, NEW.required_date)
       IS DISTINCT FROM (OLD.delivery_warehouse_id, OLD.required_date) THEN
        RAISE EXCEPTION 'No se puede modificar la propuesta al decidir';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS po_require_delivery ON purchase_orders;
CREATE TRIGGER po_require_delivery BEFORE INSERT ON purchase_orders
    FOR EACH ROW EXECUTE FUNCTION po_require_delivery();
DROP TRIGGER IF EXISTS po_delivery_immutable ON purchase_orders;
CREATE TRIGGER po_delivery_immutable BEFORE UPDATE ON purchase_orders
    FOR EACH ROW EXECUTE FUNCTION po_delivery_immutable();

-- el agente propone tambien estas dos columnas; las personas aprobadoras no las pueden tocar
