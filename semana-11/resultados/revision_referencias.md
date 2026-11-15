# Manual review of references (sample of 20, seed 11)

Criterion: the reference answers the question, uses only the passage (or the line of the document that contains it) and adds or changes no data.

Review: Claude (week 11 session), 2026-10-27, against the passage and the source document. **20/20 correct**; 2 add a detail from the same line of the source, verified, and 1 is only the figure.

| # | Id | Language | Question | Passage or exact answer | Reference | Verdict |
|---|---|---|---|---|---|---|
| 1 | int-ocr-08 | es | ¿Quién fue la responsable del inventario físico del CEDIS Norte? | Laura Méndez | Laura Méndez, jefa de almacén, fue la responsable del inventario físico del CEDIS Norte. | Correct. It adds "jefa de almacén" (warehouse manager), which is on the same line of the record (`Responsable: Laura Méndez, jefa de almacén`). |
| 2 | int-ocr-10 | es | ¿Cuántas piezas se remitieron en la nota R-4471? | 120 piezas | 120 piezas | Correct, but only the figure, not a full sentence. Accepted: the judge compares content, not style. |
| 3 | rec-29 | es | ¿Qué debo hacer si el copiloto da una respuesta incorrecta? | Reportar respuestas incorrectas al equipo de datos con la pregunta exacta y la fecha. | Debes reportarla al equipo de datos, indicando la pregunta exacta y la fecha. | Correct. |
| 4 | rec-33 | es | ¿Cuánto tiempo se conservan los videos de vigilancia? | Los videos de vigilancia se conservan **45 días** naturales. | Los videos de vigilancia se conservan **45 días** naturales. | Correct. |
| 5 | int-pdf-05 | es | ¿Qué proveedor de la categoría Seguridad tiene clasificación C? | Seguridad Andina | Seguridad Andina es el proveedor de la categoría Seguridad con clasificación C. | Correct. |
| 6 | rec-38 | es | ¿Cuál es el nivel de servicio objetivo? | El nivel de servicio objetivo es de **97%** de pedidos completos. | El nivel de servicio objetivo es de **97%** de pedidos completos. | Correct. |
| 7 | rec-13 | es | ¿Sobre qué stock se evalúa el punto de reorden? | se evalúa sobre el **stock total**, es decir, la suma de las existencias de los tres CEDIS. | El punto de reorden se evalúa sobre el stock total, es decir, la suma de las existencias de los tres CEDIS. | Correct. |
| 8 | rec-12 | es | ¿Cada cuánto se revisa la categoría Empaque? | la categoría Empaque se revisa **semanalmente** (los lunes) | La categoría Empaque se revisa semanalmente, los lunes. | Correct. |
| 9 | int-pdf-02 | es | ¿Qué recargo tiene el flete exprés sobre la tarifa normal? | 35% | El recargo por flete exprés es del 35% sobre la tarifa normal. | Correct. |
| 10 | int-imagen-12 | es | ¿Qué nivel de servicio tuvo el CEDIS Norte en septiembre de 2026? | 98.6% | El CEDIS Norte tuvo un nivel de servicio de 98.6% en septiembre de 2026. | Correct. |
| 11 | int-imagen-11 | en | What was the lowest service level among the distribution centers in September 2026? | 95.1% | The lowest service level in September 2026 was 95.1%, at CEDIS Occidente. | Correct. It adds "at CEDIS Occidente", which is in the chart (`CEDIS Occidente: 95.1%`). |
| 12 | rec-24 | en | What is the minimum quantity for a transfer between distribution centers? | Cantidad mínima por transferencia: **20 unidades** o una tarima completa, lo que sea menor. | The minimum quantity per transfer is 20 units or one full pallet, whichever is smaller. | Correct. |
| 13 | rec-07 | en | Who approves a purchase order of 120,000 pesos? | De $50,000 a $250,000 MXN \| Gerente de compras | The purchase order of 120,000 MXN falls in the $50,000 to $250,000 MXN range, so it must be approved by the purchasing manager (Gerente de compras). | Correct (in v1 it was a refusal: it read the table row as a salary range). |
| 14 | rec-29 | en | What should I do if the copilot gives a wrong answer? | Reportar respuestas incorrectas al equipo de datos con la pregunta exacta y la fecha. | You should report the incorrect answer to the data team, including the exact question and the date. | Correct. |
| 15 | rec-20 | en | What happens if the receiving difference is 3%? | Diferencia mayor a 2%: se hace un **rechazo parcial** de la diferencia y se notifica al proveedor. | If the receiving difference is greater than 2%, a partial rejection of the difference is made and the supplier is notified. | Correct. It applies the rule (>2%) without repeating the 3% from the question. |
| 16 | rec-10 | en | How is the reorder point calculated? | punto de reorden = demanda diaria promedio × tiempo de entrega del proveedor (días) × factor de seguridad | The reorder point is calculated as: average daily demand × supplier lead time (days) × safety factor. | Correct. |
| 17 | rec-06 | en | How often are class A SKUs counted? | **A:** SKUs críticos y el 20% de SKUs con mayor valor de inventario. Conteo **mensual**. | Class A SKUs are counted monthly. | Correct. |
| 18 | rec-35 | en | What is the maximum height of a pallet? | La altura máxima de una tarima es de **1.20 metros**. | The maximum height of a pallet is 1.20 metres. | Correct. |
| 19 | int-pdf-02 | en | What surcharge does express freight have over the standard rate? | 35% | The express freight surcharge is 35% over the standard rate. | Correct. |
| 20 | rec-45 | en | What is safety stock? | **Stock de seguridad:** existencia adicional para cubrir variaciones de demanda o de entrega. | Safety stock is additional inventory held to cover variations in demand or delivery. | Correct. |
