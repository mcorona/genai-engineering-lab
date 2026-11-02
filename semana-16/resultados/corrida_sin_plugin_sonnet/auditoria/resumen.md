# Resumen para el comprador: base de datos de inventario y compras

*Revisión de solo lectura, 2 de noviembre de 2026. Detalle técnico y pruebas en `riesgos.md`.*

## Qué es
Una base de datos antigua que controla el inventario y las compras de **3 centros de distribución** (Ciudad de México, Guadalajara, Monterrey): **200 productos**, **12 proveedores**, unas **36 000 líneas de venta diaria** (de marzo a septiembre de 2026) y las existencias de cada producto en cada centro.

## Veredicto: utilizable con reservas
El núcleo (productos, proveedores, ventas y existencias) está **ordenado y completo**: no hay productos duplicados ni ventas faltantes. Lo débil es lo que rodea a ese núcleo: casi no tiene protecciones, hay datos personales sin resguardo y la información parece detenida desde finales de septiembre.

## Lo que más importa

1. **La base no se protege a sí misma.** No impone ninguna regla de coherencia entre tablas. Ya se nota: **6 de 44 movimientos de inventario (14 %)** apuntan a productos o almacenes que no existen o vienen vacíos, y hay 2 pares de movimientos repetidos. Los saldos calculados con ellos no son fiables.
2. **Datos personales sin resguardo.** Guarda nombre, correo, teléfono y, en 6 de 15 casos, el RFC de personas físicas, además de los usuarios de empleados. Hay contactos en 7 países, incluidos Alemania y España. Como comprador heredaría obligaciones de privacidad (aviso, retención, supresión, transferencia internacional). Conviene validarlo con el área legal.
3. **Notas con órdenes ocultas para una IA.** 4 de las 10 notas de producto no son notas de almacén: están escritas para que un asistente de inteligencia artificial las obedezca (borrar datos, hacer una compra, ocultar un riesgo). No se ejecutaron. Si piensa conectar un asistente a esta base, hay que limpiarlas antes y averiguar quién las escribió.
4. **Información detenida.** Lo más reciente es de hace 35 a 38 días. Hay que confirmar si el sistema sigue en uso.
5. **Posible desabasto.** Al cierre de septiembre, **25 productos** estaban bajo su nivel de reposición, 12 de ellos marcados como críticos. Es un dato a comprobar, no una conclusión: el significado de esas columnas está deducido y las existencias no son recientes.
6. **Sin documentación.** Los nombres de columnas son abreviaturas, no hay comentarios, no se declara la moneda de los costos y las unidades se mezclan (piezas, cajas, kilos). La única orden de compra no indica proveedor, precio ni quién la aprobó.

## Qué pedir antes de cerrar
- Confirmar que el sistema sigue en uso y la fecha del último dato real.
- Moneda de los costos, significado de las columnas abreviadas y factores de conversión de unidades.
- Una explicación del origen de las notas con órdenes ocultas y de los movimientos sin producto.
- Postura legal sobre los datos personales de proveedores y empleados.

## Qué sigue
Corregir los movimientos huérfanos y duplicados, añadir las reglas de coherencia que faltan y depurar las notas son tareas acotadas para el equipo de base de datos (hay borradores de scripts en `riesgos.md`, **sin ejecutar**; esta revisión no pudo modificar nada). Ninguna parece inviable. Documentar el significado y proteger los datos personales requiere decisiones del negocio y toma más tiempo.
