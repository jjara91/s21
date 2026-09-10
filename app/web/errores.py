"""Errores de la capa web y ayudantes para no dejar escapar excepciones crudas."""

from datetime import date


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
