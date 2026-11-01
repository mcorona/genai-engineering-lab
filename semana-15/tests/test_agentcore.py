"""Actividad 8 (sin AWS y sin API): paquete CodeZip, permisos mínimos, simulación de la infraestructura y el agente de
AgentCore (agentcore/main.py) servido en local con el mismo protocolo HTTP que Runtime."""
import json

import pytest
from conftest import S15, VENVS
from test_equivalencia import SQL_V01, _v01

from arnes import contrato
from arnes.puente import Puente
from arnes.simulado import DobleAnthropic, Guion, Turno, herramienta

import importlib.util  # noqa: E402


def _cargar(nombre):   # por ruta: agregar agentcore/ a sys.path dejaría su main.py como módulo `main` para todos
    spec = importlib.util.spec_from_file_location(f"agentcore_{nombre}", S15 / "agentcore" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


empaquetar, infra = _cargar("empaquetar"), _cargar("infra")

CUENTA = "123456789012"
HAY_ST = (VENVS / "st" / "bin" / "python").exists()


def test_paquete_solo_lleva_el_codigo_necesario():
    ruta = empaquetar.armar(sin_dependencias=True)
    import zipfile
    nombres = set(zipfile.ZipFile(ruta).namelist())
    assert empaquetar.revisar(ruta) == []
    assert nombres == {d for _, d in empaquetar.CODIGO}                  # ni pruebas, ni .env, ni el resto del repo
    assert "main.py" in nombres and "semana-13/agente/loop.py" in nombres


@pytest.mark.skipif(not HAY_ST, reason="sin el entorno de Strands")
def test_paquete_funciona_fuera_del_repositorio(tmp_path):
    """Lo que el agente lee al resolver una tarea tiene que venir en el zip (en AgentCore no hay repositorio).
    Primer despliegue: faltaba semana-07/prices.json y todas las tareas fallaron con FileNotFoundError."""
    import subprocess
    import zipfile
    zipfile.ZipFile(empaquetar.armar(sin_dependencias=True)).extractall(tmp_path)
    codigo = ("import sys; sys.path.insert(0, 'semana-15'); from arnes.contrato import semana13, costo; "
              "import adaptadores.strands; m = semana13(); print(len(m.SISTEMA) > 0, costo('claude-haiku-5-5', 1200, 300) > 0)")
    r = subprocess.run([str(VENVS / "st" / "bin" / "python"), "-I", "-c", codigo], cwd=tmp_path, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.split() == ["True", "True"]


def test_rol_de_ejecucion_con_permisos_minimos():
    conf = infra.confianza(CUENTA)["Statement"][0]
    assert conf["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert conf["Condition"]["StringEquals"]["aws:SourceAccount"] == CUENTA
    pol = {s["Sid"]: s for s in infra.politica(CUENTA, "arn:aws:secretsmanager:us-east-1:1:secret:x")["Statement"]}
    acciones = {a for s in pol.values() for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
    assert not any(a.startswith(("bedrock:", "ecr:", "iam:", "s3:Put", "s3:Delete")) for a in acciones)
    llave = pol["LlaveDeAnthropic"]["Resource"]
    assert all("*" not in r or r.endswith(f"{infra.RUNTIME}-*") for r in llave)
    assert any(r.endswith(f"/{infra.PROVEEDOR}") for r in llave)
    assert pol["SecretoDeLaLlave"]["Resource"] == "arn:aws:secretsmanager:us-east-1:1:secret:x"   # solo su secreto
    assert pol["Codigo"]["Resource"].endswith(infra.CLAVE_ZIP)
    assert all(g.startswith(f"arn:aws:logs:us-east-1:{CUENTA}:log-group:/aws/bedrock-agentcore/runtimes/{infra.RUNTIME}")
               for g in pol["Registros"]["Resource"])


def test_crear_y_borrar_en_simulacion_no_tocan_aws(monkeypatch, tmp_path):
    sim = infra.Simulador(CUENTA)
    monkeypatch.setattr(infra, "sesion", lambda confirmar: (sim, CUENTA))
    monkeypatch.setenv("ALERTA_CORREO", "alertas@example.com")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba-no-se-imprime")
    assert infra.crear(False, tmp_path / "agente.zip") == 0
    ops = [(s, o) for s, o, _ in sim.llamadas]
    assert ops.index(("bedrock-agentcore-control", "create_api_key_credential_provider")) < \
        ops.index(("iam", "put_role_policy")) < ops.index(("bedrock-agentcore-control", "create_agent_runtime"))
    rt = next(kw for s, o, kw in sim.llamadas if o == "create_agent_runtime")
    assert rt["lifecycleConfiguration"] == {"idleRuntimeSessionTimeout": 60, "maxLifetime": 900}
    assert rt["agentRuntimeArtifact"]["codeConfiguration"]["runtime"] == "PYTHON_3_13"
    assert "authorizerConfiguration" not in rt                            # entrada por IAM (SigV4)
    con_llave = [o for s, o, kw in sim.llamadas if "sk-prueba-no-se-imprime" in json.dumps(kw)]
    assert con_llave == ["create_api_key_credential_provider"]           # la llave solo va a Identity
    bud = next(kw for s, o, kw in sim.llamadas if o == "create_budget")
    assert bud["Budget"]["BudgetLimit"] == {"Amount": "2", "Unit": "USD"} and len(bud["NotificationsWithSubscribers"]) == 3
    sim.llamadas.clear()
    assert infra.borrar(False, presupuesto=False) == 0
    borrados = {o for _, o, _ in sim.llamadas}
    assert {"delete_agent_runtime", "delete_api_key_credential_provider", "delete_role", "delete_bucket",
            "delete_log_group"} <= borrados and "delete_budget" not in borrados


# ---------- el agente de AgentCore servido en local ----------

@pytest.fixture(scope="module")
def local():
    if not HAY_ST:
        pytest.skip("sin el entorno de Strands")
    from eval.agentcore import Local
    d = Local()
    yield d
    d.cerrar()


def _guion(valor):
    return Guion([Turno([herramienta("ejecutar_sql", {"sql": SQL_V01})], 1200, 60),
                  Turno([herramienta("responder", {"estado": "respondida", "respuesta": str(valor),
                                                   "resultados": [{"clave": "n", "sql": SQL_V01, "valor": valor}]})], 1500, 90)])


def test_agente_de_agentcore_equivale_al_trabajador_local(local, entorno, adm, conexion_verificador):
    from agente.verificar import verificar
    t, valor = _v01(adm)
    srv = entorno.servidores["normal"]
    salidas, llamadas = {}, {}
    with Puente("strands") as trabajador:
        for nombre, correr in (("trabajador", lambda p: trabajador.resolver(**p)),
                               ("agentcore", lambda p: local.invocar(p, "s" * 40))):
            antes = len(srv.trazas.ultimas)
            with DobleAnthropic(_guion(valor)) as d:
                salidas[nombre] = correr({"tarea": t, "mcp_url": srv.url, "token": entorno.token("analista"),
                                          "base_url": d.base_url})
            llamadas[nombre] = [x["nombre"] for x in srv.trazas.ultimas[antes:] if x.get("metodo") == "tools/call"]
    a, b = (contrato.resultado_de_dict(salidas[n]["resultado"]) for n in ("trabajador", "agentcore"))
    for campo in ("estado", "final", "pasos", "herramientas", "tokens_in", "tokens_out", "costo_usd", "motivo"):
        assert getattr(a, campo) == getattr(b, campo), campo
    assert llamadas["trabajador"] == llamadas["agentcore"] == ["ejecutar_sql"]
    assert verificar(t, b.final, conexion_verificador, b.estado)["exito"]
    assert salidas["agentcore"]["arranque"]["invocacion"] >= 1 and "importacion_s" in salidas["agentcore"]["arranque"]


def test_sin_token_de_carga_no_hay_llave_ni_llamada_al_modelo(local, entorno, adm):
    t, _ = _v01(adm)
    with DobleAnthropic(Guion([])) as d:
        out = local.invocar({"tarea": t, "mcp_url": entorno.servidores["normal"].url, "token": entorno.token("analista")},
                            "s" * 40)
        assert d.guion.peticiones == []
    assert out["error"].startswith("identity:") and "workload access token" in out["error"]


def test_ping_reporta_arranque_sin_modelo(local):
    a = local.invocar({"ping": True}, "p" * 40)["arranque"]
    b = local.invocar({"ping": True}, "p" * 40)["arranque"]
    assert b["invocacion"] == a["invocacion"] + 1 and b["pid"] == a["pid"] and b["proceso_s"] >= a["proceso_s"]
