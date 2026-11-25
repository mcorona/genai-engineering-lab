# Activity 5: resource server with OAuth and least privilege

Code:
- [`servidor/oauth.py`](../servidor/oauth.py)
- [`servidor/http.py`](../servidor/http.py) (the front layer now authorizes)
- [`auth/permisos_oauth.json`](../auth/permisos_oauth.json)
- [`auth/roles_bd.sql`](../auth/roles_bd.sql)

Tests: [`tests/test_auth.py`](../tests/test_auth.py). They make no API calls and cost $0.

```bash
cd semana-14
python -m servidor --transporte http --oauth --trazas resultados/trazas/oauth.jsonl   # Keycloak on 8180 + copilot-db
```

## How a request flows

1. **Front layer:**
   - POST only, size limit and header checks (activity 3).
   - Then `Autorizador`, which runs **before the SDK**: it validates the JWT, works out the scopes the operation needs **from the body** (tool, resource or prompt) and answers:
     - **401** when the token is missing or invalid: `WWW-Authenticate: Bearer [error="invalid_token"], scope="legado:leer", resource_metadata="…/.well-known/oauth-protected-resource/mcp"`.
     - **403** when a scope is missing: `error="insufficient_scope", scope="<all scopes the operation needs>"`. The client can do step-up with a single challenge.
2. **SDK:** a second validation of the same token (`TokenVerifier`, `validate_token_resource`) and **Protected Resource Metadata** (RFC 9728): `resource` set to the server URI, `authorization_servers` set to Keycloak, `scopes_supported: ["legado:leer"]` (the minimum set, as the specification asks).
3. **Handler:** `fabrica_oauth` builds the `ContextoOAuth` from the validated token (`sub`, `scopes`, `azp`).
   - Tools, tables, columns and prompts come from the scopes.
   - The arguments can never change the user or the permissions.
4. **Database:** each query takes its own connection from the pool and runs `SET LOCAL ROLE` to the profile's role:

   | Scopes | PostgreSQL role |
   |---|---|
   | `leer` | `legado_perfil_l` |
   | `leer` + `ventas` | `legado_perfil_lv` |
   | `leer` + `proveedores` | `legado_perfil_lp` |
   | `leer` + `ventas` + `proveedores` | `legado_perfil_lvp` |

   - The basic read role (`legado_r_leer`) reads `artmst` **only through its non-sensitive columns**. `art_prv` (supplier FK) and `art_cst` (cost) belong to `legado_r_proveedores`.
   - The transaction stays `READ ONLY` and is always rolled back.

## JWT validation (`VerificadorJWT`)

| Check | How |
|---|---|
| Signature | JWKS from the issuer (`PyJWKClient`) with a 300 s key cache. An unknown `kid` is rejected, and the 30 s cooldown keeps an attacker from forcing repeated JWKS downloads |
| Algorithm | Fixed to `RS256`. The header is checked **before** looking up a key, so `none`, HS256 signed with the public key (HS/RS confusion) and any other algorithm are rejected |
| Claims | Exact `iss`, `aud` containing the server URI, `exp` with a 30 s margin. `exp`, `iat`, `iss`, `aud` and `sub` are required |
| Token type | Only `typ: Bearer`. ID tokens and refresh tokens are rejected |
| Never | In the query string (SDK), forwarded to the database or another service, or written to the traces |

## Least privilege by profile (tokens issued by Keycloak in activity 4)

| | analista | almacenista | vendedor |
|---|---|---|---|
| Tools in `tools/list` | 6 | 5 (no `proponer_orden_compra`) | 5 |
| Views (resources) | all 7 | `artmst`, `almmst`, `exidet`, `artnot` | those four + `vtadia` |
| `art_prv` and `art_cst` in `legado://esquema/artmst` | yes | **no** | **no** |
| Prompts | 2 | `analizar_exceso_inventario` | `analizar_exceso_inventario` |
| Database role | `legado_perfil_lvp` | `legado_perfil_l` | `legado_perfil_lv` |

## Tests (`tests/test_auth.py`, 43)

| Group | Cases |
|---|---|
| RFC 9728 and 401 | Metadata. Missing token: 401 with `scope` and `resource_metadata` |
| Invalid tokens (401) | Expired; another issuer; another audience (including `aud=legado-mcp`, which is what Keycloak issues if the client leaves out `resource`); altered signature (scopes raised in the payload); `alg=none`; HS256 with the public key; no `aud`; foreign `aud` in a list; unknown `kid`; another key with the same `kid`; ID token; no `sub`; no `exp`; garbage; `Basic` scheme; token in the query string |
| JWKS cache | 25 tokens lead to 1 download, and 10 tokens with an invented `kid` lead to no new download |
| Insufficient scope (403) | No `legado:leer`, and an empty scope set: 403 with `scope="legado:leer"`. `proponer_orden_compra` without `legado:compras:proponer`: 403 with both scopes. Analista with the scope: proposal in `PENDING_APPROVAL` |
| Tool not listed | `almacenista` does not see `proponer_orden_compra`, and calling it gets 403. An unknown tool gets a structured `herramienta_desconocida`. If the front layer were skipped, the handler still does not run it |
| Filtered lists (SDK client with the token) | Tools, views, `artmst` columns and prompts per profile, matching the table above. `resources/read` of `prvmst` by vendedor: 403 `legado:proveedores`. `prompts/get proponer_reabasto`: 403 |
| Privilege escalation through arguments (12 cases) | `usuario`, `roles` or `scope` passed as arguments: `argumentos_invalidos`. Plus: `prvmst` in `describir_esquema`; `art_prv` in `muestrear_valores`; `art_prv`, `"ART_PRV"`, `a.*`, a join to `prvmst`, `legado.prvmst`; `SET ROLE`; `set_config('role', …)`. All are rejected |
| The token stays in the server | A spy on `Herramientas.llamar` sees neither the token nor its signature. Traces carry `sujeto`, `scopes` and `cliente_oauth`, but no token and no `Bearer` |
| Database (A05) | `SET LOCAL ROLE` per profile, and the role does not carry over to the next transaction. The database denies `art_prv`, `art_cst`, `row_to_json(a)` and `prvmst` to `legado_perfil_l` and `legado_perfil_lv`, and allows them to `legado_perfil_lvp`. Allowed queries return results |
| End to end with Keycloak | Real tokens from the 3 users (PKCE + `resource`): 6 / 5 / 5 tools. A token without `resource` got 401 (since activity 7 it gets 200: the client's audience mapper emits the canonical URI, see [`claude_code.md`](claude_code.md)). Almacenista calling `proponer_orden_compra` gets 403 |

| Environment | Result |
|---|---|
| Cloud container with the legacy database (no Keycloak) | `semana-14` **100 passed**, 28 skipped (18 Keycloak tests + 1 end-to-end + 9 matrix rows still `planned`) |
| VM with Keycloak 26.8.1 (no database) | `semana-14` **112 passed**, 16 skipped (the database tests + matrix rows). `test_keycloak` + `test_auth`: 58 passed |
| `semana-13` with the database (no regression) | 106 passed, 1 skipped |
| `verificar_sdk.py` | 24/24 |

On the Mac, with Keycloak and `copilot-db` running, the expected result is **119 passed and 9 skipped** (only the matrix rows that activity 6 covers).

Threat matrix:
- **Now `covered`:** A06 (token passthrough), A07 (token theft and wrong audience), A08 (DNS rebinding, which needed authentication on every request) and A11.
- **Still `planned`:** A05, A09 and A10. They also cite the agent suite from activity 6.

## Findings

1. **The week 13 guard could be bypassed with `row_to_json`.** `SELECT row_to_json(a) FROM artmst a` names no columns and uses no `*`, so the guard (sqlglot) let it through. With the week 13 connection role (`copilot_nlq`, SELECT on every column), a profile without access to costs could read `art_cst` and `art_prv` in the JSON. With the per-profile roles the database denies it (`permission denied for view artmst`), and `test_fk_art_prv_sin_scope_proveedores` checks it through the full server. This is defense in depth catching a real hole in the first layer.
2. **The `art_prv` finding from week 13 is closed** at three layers: column permission in the context (no longer shown in the schema), the guard and the database (column privileges on the view).
3. **PyJWT 2.14 only accepts http(s) for the JWKS.** It rejects `file://` and other schemes to avoid a `jku`-style SSRF. The tests serve the JWKS over HTTP on loopback.
4. **The SDK's 401 and 403 challenges do not carry `scope`.** The front layer now emits them as the specification asks (SHOULD), with every scope the operation needs in a single challenge.
5. **The failure reason is not returned to the client.** Whatever the cause (expired, issuer, signature, audience…), the 401 says only "invalid or expired", so the response does not help anyone forge tokens. The detail stays inside the server.
