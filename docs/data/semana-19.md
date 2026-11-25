# Week 19 data (Spanish data and recorded evidence)

[Glossary](../glossary.md) · [Week 19 README](../../semana-19/README.md)

Week 19's data and evidence files outside the folders that have their own README
([`resultados/`](../../semana-19/resultados/README.md) and [`seguridad/kb_envenenados/`](../../semana-19/seguridad/kb_envenenados/README.md)).
They are of two kinds:

- **The loader's data** (`infra/loader/`). The loader is a one-shot Lambda function that runs inside the VPC and
  loads the lab database: the inventory schema, the seed-42 data, the legacy views and the article-notes table, and
  the database roles. It can also upload the legacy data dictionary to the Knowledge Base's bucket, one document per
  view. The folder has no README of its own: the whole folder is the loader's Lambda asset
  (`Code.from_asset` in `infra/cdk/app.py`), so any file added there is deployed with it.
- **The CDK synth snapshots** (`tests/snapshots/`), which the infrastructure tests compare against a fresh synth.

**Why it is in Spanish:** the loader creates the Spanish legacy schema that the lab measures (cryptic view names, a
Spanish data dictionary, and article notes with injected instructions in Spanish and English). `legado.sql` and
`artnot.sql` are byte-for-byte copies of their week 10 and week 13 sources, and a test checks it. Translating them would change the
database the agent was measured on.

**Recorded evidence:** the snapshots are the recorded output of `cdk synth`, kept as written: not edited, not
translated. Their Spanish names are the stacks' logical IDs. They are rewritten only by running the tests with
`S19_REGENERAR=1` after an intended change. The English description of the stacks is in the
[week 19 README](../../semana-19/README.md#detailed-architecture).

## Files

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `infra/loader/legado.sql` | The legacy schema: views with cryptic names over the inventory tables (same data, new names) | Copy of `semana-10/legado/legado.sql` / `infra/loader/handler.py`, `tests/test_loader.py` |
| `infra/loader/artnot.sql` | The legacy article-notes table, with injected instructions planted in some notes (week 13's indirect prompt injection cases) | Copy of `semana-13/seguridad/artnot.sql` / `infra/loader/handler.py`, `tests/test_loader.py` |
| `infra/loader/ddl_copilot.sql` | The inventory schema (the inventory-copilot tables), with the pgvector extension first | Snapshot of inventory-copilot's schema / `infra/loader/handler.py`, `tests/test_loader.py` |
| `infra/loader/seed42_datos.sql.gz` | The synthetic data of seed 42 (suppliers, warehouses, products, stock, daily sales), as a compressed `COPY` dump | inventory-copilot's generator / `infra/loader/handler.py`, `tests/test_loader.py` |
| `infra/loader/diccionario_legado.json` | The legacy data dictionary: each view's original table, its description and the meaning of each column, in Spanish. The loader turns each view into one Knowledge Base document | `infra/loader/handler.py` |
| `infra/loader/handler.py` | The loader's code | Deployed as the loader Lambda function |
| `infra/loader/rds-ca.pem` | The RDS certificate bundle, for TLS to the database | `infra/loader/handler.py`, `computo/escritor.py` |
| `infra/loader/vendor/**` | Vendored third-party packages (pg8000 and its dependencies), pinned for the Lambda runtime | `infra/loader/handler.py`; also packaged with the agent by `infra/paquete_agente.py` |
| `tests/snapshots/infra_lab.json` | Snapshot of the foundation stacks (control, base, datos), lab profile: logical IDs and resource types | `tests/test_infra_cdk.py` |
| `tests/snapshots/agentes_*.json` | Snapshot of the agent-runtime comparison stack (activity 7), lab and prod profiles | `tests/test_infra_agentes.py` |
| `tests/snapshots/gateway_*.json` | Snapshot of the AgentCore Gateway stack (activity 7), lab and prod profiles | `tests/test_infra_gateway.py` |

## Keys

| Key | Meaning |
|---|---|
| `original` | The original inventory table behind a legacy view (`diccionario_legado.json`) |
| `descripcion` | The view's description |
| `columnas` | Each column of the view and its meaning |
