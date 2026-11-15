#!/usr/bin/env python3
"""Runs a week 5 prompt template against an LLM provider.

Providers: anthropic (the default), openai, gemini. No external dependencies.
The keys are read from the environment or from semana-05/.env (ignored by Git):
ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY.
openai and gemini need --modelo. Each execution is appended to
resultados/ejecuciones.jsonl.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PLANTILLAS = RAIZ / "prompts"
REGISTRO = RAIZ / "resultados" / "ejecuciones.jsonl"
MODELO_ANTHROPIC = "claude-haiku-5-5"
PROVEEDORES = {
    "anthropic": {"clave": "ANTHROPIC_API_KEY",
                  "url": "https://api.anthropic.com/v1/messages"},
    "openai": {"clave": "OPENAI_API_KEY",
               "url": "https://api.openai.com/v1/chat/completions"},
    "gemini": {"clave": "GEMINI_API_KEY",
               "url": "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"},
}


def cargar_env_local():
    """Loads the keys from semana-05/.env if they are not in the environment. It prints no values."""
    ruta = RAIZ / ".env"
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        nombre, sep, valor = linea.strip().partition("=")
        valor = valor.strip().strip("'\"")
        if not sep or not valor:
            continue
        for proveedor in PROVEEDORES.values():
            if nombre.strip() == proveedor["clave"] and not os.environ.get(nombre.strip()):
                os.environ[nombre.strip()] = valor


def cargar_plantilla(nombre):
    ruta = PLANTILLAS / f"{nombre}.json"
    if not ruta.exists():
        disponibles = sorted(p.stem for p in PLANTILLAS.glob("*.json"))
        sys.exit(f"Template '{nombre}' does not exist. Available: {', '.join(disponibles)}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def rellenar(texto, variables):
    for clave, valor in variables.items():
        texto = texto.replace("{" + clave + "}", valor)
    return texto


def sistema_completo(plantilla):
    sistema = plantilla["sistema"]
    if plantilla.get("contexto"):
        contexto = (PLANTILLAS / plantilla["contexto"]).read_text(encoding="utf-8")
        sistema = contexto.strip() + "\n\n" + sistema
    return sistema


def mensajes_de(plantilla, variables):
    mensajes = []
    for ejemplo in plantilla.get("ejemplos", []):
        mensajes.append({"role": "user", "content": ejemplo["entrada"]})
        mensajes.append({"role": "assistant", "content": ejemplo["salida"]})
    mensajes.append({"role": "user", "content": rellenar(plantilla["usuario"], variables)})
    return mensajes


def construir(proveedor, plantilla, variables, modelo, max_tokens):
    sistema = sistema_completo(plantilla)
    mensajes = mensajes_de(plantilla, variables)
    herramientas = plantilla.get("herramientas", [])
    if proveedor == "anthropic":
        cuerpo = {"model": modelo, "max_tokens": max_tokens,
                  "system": [{"type": "text", "text": sistema,
                              "cache_control": {"type": "ephemeral"}}],
                  "messages": mensajes}
        if herramientas:
            cuerpo["tools"] = herramientas
        return cuerpo
    if proveedor == "openai":
        cuerpo = {"model": modelo, "max_completion_tokens": max_tokens,
                  "messages": [{"role": "system", "content": sistema}] + mensajes}
        if herramientas:
            cuerpo["tools"] = [{"type": "function", "function": {
                "name": h["name"], "description": h["description"],
                "parameters": h["input_schema"]}} for h in herramientas]
            # OpenAI rejects tools on chat/completions when reasoning is active (gpt-5.6-luna).
            cuerpo["reasoning_effort"] = "none"
        return cuerpo
    # gemini
    cuerpo = {"systemInstruction": {"parts": [{"text": sistema}]},
              "contents": [{"role": "user" if m["role"] == "user" else "model",
                            "parts": [{"text": m["content"]}]} for m in mensajes],
              "generationConfig": {"maxOutputTokens": max_tokens}}
    if herramientas:
        cuerpo["tools"] = [{"functionDeclarations": [{
            "name": h["name"], "description": h["description"],
            "parameters": h["input_schema"]} for h in herramientas]}]
    return cuerpo


def llamar(proveedor, cuerpo, clave, modelo):
    info = PROVEEDORES[proveedor]
    url = info["url"].format(modelo=modelo)
    cabeceras = {"content-type": "application/json"}
    if proveedor == "anthropic":
        cabeceras.update({"x-api-key": clave, "anthropic-version": "2023-06-01"})
    elif proveedor == "openai":
        cabeceras["Authorization"] = f"Bearer {clave}"
    else:
        cabeceras["x-goog-api-key"] = clave
    peticion = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"),
                                      method="POST", headers=cabeceras)
    try:
        with urllib.request.urlopen(peticion, timeout=120) as respuesta:
            return json.loads(respuesta.read())
    except urllib.error.HTTPError as error:
        detalle = error.read().decode("utf-8", errors="replace")[:500]
        sys.exit(f"Error HTTP {error.code} ({proveedor}): {detalle}")


def interpretar(proveedor, r, modelo):
    """Converts each provider's response to a common format."""
    if proveedor == "anthropic":
        uso = r.get("usage", {})
        return {
            "modelo": r.get("model", modelo),
            "texto": "".join(b.get("text", "") for b in r["content"] if b["type"] == "text"),
            "herramientas": [{"nombre": b["name"], "entrada": b["input"]}
                             for b in r["content"] if b["type"] == "tool_use"],
            "stop_reason": r.get("stop_reason"),
            "tokens_entrada": uso.get("input_tokens"),
            "tokens_salida": uso.get("output_tokens"),
            "tokens_cache_escritura": uso.get("cache_creation_input_tokens"),
            "tokens_cache_lectura": uso.get("cache_read_input_tokens"),
        }
    if proveedor == "openai":
        eleccion = r["choices"][0]
        mensaje = eleccion["message"]
        uso = r.get("usage", {})
        return {
            "modelo": r.get("model", modelo),
            "texto": mensaje.get("content") or "",
            "herramientas": [{"nombre": tc["function"]["name"],
                              "entrada": json.loads(tc["function"]["arguments"])}
                             for tc in mensaje.get("tool_calls") or []],
            "stop_reason": eleccion.get("finish_reason"),
            "tokens_entrada": uso.get("prompt_tokens"),
            "tokens_salida": uso.get("completion_tokens"),
            "tokens_cache_escritura": None,
            "tokens_cache_lectura": uso.get("prompt_tokens_details", {}).get("cached_tokens"),
        }
    candidato = r["candidates"][0]
    partes = candidato.get("content", {}).get("parts", [])
    uso = r.get("usageMetadata", {})
    return {
        "modelo": modelo,
        "texto": "".join(p.get("text", "") for p in partes),
        "herramientas": [{"nombre": p["functionCall"]["name"],
                          "entrada": p["functionCall"].get("args", {})}
                         for p in partes if "functionCall" in p],
        "stop_reason": candidato.get("finishReason"),
        "tokens_entrada": uso.get("promptTokenCount"),
        "tokens_salida": uso.get("candidatesTokenCount"),
        "tokens_cache_escritura": None,
        "tokens_cache_lectura": uso.get("cachedContentTokenCount"),
    }


def validar(salida, reglas):
    if reglas is None:
        return None
    if reglas == "json":
        try:
            json.loads(salida)
            return True
        except json.JSONDecodeError:
            return False
    if isinstance(reglas, dict) and "etiquetas" in reglas:
        return salida.strip() in reglas["etiquetas"]
    if isinstance(reglas, dict) and "resumen" in reglas:
        return validar_resumen(salida, reglas["resumen"])
    return None


def validar_resumen(salida, reglas):
    texto = salida.strip()
    if texto == reglas["respuesta_exacta"]:
        return True
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    if len(lineas) != reglas["vinetas"]:
        return False
    return all(linea.startswith("- ") and len(linea[2:].split()) <= reglas["max_palabras"]
               for linea in lineas)


def main():
    cargar_env_local()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plantilla")
    parser.add_argument("--proveedor", choices=sorted(PROVEEDORES), default="anthropic")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--var", action="append", default=[], metavar="CLAVE=VALOR")
    parser.add_argument("--archivo", action="append", default=[], metavar="CLAVE=RUTA")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--no-guardar", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the request body without calling the API.")
    args = parser.parse_args()

    if args.modelo is None:
        if args.proveedor != "anthropic":
            sys.exit(f"Pass --modelo for the provider {args.proveedor}.")
        args.modelo = MODELO_ANTHROPIC

    clave = os.environ.get(PROVEEDORES[args.proveedor]["clave"], "")
    if not clave and not args.dry_run:
        sys.exit(f"{PROVEEDORES[args.proveedor]['clave']} is missing (in the environment or in semana-05/.env).")

    plantilla = cargar_plantilla(args.plantilla)
    variables = {}
    for par in args.var:
        nombre, _, valor = par.partition("=")
        variables[nombre] = valor
    for par in args.archivo:
        nombre, _, ruta = par.partition("=")
        variables[nombre] = Path(ruta).read_text(encoding="utf-8")

    faltan = set(re.findall(r"\{(\w+)\}", plantilla["usuario"])) - set(variables)
    if faltan:
        sys.exit(f"Missing variables: {', '.join(sorted(faltan))}")

    cuerpo = construir(args.proveedor, plantilla, variables, args.modelo, args.max_tokens)
    if args.dry_run:
        print(json.dumps(cuerpo, ensure_ascii=False, indent=2))
        return

    inicio = time.perf_counter()
    crudo = llamar(args.proveedor, cuerpo, clave, args.modelo)
    latencia = time.perf_counter() - inicio
    resultado = interpretar(args.proveedor, crudo, args.modelo)

    registro = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proveedor": args.proveedor,
        "plantilla": plantilla["nombre"],
        "version": plantilla["version"],
        "contexto": plantilla.get("contexto"),
        "modelo": resultado["modelo"],
        "latencia_s": round(latencia, 3),
        "stop_reason": resultado["stop_reason"],
        "tokens_entrada": resultado["tokens_entrada"],
        "tokens_salida": resultado["tokens_salida"],
        "tokens_cache_escritura": resultado["tokens_cache_escritura"],
        "tokens_cache_lectura": resultado["tokens_cache_lectura"],
        "validacion": validar(resultado["texto"], plantilla.get("validar")),
        "texto": resultado["texto"],
        "herramientas": resultado["herramientas"],
    }
    print(json.dumps(registro, ensure_ascii=False, indent=2))
    if not args.no_guardar:
        REGISTRO.parent.mkdir(exist_ok=True)
        with REGISTRO.open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
