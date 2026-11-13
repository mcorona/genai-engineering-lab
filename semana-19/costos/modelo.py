"""Week 19, activity 2: cost model for the LegacyBridge stack (lab and prod). Offline, $0.

Prices come from precios.json, each with its source. Token percentiles come from the week 13 detail.
A line whose price is not measured (null, mark N) is listed but NOT added to the total: the output
says so (`parcial`), it is never counted as 0.
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


@dataclass
class Parametros:
    perfil: str = "lab"
    consultas_dia: float = 100.0
    percentil_tokens: str = "p95"      # p50 | p95 | max
    horas_dia: float = 8.0
    horas_sesion: float = 0.0          # para la estimación de la actividad 3
    usuarios: float = 10.0             # MAU de Cognito
    memoria_gb: float = 0.5            # Lambda, supuesto declarado
    duracion_s: float = 3.0            # Lambda por consulta, supuesto declarado
    consultas_kb_por_consulta: float = 1.0
    tokens_consulta_embedding: float = 50.0
    log_kb_por_consulta: float = 20.0  # KB de log por consulta, supuesto declarado
    llamadas_gateway_por_consulta: float = 0.0
    aprobaciones_dia: float = 0.0      # proponer_orden_compra con aprobación
    transiciones_por_aprobacion: float = 6.0
    gb_endpoint_mes: float = 1.0
    creditos_usd: float = 142.0        # H5: sin vencimiento (dato de Manuel, D)
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
    h.append(_linea("KMS, llaves administradas (prorrateado)", precios, "kms_llave_mes",
                    pf["llaves_kms"] / HORAS_MES, "llave-hora", "por hora"))
    h.append(_linea("RDS db.t4g.micro, instancia", precios, "rds_t4g_micro_hora", 1.0, "instancia-hora", "por hora"))
    h.append(_linea("RDS gp3, 20 GB (prorrateado)", precios, "rds_gp3_gb_mes", 20.0 / HORAS_MES, "GB-hora", "por hora"))
    if pf["rds_multi_az"]:
        h.append(_linea("RDS Multi-AZ, instancia adicional", precios, "rds_multi_az_hora", 1.0, "instancia-hora", "por hora",
                        "perfil prod: su precio no está medido"))
    h.append(_linea("IPv4 pública en uso", precios, "ipv4_hora", float(pf["ipv4"]), "dirección-hora", "por hora"))
    h.append(_linea("Endpoints de interfaz de VPC (endpoints x AZ-hora)", precios, "endpoint_interfaz_hora_az",
                    float(pf["endpoints"] * pf["azs"]), "endpoint-AZ-hora", "por hora"))
    return h


def lineas_fijas_mes(par: Parametros, precios: dict) -> list[dict]:
    pf = PERFILES[par.perfil]
    m = []
    m.append(_linea("Cognito, MAU", precios, "cognito_mau", par.usuarios, "MAU", "por mes"))
    m.append(_linea("CloudWatch Logs, almacenamiento", precios, "cloudwatch_almacenamiento_gb_mes", pf["log_gb"],
                    "GB-mes", "por mes"))
    m.append(_linea("AWS Budgets, 1 presupuesto (dentro de 62 budget-days gratis)", precios, "budgets_budget_dia", 30.0, "budget-days", "por mes"))
    m.append(_linea("Endpoints de VPC, datos procesados", precios, "endpoint_interfaz_gb_procesado",
                    par.gb_endpoint_mes, "GB", "por mes"))
    m.append(_linea("Step Functions, transiciones por aprobación", precios, "step_functions_transicion",
                    par.aprobaciones_dia * DIAS_MES * par.transiciones_por_aprobacion, "transiciones", "por mes"))
    return m


def lineas_consulta(par: Parametros, precios: dict, tokens_in: float, tokens_out: float) -> list[dict]:
    c = []
    c.append(_linea("Haiku 4.5 (us.), tokens de entrada", precios, "haiku45_entrada_1m", tokens_in / 1e6,
                    "M tokens", "por consulta", f"{par.percentil_tokens} de la semana 13"))
    c.append(_linea("Haiku 4.5 (us.), tokens de salida", precios, "haiku45_salida_1m", tokens_out / 1e6,
                    "M tokens", "por consulta", f"{par.percentil_tokens} de la semana 13"))
    c.append(_linea("Lambda, GB-segundo", precios, "lambda_arm_gb_s", par.memoria_gb * par.duracion_s,
                    "GB-s", "por consulta", f"memoria {par.memoria_gb} GB y {par.duracion_s} s (supuesto)"))
    c.append(_linea("Lambda, solicitudes", precios, "lambda_solicitud", 1.0, "solicitud", "por consulta"))
    c.append(_linea("API Gateway HTTP API, solicitudes", precios, "apigw_http_solicitud", 1.0, "solicitud", "por consulta"))
    c.append(_linea("Titan V2, embedding de la consulta", precios, "titan_v2_1k_tokens",
                    par.consultas_kb_por_consulta * par.tokens_consulta_embedding / 1000.0, "K tokens", "por consulta"))
    c.append(_linea("CloudWatch Logs, ingesta", precios, "cloudwatch_ingesta_gb",
                    par.log_kb_por_consulta / 1e6, "GB", "por consulta"))
    c.append(_linea("AgentCore Gateway, invocaciones", precios, "agentcore_gateway_invocacion",
                    par.llamadas_gateway_por_consulta, "invocaciones", "por consulta"))
    return c


def totales(lineas: list[dict]) -> float:
    return sum(l["costo_usd"] for l in lineas if l["costo_usd"] is not None)


def estimacion_base_hora(perfil: str = "lab") -> dict:
    """Stack base de la actividad 3 (KMS, VPC endpoints, IAM, presupuesto), por hora."""
    precios = cargar_precios()
    par = Parametros(perfil=perfil)
    lineas = [l for l in lineas_fijas_hora(par, precios) if l["partida"].startswith(("KMS", "Endpoints de interfaz"))]
    presupuesto = _linea("AWS Budgets, 1 presupuesto", precios, "budgets_budget_dia", 1.0 / 24, "budget-day/24", "por hora")
    lineas.append(presupuesto)
    return {"perfil": perfil, "lineas": lineas, "por_hora_usd": totales(lineas), "parcial": any(l["costo_usd"] is None for l in lineas)}


def modelo(par: Parametros) -> dict:
    if par.perfil not in PERFILES:
        raise ValueError(f"perfil desconocido: {par.perfil}")
    precios = cargar_precios()
    tin = tokens_s13("tokens_in", par.percentil_tokens)
    tout = tokens_s13("tokens_out", par.percentil_tokens)
    fijas_h = lineas_fijas_hora(par, precios)
    fijas_m = lineas_fijas_mes(par, precios)
    cons = lineas_consulta(par, precios, tin, tout)

    costo_hora = totales(fijas_h)
    costo_fijo_mes = totales(fijas_m) + costo_hora * DIAS_MES * par.horas_dia  # stack encendido horas_dia por día
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
    out = [f"Perfil: {res['perfil']}  (tokens {res['parametros']['percentil_tokens']}: "
           f"entrada {res['parametros']['tokens_in']:.0f}, salida {res['parametros']['tokens_out']:.0f})", ""]
    out.append("| Partida | Frecuencia | Marca | Cantidad | Costo USD |")
    out.append("|---|---|---|---|---|")
    for grupo in ("fijas_por_hora", "fijas_por_mes", "por_consulta"):
        for l in res[grupo]:
            out.append(f"| {l['partida']} | {l['frecuencia']} | {l['marca']} | {l['cantidad']:.6g} {l['unidad']} | {f(l['costo_usd'])} |")
    out.append("")
    out.append(f"Costo por hora (medido): {res['costo_por_hora_usd']:.6f} USD")
    out.append(f"Costo por consulta (medido): {res['costo_por_consulta_usd']:.8f} USD")
    out.append(f"Total del mes (medido, {'PARCIAL' if res['parcial'] else 'completo'}): {res['total_mes_usd']:.4f} USD")
    out.append(f"Neto con créditos de US$142: {res['total_mes_neto_usd']:.4f} USD")
    if res["partidas_no_medidas"]:
        out.append("No medidas (N, fuera del total): " + "; ".join(res["partidas_no_medidas"]))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--perfil", choices=sorted(PERFILES), default="lab")
    ap.add_argument("--consultas-dia", type=float, default=100.0)
    ap.add_argument("--tokens", choices=["p50", "p95", "max"], default="p95")
    ap.add_argument("--horas-dia", type=float, default=8.0)
    ap.add_argument("--horas-sesion", type=float, default=0.0)
    ap.add_argument("--usuarios", type=float, default=10.0)
    ap.add_argument("--sin-creditos", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    par = Parametros(perfil=a.perfil, consultas_dia=a.consultas_dia, percentil_tokens=a.tokens,
                     horas_dia=a.horas_dia, horas_sesion=a.horas_sesion, usuarios=a.usuarios,
                     usar_creditos=not a.sin_creditos)
    res = modelo(par)
    print(json.dumps(res, indent=2, ensure_ascii=False) if a.json else tabla(res))


if __name__ == "__main__":
    main()
