"""Week 19, activity 2: cost model for the LegacyBridge stack (lab and prod). Offline, $0.

Prices come from precios.json, each with its source. A line whose price is not measured (null, mark N) is listed but
NOT added to the total: the output says so (`parcial`), it is never counted as 0.

Two versions of the tokens per query, both kept (activity 8, step 4: the model is corrected, never the number):
- v1 (activity 2): p95 of week 13's local runs (eval_sdk_low_detalle.jsonl). Cost Explorer put it 61 % above the real
  model cost per task.
- v2 (default, 2026-11-21): the deployed agent's own spans, the 57 agent tasks of activity 8's runs
  (resultados/eval_aws/crudo_eval*.json and aprobacion_e2e.json), the same tasks Cost Explorer billed. The mean is the
  expected cost per query; p95 stays available for a conservative quote. No prompt caching was measured (0 cached
  tokens). v2 also lists ApplyGuardrail, which runs on every model call since activity 5: its price is N.
- v3 (week 20, activity 3): v2 with prompt caching. The tokens per query come from the caching prediction
  (semana-20/resultados/cache_prediccion.json, written before the run by semana-20/cache/prediccion.py), which prices
  each step of the corrected run with `cache_por_paso`: the uncached input, the cache reads (0.1x input) and the
  cache writes (1.25x with the 5-minute TTL, 2x with 1 hour) of the CACHE_PROMPT design (ADR 0014).
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

COSTOS = Path(__file__).resolve().parent
RAIZ = COSTOS.parent.parent
HORAS_MES = 730.0
DIAS_MES = 30.0
DETALLE_S13 = RAIZ / "semana-13" / "resultados" / "eval_sdk_low_detalle.jsonl"
EVAL_AWS = COSTOS.parent / "resultados" / "eval_aws"
VERSIONES = {"v1": "p95 of week 13's local runs", "v2": "the deployed agent's spans (activity 8, 57 tasks)",
             "v3": "v2 with prompt caching (week 20, activity 3): the corrected run's steps, priced by cache_por_paso"}
PREDICCION_CACHE = RAIZ / "semana-20" / "resultados" / "cache_prediccion.json"
MINIMO_CACHE_HAIKU45 = 4096   # tokens before each cache point, cumulative (prompt-caching docs, read 2026-11-25)
PERFILES = {
    # lab: 1 AZ, Single-AZ database, no public IPv4, 2 interface endpoints (logs, states; S3 is a gateway endpoint, not priced here).
    "lab": {"azs": 1, "rds_multi_az": False, "ipv4": 0, "endpoints": 2, "llaves_kms": 2, "log_gb": 1.0},
    # prod: 3 AZs for endpoints and Multi-AZ database (its price is N); 2 IPv4 and more retention.
    "prod": {"azs": 3, "rds_multi_az": True, "ipv4": 2, "endpoints": 2, "llaves_kms": 3, "log_gb": 5.0},
}


def cargar_precios() -> dict:
    datos = json.loads((COSTOS / "precios.json").read_text(encoding="utf-8"))
    return datos["precios"]


def percentil(valores: list[float], p: float) -> float:
    v = sorted(valores)
    k = (len(v) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return v[f] + (v[c] - v[f]) * (k - f)


def tokens_s13(campo: str, p: str) -> float:
    """p in {'p50','p95','max'} from the week 13 detail (252 runs, Haiku 5.5 low)."""
    filas = [json.loads(l) for l in DETALLE_S13.read_text(encoding="utf-8").splitlines() if l.strip()]
    valores = [float(f[campo]) for f in filas]
    if p == "max":
        return max(valores)
    return percentil(valores, 0.5 if p == "p50" else 0.95)


def filas_desplegado(carpeta: Path = EVAL_AWS) -> list[dict]:
    """Every agent task of activity 8's runs with its spans (warm-up and discarded runs included, aborted ones out)."""
    filas = []
    for archivo in sorted(carpeta.glob("crudo_eval*.json")):
        crudo = json.loads(archivo.read_text(encoding="utf-8"))
        filas += crudo.get("calentamiento", []) + crudo["filas"]
    aprob = carpeta / "aprobacion_e2e.json"
    if aprob.exists():
        filas += json.loads(aprob.read_text(encoding="utf-8"))["tareas"]
    return [f for f in filas if f.get("tokens_entrada")]


def tokens_desplegado(campo: str, p: str, carpeta: Path = EVAL_AWS) -> float:
    """p in {'media','p50','p95','max'} over the deployed agent's tasks; campo as in week 13 (tokens_in, tokens_out)."""
    clave = {"tokens_in": "tokens_entrada", "tokens_out": "tokens_salida"}[campo]
    valores = [float(f[clave]) for f in filas_desplegado(carpeta)]
    if p == "media":
        return sum(valores) / len(valores)
    if p == "max":
        return max(valores)
    return percentil(valores, 0.5 if p == "p50" else 0.95)


@dataclass
class Parametros:
    perfil: str = "lab"
    consultas_dia: float = 100.0
    version: str = "v2"                # v1 | v2 (VERSIONES)
    percentil_tokens: str | None = None  # media | p50 | p95 | max; by default p95 in v1, media in v2
    horas_dia: float = 8.0
    horas_sesion: float = 0.0          # for the activity 3 estimate
    usuarios: float = 10.0             # MAU de Cognito
    memoria_gb: float = 0.5            # Lambda, supuesto declarado
    duracion_s: float = 3.0            # Lambda per query, a stated assumption
    consultas_kb_por_consulta: float = 1.0
    tokens_consulta_embedding: float = 50.0
    log_kb_por_consulta: float = 20.0  # log KB per query, a stated assumption
    llamadas_gateway_por_consulta: float = 0.0
    aprobaciones_dia: float = 0.0      # proponer_orden_compra with approval
    transiciones_por_aprobacion: float = 6.0
    gb_endpoint_mes: float = 1.0
    creditos_usd: float = 142.0        # H5: no expiry (Manuel's figure, D)
    usar_creditos: bool = True
    overrides: dict = field(default_factory=dict)


def _linea(nombre: str, precios: dict, clave: str, cantidad: float | None, unidad_cantidad: str,
           frecuencia: str, etiqueta: str = "") -> dict:
    p = precios[clave]
    valor = p["valor"]
    if valor is None or cantidad is None:
        return {"partida": nombre, "frecuencia": frecuencia, "precio_clave": clave, "marca": "N",
                "cantidad": cantidad, "unidad": unidad_cantidad, "costo_usd": None, "nota": etiqueta}
    return {"partida": nombre, "frecuencia": frecuencia, "precio_clave": clave, "marca": p["marca"],
            "cantidad": cantidad, "unidad": unidad_cantidad, "costo_usd": cantidad * valor, "nota": etiqueta}


def lineas_fijas_hora(par: Parametros, precios: dict) -> list[dict]:
    pf = PERFILES[par.perfil]
    h = []
    h.append(_linea("KMS, customer managed keys (prorated)", precios, "kms_llave_mes",
                    pf["llaves_kms"] / HORAS_MES, "key-hour", "per hour"))
    h.append(_linea("RDS db.t4g.micro, instance", precios, "rds_t4g_micro_hora", 1.0, "instance-hour", "per hour"))
    h.append(_linea("RDS gp3, 20 GB (prorated)", precios, "rds_gp3_gb_mes", 20.0 / HORAS_MES, "GB-hour", "per hour"))
    if pf["rds_multi_az"]:
        h.append(_linea("RDS Multi-AZ, additional instance", precios, "rds_multi_az_hora", 1.0, "instance-hour", "per hour",
                        "prod profile: its price is not measured"))
    h.append(_linea("Public IPv4 in use", precios, "ipv4_hora", float(pf["ipv4"]), "address-hour", "per hour"))
    h.append(_linea("VPC interface endpoints (endpoints x AZ-hour)", precios, "endpoint_interfaz_hora_az",
                    float(pf["endpoints"] * pf["azs"]), "endpoint-AZ-hour", "per hour"))
    return h


def lineas_fijas_mes(par: Parametros, precios: dict) -> list[dict]:
    pf = PERFILES[par.perfil]
    m = []
    m.append(_linea("Cognito, MAU", precios, "cognito_mau", par.usuarios, "MAU", "per month"))
    m.append(_linea("CloudWatch Logs, storage", precios, "cloudwatch_almacenamiento_gb_mes", pf["log_gb"],
                    "GB-month", "per month"))
    m.append(_linea("AWS Budgets, 1 budget (within 62 free budget-days)", precios, "budgets_budget_dia", 30.0, "budget-days", "per month"))
    m.append(_linea("VPC endpoints, data processed", precios, "endpoint_interfaz_gb_procesado",
                    par.gb_endpoint_mes, "GB", "per month"))
    m.append(_linea("Step Functions, transitions per approval", precios, "step_functions_transicion",
                    par.aprobaciones_dia * DIAS_MES * par.transiciones_por_aprobacion, "transitions", "per month"))
    return m


def cache_por_paso(entrada_por_paso: list[float], *, minimo: int = MINIMO_CACHE_HAIKU45, p_acierto: float = 1.0,
                   modo: str = "historial", prefijo_fijo: float = 0.0) -> list[dict]:
    """Expected input tokens of each step of one query, split into uncached, read from and written to the cache.

    `entrada_por_paso[k]` is the whole input of call k+1 (Converse's input + read + write). Design of ADR 0014:
    - "off", or "sistema" with a fixed prefix under the minimum: everything uncached.
    - "historial" (and "historial+sistema" while the fixed prefix is under the minimum, where its point caches
      nothing): no point on the first call; from the second on, the point at the end of the history covers the whole
      input. Under the minimum it is not cached. Over it: with probability `p_acierto` the call lands where the
      previous call wrote (that call also over the minimum and itself a cached call) and reads that prefix, writing
      only what was added; otherwise it reads nothing and writes the whole prefix (another server or Region).
    """
    if modo not in ("off", "sistema", "historial", "historial+sistema"):
        raise ValueError(f"modo de caché desconocido: {modo}")
    if modo in ("sistema", "historial+sistema") and prefijo_fijo >= minimo:
        raise ValueError("the fixed prefix reaches the minimum: a system point is not modeled (not Haiku 4.5's case)")
    pasos = []
    for k, total in enumerate(entrada_por_paso):
        if modo in ("off", "sistema") or k == 0 or total < minimo:
            pasos.append({"sin_cache": total, "lectura": 0.0, "escritura": 0.0})
            continue
        previo = entrada_por_paso[k - 1]
        p = p_acierto if (k >= 2 and previo >= minimo) else 0.0
        pasos.append({"sin_cache": 0.0, "lectura": p * previo, "escritura": p * (total - previo) + (1 - p) * total})
    return pasos


def costo_cache_usd(pasos: list[dict], salida: float, precios: dict, ttl: str = "5m") -> float:
    """USD of one query from cache_por_paso's steps and its output tokens, with precios.json's Haiku 4.5 prices."""
    v = {k: precios[k]["valor"] for k in ("haiku45_entrada_1m", "haiku45_salida_1m", "haiku45_cache_lectura_1m",
                                          f"haiku45_cache_escritura_{ttl}_1m")}
    return (sum(p["sin_cache"] for p in pasos) * v["haiku45_entrada_1m"]
            + sum(p["lectura"] for p in pasos) * v["haiku45_cache_lectura_1m"]
            + sum(p["escritura"] for p in pasos) * v[f"haiku45_cache_escritura_{ttl}_1m"]
            + salida * v["haiku45_salida_1m"]) / 1e6


def tokens_v3(ruta: Path = PREDICCION_CACHE) -> dict:
    """Mean tokens per query of the caching prediction's central scenario (the 20 main tasks)."""
    if not ruta.exists():
        raise FileNotFoundError("v3 needs semana-20/resultados/cache_prediccion.json (semana-20/cache/prediccion.py)")
    return json.loads(ruta.read_text(encoding="utf-8"))["v3_por_consulta"]


def lineas_consulta(par: Parametros, precios: dict, tokens_in: float, tokens_out: float) -> list[dict]:
    fuente = {"v1": f"{par.percentil_tokens} of week 13",
              "v2": f"{par.percentil_tokens} of the deployed agent (activity 8)",
              "v3": "week 20 caching prediction (activity 3), central scenario"}[par.version]
    c = []
    if par.version == "v3":
        t = tokens_v3()
        ttl = t.get("ttl", "5m")
        c.append(_linea("Haiku 4.5 (us.), uncached input tokens", precios, "haiku45_entrada_1m",
                        t["sin_cache"] / 1e6, "M tokens", "per query", fuente))
        c.append(_linea("Haiku 4.5 (us.), cache read tokens", precios, "haiku45_cache_lectura_1m",
                        t["lectura"] / 1e6, "M tokens", "per query", fuente))
        c.append(_linea(f"Haiku 4.5 (us.), cache write tokens ({ttl})", precios,
                        f"haiku45_cache_escritura_{ttl}_1m", t["escritura"] / 1e6, "M tokens", "per query", fuente))
    else:
        c.append(_linea("Haiku 4.5 (us.), input tokens", precios, "haiku45_entrada_1m", tokens_in / 1e6,
                        "M tokens", "per query", fuente))
    c.append(_linea("Haiku 4.5 (us.), output tokens", precios, "haiku45_salida_1m", tokens_out / 1e6,
                    "M tokens", "per query", fuente))
    c.append(_linea("Lambda, GB-second", precios, "lambda_arm_gb_s", par.memoria_gb * par.duracion_s,
                    "GB-s", "per query", f"memory {par.memoria_gb} GB and {par.duracion_s} s (assumption)"))
    c.append(_linea("Lambda, requests", precios, "lambda_solicitud", 1.0, "request", "per query"))
    c.append(_linea("API Gateway HTTP API, requests", precios, "apigw_http_solicitud", 1.0, "request", "per query"))
    c.append(_linea("Titan V2, query embedding", precios, "titan_v2_1k_tokens",
                    par.consultas_kb_por_consulta * par.tokens_consulta_embedding / 1000.0, "K tokens", "per query"))
    c.append(_linea("CloudWatch Logs, ingestion", precios, "cloudwatch_ingesta_gb",
                    par.log_kb_por_consulta / 1e6, "GB", "per query"))
    c.append(_linea("AgentCore Gateway, invocations", precios, "agentcore_gateway_invocacion",
                    par.llamadas_gateway_por_consulta, "invocations", "per query"))
    if par.version in ("v2", "v3"):
        c.append(_linea("ApplyGuardrail, text units", precios, "guardrail_unidad_texto", None,
                        "text units", "per query", "runs on every model call; neither price nor units measured"))
    return c


def totales(lineas: list[dict]) -> float:
    return sum(l["costo_usd"] for l in lineas if l["costo_usd"] is not None)


def estimacion_base_hora(perfil: str = "lab") -> dict:
    """The activity 3 base stack (KMS, VPC endpoints, IAM, budget), per hour."""
    precios = cargar_precios()
    par = Parametros(perfil=perfil)
    lineas = [l for l in lineas_fijas_hora(par, precios) if l["partida"].startswith(("KMS", "VPC interface endpoints"))]
    presupuesto = _linea("AWS Budgets, 1 budget", precios, "budgets_budget_dia", 1.0 / 24, "budget-day/24", "per hour")
    lineas.append(presupuesto)
    return {"perfil": perfil, "lineas": lineas, "por_hora_usd": totales(lineas), "parcial": any(l["costo_usd"] is None for l in lineas)}


def modelo(par: Parametros) -> dict:
    if par.perfil not in PERFILES:
        raise ValueError(f"unknown profile: {par.perfil}")
    if par.version not in VERSIONES:
        raise ValueError(f"unknown version: {par.version}")
    if par.percentil_tokens is None:
        par.percentil_tokens = "p95" if par.version == "v1" else "media"
    precios = cargar_precios()
    if par.version == "v1":
        tin, tout = tokens_s13("tokens_in", par.percentil_tokens), tokens_s13("tokens_out", par.percentil_tokens)
    elif par.version == "v3":
        t = tokens_v3()
        tin, tout = t["sin_cache"] + t["lectura"] + t["escritura"], t["salida"]
    else:
        tin, tout = tokens_desplegado("tokens_in", par.percentil_tokens), tokens_desplegado("tokens_out", par.percentil_tokens)
    fijas_h = lineas_fijas_hora(par, precios)
    fijas_m = lineas_fijas_mes(par, precios)
    cons = lineas_consulta(par, precios, tin, tout)

    costo_hora = totales(fijas_h)
    costo_fijo_mes = totales(fijas_m) + costo_hora * DIAS_MES * par.horas_dia  # the stack is up horas_dia hours a day
    costo_consulta = totales(cons)
    consultas_mes = par.consultas_dia * DIAS_MES
    total_mes = costo_fijo_mes + costo_consulta * consultas_mes
    parcial = any(l["costo_usd"] is None for l in fijas_h + fijas_m + cons)
    no_medidas = [l["partida"] for l in fijas_h + fijas_m + cons if l["costo_usd"] is None]

    creditos = par.creditos_usd if par.usar_creditos else 0.0
    neto = max(0.0, total_mes - creditos)
    sesion = costo_hora * par.horas_sesion
    return {
        "perfil": par.perfil,
        "parametros": par.__dict__ | {"tokens_in": tin, "tokens_out": tout},
        "fijas_por_hora": fijas_h,
        "fijas_por_mes": fijas_m,
        "por_consulta": cons,
        "costo_por_hora_usd": costo_hora,
        "costo_por_consulta_usd": costo_consulta,
        "costo_fijo_mes_usd": costo_fijo_mes,
        "consultas_mes": consultas_mes,
        "total_mes_usd": total_mes,
        "creditos_aplicados_usd": min(creditos, total_mes),
        "total_mes_neto_usd": neto,
        "parcial": parcial,
        "partidas_no_medidas": no_medidas,
        "sesion_horas": par.horas_sesion,
        "costo_sesion_usd": sesion,
        "sesion_parcial": any(l["costo_usd"] is None for l in fijas_h),
    }


def tabla(res: dict) -> str:
    def f(x):
        return "N" if x is None else f"{x:.6f}"
    out = [f"Profile: {res['perfil']}, version {res['parametros']['version']}  (tokens {res['parametros']['percentil_tokens']}: "
           f"input {res['parametros']['tokens_in']:.0f}, output {res['parametros']['tokens_out']:.0f})", ""]
    out.append("| Item | Frequency | Mark | Amount | USD |")
    out.append("|---|---|---|---|---|")
    for grupo in ("fijas_por_hora", "fijas_por_mes", "por_consulta"):
        for l in res[grupo]:
            out.append(f"| {l['partida']} | {l['frecuencia']} | {l['marca']} | {'N' if l['cantidad'] is None else format(l['cantidad'], '.6g')} {l['unidad']} | {f(l['costo_usd'])} |")
    out.append("")
    out.append(f"Cost per hour (measured): {res['costo_por_hora_usd']:.6f} USD")
    out.append(f"Cost per query (measured): {res['costo_por_consulta_usd']:.8f} USD")
    out.append(f"Month total (measured, {'PARTIAL' if res['parcial'] else 'complete'}): {res['total_mes_usd']:.4f} USD")
    out.append(f"Net of the US$142 credits: {res['total_mes_neto_usd']:.4f} USD")
    if res["partidas_no_medidas"]:
        out.append("Not measured (N, outside the total): " + "; ".join(res["partidas_no_medidas"]))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--perfil", "--profile", choices=sorted(PERFILES), default="lab")
    ap.add_argument("--consultas-dia", "--queries-per-day", type=float, default=100.0, metavar="QUERIES_PER_DAY")
    ap.add_argument("--version", choices=sorted(VERSIONES), default="v2")
    ap.add_argument("--tokens", choices=["media", "p50", "p95", "max"], default=None)
    ap.add_argument("--horas-dia", "--hours-per-day", type=float, default=8.0, metavar="HOURS_PER_DAY")
    ap.add_argument("--horas-sesion", "--session-hours", type=float, default=0.0, metavar="SESSION_HOURS")
    ap.add_argument("--usuarios", "--users", type=float, default=10.0, metavar="USERS")
    ap.add_argument("--sin-creditos", "--no-credits", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    par = Parametros(perfil=a.perfil, consultas_dia=a.consultas_dia, version=a.version, percentil_tokens=a.tokens,
                     horas_dia=a.horas_dia, horas_sesion=a.horas_sesion, usuarios=a.usuarios,
                     usar_creditos=not a.sin_creditos)
    res = modelo(par)
    print(json.dumps(res, indent=2, ensure_ascii=False) if a.json else tabla(res))


if __name__ == "__main__":
    main()
