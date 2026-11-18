"""Week 19, activity 5: the one configuration value for the model.

Switching models is a change of MODELO_ID and nothing else (a test enforces that the model id appears only here).
Haiku 5.5 is not used: its on-demand quota is 0 (its increase request is still open).
"""
from __future__ import annotations

# Decision of Manuel (activity 1): Haiku 4.5 through the us. cross-Region inference profile.
MODELO_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# Regions of the underlying foundation models, read with get-inference-profile (2026-11-15, status ACTIVE).
REGIONES_DEL_MODELO = ("us-east-1", "us-east-2", "us-west-2")

# The company in the system prompt's variable nombre_empresa (ia/prompts_sistema.py), per language: week 13's prompt
# said "a distribution company". Used where the prompt is rendered outside the loop (activity 7, Bedrock Agents).
NOMBRE_EMPRESA = {"es": "una empresa distribuidora", "en": "a distribution company"}
