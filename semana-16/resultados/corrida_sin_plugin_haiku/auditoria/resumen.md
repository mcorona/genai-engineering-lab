# Resumen de auditoría: base de datos heredada `legado`

**Fecha:** 2 de noviembre de 2026
**Alcance:** 9 tablas y vistas, unas 37 mil filas y 46 campos. La revisión fue de solo lectura: no se modificó ningún dato.

## Qué es esta base

Es el registro del sistema anterior de la operación. Contiene el catálogo de artículos y proveedores, las existencias por almacén, los movimientos de inventario, las ventas diarias de los últimos seis meses y los contactos de proveedores. Cubre tres almacenes (Centro, Norte y Occidente).

## Conclusión general

La base sirve para consultar el catálogo, las existencias y las ventas, pero **no es confiable como fuente única para tomar decisiones de inventario ni para proteger datos personales** sin antes corregir algunos puntos. Los problemas son de diseño y de control, no de volumen. Varios pueden causar errores o incidentes si nadie los atiende.

## Hallazgos principales

1. **Datos personales sin protección declarada (prioridad alta).** La tabla de contactos de proveedores guarda nombres, correos, teléfonos y, en 6 de 15 casos, un RFC con formato de persona física. Está en texto plano y sin restricciones documentadas. Puede implicar obligaciones de protección de datos; conviene validarlo con asesoría legal.

2. **Instrucciones escondidas en un campo de notas (prioridad alta).** Dos de las 10 notas contienen texto escrito para que un asistente de inteligencia artificial lo ejecute. No se ejecutó nada, pero cualquier sistema automatizado que lea esas notas podría ser manipulado. Hay que saber quién escribió ese texto y cuándo.

3. **Movimientos de inventario que no se pueden ubicar (prioridad alta).** 6 de 44 movimientos (14 %) apuntan a un artículo o almacén que no existe o no está registrado. Los reportes por producto o por almacén quedarán incompletos.

4. **La base no protege sus propias relaciones (prioridad alta).** Ninguna relación entre tablas está declarada en el sistema. Por eso se aceptaron los errores de los puntos 3 y 5 sin que nadie fuera advertido. Cualquier nueva carga de datos puede repetirlos.

5. **Proveedores y contactos incompletos (prioridad media).** Dos contactos no tienen un proveedor válido. Un correo aparece en dos contactos. Seis teléfonos no tienen código de país.

6. **Unidades de medida mezcladas (prioridad media).** Tres artículos tienen movimientos en piezas, cajas o kilogramos sin conversión. Si se suman, los totales son incorrectos.

7. **Información que nadie documentó (prioridad media).** Ningún campo tiene descripción. Tres campos clave no se pueden interpretar con certeza: el indicador de artículo crítico, el posible punto de reorden y la moneda del costo.

8. **Historial insuficiente (prioridad media).** Los movimientos de inventario cubren solo septiembre de 2026, mientras que las ventas cubren de marzo a septiembre. Las existencias son una sola foto del 27 de septiembre sin historial. No se puede reconstruir el inventario ni auditar ajustes.

## Qué hacer ahora

- **Esta semana:** decidir quién revisa la tabla de contactos y restringir el acceso a los datos personales. Revisar las dos notas con instrucciones escondidas.
- **Próximo mes:** con operaciones, confirmar los 6 movimientos huérfanos y la unidad de medida de los 3 artículos afectados. Documentar el significado de los campos sin definición.
- **Antes de migrar o integrar la base:** definir las relaciones entre tablas y corregir los registros rotos, porque una restricción de integridad fallaría con los datos actuales.

Los cambios sobre los datos deben hacerse por el DBA, con revisión previa. Donde fue posible, la auditoría sugiere la corrección, pero no ejecutó ningún cambio.

## Limitaciones

Algunas tablas tienen muy pocas filas (por ejemplo, una sola orden de compra), así que sus conclusiones son provisionales. No se pudo confirmar si los datos son reales o de prueba. Los detalles técnicos y las consultas de verificación están en `riesgos.md`; el significado de cada campo está en `diccionario.yaml`; el mapa de relaciones está en `relaciones.mmd`.
