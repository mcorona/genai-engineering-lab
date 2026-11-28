"""Week 20, activity 4, R1: the router's fixed configuration (ADR 0015), offline ($0, no AWS, no model).

The candidates, the rules and the cache mode per model live in ia/config.py and are repeated in agente/construccion.py
(ia/ is not in the Lambda package). The prices per model are the Price List's, by SKU, and the ADR's hand-worked
budget case is computed from them."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S19))

from agente import construccion as K  # noqa: E402
from ia import config  # noqa: E402

PRECIOS_JSON = json.loads((S19.parent / "semana-20" / "resultados" / "precios.json").read_text(encoding="utf-8"))
NOVA, HAIKU, SONNET = "us.amazon.nova-lite-v1:0", config.MODELO_ID, "us.anthropic.claude-sonnet-4-6"
SENALES = ("error_herramienta", "resultado_vacio", "bloqueo_capa", "respuesta_invalida", "presion_pasos",
           "presion_tokens", "respuesta_vacia", "abstencion", "idioma")


def test_routing_is_off_by_default_in_the_configuration_and_in_its_copy():
    assert config.RUTEO == K.RUTEO_POR_OMISION == "off"
    assert tuple(config.MODOS_RUTEO) == K.MODOS_RUTEO == ("off", "r1")


def test_the_candidates_are_nova_lite_haiku_4_5_and_sonnet_4_6_cheapest_first_and_equal_in_the_copy():
    assert tuple(config.RUTEO_CANDIDATOS) == K.RUTEO_CANDIDATOS == (NOVA, HAIKU, SONNET)
    entrada = [K.PRECIOS_POR_MODELO[m].entrada_1m for m in K.RUTEO_CANDIDATOS]
    assert entrada == sorted(entrada)


def test_the_rules_are_fixed_and_equal_in_the_copy():
    assert config.RUTEO_REGLAS == K.RUTEO_REGLAS
    assert tuple(K.RUTEO_REGLAS["senales"]) == SENALES
    assert K.RUTEO_REGLAS["alcance"] == "resto_de_la_tarea"
    assert (K.RUTEO_REGLAS["max_escalamientos"], K.RUTEO_REGLAS["pasos_presion"],
            K.RUTEO_REGLAS["tokens_presion"]) == (2, 7, 50_000)
    assert K.RUTEO_REGLAS["max_escalamientos"] == len(K.RUTEO_CANDIDATOS) - 1


def test_the_cache_mode_per_model_is_the_adrs_and_equal_in_the_copy():
    assert config.CACHE_POR_MODELO == K.CACHE_POR_MODELO == {
        NOVA: "historial+sistema", HAIKU: "historial", SONNET: "historial+sistema"}
    assert set(K.CACHE_POR_MODELO.values()) <= set(K.MODOS_CACHE)


def _sku(sku: str) -> float:
    fila = next(p for p in PRECIOS_JSON["precios"] if p["sku"] == sku)
    (precio,) = fila["precios"]
    return precio["usd"] * (1000 if precio["unidad"] == "1K tokens" else 1)


@pytest.mark.parametrize("modelo, skus", [
    (NOVA, ("QRGWJ3P8FT28EYX2", "CBZ6A6U7XK8WJ3KA", "FYTFBAWEJFBAVTWK", "NF8UDYEDB4HXGNAZ")),
    (HAIKU, ("JQDUC8Q4K8C6GSGH", "X629GDA2GXAP6R54", "VJXPZKPF7EDCFXN3", "CDG7WESKYQ9N9KDN")),
    (SONNET, ("KPFGPZJ8VWMREGAV", "GMB9AQ5DYNAGYZEC", "2459RQS6BSFATF92", "UZUVWF3P26ENQTZ8")),
])
def test_each_candidates_prices_are_its_price_list_skus(modelo, skus):
    p = K.PRECIOS_POR_MODELO[modelo]
    esperado = tuple(round(_sku(s), 6) for s in skus)
    assert (p.entrada_1m, p.salida_1m, p.cache_lectura_1m, p.cache_escritura_1m) == pytest.approx(esperado)
    assert K.SKUS_POR_MODELO[modelo] == skus


def test_the_haiku_prices_are_the_ones_the_agent_already_uses():
    p = K.PRECIOS_POR_MODELO[HAIKU]
    hoy = K.precios("5m")
    assert (p.entrada_1m, p.salida_1m, p.cache_lectura_1m, p.cache_escritura_1m) == (
        hoy.entrada_1m, hoy.salida_1m, hoy.cache_lectura_1m, hoy.cache_escritura_1m)


def test_the_adrs_hand_worked_budget_case_prices_each_call_at_its_own_model():
    llamadas = [(NOVA, 2952, 149), (NOVA, 4268, 180), (HAIKU, 4548, 107), (HAIKU, 4733, 275),
                (SONNET, 4733, 275), (SONNET, 5133, 492)]
    usd = sum(K.PRECIOS_POR_MODELO[m].usd(i, o) for m, i, o in llamadas)
    assert round(usd, 7) == 0.0580356
    assert sum(i + o for _, i, o in llamadas) == 27_845
    a_precio_de_haiku = sum(K.PRECIOS_POR_MODELO[HAIKU].usd(i, o) for _, i, o in llamadas)
    assert round(a_precio_de_haiku, 7) == 0.0371327


def test_the_rewrite_of_the_prefix_at_an_escalation_to_sonnet_is_the_adrs():
    s = K.PRECIOS_POR_MODELO[SONNET]
    h = K.PRECIOS_POR_MODELO[HAIKU]
    escribir = s.usd_cache(0, 4733)
    quedarse = h.usd_cache(4548, 185)
    assert (round(escribir, 7), round(escribir - s.usd(4733, 0), 7), round(quedarse, 7)) == (
        0.0195236, 0.0039047, 0.0007547)


def test_nova_takes_only_the_5_minute_ttl():
    assert K.TTLS_POR_MODELO[NOVA] == ("5m",)
    assert K.TTLS_POR_MODELO[HAIKU] == K.TTLS_POR_MODELO[SONNET] == ("5m", "1h")


def test_each_candidate_has_its_profile_name_and_its_variable_and_the_copy_agrees():
    """The stack names one application profile per candidate (Haiku 4.5 keeps activity 2's `agente`) and passes its
    ARN in one variable, which the Lambda reads (ADR 0015 section 6)."""
    assert config.PERFIL_POR_CANDIDATO == {NOVA: "agente-nova-lite", HAIKU: "agente", SONNET: "agente-sonnet-4-6"}
    assert config.VARIABLE_POR_CANDIDATO == K.VARIABLE_POR_MODELO == {
        NOVA: "MODELO_NOVA_LITE", HAIKU: "MODELO", SONNET: "MODELO_SONNET_46"}
    assert set(config.PERFIL_POR_CANDIDATO) == set(config.RUTEO_CANDIDATOS)
