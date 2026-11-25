"""Week 20, activity 3, step 3: the caching prediction (quote v3), versioned before the live run ($0).

    .venv/bin/python semana-20/cache/prediccion.py      writes resultados/cache_prediccion.json

Input: the per-step tokens measured in step 1 (resultados/cache_medicion.json) and the prices of
semana-19/costos/precios.json (Price List, with SKUs). Each task of the corrected run is priced with
`costos/modelo.py` `cache_por_paso` and `costo_cache_usd`, in the design of ADR 0014 (CACHE_PROMPT=historial, TTL 5m).

The hit rate is the one unknown. A step can read only if Bedrock sends it to the server that served the step before
(prompt-caching docs, 2026-11-25: a request served by another server, "such as one in another Region", writes
instead of reading). The us. profile routes Haiku 4.5 to 3 Regions (ia/config.py REGIONES_DEL_MODELO, read with
get-inference-profile on 2026-11-15). No source gives the share that stays on one server, so there is no measured
"expected" rate. The prediction gives scenarios, not a guess:
- `optimista`: every step on the same server (p = 1);
- `pesimista`: each step in a Region drawn uniformly from the 3 (p = 1/3), with every miss a full write;
- `peor`: no step ever reads (p = 0), the upper bound: writes cost 1.25x, so caching costs more than no caching;
- `equilibrio`: the p at which caching costs the same as the corrected run.
The central scenario of quote v3 is `optimista`, stated as the assumption the run tests. Latency: the docs give no
figure for Bedrock, so the predicted latency is N.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
sys.path.insert(0, str(RAIZ / "semana-19"))
from costos import modelo as M  # noqa: E402

MEDICION = S20 / "resultados" / "cache_medicion.json"
SALIDA = S20 / "resultados" / "cache_prediccion.json"
REGIONES = 3
ESCENARIOS = {"optimista": 1.0, "pesimista": 1 / REGIONES, "peor": 0.0}
MODO, TTL = "historial", "5m"


def _por_tarea(fila: dict, p: float, precios: dict, ttl: str = TTL) -> dict:
    pasos = M.cache_por_paso(fila["entrada_por_paso"], p_acierto=p, modo=MODO,
                             prefijo_fijo=fila["prefijo_fijo_tokens"])
    return {"usd": M.costo_cache_usd(pasos, fila["tokens_salida"], precios, ttl),
            "sin_cache": sum(x["sin_cache"] for x in pasos), "lectura": sum(x["lectura"] for x in pasos),
            "escritura": sum(x["escritura"] for x in pasos), "pasos": pasos}


def _resumen(costos: list[float]) -> dict:
    return {"total": round(sum(costos), 6), "mediana": round(statistics.median(costos), 6),
            "p95": round(M.percentil(costos, 0.95), 6), "media": round(statistics.mean(costos), 6)}


def equilibrio(filas: list[dict], precios: dict, base: float) -> float:
    """The hit probability at which the 20 tasks cost the same as without a cache (bisection; cost falls with p)."""
    bajo, alto = 0.0, 1.0
    for _ in range(60):
        medio = (bajo + alto) / 2
        if sum(_por_tarea(f, medio, precios)["usd"] for f in filas) > base:
            bajo = medio
        else:
            alto = medio
    return round((bajo + alto) / 2, 4)


def predecir(medicion: dict | None = None) -> dict:
    m = medicion or json.loads(MEDICION.read_text(encoding="utf-8"))
    precios = M.cargar_precios()
    principales = [f for f in m["filas"] if f["fase"] == "principal"]
    todas = m["filas"]
    sin = [M.costo_cache_usd(M.cache_por_paso(f["entrada_por_paso"], modo="off"), f["tokens_salida"], precios)
           for f in principales]
    reales = [f["costo_usd"] for f in principales]
    base = sum(sin)
    escenarios = {}
    for nombre, p in ESCENARIOS.items():
        por = [_por_tarea(f, p, precios) for f in principales]
        costos = [x["usd"] for x in por]
        escenarios[nombre] = {"p_acierto": round(p, 4), **_resumen(costos),
                              "ahorro_pct": round(100 * (1 - sum(costos) / base), 1),
                              "tokens": {k: round(sum(x[k] for x in por)) for k in ("sin_cache", "lectura", "escritura")},
                              "con_calentamiento_usd": round(sum(_por_tarea(f, p, precios)["usd"] for f in todas), 6)}
    central = [_por_tarea(f, 1.0, precios) for f in principales]
    n = len(principales)
    ttl_1h = sum(_por_tarea(f, 1.0, precios, "1h")["usd"] for f in principales)
    return {
        "fecha": "2026-11-25",
        "fuente": "resultados/cache_medicion.json; semana-19/costos/precios.json; costos/modelo.py cache_por_paso",
        "diseno": {"CACHE_PROMPT": MODO, "CACHE_TTL": TTL, "adr": "semana-19/arquitectura/adr/0014-prompt-caching.md"},
        "linea_base": {"tareas": n, "modelo_sin_cache": _resumen(sin), "corrida_corregida_real": _resumen(reales),
                       "diferencia_modelo_vs_real_usd": round(base - sum(reales), 6)},
        "escenarios": escenarios,
        "equilibrio_p_acierto": equilibrio(principales, precios, base),
        "ttl_1h_optimista": {"total": round(ttl_1h, 6), "ahorro_pct": round(100 * (1 - ttl_1h / base), 1)},
        "latencia": "N: the prompt-caching docs give no latency figure for Bedrock",
        "v3_por_consulta": {"ttl": TTL, **{k: round(sum(x[k] for x in central) / n, 1)
                                           for k in ("sin_cache", "lectura", "escritura")},
                            "salida": round(sum(f["tokens_salida"] for f in principales) / n, 1),
                            "usd": round(sum(x["usd"] for x in central) / n, 8)},
        "por_tarea": [{"id": f["id"], "pasos": f["pasos"], "real_usd": f["costo_usd"], "sin_cache_usd": round(s, 6),
                       **{nombre: round(_por_tarea(f, p, precios)["usd"], 6) for nombre, p in ESCENARIOS.items()},
                       "lectura_por_paso_optimista": [round(x["lectura"]) for x in c["pasos"]],
                       "escritura_por_paso_optimista": [round(x["escritura"]) for x in c["pasos"]]}
                      for f, s, c in zip(principales, sin, central)],
    }


def main() -> int:  # pragma: no cover - the CLI around predecir()
    pr = predecir()
    SALIDA.write_text(json.dumps(pr, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: pr[k] for k in pr if k != "por_tarea"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
