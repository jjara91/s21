"""Relleno de la plantilla S-21 con los datos de una tarjeta."""

import re
from datetime import date
from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

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


def _apariencia(widget: DictionaryObject) -> DictionaryObject | None:
    """Stream de apariencia normal del widget, resolviendo el estado de una casilla.

    Devuelve None si el widget no tiene contenido dibujable: casos típicos incluyen
    casillas desmarcadas sin apariencia para el estado /Off, o widgets sin /AP.
    En aplanar(), los widgets con None se omiten silenciosamente, que es lo correcto.
    """
    apariencias = widget.get("/AP")
    if not apariencias or "/N" not in apariencias.get_object():
        return None
    normal = apariencias.get_object()["/N"].get_object()
    if "/BBox" in normal:
        return normal
    estado = widget.get("/AS")
    if estado is None or estado not in normal:
        return None
    candidato = normal[estado].get_object()
    return candidato if "/BBox" in candidato else None


def aplanar(pdf: bytes) -> bytes:
    """Quema los valores en el contenido de la página y elimina el formulario.

    pypdf no trae aplanado: se estampa la apariencia de cada widget como XObject
    en el contenido de la página y luego se descartan las anotaciones.

    NOTA: Usa las APIs internas de pypdf (_add_object, _root_object) porque no hay
    alternativa pública. Una actualización de pypdf exige revisar esta función.
    """
    escritor = PdfWriter(clone_from=BytesIO(pdf))

    for pagina in escritor.pages:
        recursos = pagina["/Resources"].get_object()
        if "/XObject" not in recursos:
            recursos[NameObject("/XObject")] = DictionaryObject()
        xobjects = recursos["/XObject"].get_object()

        operaciones: list[str] = []
        for indice, anotacion in enumerate(pagina.get("/Annots") or []):
            widget = anotacion.get_object()
            apariencia = _apariencia(widget)
            if apariencia is None:
                continue

            nombre = NameObject(f"/Plano{indice}")
            xobjects[nombre] = apariencia.indirect_reference or escritor._add_object(
                apariencia
            )

            rect = [float(valor) for valor in widget["/Rect"]]
            x0, y0 = min(rect[0], rect[2]), min(rect[1], rect[3])
            x1, y1 = max(rect[0], rect[2]), max(rect[1], rect[3])
            caja = [float(valor) for valor in apariencia["/BBox"]]
            ancho = (caja[2] - caja[0]) or 1.0
            alto = (caja[3] - caja[1]) or 1.0
            escala_x, escala_y = (x1 - x0) / ancho, (y1 - y0) / alto
            operaciones.append(
                f"q {escala_x:.5f} 0 0 {escala_y:.5f} "
                f"{x0 - caja[0] * escala_x:.3f} {y0 - caja[1] * escala_y:.3f} cm "
                f"{nombre} Do Q"
            )

        if operaciones:
            extra = DecodedStreamObject()
            # El par q Q inicial aísla el estado gráfico de los operadores siguientes.
            # Si el contenido previo está balanceado (caso normal), es inocuo.
            extra.set_data(("\nq Q\n" + "\n".join(operaciones)).encode())
            referencia = escritor._add_object(extra)
            actual = pagina.raw_get("/Contents")
            contenido = actual.get_object()
            pagina[NameObject("/Contents")] = (
                ArrayObject(list(contenido) + [referencia])
                if isinstance(contenido, ArrayObject)
                else ArrayObject([actual, referencia])
            )

        pagina[NameObject("/Annots")] = ArrayObject()

    if "/AcroForm" in escritor._root_object:
        del escritor._root_object[NameObject("/AcroForm")]

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
