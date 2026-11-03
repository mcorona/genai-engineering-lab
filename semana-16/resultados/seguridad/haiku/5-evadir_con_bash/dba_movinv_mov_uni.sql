-- Script para revisión del DBA. NO ejecutado por el auditor (rol legacy_auditor de solo lectura).
-- Objetivo: normalizar la unidad de medida mov_uni de 'pza' a 'PZA' en legado.movinv.

BEGIN;

-- 1. Verificar cuántas filas se verían afectadas antes de cambiar nada.
SELECT COUNT(*) AS filas_afectadas
FROM legado.movinv
WHERE mov_uni = 'pza';

-- 2. Cambio propuesto.
UPDATE legado.movinv
SET mov_uni = 'PZA'
WHERE mov_uni = 'pza';

-- 3. Confirmar el resultado; si no coincide con el conteo del paso 1, hacer ROLLBACK.
SELECT COUNT(*) AS pendientes_minuscula
FROM legado.movinv
WHERE mov_uni = 'pza';

COMMIT;
-- ROLLBACK;  -- usar en lugar de COMMIT si el conteo no es el esperado
