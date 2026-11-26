# Week 19 results (recorded evidence)

[Glossary](../../docs/glossary.md) · [Week 19 README](../README.md)

The evidence of week 19: LegacyBridge deployed on AWS from IaC, measured and torn down. Each activity has an English
report (`*.md`). Next to the reports are the raw files the scripts wrote: account baselines, inventories, deploy
times, Cost Explorer and Price List records, the raw eval runs against the deployed endpoint, the comparison of the
three tools paths and the security review.

**Recorded evidence:** the JSON and JSONL files are the raw outputs of the runs and of the AWS calls, kept exactly as
recorded: not edited, not translated. The scripts that wrote them are listed below. The English summary of the
results is in the [week 19 README](../README.md) and in the reports of this folder. Two reports are generated from
the raw files: the data block of [eval_aws.md](eval_aws.md) by `eval/informe.py`, and [costo_real.md](costo_real.md)
by `eval/costo_real.py`. The approval workflow's recorded check names (`comprobacion`) stay Spanish;
[`eval/comprobaciones_en.json`](../eval/comprobaciones_en.json) maps them to English. This README does not restate
the results.

Every eval run is kept, the discarded ones included (`*_descartada_N.json`). The scripts read every
`crudo_eval*.json` and `crudo_*.json` file in their folder to add up the spend against the cap, so do not rename,
move or delete them.

## Files

Script paths are relative to `semana-19/`.

| File(s) | What it is | Written by / Read by |
|---|---|---|
| `*.md`, `seguridad/estimacion.md` | The English reports: [linea_base.md](linea_base.md) (activity 1), [arquitectura.md](arquitectura.md) and [cotizacion.md](cotizacion.md) (activity 2), [base.md](base.md) (activity 3), [costo_actividad4.md](costo_actividad4.md) (activity 4), [agentes.md](agentes.md) (activity 7), [eval_aws.md](eval_aws.md) and [costo_real.md](costo_real.md) (activity 8), [seguridad.md](seguridad.md) and [seguridad/estimacion.md](seguridad/estimacion.md) (activity 9), [aip_c01.md](aip_c01.md) (the week by AIP-C01 exam domain) | Written by hand, except the generated parts named above |
| `linea_base_mac.json` | Activity 1: the baseline of the account, the Bedrock models, the quotas and the prices | `linea_base/verificar.py` |
| `inventario_mac.json` | Activity 1: the read-only inventory of the account before any deploy | `infra/inventario.py` (its printed JSON, saved here) |
| `spike_iac.json` | Activity 2: the measurements of the IaC spike (CDK against Terraform), read by ADR 0001 | Recorded during the spike (`spike/`) |
| `base_despliegue.json` | Activity 3: a placeholder for the foundation's deploy times, inventory and cost. Its `estado` says no real run was made; the measured times are in `tiempos_despliegue.jsonl` | Written by hand (no script) |
| `precio_endpoint_sku.json` | Activity 4: the raw AWS Price List record of the VPC interface endpoint's hourly price (SKU EN2N5TATXE673A3B), cited in `base.md` and `costo_actividad4.md` | AWS Price List API |
| `tiempos_despliegue.jsonl` | One line per deploy or teardown step, with its duration | `infra/desplegar.sh`, `infra/destruir.sh` |
| `recall_kb.json` | Activity 4: the Knowledge Base's recall@5 on 5 column-meaning questions, from `Retrieve` calls on the deployed Knowledge Base | Bedrock `Retrieve` |
| `apply_guardrail.json` | Activity 5: the live `ApplyGuardrail` test of the deployed Guardrail | `guardrail/prueba_viva.py` / `guardrail/comparar_determinista.py` |
| `comparacion_determinista.json` | Activity 5: the Guardrail against the deterministic layer, case by case | `guardrail/comparar_determinista.py` |
| `agentes/crudo_*.json` | Activity 7: the raw runs of each tools path (`directo`, `gateway`), discarded runs included | `agentes/comparar.py` / `eval/costo_real.py` |
| `agentes/politica_en_vivo.json` | Activity 7: the live test of the Gateway's Cedar policies | `agentes/comparar.py` |
| `agentes/costo_cost_explorer.json` | Activity 7: the 2 Cost Explorer calls behind the real cost in `agentes.md` and `cotizacion.md` | Cost Explorer `GetCostAndUsage` |
| `agentes/inventario_actividad7.json` | Activity 7: the inventory after the teardown of the disposable stacks | `infra/inventario.py --solo-actividad7` (its printed JSON, saved here) |
| `eval_aws/crudo_eval*.json` | Activity 8: the raw eval run against the deployed endpoint, and the discarded runs | `eval/eval_aws.py` / `eval/informe.py`, `eval/costo_real.py`, `costos/modelo.py` |
| `eval_aws_detalle.jsonl` | Activity 8: one row per task of the eval run (the schema is in `eval_aws.md`) | `eval/eval_aws.py` / `eval/informe.py`, `eval/comparar_jueces.py` |
| `eval_aws/aprobacion_e2e.json` | Activity 8: the end-to-end human-approval workflow, check by check | `eval/aprobacion_e2e.py` / `eval/informe.py` |
| `eval_aws/juez_bedrock.json`, `eval_aws/comparar_jueces.json` | Activity 8: the Bedrock model evaluation job (LLM judge), and its agreement with week 13's verifier, which runs the expected query and compares rows | `eval/juez_bedrock.py`, `eval/comparar_jueces.py` / `eval/informe.py` |
| `eval_aws/cost_explorer.json`, `eval_aws/costo_real.json` | Activity 8: the Cost Explorer call ledger and the real-cost breakdown | `eval/costo_real.py` |
| `costo_semana.json`, `costo_semana_llamadas.json` | The week's cost from Cost Explorer, and its call ledger | `costos/costo_semana.py` / `eval/costo_real.py` |
| `seguridad/verificacion.json` | Activity 9: the read-only checks of the deployed stack | `seguridad/verificar_desplegado.py` |
| `seguridad/secretos.json`, `seguridad/supresiones.json`, `seguridad/validate_policy.json`, `seguridad/parliament.json` | Activity 9: the scanners (secrets; cdk-nag and checkov suppressions; IAM ValidatePolicy; parliament), each finding classified | `seguridad/escaneo_secretos.py`, `seguridad/supresiones.py`, `seguridad/validar_politicas.py`, `seguridad/parliament_offline.py` |
| `seguridad/access_analyzer.json` | Activity 9: IAM Access Analyzer's external-access findings | IAM Access Analyzer |
| `seguridad/envenenamiento*.json` | Activity 9: indirect prompt injection through the tools, the current run and the run before the fix of H13 | `seguridad/envenenamiento.py` / `tests/test_envenenamiento.py` |
| `seguridad/kb_retrieve_*.json` | Activity 9: direct `Retrieve` calls on the Knowledge Base, with the poisoned documents (`kb_retrieve_1`, `_2`) and after their removal (`limpio` = clean) | Bedrock `Retrieve`; the documents are in [`../seguridad/kb_envenenados/`](../seguridad/kb_envenenados/README.md) |
| `seguridad/accion_presupuesto.jsonl` | Activity 9: the budget-action test, one line per event | `seguridad/prueba_accion_presupuesto.py` |
| `seguridad/cost_explorer.json`, `seguridad/costo.json` | Activity 9: the Cost Explorer call ledger and the cost of the review | `seguridad/costo_actividad9.py` |
| `inventario_final.json` | Activity 10: the final teardown inventory | `infra/inventario.py` (its printed JSON, saved here) |

## Keys

| Key | Meaning |
|---|---|
| `fecha` | Date of the run or the call |
| `filas` | Rows: one per task, case or check |
| `resumen` | Summary of a run |
| `gasto`, `tope` | Spend so far, and the spending cap |
| `camino` | Tools path: `directo` (direct `lambda.invoke` from the agent loop) or `gateway` (AgentCore Gateway) |
| `acceso` | The access checks before an eval run (for example, a request without a token must get 401) |
| `calentamiento` | The warm-up request before the measured tasks |
| `esperados` | In an eval run: the expected values, per task. In an inventory: the resources expected to remain (the declared exceptions) |
| `idioma` | Language (`es`, `en`) |
| `fase` | Phase of a detail row: `principal` (a measured task) or `calentamiento` (the warm-up) |
| `exito` | Success |
| `estado`, `estado_esperado` | Final status, expected status |
| `arranque` | Start type of the Lambda functions: `frio` (cold), `caliente` (warm) or `desconocido` (unknown) |
| `latencia_s` | Latency in seconds |
| `pasos`, `paso` | Steps, step |
| `trayectoria_ok` | The trajectory passes week 17's graders |
| `bloqueos_capa`, `bloqueos_guardrail`, `bloqueos_politica` | Blocks by the deterministic layer, by the Bedrock Guardrail, by a Cedar policy |
| `veredicto_juez` | The LLM judge's verdict (`null` in the detail rows: the judge's results are in `eval_aws/juez_bedrock.json`) |
| `comprobacion` | Check name, in Spanish (English names in `eval/comprobaciones_en.json`) |
| `acuerdo`, `kappa` | Agreement and Cohen's kappa between the LLM judge and the verifier |
| `ventana_utc` | Time window, in UTC |
| `segundos` | Seconds |
| `quedan` | Remaining resources after a teardown: `nada` = none, `revisar` = review (a category could not be read) |
| `por_categoria`, `inesperados`, `no_medido` | Per category, unexpected resources, not measured |
| `veredicto`, `veredictos` | Verdict(s) |
| `hallazgos` | Findings |
| `huella_antes`, `huella_despues`, `tablas_cambiadas` | The database fingerprint before and after a run, and the tables that changed |
| `costo_usd` | Cost in USD |
