# Week 14 data outside the results folder (Spanish data)

[Glossary](../glossary.md) · [Week 14 README](../../semana-14/README.md)

The Spanish data files of week 14 that sit outside a folder with its own README. The recorded runs are described in
[`resultados/README.md`](../../semana-14/resultados/README.md).

`auth/roles_bd.sql` creates one PostgreSQL role per scope profile and grants each one only the legacy views and
columns its scopes allow. The MCP server connects as `copilot_nlq` and switches to the token profile's role in each
transaction, so the database denies what the token does not allow even if the SQL guard fails. `servidor/oauth.py`
(`aplicar_roles_bd`) runs it with the admin role; `seguridad/correr.py` and `tests/test_auth.py` call that function.
Section 1 and the scope matrix in section 2 of the [week 14 README](../../semana-14/README.md) explain the design.

**Why it is in Spanish:** the role names and the legacy schema they grant on are Spanish identifiers. The server, the
permissions file (`auth/permisos_oauth.json`) and the tests refer to them by name, so renaming them would break what
was measured. The comments in the file are in English.

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `auth/roles_bd.sql` | Idempotent SQL: creates the base roles per scope and the profile roles that combine them, grants views and columns, and lets `copilot_nlq` switch only to the profile roles | Run by `servidor/oauth.py` (`aplicar_roles_bd`) with `PG_ADMIN_DSN` |

## Keys

| Key | Meaning |
|---|---|
| `legado_r_leer` | Base role for scope `legado:leer` (read): the warehouse, stock and notes views, and the article view without cost and supplier |
| `legado_r_ventas` | Base role for scope `legado:ventas` (sales): the daily sales view |
| `legado_r_proveedores` | Base role for scope `legado:proveedores` (suppliers): suppliers, purchase orders and the full article view, including cost and supplier |
| `legado_perfil_l`, `legado_perfil_lv`, `legado_perfil_lp`, `legado_perfil_lvp` | Profile roles, one per scope combination: `l` read, `v` sales, `p` suppliers |
| `copilot_nlq` | The server's connection role, which can only switch to the profile roles |
