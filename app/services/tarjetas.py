"""Puente entre la base de datos y la capa PDF."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from pypdf import PdfWriter
from sqlmodel import Session

from app.config import cargar_config
from app.pdf import exportar, plantilla
from app.services import nombramientos, registros

CARPETA_PRECURSORES = "Precursores regulares"


class PlantillaAusente(Exception):
    pass


def hay_plantilla() -> bool:
    return cargar_config().ruta_plantilla.exists()


def guardar_plantilla(contenido: bytes) -> None:
    """Vacía la tarjeta recibida y la deja como plantilla en el volumen de datos."""
    ruta = cargar_config().ruta_plantilla
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(plantilla.crear_plantilla(contenido))


def _plantilla() -> bytes:
    ruta = cargar_config().ruta_plantilla
    if not ruta.exists():
        raise PlantillaAusente(
            "todavía no hay plantilla; sube una tarjeta S-21 en /plantilla"
        )
    return ruta.read_bytes()


def pdf_de(
    sesion: Session, publicador_id: int, anio_servicio: int, *, aplanado: bool = False
) -> tuple[str, bytes]:
    base = _plantilla()
    # deja escrita la nota de cambio de privilegio donde la nota esté vacía
    registros.aplicar_notas_sugeridas(sesion, publicador_id, anio_servicio)
    datos = registros.tarjeta(sesion, publicador_id, anio_servicio)
    contenido = exportar.rellenar(base, datos)
    if aplanado:
        contenido = exportar.aplanar(contenido)
    return exportar.nombre_archivo(datos.nombre, anio_servicio), contenido


def zip_de(
    sesion: Session,
    publicador_ids: list[int],
    anio_servicio: int,
    *,
    aplanado: bool = False,
    separar_precursores: bool = False,
) -> bytes:
    """Un PDF por publicador; con `separar_precursores`, quien fue precursor
    regular aunque sea un mes del año va a su propia carpeta dentro del ZIP
    (el mismo criterio que marca la casilla en la tarjeta)."""
    salida = BytesIO()
    with ZipFile(salida, "w", ZIP_DEFLATED) as archivo:
        for publicador_id in publicador_ids:
            nombre, contenido = pdf_de(
                sesion, publicador_id, anio_servicio, aplanado=aplanado
            )
            es_precursor = "precursor_regular" in nombramientos.tipos_en_anio(
                sesion, publicador_id, anio_servicio
            )
            if separar_precursores and es_precursor:
                nombre = f"{CARPETA_PRECURSORES}/{nombre}"
            archivo.writestr(nombre, contenido)
    return salida.getvalue()


def pdf_combinado(
    sesion: Session,
    publicador_ids: list[int],
    anio_servicio: int,
    *,
    aplanado: bool = False,
) -> bytes:
    escritor = PdfWriter()
    for publicador_id in publicador_ids:
        _nombre, contenido = pdf_de(
            sesion, publicador_id, anio_servicio, aplanado=aplanado
        )
        escritor.append(BytesIO(contenido))
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
