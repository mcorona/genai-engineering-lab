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

# Week 20, activity 4, R1: the in-house router (ADR 0015). Off by default, so each optimization is measured alone.
# "r1": the task starts on the first candidate and escalates one step at a time, for the rest of the task, never back
# down, at most max_escalamientos times. With "off" the agent calls MODELO_ID (or its application profile) as today.
# agente/construccion.py repeats these values (ia/ is not in the Lambda package; test_agente_ruteo_config.py).
MODOS_RUTEO = ("off", "r1")
RUTEO = "off"
# Cheapest first, each through its us. cross-Region profile (us-east-1, us-east-2, us-west-2), all AUTHORIZED and
# AVAILABLE (get-foundation-model-availability, 2026-11-27). Sonnet 4.6, not 4.5: 4.5 is LEGACY, at the same price.
RUTEO_CANDIDATOS = ("us.amazon.nova-lite-v1:0", MODELO_ID, "us.anthropic.claude-sonnet-4-6")
# The signals (ADR 0015 section 2). Request signals send the next call to the next model; response signals send the
# same request again to the next model. The thresholds come from the cache run: 18 of 20 tasks take 6 steps or fewer,
# and 2 of 20 pass 50,000 tokens (half of the deployed task ceiling).
RUTEO_REGLAS = {
    "senales": ("error_herramienta", "resultado_vacio", "bloqueo_capa", "respuesta_invalida", "presion_pasos",
                "presion_tokens", "respuesta_vacia", "abstencion", "idioma"),
    "alcance": "resto_de_la_tarea",
    "max_escalamientos": 2,
    "pasos_presion": 7,
    "tokens_presion": 50_000,
}
# The cache mode of each candidate when CACHE_PROMPT is not "off" and RUTEO is "r1" (ADR 0015 section 3): Nova's
# minimum is 1K and its writes cost 0, Sonnet 4.6's minimum is 1,024, so both also cache the fixed prefix; Haiku 4.5
# keeps ADR 0014's mode (its minimum, 4,096, is above the fixed prefix). Nova takes only the 5-minute TTL.
CACHE_POR_MODELO = {"us.amazon.nova-lite-v1:0": "historial+sistema", MODELO_ID: "historial",
                    "us.anthropic.claude-sonnet-4-6": "historial+sistema"}
# With RUTEO=r1 the ia stack makes one application inference profile per candidate, named semana19-<this> and tagged
# componente=agente (Haiku 4.5 keeps activity 2's `agente`), and the agent's stack passes each profile's ARN to the
# Lambda in its variable (ADR 0015 section 6; agente/construccion.py repeats the variables).
PERFIL_POR_CANDIDATO = {"us.amazon.nova-lite-v1:0": "agente-nova-lite", MODELO_ID: "agente",
                        "us.anthropic.claude-sonnet-4-6": "agente-sonnet-4-6"}
VARIABLE_POR_CANDIDATO = {"us.amazon.nova-lite-v1:0": "MODELO_NOVA_LITE", MODELO_ID: "MODELO",
                          "us.anthropic.claude-sonnet-4-6": "MODELO_SONNET_46"}
