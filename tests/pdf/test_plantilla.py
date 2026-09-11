import pytest
from pypdf import PdfReader, PdfWriter

from app.pdf import campos, plantilla
from tests.fixtures import sintetico
from io import BytesIO


def _con_valores(ruta) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(
        escritor.pages[0],
        {
            campos.CABECERA_TEXTO["nombre"]: "Rojas Vega Mauricio",
            campos.CABECERA_NOMBRAMIENTOS["anciano"]: campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
        auto_regenerate=False,
    )
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def test_validar_acepta_un_s21(plantilla_sintetica):
    plantilla.validar_es_s21(plantilla_sintetica.read_bytes())  # no lanza


def test_validar_rechaza_un_pdf_sin_formulario():
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)
    with pytest.raises(plantilla.TarjetaInvalida) as error:
        plantilla.validar_es_s21(buffer.getvalue())
    assert len(error.value.faltantes) == 75


def test_validar_rechaza_un_archivo_que_no_abre_como_pdf():
    with pytest.raises(plantilla.TarjetaInvalida):
        plantilla.validar_es_s21(b"esto no es un PDF")


def test_crear_plantilla_borra_todos_los_valores(plantilla_sintetica):
    lleno = _con_valores(plantilla_sintetica)
    vacio = plantilla.crear_plantilla(lleno)

    quedan = {
        nombre: campo.get("/V")
        for nombre, campo in (PdfReader(BytesIO(vacio)).get_fields() or {}).items()
        if campo.get("/V") not in (None, "", campos.DESMARCADA)
    }
    assert quedan == {}


def test_crear_plantilla_conserva_los_75_campos(plantilla_sintetica):
    vacio = plantilla.crear_plantilla(_con_valores(plantilla_sintetica))
    presentes = set(PdfReader(BytesIO(vacio)).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)


def test_validar_acepta_una_tarjeta_guardada_por_vista_previa(plantilla_sintetica):
    # Vista Previa deja /AcroForm/Fields con un solo campo; los 75 widgets siguen
    # en la página y la tarjeta tiene que seguir siendo válida.
    roto = sintetico.romper_fields(_con_valores(plantilla_sintetica))
    plantilla.validar_es_s21(roto)  # no lanza


def test_crear_plantilla_repara_el_indice_de_campos(plantilla_sintetica):
    # una tarjeta guardada por Vista Previa trae /AcroForm/Fields con un campo:
    # la plantilla no puede heredar ese índice roto o el PDF exportado sería
    # ilegible para otros lectores
    roto = sintetico.romper_fields(_con_valores(plantilla_sintetica))
    vacio = plantilla.crear_plantilla(roto)
    assert set(PdfReader(BytesIO(vacio)).get_fields() or {}) == set(campos.TODOS_LOS_CAMPOS)
