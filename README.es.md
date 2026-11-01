# GenAI Engineering Lab

[English](README.md) · **Español**

Ingeniería de GenAI medida y reproducible sobre sistemas de negocio legados: RAG, text-to-SQL, agentes y MCP. Cada resultado está respaldado por una eval con golden set congelado, corre en CI y enlaza al PR que lo verificó. Es el laboratorio del programa "Experto en GenAI para Negocios Internacionales" de Manuel Corona (arquitecto de IA independiente), organizado por semanas (`semana-NN`).

El resumen de capacidades, resultados clave e inicio rápido está en el [README en inglés](README.md). Este documento conserva el registro de los criterios de salida de cada fase, con su evidencia.

## Mapa del repositorio

| Fase | Semanas | Tema |
|---|---|---|
| 1. Fundamentos de LLMs | `semana-01` a `semana-04` | Mini-GPT en MLX, tokens y muestreo, ajustar o no ajustar (LoRA), inferencia local contra API |
| 2. Prompts, evals y NLQ | `semana-05` a `semana-07` | Biblioteca de prompts versionada, evals de regresión en CI, NLQ bilingüe sobre inventario |
| 3. RAG y datos | `semana-08` a `semana-12` | Recuperación, RAG avanzado y multi-tenant, esquema legado y documentos no textuales, evaluación de RAG, RAG administrado en AWS y Google Cloud |
| 4. Agentes y MCP | `semana-13` a `semana-18` | Workflows contra agentes, Claude Agent SDK, servidor MCP remoto con OAuth, multi-agente, confiabilidad |

Cada semana tiene su `README.md` con método, resultados, costo y decisiones; las cifras enlazan a `resultados/`.

## Requisitos

- macOS con Apple Silicon para la Fase 1 (MLX); Linux o macOS para el resto.
- [uv](https://docs.astral.sh/uv/) y Python 3.13; Docker para PostgreSQL con pgvector.
- Las llaves de API nunca están en el repo: se leen de variables de entorno locales y, en CI, de secretos del repositorio.

## Criterio de salida de la Fase 2

Cada semana de la Fase 2 se cierra solo si cumple lo siguiente:

- [x] Los prompts y las evals viven en Git con versión (`semana-05/prompts/`, `semana-06/golden/`).
- [x] Hay una eval automática de regresión (`semana-06/evaluar.py`) que corre en GitHub Actions cuando cambian prompts, evals o `semana-07/`.
- [x] Los cambios de prompt o modelo entran por pull request, no por push directo a `main`, con la protección de rama `ProteccionRama` y el check `regresion` como requisito (verificado con el PR #2).
- [x] La eval de NLQ (semana 7) corre en cada PR, con Haiku sobre el set difícil y una base de CI con datos sintéticos de semilla 42. Verificada en el PR #3 (exactitud 0.953 en español y 1.000 en inglés); umbral 0.90 desde el PR siguiente.
- [x] Cada semana publica sus resultados en su README, con costo y exactitud por modelo.

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Criterio de salida de la Fase 3

La Fase 3 cubre las semanas 8 a 12: recuperación, RAG avanzado, asistente integrado (8 a 10), evaluación de RAG (11) y RAG administrado en la nube (12). Solo se marca lo verificado con evidencia en el repo.

- [x] La eval de recuperación corre en CI en cada PR que toca `semana-08/**` o `semana-09/**`, con umbral de recall@5 por idioma (0.90), calibrado con la primera corrida (ES 0.990, EN 0.950). Verificado en los PR #15 y #17 para semana 8 (`semana-08/resultados/ci_recuperacion.md`) y en el PR #29 para semana 9 (`semana-09/resultados/ci_semana09.md`).
- [x] Hay una comparación documentada de chunking, embeddings y bases vectoriales con recall@k, latencia y costo, en ES y EN (`semana-08/README.md`, actividades 2 a 5; chunking en `semana-08/resultados/chunking.md`, registrado el 2026-10-26).
- [x] La búsqueda híbrida y el reranking se miden contra la línea base. Reranking: nDCG@10 ES 0.904 → 0.982, EN 0.885 → 0.974. Híbrida (BM25 + vectorial con RRF): no mejora recall@5 (ES 1.000 → 0.970, EN 1.000 → 0.770) y no se adopta (`semana-08/resultados/hibrida.md`).
- [x] Las respuestas con citas se evalúan con juez, con exactitud y precisión de citas reportadas (`semana-08/README.md`, actividad 8).
- [x] Las técnicas avanzadas (reescritura, HyDE y contextual retrieval) se miden con el mismo golden set congelado, y se adoptan solo si mejoran. Las tres están medidas; ninguna mejora a la línea base y ninguna se adopta (`semana-09/resultados/comparacion_final.md`; PR #19, #20, #21 y #23).
- [x] Los filtros por tenant y roles se aplican dentro de la consulta en pgvector, Qdrant y OpenSearch, con fuga de permisos igual a 0 y prueba cruzada entre tenants. Criterio no negociable. Verificado con fuga 0 en las tres bases (PR #25 y #26) y con un check de CI que falla ante cualquier fuga en cada PR de semana 9 (PR #29).
- [x] El text-to-SQL sobre un esquema legado (vistas con nombres crípticos) se mide por ejecución en tres variantes (sin diccionario, con diccionario completo y con diccionario recuperado) contra el esquema original con el mismo modelo, con costo y latencia. Verificado con Sonnet 5.5 y Haiku 5.5 sobre el set difícil de semana 7: con Haiku, sin diccionario ES 0.884 / EN 0.953, diccionario completo 0.977 / 1.000 ($0.00033 por pregunta), diccionario recuperado 0.767 / 0.721; esquema original 0.977 / 1.000 (`semana-10/resultados/sql_legado.md`; PR #35 y #37).
- [x] Los documentos no textuales (PDFs con tablas, escaneos con OCR e imágenes) se extraen e indexan, y se mide su exactitud contra la referencia congelada (exactitud por celda, tasa de error por carácter y respuestas correctas) y el recall después de indexar. Verificado: filas íntegras pypdf 0/13, pdfplumber y Haiku 13/13 (PR #38); CER Tesseract 0.009, Haiku 0.001 (PR #39); hechos asociados en imágenes Tesseract 0/7, Haiku 7/7 (PR #40); recall@5 de lo extraído medido en las tres y en CI (1.000 por idioma, PR #44).
- [x] El asistente integrado (NLQ + RAG documental) se mide por tipo de pregunta (SQL, documental, no textual y mixta): ruteo, exactitud con citas, costo y latencia. Su seguridad es no negociable: cero escrituras SQL, fuga 0 por rol y entre tenants a través del asistente, y ninguna instrucción inyectada en documentos ejecutada, con check en CI. Verificado: ruteo ES 0.882 / EN 0.863 (PR #41); exactitud con juez 0.961 / 0.980 frente a 0.294 solo SQL y 0.608 solo documentos, con precisión de citas, costo ($0.00083 por pregunta) y latencia (p50 5.3 s) por tipo (PR #42); con la NLQ endurecida, 0 escrituras, fuga 0 en 128 casos y 0/48 instrucciones obedecidas (PR #43); check `eval-semana-10` en cada PR de semana 10 (PR #44). Las pruebas de seguridad encontraron que la conexión SQL de la actividad 7 permitía escribir objetos grandes (`lo_create`); se corrigió y el asistente usa la NLQ endurecida desde el PR #44 (`semana-10/README.md`).
- [x] La recuperación y la generación se evalúan con suites separadas: recall@k para la recuperación, y faithfulness y answer relevance (RAGAS) para la generación, con costo por consulta. Verificado: suite de recuperación con recall@k, MRR, nDCG@10 y AP@5 (más context precision y recall de RAGAS), que distingue el reranking (AP@5 +0.070 ES / +0.095 EN, IC 95 % sin el 0; PR #51); faithfulness y answer relevancy validadas con fallas conocidas antes de usarlas (PR #52); suite de generación con contextos fijos: exactitud 1.000, faithfulness 0.679 / 0.805, answer relevancy 0.890 / 0.860, abstención correcta 20/20 (PR #53); cada suite se mueve solo con su componente (PR #55); costo por consulta: responder $0.00070 (p50 4.2 s) y evaluar $0.00141, $0.28 por corrida de CI (PR #56); las dos suites corren en CI con umbral, en jobs separados (PR #57) (`semana-11/README.md`).
- [x] La misma base documental se monta en un RAG administrado de AWS (Bedrock Knowledge Bases) y de una segunda nube (Azure AI Search o Vertex AI Search), y se compara su calidad, latencia y costo con el mismo golden set. Verificado con Vertex AI Search como segunda nube: el paquete congelado (SHA-256 por archivo) en 4 KB de Bedrock sobre S3 Vectors y 2 data stores de Vertex, medidos con el golden set de semana 11 (150 preguntas) y el mismo evaluador. Con los chunks propios, Bedrock llega a exactitud 0.985 y Vertex con ranker semántico a MRR 0.977 / 0.962, contra 1.000 del pipeline propio; con la ingesta administrada y el generador común, 0.71 a 0.92 (0.969 con el parser multimodal BDA y RetrieveAndGenerate). Latencia p50 de 1.5 s (RetrieveAndGenerate) a 3.9 s (propio); costo de $0.00027 (Bedrock `Retrieve`) a $0.0012 por consulta (Vertex). Fuga 0 en 672 consultas (PR #59 a #66; `semana-12/README.md`, `semana-12/resultados/comparacion.md`).

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Criterio de salida de la Fase 4

La Fase 4 cubre las semanas 13 a 18: agentes, MCP y orquestación sobre sistemas legados. El programa la cierra con un diseño en pizarra (en 30 minutos, un sistema multiagente con MCP, sus límites de seguridad y cómo se evalúa) y con la certificación CCAR-P. Para verificarla en el repo se usa un criterio por semana más el transversal de seguridad. Solo se marca lo verificado con evidencia.

- [x] **13.** Un flujo de LegacyBridge se implementa en al menos dos patrones (workflow y agente con Claude Agent SDK) y se comparan éxito, costo y latencia con el mismo golden set congelado. Verificado sobre 84 tareas con k = 3, Haiku 5.5 `low` y verificación por ejecución. El workflow (el asistente de semana 10 con ruteo fijo) logra pass@1 0.504, y el agente con Claude Agent SDK 0.889 (+0.385, IC 95 % [0.282, 0.496]); el agente gana en reglas de negocio (+0.806), tareas compuestas (+0.604) y peticiones ambiguas (+0.542), y empata en preguntas directas, donde el workflow es más barato ($0.0004 contra $0.0018 por tarea) y más rápido (p50 3.0 s contra 10.2 s). El agente con loop propio queda como referencia: 0.921, sin diferencia significativa con el SDK (−0.032, IC [−0.071, +0.004]) (`semana-13/resultados/patrones.md`; PR #79 y el de la actividad 10).
- [x] **14.** Servidor MCP remoto con OAuth sobre la base legada de LegacyBridge, con permisos mínimos y pruebas de tool poisoning. Verificado: MCP 2026-07-28 por Streamable HTTP en `127.0.0.1`, Keycloak como servidor de autorización (PKCE S256, audiencia RFC 8707) y el servidor MCP como resource server (metadatos RFC 9728, JWT con JWKS, 401/403 con step-up) (PR #85 a #91). Permisos mínimos en tres capas: scopes, catálogos filtrados por scope y un rol de PostgreSQL por perfil; el hallazgo `art_prv` de la semana 13 queda cerrado. Tool poisoning: con las defensas del cliente (allowlist, pinning por hash, prefijo por servidor, resultados como datos) 38/38 casos, 0 instrucciones obedecidas, 0 escrituras y 0 fugas; sin defensas, el shadowing desvió el 100 % de las consultas (PR #92). El agente de la semana 13 por HTTP + OAuth logra 0.900, igual que por stdio y dentro del intervalo del 0.917 en proceso, con el mismo costo por tarea y +7 ms p50 por llamada; un rol sin el scope termina en negación o abstención en 8/8, sin fugas (PR #93). Claude Code se conecta con OAuth y recibe solo `legado:leer` (PR #94). El check `eval-semana-14` corre en cada PR con Keycloak efímero: 173 pruebas sin API y una mini eval del agente con umbrales ES 0.90 / EN 0.90 y tope de $0.40 por corrida (PR #95). Costo de la semana: $0.92 (`semana-14/README.md`).
- [ ] **15.** El mismo agente en dos frameworks, con una matriz de decisión para clientes.
- [ ] **16.** Un plugin o skill reutilizable para clientes, con su propia eval.
- [ ] **17.** Human-in-the-loop, guardrails y presupuestos de tokens aplicados; eval de trayectorias y tablero de trazas con OpenTelemetry GenAI o Langfuse.
- [ ] **18.** Diseño en pizarra de un sistema multiagente con MCP, sus límites de seguridad y su plan de evaluación, hecho en 30 minutos y versionado; CCAR-P presentado.
- [x] **Transversal (no negociable):** cero escrituras no aprobadas, fuga 0 por rol y entre tenants, y ninguna instrucción inyectada obedecida, con check en CI. Verificado en la semana 13 con 140 corridas: la huella de las tablas no cambia, las propuestas quedan en `PENDING_APPROVAL` sin ejecutarse, hay 0 fugas en 40 corridas (24 por rol y 16 entre tenants) y se obedecieron 0 instrucciones inyectadas en datos SQL y en reglas (PR #80). El check `eval-semana-13` lo exige en cada PR de la semana 13 (PR #81). Se revisa cada semana de la fase y se desmarca si alguna lo rompe. Semana 14: se mantiene sobre el servidor MCP remoto, con 0 escrituras, 0 fugas y 0 instrucciones obedecidas en 38 casos de poisoning, exigidos por `eval-semana-14` en cada PR (PR #92 y #95).

Lo que no cumple el criterio queda marcado como pendiente hasta que se resuelva.

## Estado

- **Fase 1 (semanas 1 a 4): completa.** Mini-GPT en MLX (pérdida de validación 1.72); tokens y variabilidad por idioma; decisión documentada de no ajustar (las reglas en el prompt del modelo de 27B bastan); inferencia local cuantizada contra API (la API es unas 13 veces más rápida en p50).
- **Fase 2 (semanas 5 a 7): completa.** Prompts versionados, evals de regresión en CI con protección de rama, NLQ bilingüe medido por ejecución.
- **Fase 3 (semanas 8 a 12): cerrada.** Los 11 criterios verificados con evidencia. Costo real de la semana 12 según las facturas: AWS $1.50 (cubierto con créditos), Google Cloud MXN 16.64 y Anthropic $4.94 como máximo (`semana-12/resultados/costo_real.md`).
- **Fase 4 (semanas 13 a 18): en curso.** Semana 13 completa (agente con loop propio 0.921 y con Claude Agent SDK 0.889 contra 0.504 del workflow; seguridad 140/140). Semana 14 completa: servidor MCP remoto con OAuth y permisos mínimos, 13/13 amenazas cubiertas, tool poisoning 38/38 con defensas y eval del agente en CI con Keycloak (criterio 14). Siguiente: semana 15.
