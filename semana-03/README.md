# Semana 3 · Adaptación: ¿ajustar o no ajustar?

Tarea: pasar una pregunta en español a SQL sobre el esquema legado de LegacyBridge (PostgreSQL 16) y comprobar si conviene ajustar un modelo (LoRA) o si bastan el prompt o RAG.

**Regla de decisión:** si prompt o RAG bastan, no ajustar. Documentar la decisión.

**Decisión:** no ajustar. Con el modelo de 27B, las reglas en el prompt bastan. Ver [Decisión](#decisión).

## Datos

- 229 candidatos generados desde 19 plantillas sobre el esquema legado (`generar_pares.py`).
- 220 aceptados: cada SQL se ejecuta en PostgreSQL con el rol `lb_reader`, en transacción de solo lectura y con `statement_timeout` de 5 s.
- 9 rechazados por error de ejecución (`data/rechazados.jsonl`).
- 0 coincidencias con el golden set de LegacyBridge (`evals/golden_set.yaml`, 80 casos, solo lectura). Esos casos se excluyen de los pares.
- División 80/20 por plantilla con semilla 42: **174 de entrenamiento** (`data/pares_train.jsonl`) y **46 de evaluación** (`data/pares_eval.jsonl`). La evaluación nunca entra al entrenamiento.
- Entrenamiento LoRA: 157 pares de entrenamiento y 17 de validación (`data/lora/`), generados por `preparar_lora.py`.

Las reglas de negocio que el modelo debe aplicar están en `reglas_legado.md` (12 reglas tomadas de `docs/legacy-defects.md`: vigentes, montos como texto, fechas CHAR(8), moneda y agente, líneas de factura, clientes y productos activos, existencia actual, costo con coma decimal, movimientos).

## Métodos

| Método | Modelo | Configuración |
|---|---|---|
| 27B base | Qwen3.8-27B MLX 4 bits (LM Studio) | temperature 0, razonamiento permitido, `max_tokens` 8192, se toma solo `content` |
| 7B base | Qwen2.5-Coder-7B-Instruct MLX 4 bits | temperature 0, `max_tokens` 8192 |
| 7B + LoRA v1 | Qwen2.5-Coder-7B + adaptador | mlx-lm, LoRA, 16 capas, lr 1e-5, batch 2, 300 iteraciones, `--mask-prompt`, longitud máxima 2048 |
| 7B + reglas en prompt | Qwen2.5-Coder-7B | las 12 reglas completas en el prompt de sistema (`--reglas`) |
| 27B + reglas en prompt | Qwen3.8-27B | temperature 0, `max_tokens` 8192, las 12 reglas completas en el prompt (`--reglas`) |
| 27B + RAG-lite | Qwen3.8-27B | temperature 0, `max_tokens` 8192, solo las reglas relevantes por pregunta (`--rag`, `rag_reglas.py`) |

El LoRA con lr 1e-4 quedó en NaN desde la iteración ~40. Se descartó y se reentrenó con lr 1e-5, que convergió (pérdida de validación 0.007).

## Métricas

- **Ejecuta:** la consulta corre en PostgreSQL sin error.
- **Coincide en resultado:** las filas devueltas son iguales a las de la referencia. Se ignora el orden y se normalizan montos con `$` y comas, coma decimal y códigos con ceros a la izquierda tratados como texto. Es la métrica principal.
- **Coincide en SQL (exact match):** reportada, pero muy baja (0 a 9 %) porque hay muchas consultas equivalentes. No se usa para decidir.
- **Intervalo de confianza:** Wilson al 95 % (`estadistica.py`).
- **Comparación pareada:** McNemar exacto sobre los mismos 46 pares.

## Resultados

Conjunto de evaluación: 46 pares. Métrica principal: coincide en resultado.

| Método | Ejecuta | Coincide en resultado [IC 95 %] |
|---|---|---|
| Qwen3.8-27B base | 73.9 % | 45.7 % [32.2, 59.8] |
| Qwen3.8-27B + reglas en prompt | 69.6 % | **50.0 %** [36.1, 63.9] |
| Qwen3.8-27B + RAG-lite | 58.7 % | 41.3 % [28.3, 55.7] |
| Qwen2.5-Coder-7B base | 80.4 % | 37.0 % [24.5, 51.4] |
| Qwen2.5-Coder-7B + LoRA v1 | 84.8 % | 37.0 % [24.5, 51.4] |
| Qwen2.5-Coder-7B + reglas en prompt | 54.3 % | 28.3 % [17.3, 42.5] |

Pruebas pareadas (McNemar, coincide en resultado):

- 7B base contra 7B + LoRA v1: los dos aciertan exactamente los mismos casos (0 discordantes), p = 1.000. El LoRA no cambia la coincidencia.
- 27B base contra 27B + reglas en prompt: 5 casos solo del base, 7 solo de las reglas, p = 0.774. No significativa.
- 27B base contra 27B + RAG-lite: 7 casos solo del base, 5 solo de RAG, p = 0.774. No significativa.
- 27B + reglas contra 27B + RAG-lite: 7 casos solo de reglas, 3 solo de RAG, p = 0.344. No significativa.
- 27B base contra 7B base: solo el 27B acierta 5 casos y solo el 7B acierta 1, p = 0.219. No significativa.

## Antes y después

Mismos 46 pares de evaluación, misma métrica. Cada cambio se mide contra su línea base del mismo modelo.

**Ajuste (LoRA), en el 7B**

| Métrica | Antes: 7B base | Después: 7B + LoRA v1 | Cambio |
|---|---|---|---|
| Ejecuta | 80.4 % (37/46) | 84.8 % (39/46) | +2 casos |
| Coincide en resultado | 37.0 % (17/46) | 37.0 % (17/46) | 0 |
| Exact match (SQL) | 0.0 % | 0.0 % | 0 |

Los mismos 17 casos aciertan antes y después (McNemar p = 1.000). El ajuste cambia la sintaxis, no el resultado.

**Prompt con reglas, en el 27B**

| Métrica | Antes: 27B base | Después: 27B + reglas | Cambio |
|---|---|---|---|
| Ejecuta | 73.9 % (34/46) | 69.6 % (32/46) | −2 casos |
| Coincide en resultado | 45.7 % (21/46) | 50.0 % (23/46) | +2 casos |
| Exact match (SQL) | 0.0 % | 0.0 % | 0 |

El cambio no es significativo (McNemar p = 0.774). Las reglas mejoran el resultado sin mejorar la sintaxis.

**RAG-lite, en el 27B** (referencia, no se adopta)

| Métrica | Antes: 27B base | Después: 27B + RAG-lite | Cambio |
|---|---|---|---|
| Ejecuta | 73.9 % (34/46) | 58.7 % (27/46) | −7 casos |
| Coincide en resultado | 45.7 % (21/46) | 41.3 % (19/46) | −2 casos |
| Exact match (SQL) | 0.0 % | 6.5 % (3/46) | +3 casos |

El exact match sube solo con RAG, pero el resultado baja. Es una señal de que el modelo escribe SQL distinto sin acertar el contenido. No se adopta.

**Referencia: 7B con reglas en el prompt**

| Métrica | Antes: 7B base | Después: 7B + reglas | Cambio |
|---|---|---|---|
| Ejecuta | 80.4 % (37/46) | 54.3 % (25/46) | −12 casos |
| Coincide en resultado | 37.0 % (17/46) | 28.3 % (13/46) | −4 casos |
| Exact match (SQL) | 0.0 % | 8.7 % (4/46) | +4 casos |

Un prompt largo confunde al 7B: copia fragmentos de SQL de las reglas y eso se refleja en ejecución y en resultado.

## Lectura

- **El LoRA v1 aprende el formato, no las reglas.** Ejecuta más (80.4 % a 84.8 %), pero acierta exactamente los mismos casos que el base.
- **Las reglas en el prompt empeoran al 7B.** Ejecuta 54 %: copia fragmentos de SQL de las reglas (por ejemplo `COUNT(DISTINCT ON ...)`) e inventa columnas. Un prompt largo con fragmentos confunde a este modelo.
- **El 27B con reglas en el prompt es el mejor método medido** (50.0 %), pero frente al 27B base (45.7 %) la diferencia no es significativa.
- **RAG-lite no mejora al base** (41.3 %). Seleccionar reglas por palabras clave pierde contexto que el modelo sí usa cuando recibe todas.
- **Las reglas en el prompt ayudan al 27B y dañan al 7B.** El modelo grande las usa; el pequeño copia fragmentos de SQL y se equivoca.

## Decisión

**No ajustar.** Para este esquema y este modelo, el prompt basta.

- El 27B con las reglas completas en el prompt iguala y supera ligeramente al base (50.0 % contra 45.7 %). Ninguna diferencia es significativa, pero el prompt no empeora el resultado.
- El LoRA v1 no mejora la coincidencia en el 7B: aciertan los mismos casos que el base del 7B.
- RAG-lite no basta: queda por debajo de las reglas completas (p = 0.344) y no mejora al base.

Limitación de la comparación: el ajuste se probó en el 7B, no en el 27B. Con 46 pares no hay poder para detectar diferencias de 5 a 10 puntos. La conclusión es que no hay evidencia de que el ajuste aporte, y que el prompt en el modelo grande alcanza el nivel del base sin entrenar nada.

Método recomendado para este caso: 27B con las reglas en el prompt (`--reglas`).

## Limitaciones

- **Solapamiento de datos.** Entrenamiento y evaluación comparten clientes, facturas y artículos. La prueba mide aplicar reglas sobre registros conocidos, no generalizar a registros nuevos.
- **Muestra pequeña.** Con n = 46 los intervalos miden unos ±14 puntos. Diferencias de 1 a 3 casos no son evidencia.
- **Métrica estricta.** Columnas extra (por ejemplo `clave`) y top-1 frente a ranking cuentan como fallo. La normalización numérica no cambió ningún resultado (`--reevaluar`), así que los fallos son de contenido, no de formato.
- **Exact match no informativa** para SQL equivalente.
- **Razonamiento del 27B.** Si el modelo agota los 8192 tokens sin producir SQL, cuenta como fallo. Revisar `finish_reason` en `resultados/*_detalle.jsonl`.
- **Corridas descartadas, se conservan para trazabilidad:**
  - `sin_razonamiento_roto_base_*`: corrida con `/no_think` y 1024 tokens. 28 de 46 casos sin SQL. Descartada.
  - `prueba_*`: pruebas de 3 pares. Están en `.gitignore`.

## Cómo correrlo

Requiere LM Studio en `http://localhost:1234/v1` con el modelo 27B cargado, la base de LegacyBridge arriba (`legacybridge2-db`) y `~/legacybridge-v2/.env` con `LB_READER_PASSWORD`.

```bash
cd ~/AI-projects-llm-internals
set -a; source ~/legacybridge-v2/.env; set +a

# Corridas del 27B
uv run python semana-03/evaluar_sql.py --nombre base27b_reglas --reglas
uv run python semana-03/evaluar_sql.py --nombre base27b_rag --rag

# Intervalos y comparación pareada
uv run python semana-03/estadistica.py base base27b_reglas base27b_rag --comparar base base27b_reglas
```

Para el 7B con LoRA, levantar el servidor con el adaptador en otro puerto:

```bash
mlx_lm.server --model $HOME/.lmstudio/models/lmstudio-community/Qwen2.5-Coder-7B-Instruct-MLX-4bit \
  --adapter-path semana-03/adapters/qwen7b-sql --port 8081
uv run python semana-03/evaluar_sql.py --nombre lora7b --base-url http://localhost:8081/v1 \
  --modelo "$HOME/.lmstudio/models/lmstudio-community/Qwen2.5-Coder-7B-Instruct-MLX-4bit"
```

Los resultados ya calculados no requieren modelo; `--reevaluar NOMBRE` recalcula las métricas desde el detalle.

## Archivos

- `generar_pares.py`: plantillas, validación en PostgreSQL y división 80/20.
- `preparar_lora.py`: formato de entrenamiento para mlx-lm.
- `evaluar_sql.py`: genera SQL y compara ejecución y resultado. Opciones `--reglas`, `--rag`, `--reevaluar`.
- `rag_reglas.py`: selección de reglas por palabras clave.
- `estadistica.py`: intervalos de Wilson y McNemar.
- `reglas_legado.md`: reglas de negocio que el modelo debe aplicar.
- `data/`: pares de entrenamiento, evaluación y rechazados, y resumen.
- `resultados/`: detalle y resumen de cada corrida.
- `adapters/`: pesos del LoRA. **Ignorado por git**, se regenera con `mlx_lm.lora`.
