# Activity 2: MCP primitives (tools, resources, prompts)

Code: [`servidor/primitivas.py`](../servidor/primitivas.py) and [`servidor/salidas.py`](../servidor/salidas.py). Tests: [`tests/test_primitivas.py`](../tests/test_primitivas.py). Everything runs through an in-memory MCP client (`mcp.Client(server)`) on protocol 2026-07-28. No API calls, $0.

The server reuses the week 13 implementation (`Herramientas.llamar`) unchanged: guard, permissions, limits and structured errors are the same, and nothing is duplicated. The user, and therefore the permissions, is set by whoever creates the server through `crear_servidor(fabrica)`, never by the model. In this activity the user is fixed per process; in activity 5 it comes from each request's OAuth token.

## Tools

The six week 13 tools keep the same `name`, `description` and `inputSchema` (`test_catalogo_igual_a_semana13`). Each one adds:
- **`title`**.
- **`outputSchema`:** `{"type": "object", "anyOf": [success, error]}`.
  - Both branches have `additionalProperties: false`.
  - Every `$ref` is resolved inline.
  - The schema is valid Draft 2020-12.
  - It is generated from Pydantic models, which are the same ones that validate the outputs in the tests.
- **`structuredContent`:** exactly the week 13 output. `content[0].text` carries the same serialized JSON.
- **`isError`:** `not ok`.
- **`_meta`:** `io.legacybridge/untrusted: true` and `io.legacybridge/source: legado.<tool>` on every result, success or error (threat A04).

| Tool | `readOnlyHint` | `destructiveHint` | `idempotentHint` | `openWorldHint` |
|---|---|---|---|---|
| `describir_esquema`, `buscar_regla_negocio`, `muestrear_valores`, `validar_sql`, `ejecutar_sql` | true | false | true | false |
| `proponer_orden_compra` | **false** | false | false | false |

`proponer_orden_compra` writes nothing to the database. It does record a proposal, which is server state, and it is not idempotent. Declaring it `readOnlyHint: true` would be false, so a client could skip the confirmation. Its contract only allows `estado: "PENDING_APPROVAL"` and `ejecutada: false`, both as `const` (`test_herramientas_solo_lectura`, A10).

**Equivalence with week 13:**
- **Coverage:** 18 cases without a database and 17 with one (legacy CI database), for each of the 3 users (`analista`, `almacenista`, `vendedor`).
- **Cases:** valid and invalid arguments, permission denied, writes and `lo_create` blocked, the other tenant's table, a timeout (`pg_sleep`), 0 rows, truncation, a proposal with an unknown SKU, and an unknown tool.
- **Checks:** `structuredContent` equals the native output, and every output passes both `jsonschema` against the published `outputSchema` and the Pydantic model.

## Resources

| URI | Content | `cacheScope` / `ttlMs` |
|---|---|---|
| `legado://manifiesto` | SHA-256 of each tool as `tools/list` serves it (canonical JSON without `_meta`) and of the whole catalog | public / 300000 |
| `legado://esquema/{vista}` (template) | `describir_esquema` for that view: only the columns visible to the user, plus the data dictionary and the original name | private / 60000 |
| `legado://reglas/{id}` (template) | One of the 15 rules: name and definition in Spanish and English, plus its source | public / 300000 |

**Listing:**
- `resources/list` returns the manifest, the views the user can see (`analista` 7, `almacenista` 4, `vendedor` 5) and the 15 rules. It is private, because it depends on the user.
- `resources/templates/list` returns both templates.

**Errors:** an unknown URI, another scheme (`file://`), a view that exists but the user cannot see, and a rule that does not exist all get the same error, `-32602` "not found". The goal is that a user cannot use the error to discover what exists for other roles. The 2026-07-28 specification uses `-32602` for a missing resource.

**Manifest catalog** (version 0.2.0): `d8184b6e…c4f658028`. `test_manifiesto_coincide_con_tools_list` checks that:
- The hashes match what the client actually receives.
- Adding text to a description, or changing `additionalProperties` in a schema, changes the hash. This is the rug pull defense for activity 6.

## Prompts

| Prompt | Arguments (validated) | Declared tools | Users who see it |
|---|---|---|---|
| `analizar_exceso_inventario` | `linea` (optional, letters only, ≤30), `max_skus` (1–50, default 10) | `buscar_regla_negocio`, `describir_esquema`, `muestrear_valores`, `ejecutar_sql` | analista, almacenista, vendedor |
| `proponer_reabasto` | `sku` (required, `^SKU-\d{4}$`) | `buscar_regla_negocio`, `describir_esquema`, `ejecutar_sql`, `proponer_orden_compra` | analista only (purchasing role and `art_cst`) |

**Declarations and permissions:**
- Each template declares its tools, tables and columns.
- A user sees a template only if it has permission for everything the template declares. Otherwise the template does not appear in `prompts/list`, and `prompts/get` returns `-32602`.
- The text, in Spanish or English according to the context, mentions only declared tools and tables, all of them permitted for the user (`test_prompts_solo_usan_herramientas_permitidas`, 3 users × 2 languages).

**Argument validation:**
- Arguments are validated with Pydantic (`extra="forbid"`) before they are interpolated, so injection through an argument (a line break followed by instructions, or SQL in `linea`) gets `-32602`.
- `analizar_exceso_inventario` is read-only and does not mention `proponer_orden_compra`.
- `proponer_reabasto` registers a proposal only if the SKU meets R-PROPUESTA, and states that it stays in PENDING_APPROVAL.

## Results

| Run | Result |
|---|---|
| `pytest semana-14/tests` without a database | 37 passed, 16 skipped (3 tests need the database; 13 are threat rows still `planned`) |
| `pytest semana-14/tests` with the legacy database | **40 passed**, 13 skipped (the `planned` rows) |
| `pytest semana-13/tests` with a database (no regression) | 106 passed, 1 skipped |

The `eval-semana-14` workflow now starts PostgreSQL with the legacy schema, so equivalence with the database runs on every PR, still without API calls.

## Findings
- **Errors from the in-memory client:** the SDK client runs inside an anyio task group, so a protocol error (`MCPError`) arrives wrapped in an `ExceptionGroup`. The test helper unwraps it.
- **Manifest hashes depend on how the SDK serializes:** they come from `Tool.model_dump(by_alias, exclude_none)`. An SDK upgrade that changes serialization changes the hashes. That is the desired behavior (it forces a re-approval), and it is documented in the manifest itself (`canonicalizacion`).
- **`art_prv` is still visible:** `almacenista` still sees `artmst.art_prv` in `legado://esquema/artmst`, the same as in `describir_esquema`. Activity 5 closes this with scopes and column permissions that include foreign keys (A05).
