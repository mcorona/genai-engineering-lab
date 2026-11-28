"""Week 20, activity 4, R0: the local Haiku 4.5 baseline (week 19 hand-off, item 6; Manuel's decision of 2026-11-23).

    semana-20/ruteo/base_local.sh                                   the local CI database (Docker, seed 42), $0
    .venv/bin/python semana-20/ruteo/r0_local.py                    simulation: week 13's recorded turns, $0
    .venv/bin/python semana-20/ruteo/r0_local.py --si               the run: Anthropic's API, Haiku 4.5 (costs money)
    .venv/bin/python semana-20/ruteo/r0_local.py --informe          the comparison, offline

Week 17's 20/20 was Haiku 5.5 run locally; week 20's baseline (16/20) is Haiku 4.5 on AWS. R0 runs the same 20 tasks
(the 10 + 10 CI golden tasks) with week 17's local harness (`semana-17/ci/eval_ci.py`, `correr_subconjunto`: the
guarded agent, the real tools on the CI database, the week 13 verifier, the week 17 graders), changing only what makes
it Haiku 4.5 as deployed:
- the model is the deployed agent's (`claude-haiku-4-5-20251001`);
- the request goes without `output_config.effort`, as the Converse adapter sends it (Converse has no equivalent);
- the per-task budget is the deployed ceiling of week 20 (0.12 USD and 100,000 tokens), read from
  `semana-19/agente/construccion.py`, so the budget cuts no task, as in the corrected run.

So R0 against week 17 is the model's effect, and R0 against the deployed run is the port's. Its four failures are put
beside the deployed run's (c02 and r05, in both languages).

The run has its own cap (`TOPE_USD`), checked before every model call: the call that would start past it is refused,
its task ends in `error` and is reported as not run. Costs are priced at week 7's table for Haiku 4.5 (1.1 and 5.5 USD
per million, the regional Bedrock price), an upper bound of Anthropic's API price.

The raw file (`resultados/ruteo/r0_local.json`) has ids and numbers only: no prompt, SQL, answer or row.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

S20 = Path(__file__).resolve().parents[1]
RAIZ = S20.parent
S17 = RAIZ / "semana-17"
S19 = RAIZ / "semana-19"
CONSTRUCCION = S19 / "agente" / "construccion.py"
PRECIOS = RAIZ / "semana-07" / "prices.json"
LINEA_BASE_S17 = S17 / "resultados" / "eval_ci_local.json"
DETALLE_DESPLEGADA = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
SALIDA = S20 / "resultados" / "ruteo"
CRUDO = SALIDA / "r0_local.json"
COMPARACION = SALIDA / "r0_comparacion.json"

MODELO = "claude-haiku-4-5-20251001"
# Manuel's OK is asked for this cap. The expected spend is the corrected run's 0.927825 USD for the same 20 tasks
# (0.046 per task), at the same prices.
TOPE_USD = 1.50
COSTO_ESPERADO_TAREA = 0.046
MOTIVO_TOPE = "tope de la corrida"
CAMPOS_FILA = {"id", "corrida", "estado", "motivo", "exito", "usd", "tope_usd", "sobre_el_tope", "trayectoria_ok",
               "fallan"}


class TopeAlcanzado(RuntimeError):
    pass


def como_el_desplegado(api: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """The loop's body as the deployed adapter sends it: without `output_config` (effort has no Converse equivalent)."""
    return lambda cuerpo: api({k: v for k, v in cuerpo.items() if k != "output_config"})


class Tope:
    """The run's cap in USD, over every model call of the run. One writer: the calls go one at a time."""

    def __init__(self, usd: float, entrada_1m: float, salida_1m: float):
        self.usd, self.entrada_1m, self.salida_1m = usd, entrada_1m, salida_1m
        self.gastado = 0.0
        self.llamadas = 0

    def envolver(self, api: Callable[[dict], dict]) -> Callable[[dict], dict]:
        def con_tope(cuerpo: dict) -> dict:
            if self.gastado >= self.usd:
                raise TopeAlcanzado(f"{MOTIVO_TOPE} ({self.usd} USD)")
            resp = api(cuerpo)
            uso = resp.get("usage", {})
            self.gastado += (uso.get("input_tokens", 0) * self.entrada_1m + uso.get("output_tokens", 0) * self.salida_1m) / 1e6
            self.llamadas += 1
            return resp
        return con_tope


def tope_de_haiku45(usd: float) -> Tope:
    p = json.loads(PRECIOS.read_text(encoding="utf-8"))[f"anthropic:{MODELO}"]
    return Tope(usd=usd, entrada_1m=p["in"], salida_1m=p["out"])


def _constante(archivo: Path, nombre: str):
    for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise LookupError(f"{nombre} is not in {archivo}")


def politica():
    """Week 17's policy with only the task limit: the deployed ceiling (`_TECHO_SEMANA20`), as the Lambda builds it."""
    if str(S17) not in sys.path:
        sys.path.insert(0, str(S17))
    from presupuestos.politica import Limite, Politica
    return Politica(tarea=Limite(**_constante(CONSTRUCCION, "_TECHO_SEMANA20")))


def faltantes(entorno, si: bool) -> list[str]:
    return [v for v in (["ANTHROPIC_API_KEY"] if si else []) + ["PG_ADMIN_DSN"] if not entorno.get(v)]


def crudo(sub: dict, *, tope: Tope, modo: str, segundos: float) -> dict:
    return {"fecha": time.strftime("%Y-%m-%d"), "modelo": MODELO, "modo": modo, "tope_usd": tope.usd,
            "gastado_usd": round(tope.gastado, 8), "llamadas": tope.llamadas, "segundos": segundos,
            "filas": [{k: v for k, v in f.items() if k in CAMPOS_FILA} for f in sub["filas"]],
            "presupuesto": sub["presupuesto"], "omisiones_del_esquema": sub["omisiones_del_esquema"]}


# ---------------------------------------------------------------- the report (offline, its own process)

def semana17(archivo: Path = LINEA_BASE_S17) -> dict[str, bool]:
    return {f["id"]: bool(f["exito"]) for f in json.loads(archivo.read_text(encoding="utf-8"))["subconjunto"]["filas"]}


def desplegada(archivo: Path = DETALLE_DESPLEGADA) -> dict[str, bool]:
    """The corrected run of week 20 (activity 1, the baseline), its 20 main tasks without the warm-up."""
    filas = [json.loads(linea) for linea in archivo.read_text(encoding="utf-8").splitlines() if linea.strip()]
    return {f["id"]: bool(f["exito"]) for f in filas if f["fase"] != "calentamiento"}


def _regla():
    """Week 10's rule as week 19's eval applies it (eval_aws.regla_semana10)."""
    for ruta in (S19, S17):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    spec = importlib.util.spec_from_file_location("eval_aws_s19_r0", S19 / "eval" / "eval_aws.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.regla_semana10


def comparar(filas: list[dict], *, s17: dict[str, bool], desplegada: dict[str, bool]) -> dict:
    regla = _regla()
    r0 = {f["id"]: bool(f["exito"]) for f in filas}
    grupos = {g: [i for i in r0 if g == "total" or i.endswith(f"-{g}")] for g in ("es", "en", "total")}
    reglas = {g: regla(sum(r0[i] for i in ids) / len(ids), sum(s17[i] for i in ids) / len(ids), len(ids))
              for g, ids in grupos.items()}
    falla_r0 = {i for i, ok in r0.items() if not ok}
    falla_d = {i for i, ok in desplegada.items() if not ok and i in r0}
    return {
        "exito": {g: f"{sum(r0[i] for i in ids)}/{len(ids)}" for g, ids in grupos.items()},
        "regla_semana10": reglas,
        "regresion": any(r["regresion"] for r in reglas.values()),
        "fallan": {"r0": sorted(falla_r0), "desplegada": sorted(falla_d), "en_ambas": sorted(falla_r0 & falla_d),
                   "solo_r0": sorted(falla_r0 - falla_d), "solo_desplegada": sorted(falla_d - falla_r0)},
        "no_corridas": sorted(f["id"] for f in filas if f["estado"] == "error" and MOTIVO_TOPE in str(f.get("motivo"))),
        "por_tarea": {i: {"r0": r0[i], "semana17": s17.get(i), "desplegada": desplegada.get(i)} for i in sorted(r0)},
    }


# ---------------------------------------------------------------- the run

def correr(si: bool, tope: Tope) -> dict:
    spec = importlib.util.spec_from_file_location("eval_ci_s17_r0", S17 / "ci" / "eval_ci.py")
    ec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ec)
    api = None
    if si:
        from agente.loop import api_anthropic   # week 13's, on the path eval_ci set
        api = tope.envolver(como_el_desplegado(api_anthropic))
    t0 = time.time()
    sub = ec.correr_subconjunto(not si, None, modelo=MODELO, politica=politica(), api=api)
    return crudo(sub, tope=tope, modo="modelo real" if si else "simulacion", segundos=round(time.time() - t0, 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--si", "--yes", action="store_true", help="the real run: Anthropic's API, costs money")
    ap.add_argument("--informe", "--report", action="store_true", help="the comparison, offline")
    ap.add_argument("--tope-usd", "--max-usd", type=float, default=TOPE_USD, metavar="MAX_USD")
    a = ap.parse_args(argv)
    if a.informe:
        inf = comparar(json.loads(CRUDO.read_text(encoding="utf-8"))["filas"], s17=semana17(), desplegada=desplegada())
        COMPARACION.write_text(json.dumps(inf, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: inf[k] for k in ("exito", "regresion", "fallan", "no_corridas")}, ensure_ascii=False, indent=1))
        return 0
    falta = faltantes(os.environ, a.si)
    if falta:
        print(f"[r0] missing in the environment: {', '.join(falta)} (semana-20/ruteo/base_local.sh prints the DSN)",
              file=sys.stderr)
        return 2
    if a.si and CRUDO.exists():
        print(f"[r0] {CRUDO} exists: move it aside and lower --tope-usd by its gastado_usd before another attempt",
              file=sys.stderr)
        return 2
    tope = tope_de_haiku45(a.tope_usd)
    print(f"[r0] 20 tasks · {MODELO} · {'REAL model' if a.si else 'simulation (week 13 recorded turns), $0'} · "
          f"expected {20 * COSTO_ESPERADO_TAREA:.2f} USD · run cap {tope.usd:.2f} USD · task ceiling "
          f"{politica().tarea.usd} USD / {politica().tarea.tokens} tokens", flush=True)
    salida = correr(a.si, tope)
    exitos = sum(f["exito"] for f in salida["filas"])
    print(f"[r0] {exitos}/{len(salida['filas'])} · {salida['gastado_usd']:.6f} USD · {salida['llamadas']} calls")
    if a.si:
        SALIDA.mkdir(parents=True, exist_ok=True)
        CRUDO.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[r0] {CRUDO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
