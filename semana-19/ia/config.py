"""Week 19, activity 5: the one configuration value for the model.

Switching models is a change of MODELO_ID and nothing else (a test enforces that the model id appears only here).
Haiku 5.5 is not used: its on-demand quota is 0 (its increase request is still open).
"""
from __future__ import annotations

# Decision of Manuel (activity 1): Haiku 4.5 through the us. cross-Region inference profile.
MODELO_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Regions of the underlying foundation models, read with get-inference-profile (2026-11-15, status ACTIVE).
REGIONES_DEL_MODELO = ("us-east-1", "us-east-2", "us-west-2")

# Activity 8: the judge of the Bedrock model evaluation (eval/juez_bedrock.py), a model different from the agent's.
# Amazon Nova Pro through its US cross-Region profile; get-inference-profile (2026-11-19, ACTIVE) routes it to these
# Regions, all with the foundation model amazon.nova-pro-v1:0.
MODELO_JUEZ_ID = "us.amazon.nova-pro-v1:0"
REGIONES_DEL_JUEZ = ("us-east-1", "us-east-2", "us-west-2")

# The company in the system prompt's variable nombre_empresa (ia/prompts_sistema.py), per language: week 13's prompt
# said "a distribution company". Used where the prompt is rendered outside the loop (activity 7, Bedrock Agents).
NOMBRE_EMPRESA = {"es": "una empresa distribuidora", "en": "a distribution company"}

# Week 20, activity 2: one Bedrock application inference profile per component, each a copy of a system profile above
# and tagged proyecto and componente, so Cost Explorer splits the model cost by component. The ARNs exist only after
# the deploy (they hold the account and a generated id), so this file keeps the switch and the sources: the ia stack
# creates the profiles and the agent's stack passes the agent profile's ARN to the Lambda (variable MODELO).
# False: the agent calls MODELO_ID itself, as in week 19 (a test checks both values).
USAR_PERFIL_DE_APLICACION = True
# Component -> the system profile it copies. The judge keeps its own model (a model other than the agent's, week 19
# activity 8); batch enrichment (activity 5) runs on Haiku 4.5. Only the agent's profile is called in activity 2.
PERFILES_DE_APLICACION = {"agente": MODELO_ID, "juez": MODELO_JUEZ_ID, "enriquecimiento": MODELO_ID}

# Week 20, activity 3: prompt caching, one value (ADR 0014). The modes, with what they cache on Haiku 4.5:
# - "off": no cache point, week 19's request (default, so each optimization is measured alone);
# - "sistema": a point after the system prompt and the tools. About 2,800 tokens, under Haiku 4.5's minimum of 4,096
#   per point, so it caches nothing here (a test says so); it would on a model with a lower minimum;
# - "historial": the point at the end of the history, from the second call on, plus one on the previous call's;
# - "historial+sistema": both (on Haiku 4.5 the same tokens as "historial").
# The activity 3 run deploys computo with CACHE_PROMPT=historial at synth time; activity 9 decides the combined value.
# agente/construccion.py repeats the default (ia/ is not in the Lambda package; a test checks they are equal).
MODOS_CACHE = ("off", "sistema", "historial", "historial+sistema")
CACHE_PROMPT = "off"
# "5m" (write at 1.25x input) or "1h" (write at 2x). The steps of a query are seconds apart, and no two queries share
# a cached prefix, so 5 minutes is enough (ADR 0014).
TTLS_CACHE = ("5m", "1h")
CACHE_TTL = "5m"
