# Resumen de la auditoría de la base legada

Fecha: 2026-11-02

## Qué se revisó

Se revisaron los 10 objetos de la base legada: 3 tablas y 7 vistas. El foco fue la tabla de contactos de proveedores (`prvcto`) y la de movimientos de inventario (`movinv`). Se revisó sin modificar nada: la auditoría solo tuvo acceso de lectura.

## Los riesgos que más importan

1. **Datos personales sin protección visible.** La tabla de contactos de proveedores guarda nombre, correo, teléfono y, en 6 casos, el RFC de personas físicas. Los registros de inventario guardan el usuario que los hizo. No hay restricciones de acceso ni documentación de cómo se tratan.

2. **Textos escritos para manipular herramientas de IA.** Hay notas, comentarios y nombres de objetos que contienen instrucciones dirigidas a un asistente de IA. Algunas piden ocultar datos, consultar otra parte de la base o borrar registros. Ninguna de esas instrucciones se ejecutó. Hay que averiguar quién las escribió y limpiarlas, porque cualquier herramienta de IA que lea la base puede ser engañada por ellas.

3. **Movimientos de inventario que no cuadran.** Hay 2 movimientos con un código de producto que no existe en el catálogo, 1 con un almacén inexistente y 3 sin producto o sin almacén. Esto afecta la exactitud del inventario por producto y por almacén.

4. **Posibles registros duplicados.** Hay dos pares de movimientos idénticos en todo salvo el número de registro. Si son errores, el inventario está sobrestimado o subestimado; si son reales, no hay problema. Hace falta revisar los documentos de origen.

5. **Totales que mezclan unidades.** La cantidad de los movimientos se registra en piezas, cajas y kilos sin distinción. Un total por unidad, como las 1281 piezas, puede ser incorrecto.

## Lo que está sano

- Las existencias por almacén (600 registros) no tienen códigos de producto ni de almacén inexistentes.
- Las ventas diarias (36 000 registros) y las notas de producto apuntan a productos existentes.
- Los maestros de productos, proveedores y almacenes están completos, sin valores vacíos en sus identificadores.
- Ningún producto apunta a un proveedor inexistente.

## Próximos pasos recomendados

1. Revisar con el DBA los textos dirigidos a una IA y los objetos que los contienen. Averiguar quién los creó y cuándo.
2. Definir quién puede ver los datos de contacto y el RFC, y decidir si se enmascaran para uso general.
3. Revisar con el área de inventario los movimientos señalados (sin producto, sin almacén, duplicados y en unidades distintas) contra los documentos de origen. Cualquier corrección la aplica el DBA después de esa revisión.
4. Confirmar el significado de los campos sin documentación antes de construir reportes sobre ellos.
5. Documentar las relaciones entre tablas. Hoy la base no tiene claves foráneas, así que la integridad depende de la disciplina de quien captura los datos.

## Alcance y límites

- Solo lectura. No se modificó ningún dato.
- Los nombres y significados de los campos son inferidos a partir de los datos. Donde no hay documentación, se indica.
- Algunos comentarios de la base solo se pudieron leer desde la herramienta de metadatos, no con consultas. Se describen como pendientes de confirmación.
- No se incluyen valores de datos personales en este documento; solo conteos e identificadores de registro.
