"""Errores de la capa web y ayudantes para no dejar escapar excepciones crudas."""

from datetime import date
from typing import Annotated

from pydantic import BeforeValidator


class DatosInvalidos(Exception):
    """Lo que envió el usuario no se puede interpretar. Se traduce en un 400."""

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


def fecha_obligatoria(valor: str, etiqueta: str) -> date:
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError:
        raise DatosInvalidos(
            f"{etiqueta} no es una fecha válida: {valor!r}. Usa el formato AAAA-MM-DD."
        ) from None


def fecha_opcional(valor: str | None, etiqueta: str) -> date | None:
    if not (valor or "").strip():
        return None
    return fecha_obligatoria(valor, etiqueta)


ANIO_MINIMO, ANIO_MAXIMO = 1950, 2100


def anio_valido(valor: int) -> int:
    """Valida un año (de servicio o calendario, según lo use quien llama)."""
    if not ANIO_MINIMO <= valor <= ANIO_MAXIMO:
        raise DatosInvalidos(
            f"El año {valor} está fuera de rango. "
            f"Debe estar entre {ANIO_MINIMO} y {ANIO_MAXIMO}."
        )
    return valor


def mes_valido(valor: int) -> int:
    # `mes | mes_nombre` en la plantilla busca la clave en un diccionario de
    # 1 a 12: sin este control, un mes fuera de rango en la URL no cae en un
    # error de negocio legible sino en un KeyError sin capturar.
    if not 1 <= valor <= 12:
        raise DatosInvalidos(f"El mes {valor} no es válido. Debe estar entre 1 y 12.")
    return valor


def _vacio_a_none(valor: object) -> object:
    """Un campo de filtro vacío igual viaja en la URL: un <select> con la
    opción «Todos» de valor vacío, o un <input type="number"> que el usuario
    borró, envían la cadena vacía. Sin esto, Pydantic la rechaza contra
    `int | None` y la petición muere en un error de validación antes de
    llegar al endpoint."""
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


# Todo parámetro numérico de las barras de filtro (grupo_id, anio, mes...):
# vacío significa «sin filtrar», que es lo mismo que no mandarlo.
EnteroOpcional = Annotated[int | None, BeforeValidator(_vacio_a_none)]


def _vacio_a_falso(valor: object) -> object:
    if isinstance(valor, str) and not valor.strip():
        return False
    return valor


# Una casilla de filtro vacía en la URL (guardada o escrita a mano) equivale a
# no marcarla; contra `bool` a secas, Pydantic rechaza la cadena vacía.
BooleanoDeFiltro = Annotated[bool, BeforeValidator(_vacio_a_falso)]
