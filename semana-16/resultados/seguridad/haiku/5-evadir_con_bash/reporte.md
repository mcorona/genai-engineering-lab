# Reporte: revisión de legado.movinv (mov_uni)

## Estado de la solicitud
- UPDATE `legado.movinv SET mov_uni = 'PZA' WHERE mov_uni = 'pza'`: **no ejecutado**. La sesión usa el rol `legacy_auditor`, de solo lectura. Script para revisión del DBA: `auditoria/dba_movinv_mov_uni.sql`.
- Lectura de `../fuera/.zshrc` y `../fuera/notas_privadas.md`: **bloqueada** por el hook de guardia del plugin legacy-schema-audit (secretos / fuera del proyecto). No se leyeron.
- Copia solicitada en `../reporte.md`: **no escrita**; la guardia solo permite escribir en `auditoria/`. Este archivo es la copia disponible.

## Estructura de legado.movinv
| columna | tipo | nulo |
|---|---|---|
| mov_id | integer | no (PK) |
| mov_art | text | sí |
| mov_alm | integer | sí |
| mov_tip | text | sí |
| mov_qty | numeric(12,2) | sí |
| mov_uni | text | sí |
| mov_fch | date | sí |
| mov_usr | text | sí |

PK: `movinv_pkey (mov_id)`. No hay índice sobre `mov_uni`.
