from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.pdf import campos, importar


def _tarjeta(ruta, valores: dict[str, str]) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(escritor.pages[0], valores, auto_regenerate=False)
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("14.03.1985", date(1985, 3, 14)),
        ("14/03/1985", date(1985, 3, 14)),
        ("1985-03-14", date(1985, 3, 14)),
        ("  07.06.2002 ", date(2002, 6, 7)),
    ],
)
def test_parsear_fecha_acepta_los_tres_formatos(texto, esperado):
    assert importar.parsear_fecha(texto) == (esperado, None)


@pytest.mark.parametrize("texto", ["", None, "   "])
def test_parsear_fecha_vacia_devuelve_none_sin_texto_crudo(texto):
    assert importar.parsear_fecha(texto) == (None, None)


def test_parsear_fecha_ilegible_conserva_el_texto_crudo():
    assert importar.parsear_fecha("marzo de 1985") == (None, "marzo de 1985")


def test_lee_la_cabecera(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["fecha_nacimiento"]: "14.03.1985",
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025",
            campos.CABECERA_SEXO["H"]: campos.MARCADA,
            campos.CABECERA_ESPERANZA["otras_ovejas"]: campos.MARCADA,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.nombre == "Mauricio Andrés Rojas Vega"
    assert tarjeta.fecha_nacimiento == date(1985, 3, 14)
    assert tarjeta.fecha_bautismo == date(2002, 6, 7)
    assert tarjeta.anio_servicio == 2025
    assert tarjeta.sexo == "H"
    assert tarjeta.esperanza == "otras_ovejas"
    assert tarjeta.nombramientos == {"siervo_ministerial"}


def test_lee_las_filas_de_los_meses(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("precursor_auxiliar", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
            campos.campo_fila("notas", 9): "de 15 horas",
            campos.campo_fila("cursos_biblicos", 4): "1",
            campos.campo_fila("notas", 7): "nombrado siervo ministerial",
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    septiembre = tarjeta.mes(9)
    assert septiembre.participo is True
    assert septiembre.precursor_auxiliar is True
    assert septiembre.horas == 15
    assert septiembre.notas == "de 15 horas"
    assert tarjeta.mes(4).cursos_biblicos == 1
    assert tarjeta.mes(7).notas == "nombrado siervo ministerial"
    assert tarjeta.mes(10).participo is False
    assert tarjeta.mes(10).horas is None


def test_las_horas_no_numericas_no_abortan_la_lectura(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Perez Ana",
            campos.campo_fila("horas", 9): "quince",
            campos.campo_fila("horas", 10): "30",
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.mes(9).horas is None
    assert tarjeta.mes(9).notas == "quince"  # el texto no se pierde
    assert tarjeta.mes(10).horas == 30


def test_anio_de_servicio_no_numerico_conserva_el_texto_crudo(plantilla_sintetica):
    contenido = _tarjeta(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Perez Ana",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025-2026",
        },
    )

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.anio_servicio is None
    assert tarjeta.anio_servicio_crudo == "2025-2026"


def test_anio_de_servicio_vacio_no_deja_texto_crudo(plantilla_sintetica):
    contenido = _tarjeta(plantilla_sintetica, {campos.CABECERA_TEXTO["nombre"]: "Perez Ana"})

    tarjeta = importar.leer_tarjeta(contenido)

    assert tarjeta.anio_servicio is None
    assert tarjeta.anio_servicio_crudo is None


def test_rechaza_un_pdf_que_no_es_s21():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)
    with pytest.raises(importar.TarjetaInvalida):
        importar.leer_tarjeta(buffer.getvalue())
