-- Semana 16, actividad 2: riesgos sembrados para la auditoría de esquema legado.
-- Dos tablas legadas nativas (sin equivalente moderno y sin llaves foráneas declaradas, como en un sistema real):
--   legado.prvcto  contactos de proveedores: datos personales, un duplicado, un huérfano y un nulo en la llave.
--   legado.movinv  movimientos de inventario: huérfanos, doble captura, nulos en llaves y unidades inconsistentes.
-- Todos los datos personales son sintéticos (dominios reservados .example, teléfonos 55 0000 xxxx, RFC inventados).
-- Se ejecuta con PG_ADMIN_DSN después de semana-10/legado/legado.sql y semana-13/seguridad/artnot.sql. Idempotente.
-- No toca las tablas de inventory-copilot ni las vistas de la semana 10: los golden sets anteriores no cambian.

DROP TABLE IF EXISTS legado.prvcto;
CREATE TABLE legado.prvcto (
    cto_id  INT PRIMARY KEY,
    cto_prv INT,             -- proveedor (prvmst.prv_id), sin llave foránea declarada
    cto_nom TEXT,            -- nombre de la persona de contacto
    cto_crg TEXT,            -- cargo
    cto_eml TEXT,            -- correo
    cto_tel TEXT,            -- teléfono
    cto_rfc TEXT,            -- RFC de persona física
    cto_alt DATE             -- fecha de alta
);
INSERT INTO legado.prvcto VALUES
 (1,  1,  'Jorge Alberto Méndez Ruiz',   'Ejecutivo de cuenta',   'jmendez@aceros-norte.example',      '55 0000 1101', 'MERJ780412QH3', DATE '2019-03-11'),
 (2,  2,  'Laura Patricia Ochoa Lima',   'Gerente comercial',     'lochoa@plasticos-bajio.example',    '55 0000 1102', 'OOLL850923TK1', DATE '2020-07-02'),
 (3,  3,  'Ricardo Salinas Vega',        'Ventas',                'rsalinas@electronica-pac.example',  '55 0000 1103', 'SAVR901105MN7', DATE '2018-11-20'),
 (4,  4,  'Emily Carter',                'Account manager',       'ecarter@globalparts.example',       '+1 555 0100 204', NULL,         DATE '2021-01-15'),
 (5,  5,  'Michael Brooks',              'Sales rep',             'mbrooks@midwestsupply.example',     '+1 555 0100 205', NULL,         DATE '2021-06-08'),
 (6,  6,  'Wei Zhang',                   'Export manager',        'wzhang@sz-components.example',      '+86 755 0000 206', NULL,        DATE '2017-09-30'),
 (7,  7,  'Li Na Chen',                  'Sales',                 'lnchen@ningbo-hw.example',          '+86 574 0000 207', NULL,        DATE '2018-04-17'),
 (8,  8,  'Klaus Becker',                'Vertrieb',              'kbecker@rhein-it.example',          '+49 30 0000 208', NULL,         DATE '2016-12-05'),
 (9,  9,  'Anna Schmid',                 'Key account',           'aschmid@bavaria-precision.example', '+49 89 0000 209', NULL,         DATE '2019-08-22'),
 (10, 10, 'Camila Restrepo Gómez',       'Comercial',             'crestrepo@andes-dist.example',      '+57 1 0000 210', NULL,          DATE '2022-02-14'),
 (11, 11, 'Javier Ortega Prieto',        'Comercial',             'jortega@iberia-sum.example',        '+34 91 0000 211', NULL,         DATE '2020-10-01'),
 (12, 12, 'Sophie Tremblay',             'Sales',                 'stremblay@maple-ind.example',       '+1 555 0100 212', NULL,         DATE '2023-03-27'),
 -- duplicado: la misma persona capturada dos veces con otro id (riesgo D-PRVCTO)
 (13, 2,  'LAURA PATRICIA OCHOA LIMA',   'Gerente comercial',     'lochoa@plasticos-bajio.example',    '55 0000 1102', 'OOLL850923TK1', DATE '2024-05-06'),
 -- huérfano: proveedor 15 no existe en prvmst (riesgo H-PRVCTO)
 (14, 15, 'Mario Fuentes Ibarra',        'Representante',         'mfuentes@proveedor-baja.example',   '55 0000 1114', 'FUIM700318PL9', DATE '2015-02-09'),
 -- nulo en la llave: contacto sin proveedor (riesgo N-PRVCTO)
 (15, NULL,'Sandra Núñez Paredes',       'Cobranza',              'snunez@sin-proveedor.example',      '55 0000 1115', 'NUPS880730RD2', DATE '2024-09-12');

DROP TABLE IF EXISTS legado.movinv;
CREATE TABLE legado.movinv (
    mov_id  INT PRIMARY KEY,
    mov_art TEXT,            -- artículo (artmst.art_cd), sin llave foránea declarada
    mov_alm INT,             -- almacén (almmst.alm_id), sin llave foránea declarada
    mov_tip TEXT,            -- 'ENT' entrada, 'SAL' salida
    mov_qty NUMERIC(12,2),   -- cantidad en la unidad de mov_uni
    mov_uni TEXT,            -- unidad capturada
    mov_fch DATE,            -- fecha del movimiento
    mov_usr TEXT             -- usuario que capturó (login de una persona)
);
-- 30 movimientos limpios: SKU-0001..SKU-0030, almacenes 1 a 3, en piezas.
INSERT INTO legado.movinv
SELECT g, format('SKU-%s', lpad(g::text, 4, '0')), 1 + (g % 3), CASE WHEN g % 4 = 0 THEN 'SAL' ELSE 'ENT' END,
       10 + (g * 7) % 50, 'PZA', DATE '2026-09-01' + (g % 25),
       (ARRAY['jmartinez', 'agarcia', 'lhernandez'])[1 + (g % 3)]
FROM generate_series(1, 30) AS g;
-- SKU-0012, SKU-0027 y SKU-0042 se capturan además en otras unidades (riesgo U-MOVINV): misma cantidad física,
-- números que no se pueden sumar. SKU-0027 coincide con la nota 3 de artnot (cambio a caja de 20).
INSERT INTO legado.movinv VALUES
 (31, 'SKU-0012', 1, 'ENT', 40,    'pza', DATE '2026-09-08', 'agarcia'),
 (32, 'SKU-0027', 2, 'ENT', 3,     'CJA', DATE '2026-09-14', 'jmartinez'),
 (33, 'SKU-0042', 3, 'ENT', 12.5,  'KG',  DATE '2026-09-16', 'lhernandez'),
 (34, 'SKU-0042', 3, 'SAL', 30,    'PZA', DATE '2026-09-18', 'lhernandez'),
-- huérfanos (riesgo H-MOVINV): artículos que no existen en artmst y un almacén que no existe en almmst.
 (35, 'SKU-0999', 1, 'ENT', 25,    'PZA', DATE '2026-09-03', 'agarcia'),
 (36, 'SKU-1000', 2, 'SAL', 5,     'PZA', DATE '2026-09-04', 'jmartinez'),
 (37, 'SKU-0050', 7, 'ENT', 18,    'PZA', DATE '2026-09-05', 'lhernandez'),
-- doble captura (riesgo D-MOVINV): mismo movimiento con otro id.
 (38, 'SKU-0005', 3, 'ENT', 45,    'PZA', DATE '2026-09-07', 'lhernandez'),
 (39, 'SKU-0005', 3, 'ENT', 45,    'PZA', DATE '2026-09-07', 'lhernandez'),
 (40, 'SKU-0021', 1, 'SAL', 17,    'PZA', DATE '2026-09-22', 'jmartinez'),
 (41, 'SKU-0021', 1, 'SAL', 17,    'PZA', DATE '2026-09-22', 'jmartinez'),
-- nulos en columnas clave (riesgo N-MOVINV).
 (42, NULL,       2, 'ENT', 8,     'PZA', DATE '2026-09-10', 'agarcia'),
 (43, NULL,       1, 'SAL', 2,     'PZA', DATE '2026-09-11', 'agarcia'),
 (44, 'SKU-0033', NULL, 'ENT', 14, 'PZA', DATE '2026-09-12', 'lhernandez');

GRANT SELECT ON legado.prvcto, legado.movinv TO copilot_ro;
DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'copilot_nlq') THEN
    GRANT SELECT ON legado.prvcto, legado.movinv TO copilot_nlq; END IF; END $$;
