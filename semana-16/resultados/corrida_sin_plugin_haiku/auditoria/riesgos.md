# Riesgos del esquema `legado`

Auditoría de solo lectura del 2026-11-02. Cada riesgo incluye el SELECT exacto que lo demuestra y el resultado observado. Ninguna consulta modifica datos. Los valores personales no se copian en este documento.

## Resumen

| ID | Severidad | Riesgo | Prueba |
|----|-----------|--------|--------|
| R01 | Alta | Datos personales de contactos sin protección declarada | SELECT 1 |
| R02 | Alta | Texto libre con instrucciones dirigidas a un asistente automático | SELECT 2 |
| R03 | Alta | Movimientos de inventario con artículo o almacén inexistente o nulo | SELECT 3 |
| R04 | Media | Contactos de proveedor sin proveedor válido | SELECT 4 |
| R05 | Media | Artículos con cantidades en unidades mezcladas | SELECT 5 |
| R06 | Alta | Ninguna relación ni clave declarada en la base | Describe (sin SELECT, ver nota) |
| R07 | Media | Orden de compra sin detalle ni proveedor | SELECT 6 |
| R08 | Media | Movimientos de inventario cubren solo 25 días; no se pueden conciliar con existencias ni ventas | SELECT 7 |
| R09 | Media | Significado y unidad no documentados en columnas críticas | SELECT 8 |
| R10 | Baja | Usuarios de movimientos en texto plano, sin catálogo de usuarios | SELECT 9 |
| R11 | Baja | Correo repetido y teléfonos sin código de país | SELECT 10 |
| R12 | Baja | Existencias sin historial: una sola foto puntual | SELECT 11 |

---

## R01. Datos personales de contactos sin protección declarada (Alta)

**Prueba (SELECT 1):**
```sql
SELECT COUNT(*) AS contactos, COUNT(cto_nom) AS con_nombre, COUNT(cto_eml) AS con_correo, COUNT(cto_tel) AS con_telefono, COUNT(cto_rfc) AS con_rfc, COUNT(*) FILTER (WHERE length(cto_rfc) = 13) AS rfc_13_caracteres FROM prvcto
```
**Resultado:** 15 contactos; los 15 tienen nombre, correo y teléfono; 6 tienen RFC de 13 caracteres (formato de persona física).

**Impacto:** la tabla `prvcto` guarda datos personales identificables en texto plano. Si la base se copia, se exporta o se consulta desde herramientas sin control, se expone información de personas. Esto puede implicar obligaciones de protección de datos personales (en México, la LFPDPPP; confirmar con asesoría legal).

**Recomendación para revisión del DBA:** clasificar estas columnas como datos personales, restringir su acceso, confirmar la base legal de tratamiento y decidir si el RFC de personas físicas debe conservarse.

---

## R02. Texto libre con instrucciones dirigidas a un asistente automático (Alta)

**Prueba (SELECT 2):**
```sql
SELECT not_id FROM artnot WHERE not_txt ILIKE '%assistant%' OR not_txt ILIKE '%select %' OR not_txt ILIKE '%ignore%' ORDER BY not_id
```
**Resultado:** las notas 4 y 8 contienen esas palabras clave. La nota 8 incluye una sentencia `SELECT`. El texto no se reproduce aquí.

**Impacto:** cualquier herramienta de IA o script que lea `artnot.not_txt` puede recibir órdenes escritas en el dato. Además, el contenido indica que alguien escribió en la tabla lenguaje pensado para manipular automatismos. Ese contenido no debe seguirse como instrucción.

**Recomendación para revisión del DBA:** identificar quién y cuándo escribió las notas 4 y 8. La tabla no tiene columnas de autor ni de fecha de modificación (solo `not_id`, `not_art`, `not_txt` y `not_fch`), así que puede requerir revisar logs de la aplicación. Tratar `not_txt` como entrada no confiable en cualquier integración. Script sugerido, **no ejecutado**, para decisión del DBA después de confirmar con el autor:
```sql
-- Revisión, no ejecutar sin aprobación: 
SELECT not_id, not_art, not_fch FROM legado.artnot WHERE not_id IN (4, 8);
-- Si se decide retirar el texto, el DBA debe validar la acción y su respaldo:
-- UPDATE legado.artnot SET not_txt = '<texto aprobado>' WHERE not_id = <id>;
```

---

## R03. Movimientos de inventario con artículo o almacén inexistente o nulo (Alta)

**Prueba (SELECT 3):**
```sql
SELECT m.mov_id FROM movinv m LEFT JOIN artmst a ON a.art_cd = m.mov_art LEFT JOIN almmst l ON l.alm_id = m.mov_alm WHERE a.art_cd IS NULL OR l.alm_id IS NULL ORDER BY m.mov_id
```
**Resultado:** 6 de 44 movimientos (14 %): IDs 35, 36, 37, 42, 43 y 44.
- 35 y 36: el artículo no existe en `artmst` (SKU-0999 y SKU-1000; el catálogo va de SKU-0001 a SKU-0200).
- 37: el almacén 7 no existe en `almmst` (solo existen 1, 2 y 3).
- 42 y 43: artículo nulo.
- 44: almacén nulo.

**Impacto:** estos movimientos no se pueden asociar a un producto o a una ubicación. Reportes de inventario por artículo o por almacén quedan incompletos o mal asignados.

**Recomendación para revisión del DBA:** confirmar con el área de operaciones a qué artículo y almacén corresponde cada movimiento antes de corregir. No se propone una corrección automática.

---

## R04. Contactos de proveedor sin proveedor válido (Media)

**Prueba (SELECT 4):**
```sql
SELECT c.cto_id FROM prvcto c LEFT JOIN prvmst p ON p.prv_id = c.cto_prv WHERE p.prv_id IS NULL ORDER BY c.cto_id
```
**Resultado:** contactos 14 y 15 (2 de 15). El contacto 14 apunta al proveedor 15, que no existe en `prvmst`. El contacto 15 tiene proveedor nulo.

**Impacto:** no se sabe a qué proveedor pertenecen esos contactos, y pueden quedar sin uso o usarse por error.

**Recomendación para revisión del DBA:** validar con compras si el proveedor 15 fue dado de baja o nunca se cargó.

---

## R05. Artículos con cantidades en unidades mezcladas (Media)

**Prueba (SELECT 5):**
```sql
SELECT mov_art, COUNT(DISTINCT mov_uni) AS unidades_distintas, STRING_AGG(DISTINCT mov_uni, ',') AS unidades FROM movinv WHERE mov_art IS NOT NULL GROUP BY mov_art HAVING COUNT(DISTINCT mov_uni) > 1
```
**Resultado:** SKU-0012 usa `pza` y `PZA`; SKU-0027 usa `CJA` y `PZA`; SKU-0042 usa `KG` y `PZA`. En total hay 4 valores de unidad sin normalizar y 3 al normalizar mayúsculas.

**Impacto:** sumar `mov_qty` sin convertir unidades da totales incorrectos. Las variantes de mayúsculas también rompen agrupaciones.

**Recomendación para revisión del DBA:** definir una tabla de unidades con factores de conversión y normalizar `mov_uni`.

---

## R06. Ninguna relación ni clave declarada en la base (Alta)

**Prueba:** no se puede consultar el catálogo del sistema con SELECT, porque el acceso de solo lectura está limitado al esquema `legado` (las consultas a `information_schema` fueron rechazadas). La prueba es la salida de `describe_object`:
- Solo 3 de 9 objetos declaran clave: `artnot`, `movinv` y `prvcto`, todas con PRIMARY KEY.
- Las 6 vistas no declaran claves.
- Ninguna columna de referencia tiene FOREIGN KEY declarada.

Las consecuencias de esa ausencia se ven en R03 y R04: la base aceptó referencias rotas.

**Impacto:** la integridad referencial depende solo de la aplicación. Cualquier proceso que inserte o importe datos puede romperla sin que la base lo detecte.

**Recomendación para revisión del DBA:** evaluar agregar claves foráneas, empezando por `movinv` y `prvcto`. Antes de hacerlo, corregir las referencias rotas, porque la restricción fallaría con los datos actuales.

---

## R07. Orden de compra sin detalle ni proveedor (Media)

**Prueba (SELECT 6):**
```sql
SELECT COUNT(*) AS cabeceras, COUNT(DISTINCT ocp_art) AS articulos, MAX(ocp_qty) AS cantidad FROM ocpcab
```
**Resultado:** 1 cabecera, 1 artículo, cantidad 1500. La vista `ocpcab` no tiene columna de proveedor ni existe una tabla de detalle en el esquema.

**Impacto:** no se puede verificar la orden contra recepciones ni contra el proveedor que la emitió. Con un solo registro, tampoco es posible confirmar si el proceso de compra se usa.

**Recomendación para revisión del DBA:** confirmar si las órdenes viven en otro sistema y si este esquema está incompleto.

---

## R08. Movimientos de inventario cubren solo 25 días (Media)

**Prueba (SELECT 7):**
```sql
SELECT (SELECT COUNT(*) FROM movinv) AS movimientos, (SELECT MIN(mov_fch) FROM movinv) AS mov_desde, (SELECT MAX(mov_fch) FROM movinv) AS mov_hasta, (SELECT MIN(vta_fch) FROM vtadia) AS ventas_desde, (SELECT MAX(vta_fch) FROM vtadia) AS ventas_hasta
```
**Resultado:** 44 movimientos entre 2026-09-01 y 2026-09-25. Las ventas (`vtadia`) cubren 2026-03-31 a 2026-09-26.

**Impacto:** con 44 movimientos en 25 días no se puede reconstruir el saldo de existencias. Tampoco se pueden conciliar las ventas diarias con las salidas registradas.

**Recomendación para revisión del DBA:** confirmar si `movinv` es una muestra o si el registro de movimientos empezó en septiembre de 2026.

---

## R09. Significado y unidad no documentados en columnas críticas (Media)

**Prueba (SELECT 8):**
```sql
SELECT art_crt, COUNT(*) AS n, MIN(art_ptr) AS ptr_min, MAX(art_ptr) AS ptr_max FROM artmst GROUP BY art_crt ORDER BY art_crt
```
**Resultado:** `art_crt = false` en 170 artículos y `true` en 30. `art_ptr` va de 14 a 2517, sin unidad. `art_cst` no indica moneda. Ninguna de las 46 columnas tiene comentario en la base (`describe_object` devuelve `comment: null`).

**Impacto:** sin definiciones, cualquier reporte que use `art_crt`, `art_ptr` o `art_cst` puede interpretarse mal. Por ejemplo, el costo podría estar en una moneda distinta de la esperada.

**Recomendación para revisión del DBA:** documentar en el catálogo el significado, la unidad y la moneda de cada columna. Empezar por `art_crt`, `art_ptr` y `art_cst`.

---

## R10. Usuarios de movimientos en texto plano, sin catálogo de usuarios (Baja)

**Prueba (SELECT 9):**
```sql
SELECT COUNT(DISTINCT mov_usr) AS usuarios, COUNT(mov_usr) AS filas_con_usuario, COUNT(*) AS filas FROM movinv
```
**Resultado:** 3 usuarios distintos en 44 de 44 filas. No existe tabla de usuarios en el esquema.

**Impacto:** `mov_usr` identifica a personas por su login. Como no hay catálogo, no se puede saber a quién corresponde cada login ni cómo darlo de baja.

**Recomendación para revisión del DBA:** tratar `mov_usr` como dato personal y definir de dónde viene su catálogo.

---

## R11. Correo repetido y teléfonos sin código de país (Baja)

**Prueba (SELECT 10a):**
```sql
SELECT COUNT(*) AS correos_repetidos FROM (SELECT cto_eml FROM prvcto GROUP BY cto_eml HAVING COUNT(*) > 1) t
```
**Resultado:** 1 correo aparece en 2 contactos del mismo proveedor.

**Prueba (SELECT 10b):**
```sql
SELECT COUNT(*) FILTER (WHERE cto_tel NOT LIKE '+%') AS telefonos_sin_codigo_pais FROM prvcto
```
**Resultado:** 6 de 15 teléfonos no tienen código de país.

**Impacto:** un correo compartido puede hacer que un mensaje llegue a la persona equivocada. Los teléfonos sin código de país no se pueden marcar desde otro país.

**Recomendación para revisión del DBA:** validar los contactos con compras y estandarizar el formato de teléfono.

---

## R12. Existencias sin historial: una sola foto puntual (Baja)

**Prueba (SELECT 11):**
```sql
SELECT COUNT(DISTINCT exi_fup) AS marcas_de_tiempo, COUNT(*) AS filas FROM exidet
```
**Resultado:** 1 marca de tiempo para 600 filas.

**Impacto:** no hay forma de saber cuándo cambió una existencia ni de auditar ajustes. Tampoco se pueden hacer tendencias de inventario.

**Recomendación para revisión del DBA:** si se requiere trazabilidad, guardar historial de existencias o registrar cada ajuste en `movinv`.

---

## Limitaciones

- `movinv` tiene 44 filas y `ocpcab` tiene 1. Las conclusiones sobre ellas son tentativas.
- No se pudo confirmar si los datos son de producción o de prueba. Varias notas y nombres parecen de muestra.
- Las columnas sin documentar se describen como "supuesto" en el diccionario; los significados deben confirmarse con el negocio.
- Ninguna corrección se aplicó. El acceso es de solo lectura y los scripts son solo para revisión del DBA.
