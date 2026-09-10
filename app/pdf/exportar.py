"""Relleno de la plantilla S-21 con los datos de una tarjeta."""

import re
from datetime import date
from io import BytesIO

from pypdf import PdfWriter

from app.dominio import DatosTarjeta
from app.pdf import campos

FORMATO_FECHA = "%d.%m.%Y"


def _fecha(valor: date | None, crudo: str | None) -> str:
    if valor is not None:
        return valor.strftime(FORMATO_FECHA)
    return crudo or ""


def _numero(valor: int | None) -> str:
    return "" if valor is None else str(valor)


def _casilla(activa: bool) -> str:
    return campos.MARCADA if activa else campos.DESMARCADA


def valores_de(datos: DatosTarjeta) -> dict[str, str]:
    """Traduce la tarjeta al diccionario de campos del formulario."""
    valores: dict[str, str] = {
        campos.CABECERA_TEXTO["nombre"]: datos.nombre or "",
        campos.CABECERA_TEXTO["fecha_nacimiento"]: _fecha(
            datos.fecha_nacimiento, datos.fecha_nacimiento_cruda
        ),
        campos.CABECERA_TEXTO["fecha_bautismo"]: _fecha(
            datos.fecha_bautismo, datos.fecha_bautismo_cruda
        ),
        campos.CABECERA_TEXTO["anio_servicio"]: _numero(datos.anio_servicio),
        campos.TOTAL["horas"]: _numero(datos.total_horas()),
        # el formulario tiene una nota junto al total; no hay dato que la alimente
        campos.TOTAL["notas"]: "",
    }

    for clave, campo in campos.CABECERA_SEXO.items():
        valores[campo] = _casilla(datos.sexo == clave)
    for clave, campo in campos.CABECERA_ESPERANZA.items():
        valores[campo] = _casilla(datos.esperanza == clave)
    for clave, campo in campos.CABECERA_NOMBRAMIENTOS.items():
        valores[campo] = _casilla(clave in datos.nombramientos)

    for fila in datos.meses:
        valores[campos.campo_fila("participo", fila.mes)] = _casilla(fila.participo)
        valores[campos.campo_fila("cursos_biblicos", fila.mes)] = _numero(
            fila.cursos_biblicos
        )
        valores[campos.campo_fila("precursor_auxiliar", fila.mes)] = _casilla(
            fila.precursor_auxiliar
        )
        valores[campos.campo_fila("horas", fila.mes)] = _numero(fila.horas)
        valores[campos.campo_fila("notas", fila.mes)] = fila.notas or ""

    return valores


def rellenar(plantilla: bytes, datos: DatosTarjeta) -> bytes:
    escritor = PdfWriter(clone_from=BytesIO(plantilla))
    escritor.set_need_appearances_writer(True)
    for pagina in escritor.pages:
        escritor.update_page_form_field_values(
            pagina, valores_de(datos), auto_regenerate=True
        )
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def nombre_archivo(nombre: str, anio_servicio: int) -> str:
    limpio = re.sub(r"[/\\:]", "-", nombre).strip()
    return f"{limpio} - {anio_servicio}.pdf"
