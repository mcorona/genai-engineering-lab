-- Esquema legado de semana 10: vistas con nombres crípticos sobre las tablas de inventory-copilot.
-- Mismos datos y mismos valores; solo cambian los nombres. Se ejecuta con el rol administrador (PG_ADMIN_DSN).
-- search_path para resolver las tablas base donde estén (esquema copilot o public).
SET search_path = copilot, public;

DROP SCHEMA IF EXISTS legado CASCADE;
CREATE SCHEMA legado;

CREATE VIEW legado.prvmst AS
SELECT supplier_id AS prv_id, name AS prv_nm, country AS prv_pais, lead_time_days AS prv_dte FROM suppliers;

CREATE VIEW legado.artmst AS
SELECT sku AS art_cd, name AS art_dsc, category AS art_lin, unit_cost AS art_cst,
       reorder_point AS art_ptr, critical AS art_crt, supplier_id AS art_prv FROM products;

CREATE VIEW legado.almmst AS
SELECT warehouse_id AS alm_id, name AS alm_dsc, city AS alm_cdd FROM warehouses;

CREATE VIEW legado.exidet AS
SELECT sku AS exi_art, warehouse_id AS exi_alm, on_hand AS exi_qty, updated_at AS exi_fup FROM stock;

CREATE VIEW legado.vtadia AS
SELECT sku AS vta_art, day AS vta_fch, units AS vta_und FROM sales_daily;

CREATE VIEW legado.ocpcab AS
SELECT po_id AS ocp_id, sku AS ocp_art, qty AS ocp_qty, status AS ocp_sts, created_at AS ocp_fcr FROM purchase_orders;

-- El rol de solo lectura solo ve las vistas del esquema legado (además de lo que ya tenía).
GRANT USAGE ON SCHEMA legado TO copilot_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA legado TO copilot_ro;
