"""Week 19, activity 9: the secret scan's classifier, offline (no gitleaks binary, no AWS)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

S19 = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("escaneo_secretos", S19 / "seguridad" / "escaneo_secretos.py")
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

# A credential-shaped value, built at run time so this file carries none.
LLAVE_FALSA = "AKIA" + "Q7X2" * 4
SIN_FUENTE = lambda commit, archivo: ""  # noqa: E731


def h(archivo, secreto, **extra):
    return {"File": archivo, "Secret": secreto, "RuleID": "generic-api-key", "StartLine": 3, "Commit": "", **extra}


def test_vendor_es_de_terceros():
    assert E.clasificar(h("semana-19/guardrail/vendor/botocore/data/x.json", LLAVE_FALSA), fuente=SIN_FUENTE)[0] == "tercero"


def test_archivo_del_record_es_de_terceros(tmp_path):
    asset = tmp_path / ("asset." + "a" * 64)
    (asset / "PyJWT-2.10.1.dist-info").mkdir(parents=True)
    (asset / "PyJWT-2.10.1.dist-info" / "RECORD").write_text("jwt/algorithms.py,sha256=x,1\njwt/__init__.py,,\n")
    terceros = E.archivos_de_terceros(tmp_path)
    archivo = f"asset.{'a' * 64}/jwt/algorithms.py"
    assert archivo in terceros
    assert E.clasificar(h(archivo, LLAVE_FALSA), terceros=terceros, fuente=SIN_FUENTE)[0] == "tercero"
    # Our own code in the same asset is not third-party.
    assert E.clasificar(h(f"asset.{'a' * 64}/agente/x.py", LLAVE_FALSA), terceros=terceros,
                        fuente=SIN_FUENTE)[0] == "sin_clasificar"


@pytest.mark.parametrize("secreto", ["0" * 64, "ab" * 32 + ".zip", "cd" * 32 + ".json"])
def test_llave_de_asset_es_falso_positivo(secreto):
    assert E.clasificar(h("semana19-computo.template.json", secreto), fuente=SIN_FUENTE)[0] == "falso_positivo"


def test_identificador_y_argumento_con_nombre_son_falsos_positivos():
    assert E.clasificar(h("semana-19/infra/cdk/app.py", "SecretoBdLeer"), fuente=SIN_FUENTE)[0] == "falso_positivo"
    assert E.clasificar(h("semana-19/infra/cdk/app.py", "llave_de_prompt="), fuente=SIN_FUENTE)[0] == "falso_positivo"
    # A keyword argument outside Python is not explained.
    assert E.clasificar(h("notas.txt", "llave_de_prompt="), fuente=SIN_FUENTE)[0] == "sin_clasificar"


def test_sid_declarado_en_su_commit():
    sid = "CifrarConLaLlaveS3Kms"
    fuente = lambda commit, archivo: f'_declaracion(sid="{sid}", actions=[])' if commit == "abc1234" else ""  # noqa: E731
    assert E.clasificar(h("semana-19/infra/cdk/app.py", sid, Commit="abc1234"), fuente=fuente)[0] == "falso_positivo"
    # The same value without the declaration at that commit stays unexplained.
    assert E.clasificar(h("semana-19/infra/cdk/app.py", sid, Commit="fff0000"), fuente=fuente)[0] == "sin_clasificar"


def test_archivo_de_prueba_listado():
    clase, razon = E.clasificar(h("semana-19/tests/test_agentes_comparar.py", LLAVE_FALSA), fuente=SIN_FUENTE)
    assert clase == "prueba" and razon


def test_llave_en_codigo_propio_no_se_explica():
    assert E.clasificar(h("semana-19/agente/handler.py", LLAVE_FALSA), fuente=SIN_FUENTE)[0] == "sin_clasificar"


def test_el_resumen_no_guarda_secretos_ni_autores(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "fuente_en_commit", SIN_FUENTE)
    hallazgos = [h("semana-19/agente/handler.py", LLAVE_FALSA, Author="Alguien", Email="a" + chr(64) + "b.invalid",
                   Match=f'key = "{LLAVE_FALSA}"', Commit="0123456789abcdef"),
                 h("semana-19/guardrail/vendor/x.json", LLAVE_FALSA)]
    r = E.resumen("historia", hallazgos, raiz=tmp_path)
    texto = json.dumps(E.armar([r], "8.30.1"))
    assert LLAVE_FALSA not in texto and "Alguien" not in texto and chr(64) not in texto
    assert r["hallazgos"] == 2 and r["por_clase"] == {"sin_clasificar": 1, "tercero": 1}
    assert [f["commit"] for f in r["detalle"]] == ["0123456"]


def test_rutas_absolutas_del_synth_quedan_relativas(tmp_path):
    r = E.resumen("cdk_out_lab", [h(str(tmp_path / "semana19-ia.template.json"), "0" * 64)], raiz=tmp_path)
    assert r["detalle"][0]["archivo"] == "semana19-ia.template.json"


def test_main_sale_con_1_si_queda_algo_sin_clasificar(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "version_de", lambda b: "8.30.1")
    monkeypatch.setattr(E, "fuente_en_commit", SIN_FUENTE)
    monkeypatch.setattr(E, "correr_gitleaks", lambda b, m, o: [h("semana-19/agente/handler.py", LLAVE_FALSA)])
    salida = tmp_path / "s.json"
    assert E.main(["--gitleaks", "gl", "--salida", str(salida)]) == 1
    assert json.loads(salida.read_text())["veredicto"] == "revisar"
    monkeypatch.setattr(E, "correr_gitleaks", lambda b, m, o: [h("semana-19/guardrail/vendor/x", LLAVE_FALSA)])
    assert E.main(["--gitleaks", "gl", "--salida", str(salida)]) == 0


def test_version_fija(monkeypatch):
    monkeypatch.setattr(E, "version_de", lambda b: "8.18.0")
    with pytest.raises(SystemExit):
        E.main(["--gitleaks", "gl", "--sin-historia"])


def test_informe_versionado_sin_hallazgos_sin_clasificar():
    informe = json.loads((S19 / "resultados" / "seguridad" / "secretos.json").read_text(encoding="utf-8"))
    assert informe["herramienta"] == f"gitleaks {E.VERSION_GITLEAKS}"
    assert informe["sin_clasificar"] == 0 and informe["veredicto"] == "ok"
    assert {a["alcance"] for a in informe["alcances"]} == {"historia", "cdk_out_lab", "cdk_out_prod"}
    assert informe["cuenta_en_historial"]["estado"] == "aceptado"
