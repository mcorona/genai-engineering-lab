"""Week 19, activity 8, step 0: no versioned file of semana-19 carries an account ID inside an ARN.

The first ApplyGuardrail run (activity 5) saved 24 ARNs with the account. Every results writer goes through
comun.redaccion; this test catches the next one that does not.

Out of scope, on purpose:
- `guardrail/vendor/`: botocore's unmodified data files, whose examples use AWS documentation accounts;
- in `tests/`, the documentation placeholders 123456789012 and 111111111111, used as fixtures of the redaction itself.
"""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

S19 = Path(__file__).resolve().parents[1]
RAIZ = S19.parent
ARN_CON_CUENTA = re.compile(r"arn:aws[^:]*:[^:]*:[^:]*:(\d{12}):")
VENDOR = "semana-19/guardrail/vendor/"
EJEMPLOS_EN_PRUEBAS = {"123456789012", "111111111111"}
CUENTA_FALSA = "9876543" + "21098"   # built at run time, so this file does not carry it


def _versionados() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z", "semana-19"], cwd=RAIZ, capture_output=True, check=True)
    return [f for f in r.stdout.decode("utf-8").split("\0") if f]


def hallazgos(archivos: list[str], leer=lambda f: (RAIZ / f).read_bytes()) -> list[tuple[str, str]]:
    malos = []
    for f in archivos:
        if f.startswith(VENDOR):
            continue
        try:
            texto = leer(f).decode("utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for m in ARN_CON_CUENTA.finditer(texto):
            if f.startswith("semana-19/tests/") and m.group(1) in EJEMPLOS_EN_PRUEBAS:
                continue
            malos.append((f, m.group(0)[:-13] + "<12 digits>:"))
    return malos


def test_ningun_archivo_versionado_trae_la_cuenta_en_un_arn():
    archivos = _versionados()
    assert any(f.startswith("semana-19/resultados/") for f in archivos)
    assert hallazgos(archivos) == []


def test_la_prueba_detecta_un_arn_con_cuenta_y_respeta_las_excepciones():
    c = CUENTA_FALSA
    contenido = {
        "semana-19/resultados/x.json": f'{{"a": "arn:aws:bedrock:us-east-1:{c}:guardrail/g"}}'.encode(),
        "semana-19/resultados/ok.json": b'{"a": "arn:aws:bedrock:us-east-1:<account>:guardrail/g"}',
        "semana-19/guardrail/vendor/botocore/data/x/examples-1.json": f'"arn:aws:iam::{c}:role/r"'.encode(),
        "semana-19/tests/test_x.py": b'"arn:aws:iam::123456789012:role/r"',
        "semana-19/tests/test_y.py": f'"arn:aws:iam::{c}:role/r"'.encode(),
        "semana-19/arquitectura/diagrama.svg": b'\xff\xfe binary',
    }
    malos = hallazgos(list(contenido), leer=lambda f: contenido[f])
    assert [f for f, _ in malos] == ["semana-19/resultados/x.json", "semana-19/tests/test_y.py"]
    assert all(c not in arn for _, arn in malos)


def test_prueba_viva_redacta_lo_que_escribe():
    spec = importlib.util.spec_from_file_location("prueba_viva", S19 / "guardrail" / "prueba_viva.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    texto = modulo.texto_del_resultado([{"tipo": "golden", "id": "s01-es", "accion": "NONE", "evaluacion": [
        {"topicPolicy": {"guardrailArn": f"arn:aws:bedrock:us-east-1:{CUENTA_FALSA}:guardrail/teps1un80k04"}}]}])
    assert CUENTA_FALSA not in texto
    assert json.loads(texto)["resultados"][0]["evaluacion"][0]["topicPolicy"]["guardrailArn"].endswith(
        ":<account>:guardrail/teps1un80k04")
