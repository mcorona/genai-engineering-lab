"""The agent's structured final answer. It is delivered with the `responder` tool, whose JSON Schema is this model."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ESTADOS_MODELO = ("respondida", "requiere_aclaracion", "abstenida")
ESTADOS = ESTADOS_MODELO + ("limite_alcanzado", "error")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Resultado(_M):
    clave: str = Field(description="Output key name, exactly as listed in the task.")
    sql: str = Field(description="The single SELECT, over the legacy tables, whose result is exactly this key's value.")
    valor: str | int | float | bool | None | list = Field(
        description="The value: a number, a text, or a list (of values or of rows) as returned by the SQL.")


class Evidencia(_M):
    tipo: Literal["filas", "regla"]
    referencia: str = Field(description="For rows, the SQL that was run; for a rule, its id (e.g. R-COB).")
    extracto: str = Field(max_length=600, description="Short excerpt: a few rows, or the part of the rule that was applied.")


class RespuestaFinal(_M):
    estado: Literal[ESTADOS_MODELO]  # type: ignore[valid-type]
    respuesta: str = Field(max_length=2000, description="Answer for the user, in the language of the task.")
    resultados: list[Resultado] = Field(default_factory=list,
                                        description="One entry per output key when estado is 'respondida'; empty otherwise.")
    evidencia: list[Evidencia] = Field(default_factory=list)
    supuestos: list[str] = Field(default_factory=list, description="Interpretations or assumptions you made.")
    pregunta_aclaracion: str | None = Field(default=None, description="Required when estado is 'requiere_aclaracion'.")


def herramienta_responder() -> dict:
    esquema = RespuestaFinal.model_json_schema()
    return {"name": "responder",
            "description": "Deliver the final answer and end the task. Call it exactly once, alone, when you are done: "
                           "with estado 'respondida' and one resultado per output key, 'requiere_aclaracion' with a "
                           "question if the request is ambiguous, or 'abstenida' if the data cannot answer it.",
            "input_schema": esquema}
