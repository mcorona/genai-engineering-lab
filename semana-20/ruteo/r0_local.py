"""Week 20, activity 4, R0: the local Haiku 4.5 baseline (week 19 hand-off, item 6; Manuel's decision of 2026-11-23).

    semana-20/ruteo/base_local.sh                                   the local CI database (Docker, seed 42), $0
    .venv/bin/python semana-20/ruteo/r0_local.py                    simulation: week 13's recorded turns, $0
    AWS_PROFILE=... .venv/bin/python semana-20/ruteo/r0_local.py --si   the run: Bedrock from the Mac (costs money)
    .venv/bin/python semana-20/ruteo/r0_local.py --informe          the comparison, offline

Week 17's 20/20 was Haiku 5.5 run locally; week 20's baseline (16/20) is Haiku 4.5 on AWS. R0 runs the same 20 tasks
(the 10 + 10 CI golden tasks) with week 17's local harness (`semana-17/ci/eval_ci.py`, `correr_subconjunto`: the
guarded agent, the real tools on the CI database, the week 13 verifier, the week 17 graders), changing only what makes
it Haiku 4.5 as deployed:
- the model is the deployed agent's, through Bedrock: the `us.` cross-Region profile of `semana-19/ia/config.py`
  (MODELO_ID), called from the Mac with the operator's AWS credentials (no Anthropic API key);
- the request is week 19's Converse adapter's (`semana-19/agente/converse_adaptador.py`, loaded by its path), so it
  goes without `output_config.effort`, as deployed. Without the guardrail and without a cache point: week 17's local
  harness had neither, and both belong to the port (the guardrail) or to an optimization (the cache);
- the per-task budget is the deployed ceiling of week 20 (0.12 USD and 100,000 tokens), read from
  `semana-19/agente/construccion.py`, so the budget cuts no task, as in the corrected run.

So R0 against week 17 is the model's effect, and R0 against the deployed runs (the corrected run and the cache run) is
the port's. Its failures are put beside theirs (c02 and r05, in both languages; c06-en in the cache run).

The run has its own cap in dollars and in tokens (`TOPE_USD`, `TOPE_TOKENS`), over its own calls only, checked before
every model call: the call that would start past it is refused, its task ends in `error` and is reported as not run.
Costs are priced at the Price List's regional Haiku 4.5 SKUs (`SKUS`, in `resultados/precios.json`), the price of the
`us.` profile.

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
CONFIG_IA = S19 / "ia" / "config.py"
ADAPTADOR = S19 / "agente" / "converse_adaptador.py"
PRECIOS = S20 / "resultados" / "precios.json"
LINEA_BASE_S17 = S17 / "resultados" / "eval_ci_local.json"
DETALLE_DESPLEGADA = S20 / "resultados" / "corrida_corregida_detalle.jsonl"
DETALLE_CACHE = S20 / "resultados" / "cache_detalle.jsonl"
SALIDA = S20 / "resultados" / "ruteo"
CRUDO = SALIDA / "r0_local.json"
COMPARACION = SALIDA / "r0_comparacion.json"

REGION = "us-east-1"
# The name week 17's per-task budget prices the model by (semana-07/prices.json, the same 1.1 and 5.5 as the SKUs).
MODELO_PRESUPUESTO = "claude-haiku-4-5-20251001"
# Manuel's OK is asked for these caps. The expected spend is the corrected run's for the same 20 tasks without cache:
# 0.927825 USD and 694,197 tokens (656,877 in, 37,320 out), at the same prices.
TOPE_USD = 1.50
TOPE_TOKENS = 1_100_000
COSTO_ESPERADO_TAREA = 0.046
# Claude Haiku 4.5, on-demand, us-east-1, regional (the price of the us. profile): input and output tokens.
SKUS = {"entrada": "JQDUC8Q4K8C6GSGH", "salida": "X629GDA2GXAP6R54"}
MOTIVO_TOPE = "tope de la corrida"
CAMPOS_FILA = {"id", "corrida", "estado", "motivo", "exito", "usd", "tope_usd", "sobre_el_tope", "trayectoria_ok",
               "fallan"}


class TopeAlcanzado(RuntimeError):
    pass


class Tope:
    """The run's cap in USD and in tokens, over this run's own model calls. One writer: the calls go one at a time."""

    def __init__(self, usd: float, tokens: int, entrada_1m: float, salida_1m: float):
        self.usd, self.tokens, self.entrada_1m, self.salida_1m = usd, tokens, entrada_1m, salida_1m
        self.gastado = 0.0
        self.tokens_gastados = 0
        self.llamadas = 0

    def envolver(self, api: Callable[[dict], dict]) -> Callable[[dict], dict]:
        def con_tope(cuerpo: dict) -> dict:
            if self.gastado >= self.usd or self.tokens_gastados >= self.tokens:
                raise TopeAlcanzado(f"{MOTIVO_TOPE} ({self.usd} USD, {self.tokens} tokens)")
            resp = api(cuerpo)
            uso = resp.get("usage", {})
            tin, tout = uso.get("input_tokens", 0), uso.get("output_tokens", 0)
            self.gastado += (tin * self.entrada_1m + tout * self.salida_1m) / 1e6
            self.tokens_gastados += tin + tout
            self.llamadas += 1
            return resp
        return con_tope


def _precio_1m(sku: str) -> float:
    filas = json.loads(PRECIOS.read_text(encoding="utf-8"))["precios"]
    (fila,) = [f for f in filas if f["sku"] == sku]
    (precio,) = fila["precios"]
    assert precio["unidad"] == "1M tokens", precio
    return precio["usd"]


def tope_de_haiku45(usd: float, tokens: int) -> Tope:
    return Tope(usd=usd, tokens=tokens, entrada_1m=_precio_1m(SKUS["entrada"]), salida_1m=_precio_1m(SKUS["salida"]))


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def api_bedrock(llamar: Callable[[dict], dict], tope: Tope) -> Callable[[dict], dict]:
    """The loop's `api=`: week 19's Converse adapter (no guardrail, no cache point) behind the run's cap. `llamar` is
    `cliente.converse(**req)` or a fake in tests."""
    adaptador = _cargar("converse_adaptador_s19_r0", ADAPTADOR)   # by path: semana-13's `agente` is on sys.path
    return tope.envolver(adaptador.api_converse(llamar, modelo_id=MODELO_ID))


def _constante(archivo: Path, nombre: str):
    for nodo in ast.parse(archivo.read_text(encoding="utf-8")).body:
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise LookupError(f"{nombre} is not in {archivo}")


MODELO_ID = _constante(CONFIG_IA, "MODELO_ID")


def politica():
    """Week 17's policy with only the task limit: the deployed ceiling (`_TECHO_SEMANA20`), as the Lambda builds it."""
    if str(S17) not in sys.path:
        sys.path.insert(0, str(S17))
    from presupuestos.politica import Limite, Politica
    return Politica(tarea=Limite(**_constante(CONSTRUCCION, "_TECHO_SEMANA20")))


def faltantes(entorno, si: bool) -> list[str]:
    return [v for v in (["AWS_PROFILE"] if si else []) + ["PG_ADMIN_DSN"] if not entorno.get(v)]


def crudo(sub: dict, *, tope: Tope, modo: str, segundos: float) -> dict:
    return {"fecha": time.strftime("%Y-%m-%d"), "modelo": MODELO_ID, "modo": modo, "tope_usd": tope.usd,
            "tope_tokens": tope.tokens, "gastado_usd": round(tope.gastado, 8), "tokens": tope.tokens_gastados,
            "llamadas": tope.llamadas, "segundos": segundos,
            "filas": [{k: v for k, v in f.items() if k in CAMPOS_FILA} for f in sub["filas"]],
            "presupuesto": sub["presupuesto"], "omisiones_del_esquema": sub["omisiones_del_esquema"]}


# ---------------------------------------------------------------- the report (offline, its own process)

def semana17(archivo: Path = LINEA_BASE_S17) -> dict[str, bool]:
    return {f["id"]: bool(f["exito"]) for f in json.loads(archivo.read_text(encoding="utf-8"))["subconjunto"]["filas"]}


def corrida_aws(archivo: Path) -> dict[str, dict]:
    """A deployed run of week 20 (the corrected run of activity 1, the cache run of activity 3): its 20 main tasks
    without the warm-up, each with its success and its state."""
    filas = [json.loads(linea) for linea in archivo.read_text(encoding="utf-8").splitlines() if linea.strip()]
    return {f["id"]: {"exito": bool(f["exito"]), "estado": f["estado"]} for f in filas if f["fase"] != "calentamiento"}


def _regla():
    """Week 10's rule as week 19's eval applies it (eval_aws.regla_semana10)."""
    for ruta in (S19, S17):
        if str(ruta) not in sys.path:
            sys.path.insert(0, str(ruta))
    return _cargar("eval_aws_s19_r0", S19 / "eval" / "eval_aws.py").regla_semana10


def silenciosamente_equivocadas(filas: dict[str, dict]) -> list[str]:
    """Answered tasks the verifier rejects: the state says `respondida` and the success says no."""
    return sorted(i for i, f in filas.items() if f["estado"] == "respondida" and not f["exito"])


def conclusion(r0: dict[str, bool], s17: dict[str, bool], fallan_aws: set[str], regresion: bool) -> dict:
    """Fixed before the run. The model's effect: tasks R0 fails that week 17 passed. The port's: tasks a deployed run
    fails that R0 passes. R1 is deployed, so its week 10 verdict is always against the cache run (same port, same
    cache); when R0 regresses against week 17, the gap is Haiku 4.5's and escalating is meant to close it, so R1 is
    also put against week 17's 20/20. When it does not, that gap is the port's and no router can close it."""
    modelo = sorted(i for i, ok in r0.items() if not ok and s17.get(i))
    port = sorted(i for i in fallan_aws if r0.get(i))
    causa = ("ambos" if port else "modelo") if regresion else "port"
    return {"efecto_modelo": modelo, "efecto_port": port, "causa": causa,
            "linea_base_r1": {"veredicto_contra": "cache", "tambien_contra_semana17": regresion}}


def comparar(filas: list[dict], *, s17: dict[str, bool], desplegada: dict[str, dict], cache: dict[str, dict]) -> dict:
    regla = _regla()
    r0 = {f["id"]: bool(f["exito"]) for f in filas}
    grupos = {g: [i for i in r0 if g == "total" or i.endswith(f"-{g}")] for g in ("es", "en", "total")}
    reglas = {g: regla(sum(r0[i] for i in ids) / len(ids), sum(s17[i] for i in ids) / len(ids), len(ids))
              for g, ids in grupos.items()}
    regresion = any(r["regresion"] for r in reglas.values())
    corridas = {"r0": {f["id"]: {"exito": bool(f["exito"]), "estado": f["estado"]} for f in filas},
                "desplegada": desplegada, "cache": cache}
    fallan = {n: sorted(i for i, f in c.items() if not f["exito"] and i in r0) for n, c in corridas.items()}
    return {
        "exito": {g: f"{sum(r0[i] for i in ids)}/{len(ids)}" for g, ids in grupos.items()},
        "regla_semana10": reglas,
        "regresion": regresion,
        "fallan": fallan,
        "silenciosamente_equivocadas": {n: silenciosamente_equivocadas(c) for n, c in corridas.items()},
        "conclusion": conclusion(r0, s17, set(fallan["desplegada"]) | set(fallan["cache"]), regresion),
        "no_corridas": sorted(f["id"] for f in filas if f["estado"] == "error" and MOTIVO_TOPE in str(f.get("motivo"))),
        "por_tarea": {i: {"r0": r0[i], "semana17": s17.get(i), "desplegada": desplegada[i]["exito"],
                          "cache": cache[i]["exito"]} for i in sorted(r0)},
    }


# ---------------------------------------------------------------- the run

def correr(si: bool, tope: Tope) -> dict:
    ec = _cargar("eval_ci_s17_r0", S17 / "ci" / "eval_ci.py")
    api = None
    if si:
        import boto3
        cliente = boto3.client("bedrock-runtime", region_name=REGION)   # AWS_PROFILE's credentials
        api = api_bedrock(lambda req: cliente.converse(**req), tope)
    t0 = time.time()
    sub = ec.correr_subconjunto(not si, None, modelo=MODELO_PRESUPUESTO, politica=politica(), api=api)
    return crudo(sub, tope=tope, modo="modelo real" if si else "simulacion", segundos=round(time.time() - t0, 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--si", "--yes", action="store_true", help="the real run: Bedrock from the Mac, costs money")
    ap.add_argument("--informe", "--report", action="store_true", help="the comparison, offline")
    ap.add_argument("--tope-usd", "--max-usd", type=float, default=TOPE_USD, metavar="MAX_USD")
    ap.add_argument("--tope-tokens", "--max-tokens", type=int, default=TOPE_TOKENS, metavar="MAX_TOKENS")
    a = ap.parse_args(argv)
    if a.informe:
        inf = comparar(json.loads(CRUDO.read_text(encoding="utf-8"))["filas"], s17=semana17(),
                       desplegada=corrida_aws(DETALLE_DESPLEGADA), cache=corrida_aws(DETALLE_CACHE))
        COMPARACION.write_text(json.dumps(inf, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: inf[k] for k in ("exito", "regresion", "fallan", "silenciosamente_equivocadas", "conclusion",
                                              "no_corridas")}, ensure_ascii=False, indent=1))
        return 0
    falta = faltantes(os.environ, a.si)
    if falta:
        print(f"[r0] missing in the environment: {', '.join(falta)} (semana-20/ruteo/base_local.sh prints the DSN)",
              file=sys.stderr)
        return 2
    if a.si and CRUDO.exists():
        print(f"[r0] {CRUDO} exists: move it aside and lower the caps by its gastado_usd and tokens before another attempt",
              file=sys.stderr)
        return 2
    tope = tope_de_haiku45(a.tope_usd, a.tope_tokens)
    print(f"[r0] 20 tasks · {MODELO_ID} · {'REAL model, Bedrock' if a.si else 'simulation (week 13 recorded turns), $0'} · "
          f"expected {20 * COSTO_ESPERADO_TAREA:.2f} USD · run cap {tope.usd:.2f} USD / {tope.tokens} tokens · task ceiling "
          f"{politica().tarea.usd} USD / {politica().tarea.tokens} tokens", flush=True)
    salida = correr(a.si, tope)
    exitos = sum(f["exito"] for f in salida["filas"])
    print(f"[r0] {exitos}/{len(salida['filas'])} · {salida['gastado_usd']:.6f} USD · {salida['tokens']} tokens · "
          f"{salida['llamadas']} calls")
    if a.si:
        SALIDA.mkdir(parents=True, exist_ok=True)
        CRUDO.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[r0] {CRUDO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
