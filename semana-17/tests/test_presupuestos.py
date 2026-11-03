"""Activity 4 (token and cost budgets), no API ($0).

Three layers, from the cheapest to the most real:

* the policy and the store, as pure code and a SQLite file (thousands of cases, threads);
* the agent layer around a fake model call, with the same code the loop uses;
* the real week 13 loop, the week 14 MCP client, the OAuth-protected server and PostgreSQL, with the scripted model.

The calibration is checked against the data it comes from (the 252 committed runs of week 13), and the report of the paid
evaluation, once it exists, against the policy."""
import json
import random
import sys
import threading
import time
from pathlib import Path

import pytest

S17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(S17))

from instrumentacion import esquema as E  # noqa: E402
from instrumentacion.laboratorio import Laboratorio, configurar_trazas, resumen  # noqa: E402
from instrumentacion.modelo_guionado import turnos_principal  # noqa: E402
from presupuestos import calibracion as CAL  # noqa: E402
from presupuestos import estimacion as EST  # noqa: E402
from presupuestos.agente_presupuestado import (  # noqa: E402
    _PRES,
    AgentePresupuestado,
    EstadoPresupuesto,
    PresupuestoAgotado,
    api_presupuestada,
)
from presupuestos.almacen import AlmacenGasto  # noqa: E402
from presupuestos.politica import Gasto, Limite, Politica, decidir  # noqa: E402

M, S = "claude-haiku-5-5", "claude-sonnet-5-5"
POLITICA_FILE = S17 / "presupuestos" / "politica_calibrada.json"
REPORTE = json.loads((S17 / "resultados" / "presupuestos_calibracion.json").read_text(encoding="utf-8"))


def pol(**kw) -> Politica:
    return Politica(Limite(0.01, 100_000), min_salida=500, max_salida=4000, **kw)


# ---------- the policy ----------

def test_permite_con_el_max_tokens_que_el_presupuesto_paga():
    d = decidir(pol(), M, 10_000, {"task": Gasto(0.01, 100_000)})
    assert (d.accion, d.motivo, d.max_tokens) == ("allow", "ok", 4000)                    # never above the loop's own limit
    d = decidir(pol(), M, 10_000, {"task": Gasto(0.0015, 100_000)})                      # 0.0015 - 10,000 x $0.1/M leaves 1,000 tokens
    assert (d.accion, d.max_tokens) == ("allow", 1000)
    assert d.estimado_usd == pytest.approx(10_000 * 0.1 / 1e6 + 1000 * 0.5 / 1e6)
    assert d.estimado_tokens == 11_000


def test_para_cuando_no_cabe_la_salida_minima_y_nombra_el_alcance_y_la_dimension():
    d = decidir(pol(), M, 10_000, {"task": Gasto(0.0012, 100_000)})                      # 400 tokens of room, 500 needed
    assert (d.accion, d.alcance, d.motivo, d.max_tokens) == ("stop", "task", "usd", 0)
    d = decidir(pol(), M, 10_000, {"task": Gasto(1.0, 10_300)})
    assert (d.accion, d.motivo) == ("stop", "tokens")
    d = decidir(pol(), M, 10_000, {"task": Gasto(0.01, 100_000), "session": Gasto(0.0013, 100_000)})
    assert (d.accion, d.alcance) == ("allow", "session") and d.max_tokens in (599, 600)  # the tightest scope limits the call (floor, never up)
    d = decidir(pol(), M, 10_000, {"task": Gasto(0.01, 100_000), "tenant_day": Gasto(0.0011, 100_000)})
    assert (d.accion, d.alcance, d.motivo) == ("stop", "tenant_day", "usd")


def test_degrada_solo_al_modelo_que_la_politica_nombra():
    p = pol(degradar={S: M})
    d = decidir(p, S, 5000, {"task": Gasto(0.011, 100_000)})                             # Sonnet's prompt alone costs 0.01
    assert (d.accion, d.motivo, d.modelo, d.modelo_origen) == ("degrade", "degradado", M, S) and d.max_tokens >= 500
    assert decidir(p, S, 5000, {"task": Gasto(1.0, 100_000)}).accion == "allow"          # it fits: no degrade
    assert decidir(pol(), S, 5000, {"task": Gasto(0.011, 100_000)}).accion == "stop"     # not named: it stops, it does not improvise
    assert decidir(p, M, 5000, {"task": Gasto(0.0001, 100_000)}).accion == "stop"        # nothing cheaper than the cheapest
    suave = pol(degradar={S: M}, umbral_degradar=0.5)
    assert decidir(suave, S, 5000, {"task": Gasto(1.0, 100_000)}, Gasto(0.004, 0)).modelo == S
    assert decidir(suave, S, 5000, {"task": Gasto(1.0, 100_000)}, Gasto(0.006, 0)).modelo == M


def test_el_tramo_de_mas_de_100k_se_cobra_mas():
    assert EST.precio(M, 100_000) == (0.1, 0.5) and EST.precio(M, 100_001) == (0.5, 2.5)
    d = decidir(pol(), M, 150_000, {"task": Gasto(0.1, 1_000_000)})
    assert d.accion == "allow" and d.max_tokens == 4000                                  # room: 10,000 tokens at the higher rate
    assert d.estimado_usd == pytest.approx(150_000 * 0.5 / 1e6 + 4000 * 2.5 / 1e6)       # the whole call is charged at the 100k+ tier
    assert decidir(pol(), M, 150_000, {"task": Gasto(0.0763, 1_000_000)}).max_tokens in (519, 520)     # (0.0763 - 0.075) / 2.5e-6
    assert decidir(pol(), M, 150_000, {"task": Gasto(0.0755, 1_000_000)}).accion == "stop"             # 200 tokens: below the minimum
    with pytest.raises(KeyError):
        EST.precio("claude-inventado")                                                   # no price, no enforcement: never a guess


def test_un_permiso_nunca_cuesta_mas_de_lo_que_queda_en_ningun_alcance():
    azar = random.Random(4)
    permitidas = paradas = 0
    for _ in range(5000):
        restante = {a: Gasto(10 ** azar.uniform(-4, -0.8), int(10 ** azar.uniform(3.5, 6.3))) for a in azar.sample(["task", "session", "tenant_day"], azar.randint(1, 3))}
        restante.setdefault("task", Gasto(10 ** azar.uniform(-4, -0.8), int(10 ** azar.uniform(3.5, 6.3))))
        p = pol(degradar=azar.choice([{}, {S: M}]))
        modelo, est_in = azar.choice([M, S]), int(10 ** azar.uniform(2.7, 5.2))
        d = decidir(p, modelo, est_in, restante)
        if d.accion == "stop":
            paradas += 1
            assert d.max_tokens == 0
            continue
        permitidas += 1
        p_in, p_out = EST.precio(d.modelo, est_in)
        costo_maximo = est_in * p_in / 1e6 + d.max_tokens * p_out / 1e6
        assert p.min_salida <= d.max_tokens <= p.max_salida
        for r in restante.values():
            assert costo_maximo <= r.usd + 1e-12 and est_in + d.max_tokens <= r.tokens
        assert d.estimado_usd == pytest.approx(costo_maximo)
    assert permitidas > 500 and paradas > 500                                            # both branches were exercised


def test_la_estimacion_crece_con_lo_que_entra_y_cuenta_la_cache_como_entrada():
    a = EST.entrada_siguiente(5000, 300, {"role": "user", "content": "x" * 100})
    b = EST.entrada_siguiente(5000, 300, {"role": "user", "content": "x" * 5000})
    assert 5300 * EST.MARGEN_ENTRADA <= a < b
    usd, tok = EST.costo_real(M, {"input_tokens": 1000, "cache_read_input_tokens": 800, "cache_creation_input_tokens": 200,
                                  "output_tokens": 100})
    assert tok == 2100 and usd == pytest.approx((2000 * 0.1 + 100 * 0.5) / 1e6)          # all of it at the input price: an upper bound


# ---------- the calibration comes from the data ----------

def test_la_politica_y_el_informe_salen_de_las_252_corridas_de_la_semana_13():
    runs = CAL.cargar()
    dist = CAL.distribucion(runs)
    assert dist["corridas"] == 252 and dist["tareas"] == 84 and dist["repeticiones"] == 3
    assert json.loads(json.dumps(dist)) == REPORTE["distribucion"]
    assert CAL.elegir(runs, dist) == json.loads(POLITICA_FILE.read_text(encoding="utf-8"))
    p = Politica.desde_archivo()
    usd, tok = dist["usd_por_corrida"], dist["tokens_por_corrida"]
    assert usd["p99"] <= p.tarea.usd < usd["p99"] + 0.0001 and tok["p99"] <= p.tarea.tokens < tok["p99"] + 1000   # p99, rounded UP
    assert p.tarea.usd < p.sesion.usd < p.tenant_dia.usd and p.tarea.tokens < p.sesion.tokens < p.tenant_dia.tokens
    assert p.min_salida >= dist["salida_por_paso"]["p95"] and p.max_salida == 4000
    assert (p.tarea.usd, p.tarea.tokens, p.sesion.usd, p.tenant_dia.usd) == (0.0063, 46000, 0.039, 0.32)


def test_la_estimacion_no_subestima_ninguna_de_las_930_llamadas_registradas():
    runs = CAL.cargar()
    en_uso = CAL.validar_estimacion(runs, EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA)
    assert en_uso == REPORTE["estimacion_en_uso"]
    assert en_uso["primera_llamada"]["llamadas"] == 252 and en_uso["llamadas_siguientes"]["llamadas"] == 678
    assert en_uso["primera_llamada"]["subestima"] == 0 and en_uso["llamadas_siguientes"]["subestima"] == 0
    assert en_uso["llamadas_siguientes"]["razon_minima"] >= 1.09                          # the margin is what keeps it above 1
    sin_margen = CAL.validar_estimacion(runs, 1.3, 1.0)
    assert sin_margen["llamadas_siguientes"]["razon_minima"] < 1.01                      # why the margin exists: 1.001 is not a bound
    assert (EST.CHARS_POR_TOKEN, EST.MARGEN_ENTRADA) == (1.5, 1.10)                      # `validar_estimacion` restores what it changes


def test_la_repeticion_de_la_semana_13_nunca_pasa_del_tope_y_pierde_poco():
    runs = CAL.cargar()
    p = Politica.desde_archivo()
    r = CAL.repetir(runs, p)
    assert r == {k: v for k, v in REPORTE["repeticion"]["elegida"].items() if k not in ("tope_usd", "tope_tokens")}
    assert r["nunca_pasa_del_tope"] and r["gasto_maximo_de_una_corrida"] <= p.tarea.usd
    assert r["cortadas"] <= 0.02 * len(runs)                                            # a p99 budget cuts about 1 run in 60
    assert all(v["nunca_pasa_del_tope"] for k, v in REPORTE["repeticion"].items())
    assert REPORTE["repeticion"]["p90"]["cortadas"] > REPORTE["repeticion"]["p95"]["cortadas"] > REPORTE["repeticion"]["p99"]["cortadas"] \
        > REPORTE["repeticion"]["max"]["cortadas"] >= 1


# ---------- the store ----------

@pytest.fixture
def almacen(tmp_path):
    return AlmacenGasto(tmp_path / "gasto.sqlite")


CUENTAS = {"session": ("session", "s1", ""), "tenant_day": ("tenant_day", "acme", "2026-11-03")}
LIMITES = {"session": Limite(0.001, 10_000), "tenant_day": Limite(0.002, 20_000)}


def test_reservar_es_todo_o_nada_y_liquidar_cobra_lo_real(almacen):
    assert almacen.reservar(CUENTAS, LIMITES, 0.0006, 4000, "g1") == (True, None, None)
    assert almacen.restante(CUENTAS, LIMITES)["session"] == Gasto(pytest.approx(0.0004), 6000)
    ok, alcance, dimension = almacen.reservar(CUENTAS, LIMITES, 0.0006, 4000, "g2")      # the session has 0.0004 left
    assert (ok, alcance, dimension) == (False, "session", "usd")
    assert almacen.restante(CUENTAS, LIMITES)["tenant_day"] == Gasto(pytest.approx(0.0014), 16_000)   # nothing was taken for g2
    assert almacen.reservar(CUENTAS, LIMITES, 0.0001, 7000, "g3")[1:] == ("session", "tokens")
    almacen.liquidar(CUENTAS, "g1", 0.0003, 2500)                                        # the call cost less than its upper estimate
    assert almacen.gastado(CUENTAS["session"]) == Gasto(pytest.approx(0.0003), 2500)
    assert almacen.reservado() == 0
    assert almacen.reservar(CUENTAS, LIMITES, 0.0006, 4000, "g4")[0] is True             # the unused part is free again
    almacen.liberar("g4")                                                                 # a failed call costs nothing
    assert almacen.gastado(CUENTAS["session"]).usd == pytest.approx(0.0003) and almacen.reservado() == 0


def test_la_reserva_de_un_proceso_muerto_vence_y_el_dia_nuevo_empieza_en_cero(tmp_path):
    ahora = [1000.0]
    a = AlmacenGasto(tmp_path / "g.sqlite", ttl_s=600, reloj=lambda: ahora[0])
    assert a.reservar(CUENTAS, LIMITES, 0.0009, 9000, "muerto")[0]
    assert a.reservar(CUENTAS, LIMITES, 0.0009, 9000, "otro")[0] is False                # blocked by the dead one...
    ahora[0] += 601
    assert a.reservar(CUENTAS, LIMITES, 0.0009, 9000, "otro")[0] is True                 # ...until it expires
    manana = {**CUENTAS, "tenant_day": ("tenant_day", "acme", "2026-11-04")}
    a.liquidar(CUENTAS, "otro", 0.0019, 19_000)
    assert a.restante(CUENTAS, LIMITES)["tenant_day"].usd == pytest.approx(0.0001)
    assert a.restante(manana, LIMITES)["tenant_day"].usd == pytest.approx(0.002)


def test_ocho_hilos_no_gastan_mas_que_el_limite_del_tenant(almacen):
    limites = {"tenant_day": Limite(0.01, 10**9)}
    cuenta = {"tenant_day": ("tenant_day", "acme", "2026-11-03")}
    concedidas, candado = [], threading.Lock()

    def hilo(n):
        for i in range(60):
            grupo = f"h{n}-{i}"
            if almacen.reservar(cuenta, limites, 0.0004, 1000, grupo)[0]:
                time.sleep(0.0005)
                almacen.liquidar(cuenta, grupo, 0.0004, 1000)
                with candado:
                    concedidas.append(grupo)
    hilos = [threading.Thread(target=hilo, args=(n,)) for n in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert len(concedidas) == 25                                                         # 0.01 / 0.0004: exactly the budget, no more
    assert almacen.gastado(cuenta["tenant_day"]).usd == pytest.approx(0.01) and almacen.reservado() == 0


# ---------- the agent layer, around a fake model call ----------

def simular(politica, usos, *, almacen=None, cuentas=None, modelo=M, extra_texto=200):
    """The wrapper around a model call that reports `usos[k] = (input, output)` tokens (output cut at `max_tokens`, as the API does)."""
    est = EstadoPresupuesto(politica, almacen, cuentas or {})
    token = _PRES.set(est)
    cuerpos = []

    def api(cuerpo):
        cuerpos.append(cuerpo)
        i, o = usos[len(cuerpos) - 1]
        return {"usage": {"input_tokens": i, "output_tokens": min(o, cuerpo["max_tokens"])}, "stop_reason": "tool_use",
                "content": []}
    llamar = api_presupuestada(api)
    mensajes = [{"role": "user", "content": "q" * 3000}]
    try:
        for _ in usos:
            llamar({"model": modelo, "max_tokens": 4000, "system": "s", "tools": [], "messages": mensajes})
            mensajes += [{"role": "assistant", "content": "a"}, {"role": "user", "content": "r" * extra_texto}]
    except PresupuestoAgotado:
        pass
    finally:
        _PRES.reset(token)
    return est, cuerpos


def trayectoria(azar, n):
    """Token usage that respects the estimate by construction (the estimator itself is checked on the real data above)."""
    usos, previa, salida_prev = [], 0, 0
    for k in range(n):
        base = 2000 if k == 0 else previa + salida_prev + azar.randint(0, 300)
        salida = azar.randint(50, 2500)
        usos.append((base, salida))
        previa, salida_prev = base, salida
    return usos


def test_ninguna_tarea_gasta_mas_que_su_tope_en_500_trayectorias_al_azar():
    azar = random.Random(11)
    paradas = completas = 0
    for _ in range(500):
        tope = Limite(10 ** azar.uniform(-3.0, -1.8), int(10 ** azar.uniform(4.2, 5.4)))
        est, cuerpos = simular(Politica(tope, min_salida=500), trayectoria(azar, azar.randint(2, 8)))
        assert est.gasto.usd <= tope.usd + 1e-12 and est.gasto.tokens <= tope.tokens
        assert not est.subestimaciones and not est.sobregasto
        assert len(cuerpos) == est.llamadas
        assert all(c["max_tokens"] >= 500 for c in cuerpos)
        if est.parada:
            paradas += 1
            assert est.parada.accion == "stop"
        else:
            completas += 1
    assert paradas > 50 and completas > 50


def test_ocho_tareas_a_la_vez_nunca_pasan_del_presupuesto_del_dia(almacen):
    cuentas = {"tenant_day": ("tenant_day", "acme", "2026-11-03")}
    p = Politica(Limite(0.01, 10**7), tenant_dia=Limite(0.03, 10**7), min_salida=500)
    resultados, candado = [], threading.Lock()

    def tarea(n):
        azar = random.Random(n)
        for _ in range(6):
            est, cuerpos = simular(p, trayectoria(azar, 4), almacen=almacen, cuentas=cuentas)
            with candado:
                resultados.append((est.gasto.usd, bool(est.parada)))
    hilos = [threading.Thread(target=tarea, args=(n,)) for n in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    total = almacen.gastado(cuentas["tenant_day"]).usd
    assert total <= 0.03 + 1e-9 and total == pytest.approx(sum(g for g, _ in resultados))   # the store holds exactly what was spent
    assert almacen.reservado() == 0
    assert any(parada for _, parada in resultados) and any(not parada for _, parada in resultados)


def test_un_error_de_la_api_libera_la_reserva_y_no_se_reintenta(almacen):
    cuentas = {"tenant_day": ("tenant_day", "acme", "2026-11-03")}
    p = Politica(Limite(0.01, 10**7), tenant_dia=Limite(0.01, 10**7), min_salida=500)
    est = EstadoPresupuesto(p, almacen, cuentas)
    token = _PRES.set(est)
    llamadas = []

    def api(cuerpo):
        llamadas.append(cuerpo)
        raise RuntimeError("API HTTP 529")
    try:
        with pytest.raises(RuntimeError):
            api_presupuestada(api)({"model": M, "max_tokens": 4000, "messages": [{"role": "user", "content": "q"}]})
    finally:
        _PRES.reset(token)
    assert len(llamadas) == 1 and almacen.reservado() == 0                               # one try, nothing held, nothing billed
    assert almacen.gastado(cuentas["tenant_day"]) == Gasto(0.0, 0) and est.gasto == Gasto()


# ---------- the real loop, client, server and database, with the scripted model ----------

TAREA_TOPE = Limite(0.0011, 10**6)         # call 1 fits (and costs about 0.0005); call 2 needs about 0.00075 and 0.0006 is left


def uso_turnos(usos=((3000, 400), (3600, 500), (4200, 300))):
    turnos = turnos_principal()
    for t, (i, o) in zip(turnos, usos):
        t["usage"] = {"input_tokens": i, "output_tokens": o}
    return turnos


def _estable(exp, ms=400):
    n, t0 = -1, time.time()
    while time.time() - t0 < 10:
        actual = len(exp.get_finished_spans())
        if actual == n:
            return
        n = actual
        time.sleep(ms / 1000)


@pytest.fixture(scope="module")
def banco(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("LAB_OBS_SALT", "sal-de-prueba-actividad-4")
    mp.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "NO_CONTENT")
    E.ESTRICTO = True
    exp = configurar_trazas()
    lab = Laboratorio(tenant="lab")
    ruta = tmp_path_factory.mktemp("presupuestos") / "gasto.sqlite"
    ahora = [1_793_000_000.0]
    almacen = AlmacenGasto(ruta, reloj=lambda: ahora[0])
    b = {"lab": lab, "exp": exp, "almacen": almacen, "reloj": ahora}
    try:
        yield b
    finally:
        lab.cerrar()
        E.ESTRICTO = False
        mp.undo()


def correr(banco, turnos, politica, **kw):
    banco["exp"].clear()
    kw.setdefault("almacen", banco["almacen"])
    kw.setdefault("reloj", lambda: banco["reloj"][0])
    r, modelo, cliente = banco["lab"].correr(turnos, agente_clase=AgentePresupuestado, politica=politica, **kw)
    _estable(banco["exp"])
    spans = resumen(banco["exp"].get_finished_spans())
    raiz = next(s for s in spans if s["name"].startswith("invoke_agent"))
    return {"r": r, "modelo": modelo, "est": banco["lab"].ultimo_agente.ultimo, "spans": [s for s in spans if s["trace"] == raiz["trace"]],
            "raiz": raiz}


def eventos(c):
    return [e for e in c["raiz"]["eventos"] if e["name"] == E.EVENTO_PRESUPUESTO]


def test_con_presupuesto_de_sobra_el_agente_responde_y_deja_un_evento_por_llamada(banco):
    c = correr(banco, uso_turnos(), Politica(Limite(0.01, 150_000), min_salida=500))
    assert c["r"].estado == "respondida" and c["r"].pasos == 3 and len(c["modelo"].llamadas) == 3
    ev = eventos(c)
    assert [e["attrs"]["lab.budget.decision"] for e in ev] == ["allow"] * 3
    assert [e["attrs"]["lab.budget.step"] for e in ev] == [1, 2, 3]
    assert all(e["attrs"]["lab.budget.limit_usd"] == 0.01 and e["attrs"]["lab.budget.scope"] == "task" for e in ev)
    assert ev[0]["attrs"]["lab.budget.spent_usd"] == 0
    # the spend is the sum of the chat spans' own costs, and each call carried the max_tokens its event says
    gasto = [s["attrs"]["lab.cost.usd"] for s in c["spans"] if s["name"].startswith("chat")]
    assert ev[-1]["attrs"]["lab.budget.spent_usd"] == pytest.approx(sum(gasto[:2]), abs=1e-7)
    assert c["est"].gasto.usd == pytest.approx(sum(gasto)) == pytest.approx(c["r"].costo_usd)
    assert [x["max_tokens"] for x in c["modelo"].llamadas] == [e["attrs"]["lab.budget.max_tokens"] for e in ev]
    assert not c["est"].subestimaciones and not c["est"].sobregasto
    assert all(e["attrs"]["lab.budget.estimate_usd"] >= g for e, g in zip(ev, gasto))     # each estimate was an upper bound
    assert c["raiz"]["attrs"]["lab.budget.max_tokens_total"] == 150_000                    # the loop's own cap follows the task budget


def test_al_agotarse_el_presupuesto_de_la_tarea_el_agente_para_y_dice_por_que(banco):
    c = correr(banco, uso_turnos(), Politica(TAREA_TOPE, min_salida=500))
    r, est = c["r"], c["est"]
    assert (r.estado, r.motivo, r.pasos) == ("limite_alcanzado", "presupuesto_tarea", 1)
    assert len(c["modelo"].llamadas) == 1                                                   # the model was NOT called a second time
    assert est.gasto.usd <= TAREA_TOPE.usd and r.costo_usd <= TAREA_TOPE.usd
    assert r.final["estado"] == "limite_alcanzado" and r.final["motivo"] == "presupuesto_tarea"
    texto = r.final["respuesta"]
    assert "task budget" in texto and "0.0011 USD" in texto and "1 model calls" in texto and "no final answer" in texto
    assert r.final["presupuesto"]["alcance"] == "task" and r.final["presupuesto"]["limite_usd"] == 0.0011
    ev = eventos(c)
    assert [e["attrs"]["lab.budget.decision"] for e in ev] == ["allow", "stop"]
    stop = ev[1]["attrs"]
    assert (stop["lab.budget.scope"], stop["lab.budget.reason"], stop["lab.budget.max_tokens"]) == ("task", "usd", 0)
    assert stop["lab.budget.limit_usd"] == 0.0011 and 0 < stop["lab.budget.spent_usd"] <= 0.0011
    assert stop["lab.budget.estimate_usd"] > 0.0011 - stop["lab.budget.spent_usd"]          # the next call would not have fit
    assert len([s for s in c["spans"] if s["name"].startswith("chat")]) == 1                # no chat span for a call never made
    assert (c["raiz"]["attrs"]["lab.outcome.status"], c["raiz"]["attrs"]["lab.outcome.reason"]) == ("limite_alcanzado", "presupuesto_tarea")
    assert c["raiz"]["estado"] == "ERROR"


def test_el_limite_de_tokens_tambien_detiene_y_el_texto_sale_en_el_idioma_de_la_tarea(banco):
    tarea = {"id": "s01-es", "lang": "es", "tarea": "¿Qué productos tienen existencia total por debajo del punto de reorden?"}
    c = correr(banco, uso_turnos(), Politica(Limite(1.0, 7000), min_salida=500), tarea=tarea)
    assert (c["r"].estado, c["r"].motivo) == ("limite_alcanzado", "presupuesto_tarea")
    assert eventos(c)[-1]["attrs"]["lab.budget.reason"] == "tokens"
    assert "No pude terminar" in c["r"].final["respuesta"] and "presupuesto de la tarea" in c["r"].final["respuesta"]
    assert c["est"].gasto.tokens <= 7000


def test_una_respuesta_cortada_por_el_max_tokens_del_presupuesto_cuenta_como_parada_por_presupuesto(banco):
    c = correr(banco, uso_turnos(((3000, 2000), (3600, 500), (4200, 300))), Politica(TAREA_TOPE, min_salida=500))
    assert c["modelo"].llamadas[0]["max_tokens"] < 2000                                      # the budget allowed fewer tokens than the turn needs
    assert (c["r"].estado, c["r"].motivo) == ("limite_alcanzado", "presupuesto_tarea")       # not `max_tokens_salida`: the cut was the budget's
    assert c["est"].gasto.usd <= TAREA_TOPE.usd and c["r"].final["presupuesto"]["alcance"] == "task"
    assert len(c["modelo"].llamadas) == 1


def test_el_agente_degrada_al_modelo_barato_que_la_politica_nombra(banco):
    p = Politica(Limite(0.01, 10**6), min_salida=500, degradar={S: M})
    c = correr(banco, uso_turnos(), p, modelo=S)
    assert c["r"].estado == "respondida" and [x["modelo"] for x in c["modelo"].llamadas] == [M, M, M]   # sticky after the first call
    primero = eventos(c)[0]["attrs"]
    assert (primero["lab.budget.decision"], primero["lab.budget.reason"], primero["gen_ai.request.model"], primero["lab.budget.model.from"]) \
        == ("degrade", "degradado", M, S)
    assert [e["attrs"]["lab.budget.decision"] for e in eventos(c)[1:]] == ["allow", "allow"]
    assert c["est"].gasto.usd <= 0.01
    # the run's cost is priced at the model that answered (Haiku), not at the Sonnet the loop was built with
    gasto = [s["attrs"]["lab.cost.usd"] for s in c["spans"] if s["name"].startswith("chat")]
    assert c["r"].costo_usd == pytest.approx(sum(gasto)) == pytest.approx(c["est"].gasto.usd)
    assert c["raiz"]["attrs"]["lab.run.cost_usd"] == pytest.approx(c["r"].costo_usd) and c["est"].modelos == [M, M, M]
    sin_politica = correr(banco, uso_turnos(), Politica(Limite(0.01, 10**6), min_salida=500), modelo=S)
    assert (sin_politica["r"].estado, sin_politica["r"].motivo) == ("limite_alcanzado", "presupuesto_tarea")   # not named: stops, never improvises
    assert sin_politica["modelo"].llamadas == []


def test_la_sesion_y_el_dia_del_tenant_se_comparten_entre_tareas_y_el_dia_nuevo_empieza_en_cero(banco):
    sesion = Limite(0.0012, 10**6)
    p = Politica(Limite(0.01, 10**6), sesion=sesion, min_salida=500)
    a = correr(banco, uso_turnos(), p, sesion="s-presupuesto")
    assert (a["r"].estado, a["r"].motivo, a["r"].pasos) == ("limite_alcanzado", "presupuesto_sesion", 1)
    b = correr(banco, uso_turnos(), p, sesion="s-presupuesto")
    assert (b["r"].motivo, b["r"].pasos, b["modelo"].llamadas) == ("presupuesto_sesion", 0, [])      # the session is already spent
    assert "session budget" in b["r"].final["respuesta"]
    assert banco["almacen"].gastado(("session", "s-presupuesto", "")).usd == pytest.approx(a["r"].costo_usd)
    c = correr(banco, uso_turnos(), p, sesion="otra-sesion")                                        # another session starts fresh
    assert c["r"].pasos == 1 and c["r"].motivo == "presupuesto_sesion"

    dia = Limite(0.0012, 10**6)
    pd = Politica(Limite(0.01, 10**6), tenant_dia=dia, min_salida=500)
    d1 = correr(banco, uso_turnos(), pd)
    assert (d1["r"].motivo, d1["r"].pasos) == ("presupuesto_tenant_dia", 1)
    d2 = correr(banco, uso_turnos(), pd)
    assert (d2["r"].motivo, d2["r"].pasos) == ("presupuesto_tenant_dia", 0)
    assert eventos(d2)[-1]["attrs"]["lab.budget.scope"] == "tenant_day"
    banco["reloj"][0] += 86_400                                                                     # the next UTC day
    d3 = correr(banco, uso_turnos(), pd)
    assert d3["r"].pasos == 1                                                                       # a new day: the account is empty again
    assert banco["almacen"].reservado() == 0


def test_un_error_de_la_api_en_el_agente_no_se_reintenta_ni_deja_reservas(banco):
    p = Politica(Limite(0.01, 10**6), sesion=Limite(0.01, 10**6), min_salida=500)
    c = correr(banco, uso_turnos(), p, sesion="s-falla", modelo_falla=1)
    assert c["r"].estado == "error" and c["r"].motivo.startswith("api:")
    assert len(c["modelo"].llamadas) == 2                                                           # the second call failed once, not retried
    assert banco["almacen"].reservado() == 0
    assert banco["almacen"].gastado(("session", "s-falla", "")).usd == pytest.approx(c["r"].costo_usd)   # only the call that happened
    assert c["raiz"]["attrs"]["lab.outcome.reason"] == "api_error"


def test_los_eventos_son_solo_numeros_y_vocabulario_fijo(banco):
    c = correr(banco, uso_turnos(), Politica(TAREA_TOPE, min_salida=500))
    claves = E.claves_de_eventos()
    assert len(claves) == 13 and not (claves & E.claves_permitidas() - {"gen_ai.request.model"})   # events have their own keys
    for e in eventos(c):
        assert set(e["attrs"]) <= claves
        for k, v in e["attrs"].items():
            assert E.ATRIBUTOS_EVENTO[E.EVENTO_PRESUPUESTO][k](v), (k, v)
            assert isinstance(v, (int, float)) or v in (E.ACCIONES_PRESUPUESTO + E.ALCANCES_PRESUPUESTO + E.MOTIVOS_PRESUPUESTO) \
                or E.ID(v)
    texto = json.dumps([s["eventos"] for s in c["spans"]], default=str)
    assert "budget" in texto and "partial" not in texto and "Stopped" not in texto                  # the partial answer is not on any span
    class Span:
        def add_event(self, *a, **k):
            pass
    with pytest.raises(E.ErrorEsquema):
        E.fijar_evento(Span(), E.EVENTO_PRESUPUESTO, {"lab.budget.reason": "porque sí"})            # free text is refused in strict mode
    with pytest.raises(E.ErrorEsquema):
        E.fijar_evento(Span(), "gen_ai.budget.nuevo", {})


def test_el_motivo_de_parada_nuevo_esta_en_el_vocabulario():
    assert {"presupuesto_tarea", "presupuesto_sesion", "presupuesto_tenant_dia"} <= set(E.MOTIVOS)
    assert E.clasificar_motivo("presupuesto_sesion") == "presupuesto_sesion"
    assert len(E.claves_permitidas()) == 67                                                         # the span shape did not grow: only enum values


# --- the evaluation runner: the $0 replay of the 84 tasks of week 13 and the report it writes ---------------------------------------

import os  # noqa: E402
import subprocess  # noqa: E402

REPORTE_REPRODUCCION = S17 / "resultados" / "presupuestos_eval_reproduccion.json"


def _runner(tmp_path, *args, env=None):
    """The runner in its own process: it sets the salt, the exporter and the strict flag globally, so it must not share ours."""
    salida = tmp_path / "informe.json"
    p = subprocess.run([sys.executable, "-m", "presupuestos.correr_eval", "--salida", str(salida), *args], cwd=S17, capture_output=True,
                       text=True, timeout=300, env=env)
    return p, (json.loads(salida.read_text(encoding="utf-8")) if salida.exists() else None)


def _nucleo(informe: dict) -> dict:
    return {k: informe[k] for k in ("modelo", "esfuerzo", "tareas", "politica", "resultado", "costo", "garantias", "base_semana_13", "tareas_cortadas")}


@pytest.fixture(scope="module")
def reproduccion_secuencial(tmp_path_factory):
    p, informe = _runner(tmp_path_factory.mktemp("repro"), "--reproduccion", "--paralelo", "1")
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-1500:]
    return informe


def test_la_reproduccion_de_las_84_tareas_cumple_todas_las_garantias(reproduccion_secuencial):
    i, g, c = reproduccion_secuencial, reproduccion_secuencial["garantias"], reproduccion_secuencial["costo"]
    pol = Politica.desde_archivo()
    assert i["ok"] is True and i["tareas"] == 84 and i["modo"].startswith("reproduccion")
    assert g["ninguna_tarea_pasa_de_su_tope"] and g["gasto_maximo_de_una_tarea_usd"] <= pol.tarea.usd
    assert g["tokens_maximos_de_una_tarea"] <= pol.tarea.tokens
    assert g["ninguna_sesion_pasa_de_su_tope"] and g["gasto_maximo_de_una_sesion_usd"] <= pol.sesion.usd
    assert g["el_dia_no_pasa_de_su_tope"] and c["total_usd"] <= pol.tenant_dia.usd
    assert g["subestimaciones_de_la_entrada"] == 0 and g["llamadas_mas_caras_que_su_estimado"] == 0
    assert g["gasto_del_bucle_igual_al_del_presupuesto"] and g["un_evento_por_decision"] and g["omisiones_del_esquema"] == {}
    cont = g["contabilidad"]
    assert g["la_contabilidad_coincide"] and cont["reservas_vivas"] == 0
    assert cont["dia_del_tenant_en_el_almacen"] == pytest.approx(c["total_usd"], abs=1e-6) == pytest.approx(cont["suma_de_las_tareas"], abs=1e-6)
    assert sum(cont["sesiones_en_el_almacen"].values()) == pytest.approx(c["total_usd"], abs=1e-6)


def test_la_reproduccion_solo_cambia_las_tareas_que_el_presupuesto_corto(reproduccion_secuencial):
    i, base = reproduccion_secuencial, reproduccion_secuencial["base_semana_13"]["repeticion_0"]
    cortadas = i["tareas_cortadas"]
    assert i["resultado"]["respuestas_parciales"] == len(cortadas) and i["resultado"]["estados"].get("limite_alcanzado", 0) == len(cortadas)
    assert all(t["motivo"].startswith("presupuesto_") for t in cortadas)
    # the replayed turns are the recorded turns: what the budget did not touch scores and costs as in week 13
    fallos_base = base["corridas"] - round(base["exito"] * base["corridas"])
    fallos_aqui = i["tareas"] - i["resultado"]["exitos"]
    assert fallos_aqui == fallos_base + sum(1 for t in cortadas if t["esperado"] == "respondida")
    assert i["costo"]["total_usd"] <= base["usd"]["total"]
    assert i["costo"]["total_usd"] >= base["usd"]["total"] - len(cortadas) * base["usd"]["max"]


def test_la_reproduccion_secuencial_es_determinista_y_el_informe_publicado_es_el_de_hoy(reproduccion_secuencial):
    publicado = json.loads(REPORTE_REPRODUCCION.read_text(encoding="utf-8"))
    assert publicado["paralelo"] == 1
    assert _nucleo(publicado) == _nucleo(reproduccion_secuencial)


def test_la_reproduccion_en_paralelo_cumple_las_mismas_garantias(tmp_path):
    p, i = _runner(tmp_path, "--reproduccion", "--paralelo", "4")
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-1500:]
    assert i["ok"] is True and i["tareas"] == 84
    assert i["garantias"]["la_contabilidad_coincide"] and i["garantias"]["contabilidad"]["reservas_vivas"] == 0


def test_el_informe_no_lleva_texto_de_usuario_ni_de_modelo(reproduccion_secuencial):
    crudo = json.dumps(reproduccion_secuencial, ensure_ascii=False)
    for tarea in map(json.loads, open(S17.parent / "semana-13" / "golden" / "tareas_es.jsonl", encoding="utf-8")):
        assert tarea["tarea"] not in crudo
    assert "SELECT" not in crudo.upper() and "/Users/" not in crudo and "sk-ant" not in crudo


def test_sin_confirmar_el_gasto_no_se_llama_al_modelo(tmp_path):
    """The real model needs its own flag and the key; without the flag the runner uses the recorded turns, and with the flag but
    without the key it stops before any call."""
    sin_clave = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    p, informe = _runner(tmp_path, "--confirmo-gasto", env=sin_clave)
    assert p.returncode == 2 and informe is None and "ANTHROPIC_API_KEY" in p.stderr
    p, informe = _runner(tmp_path, "--reproduccion", "--tareas", "s01", env={**sin_clave, "ANTHROPIC_API_KEY": "clave-falsa-que-no-se-usa"})
    assert p.returncode == 0 and informe["modo"].startswith("reproduccion") and informe["tareas"] == 2
    assert "clave-falsa" not in p.stdout + p.stderr and "clave-falsa" not in json.dumps(informe)


# --- the evidence of the paid run (84 tasks, real Haiku 5.5) and of the Langfuse check: committed files, no API, no stack --------------

REPORTE_REAL = S17 / "resultados" / "presupuestos_eval.json"
CONSOLA_REAL = S17 / "resultados" / "presupuestos_eval_consola.txt"
REPORTE_LANGFUSE = S17 / "resultados" / "presupuestos_langfuse.json"


def _consola():
    """One row per task of the paid run, parsed from its console output (the report keeps only the aggregates and the cut tasks)."""
    filas = {}
    for linea in CONSOLA_REAL.read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) > 6 and partes[3].startswith("exito="):
            filas[partes[0]] = {"tipo": partes[1], "estado": partes[2], "exito": partes[3] == "exito=si", "usd": float(partes[5].lstrip("$")),
                                "motivo": partes[6]}
    return filas


def test_la_corrida_pagada_nunca_cruzo_un_tope_y_su_contabilidad_cuadra():
    i, pol = json.loads(REPORTE_REAL.read_text(encoding="utf-8")), Politica.desde_archivo()
    g, c = i["garantias"], i["costo"]
    assert i["modo"] == "modelo real" and i["tareas"] == 84 and i["modelo"] == M and i["esfuerzo"] == "low" and i["ok"] is True
    assert g["gasto_maximo_de_una_tarea_usd"] <= pol.tarea.usd and g["tokens_maximos_de_una_tarea"] <= pol.tarea.tokens
    assert g["gasto_maximo_de_una_sesion_usd"] <= pol.sesion.usd and c["total_usd"] <= pol.tenant_dia.usd
    assert g["subestimaciones_de_la_entrada"] == 0 and g["llamadas_mas_caras_que_su_estimado"] == 0     # the estimate was an upper bound on every real call
    assert g["gasto_del_bucle_igual_al_del_presupuesto"] and g["un_evento_por_decision"] and g["omisiones_del_esquema"] == {}
    assert g["la_contabilidad_coincide"] and g["contabilidad"]["reservas_vivas"] == 0
    assert g["contabilidad"]["dia_del_tenant_en_el_almacen"] == pytest.approx(c["total_usd"], abs=1e-6)
    assert i["politica"]["tarea"] == {"usd": pol.tarea.usd, "tokens": pol.tarea.tokens}                 # the report is of the policy that ships
    assert c["total_usd"] <= c["estimado_antes_usd"] * 1.10                                              # the bill was the one that was authorized


def test_la_corrida_pagada_se_reconstruye_desde_su_salida_de_consola():
    i, filas = json.loads(REPORTE_REAL.read_text(encoding="utf-8")), _consola()
    assert len(filas) == 84 and i["tareas"] == 84
    assert sum(f["exito"] for f in filas.values()) == i["resultado"]["exitos"] == 74
    assert sum(f["usd"] for f in filas.values()) == pytest.approx(i["costo"]["total_usd"], abs=84 * 5e-6)    # each of the 84 rows is rounded to $0.00001
    assert max(f["usd"] for f in filas.values()) <= Politica.desde_archivo().tarea.usd
    cortadas = {k for k, f in filas.items() if f["motivo"].startswith("presupuesto_")}
    assert cortadas == {t["id"] for t in i["tareas_cortadas"]} and len(cortadas) == i["resultado"]["respuestas_parciales"] == 2
    assert {filas[k]["motivo"] for k in cortadas} == set(i["resultado"]["motivos_de_parada"]) == {"presupuesto_tarea", "presupuesto_sesion"}
    assert all(filas[k]["estado"] == "limite_alcanzado" for k in cortadas)


def test_cada_fallo_de_la_corrida_pagada_tiene_una_causa_medida():
    """A task failed either because the budget cut it, or because week 13 already fails it in at least one of its three runs, or
    it is listed as unexplained. There is exactly one of the last kind and it has no budget involvement in the numbers we keep
    (it spent a third of its cap), but the run was not repeated, so it is reported as run-to-run variation, not proved."""
    filas = _consola()
    base = {}
    for r in map(json.loads, open(S17.parent / "semana-13" / "resultados" / "eval_haiku_low_detalle.jsonl", encoding="utf-8")):
        base.setdefault(r["id"], []).append(r["exito"])
    fallos = {k for k, f in filas.items() if not f["exito"]}
    cortadas = {k for k, f in filas.items() if f["motivo"].startswith("presupuesto_")}
    ya_fallaba = {k for k in fallos - cortadas if not all(base[k])}
    sin_explicar = fallos - cortadas - ya_fallaba
    assert len(fallos) == 10 and cortadas == {"r07-es", "c08-es"} and sin_explicar == {"s10-es"}
    assert all(all(base[k]) for k in cortadas)                       # both cut tasks passed 3 of 3 runs in week 13: the budget cost two successes
    assert all(filas[k]["usd"] < 0.5 * Politica.desde_archivo().tarea.usd for k in sin_explicar)


def test_el_costo_de_la_corrida_pagada_es_el_de_la_semana_13_menos_lo_que_se_corto():
    i = json.loads(REPORTE_REAL.read_text(encoding="utf-8"))
    base = i["base_semana_13"]["repeticion_0"]["usd"]["total"]
    assert i["costo"]["total_usd"] < base                                                             # never above what week 13 spent on the same tasks
    assert i["costo"]["por_tarea"]["max"] <= Politica.desde_archivo().tarea.usd < base / 30


def test_los_eventos_de_presupuesto_llegan_al_archivo_del_collector_y_no_a_langfuse():
    i = json.loads(REPORTE_LANGFUSE.read_text(encoding="utf-8"))
    e = i["escenarios"]
    assert i["ok"] is True and set(e) == {"permite", "degrada", "para_tarea", "para_sesion_1", "para_sesion_2"}
    assert e["permite"]["decisiones"] == ["allow"] * 3 and e["degrada"]["decisiones"] == ["degrade", "allow", "allow"]
    assert e["para_tarea"]["decisiones"] == ["allow", "stop"] and e["para_sesion_2"]["decisiones"] == ["stop"]
    assert e["para_sesion_2"]["spans"] == 1 and e["para_sesion_2"]["alcances"] == ["session"]           # the second task never called the model
    assert all(x["ok"] and x["eventos_del_archivo_iguales_a_los_del_laboratorio"] and x["costo_en_langfuse_igual_al_del_agente"]
               and x["resultado_del_agente_en_langfuse_igual"] and x["modelos_de_las_generaciones_en_langfuse_iguales"]
               and x["observaciones_en_langfuse"] == x["spans"] for x in e.values())
    assert all(x["eventos_en_el_archivo_del_collector"] == len(x["decisiones"]) for x in e.values())
    assert e["degrada"]["modelos"] == [M, M, M]
    assert i["los_eventos_llegan_a_langfuse"] is False                                                 # measured: Langfuse v4 drops span events
    assert i["canarios"]["fugas"] == [] and "/Users/" not in json.dumps(i)


def test_los_informes_de_la_actividad_4_no_tienen_rutas_locales_ni_secretos():
    for ruta in (REPORTE_REAL, REPORTE_REPRODUCCION, REPORTE_LANGFUSE, CONSOLA_REAL, S17 / "resultados" / "presupuestos_calibracion.json"):
        texto = ruta.read_text(encoding="utf-8")
        assert "/Users/" not in texto and "sk-ant" not in texto and "ANTHROPIC_API_KEY" not in texto, ruta.name
