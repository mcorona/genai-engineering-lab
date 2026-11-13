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
