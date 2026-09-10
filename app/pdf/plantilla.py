"""Validación de que un PDF es una tarjeta S-21 y vaciado a plantilla."""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from app.pdf import campos


class TarjetaInvalida(Exception):
    def __init__(self, mensaje: str, faltantes: list[str] | None = None) -> None:
        super().__init__(mensaje)
        self.faltantes = faltantes or []


def _leer(contenido: bytes) -> PdfReader:
    try:
        return PdfReader(BytesIO(contenido))
    except (PdfReadError, OSError, ValueError) as error:
        raise TarjetaInvalida(f"el archivo no se pudo abrir como PDF: {error}") from error


def validar_es_s21(contenido: bytes) -> None:
    """Lanza TarjetaInvalida si el PDF no trae los 75 campos del S-21."""
    lector = _leer(contenido)
    presentes = set(lector.get_fields() or {})
    faltantes = sorted(campos.TODOS_LOS_CAMPOS - presentes)
    if faltantes:
        raise TarjetaInvalida(
            "el PDF no es una tarjeta S-21 rellenable "
            f"(faltan {len(faltantes)} campos, por ejemplo {faltantes[0]}); "
            "si es una tarjeta escaneada no sirve, hace falta el formulario original",
            faltantes,
        )


def crear_plantilla(contenido: bytes) -> bytes:
    """Devuelve la misma tarjeta con los 75 campos en blanco."""
    validar_es_s21(contenido)
    escritor = PdfWriter(clone_from=BytesIO(contenido))
    escritor.set_need_appearances_writer(True)

    en_blanco: dict[str, str] = {nombre: "" for nombre in campos.CAMPOS_TEXTO}
    en_blanco.update({nombre: campos.DESMARCADA for nombre in campos.CAMPOS_CASILLA})
    for pagina in escritor.pages:
        escritor.update_page_form_field_values(pagina, en_blanco, auto_regenerate=False)

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
