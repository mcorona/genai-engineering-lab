# AIP-C01: running list (week 19)

Each row: concept → where the lab shows it → evidence. Status: **medido** (M), **D** (documentado con enlace), **parcial** or **falla**; nothing is marked without its evidence. Domains: D1 FM integration and data (31%), D2 implementation (26%), D3 security and governance (20%), D4 efficiency (12%), D5 testing and troubleshooting (11%).

## Activity 1 (D1, D3)

| Concept | Domain | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Inference profiles (cross-region) versus base model IDs | D1 | `linea_base/verificar.py`, sonda `bedrock`, `inference_profiles` | `resultados/linea_base_mac.json`, `bedrock.inference_profiles` | medido 2026-11-12 |
| On-demand quotas for tokens and requests per minute, per model | D1 | sonda `cuotas` (Service Quotas `bedrock`) | `resultados/linea_base_mac.json` | medido 2026-11-12 |
| Model availability by region and access | D1 | sonda `bedrock`, `list_foundation_models` | `resultados/linea_base_mac.json` | medido 2026-11-12 |
| Free tier and credits as cost controls | D3 | sonda `cuenta` (Free Tier API) and Billing screen | `resultados/linea_base.md` §1: plan PAID medido; créditos US$142 sin vencimiento (D, Billing) | medido (plan) + D (créditos) |
| Budgets with alerts at actual and forecast thresholds | D3 | `infra/presupuesto.py` (simulation, tested) | `semana-19/tests/test_preparacion.py` | en simulación |
| Least-privilege readiness: named admin and operator profiles, no access keys | D3 | `preparar/verificar_entorno.py` | operador y admin son la misma identidad (`linea_base.md` §7): excepción abierta | falla |
| Tag-based resource inventory and a teardown proof | D3 | `infra/inventario.py` (Tagging API plus name prefix) | `"quedan": "nada"` from the Mac run | medido 2026-11-12 |
| KMS key pending deletion billing | D3 | KMS pricing doc (no es artículo del catálogo) | `resultados/linea_base.md` §3 (D con enlace) | D |

## Activity 2 (D1, D2, D4)

| Concept | Domain | Where the lab shows it | Evidence | Status |
|---|---|---|---|---|
| Model choice by cost per token against fixed cost per hour | D4 | `semana-19/costos/modelo.py` (per query and per hour, two profiles) | `resultados/cotizacion.md`, per query 0.0799 USD and per hour 0.0219 USD (lab, partial) | medido (partial: endpoints N) |
| Inference profiles (`us.`) and quotas as a model choice constraint | D1 | `semana-19/costos/precios.json` (Haiku 4.5 regional, `us.`); Haiku 5.5 quota 0 | `resultados/linea_base.md` H1, H2; cuota Haiku 5.5 en CASE_OPENED | medido |
| Converse API with Guardrail | D2 | `semana-19/arquitectura/diagrama.mmd` (agent → Converse); Guardrail in both IaC tools | `resultados/spike_iac.json` (`guardrail_y_kb`) | diseño y synth; no invocado |
| Prompt Management versions in the request path | D2 | diagram node "versión de Prompt Management" | `arquitectura/diagrama.svg` | diseño |
| Serverless patterns: Lambda outside the VPC, HTTP API with JWT, Step Functions with `waitForTaskToken` | D2 | `arquitectura/adr/0002`, `0004`, `0005` | ADRs and the diagram | diseño; prices M or N per item |
| Fixed cost versus variable cost (zero queries is only the fixed part) | D4 | `costos/modelo.py` and `tests/test_costos.py` (zero queries test) | `cotizacion.md`: 5.44 USD/month lab with 0 queries (partial) | medido |
| Knowledge Base on S3 Vectors with Titan V2 | D1 | `spike/cdk/app_ia.py`, `spike/terraform/ia.tf` | `spike_iac.json` (`ia`), validate and synth | sintetizado; no desplegado |
