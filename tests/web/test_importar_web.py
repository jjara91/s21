from io import BytesIO

from pypdf import PdfWriter

from app.pdf import campos
from tests.fixtures.sintetico import crear_s21_sintetico


def _tarjeta_bytes(tmp_path, nombre: str, anio: str = "2025") -> bytes:
    base = crear_s21_sintetico(tmp_path / f"{nombre}.pdf")
    escritor = PdfWriter(clone_from=str(base))
    escritor.update_page_form_field_values(
        escritor.pages[0],
        {
            campos.CABECERA_TEXTO["nombre"]: nombre,
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: anio,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
        auto_regenerate=False,
    )
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def _subir(cliente, tmp_path, nombres: list[str]):
    archivos = [
        ("archivos", (f"{nombre}.pdf", _tarjeta_bytes(tmp_path, nombre), "application/pdf"))
        for nombre in nombres
    ]
    return cliente.post("/importar", files=archivos, follow_redirects=True)


def test_la_pantalla_de_importar_carga(cliente):
    assert cliente.get("/importar").status_code == 200


def test_subir_lleva_a_la_revision_sin_escribir_nada(cliente, tmp_path):
    respuesta = _subir(cliente, tmp_path, ["Rojas Mauricio"])

    assert "Rojas Mauricio" in respuesta.text
    assert "Crear nuevo" in respuesta.text
    # nada en la base todavía
    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_rechaza_un_pdf_que_no_es_s21(cliente):
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    escritor.write(buffer)

    respuesta = cliente.post(
        "/importar",
        files=[("archivos", ("cualquiera.pdf", buffer.getvalue(), "application/pdf"))],
        follow_redirects=True,
    )

    assert "no es una tarjeta S-21 rellenable" in respuesta.text


def test_aplicar_la_revision_crea_el_publicador_y_sus_registros(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]

    cliente.post(
        f"/importar/{lote}",
        data={
            "destino_0": "nuevo",
            "campo_0_fecha_bautismo": "1",
            "nombramiento_0_siervo_ministerial": "1",
            "desde_0_siervo_ministerial": "2024-09-01",
            "mes_0_9": "1",
        },
        follow_redirects=True,
    )

    assert "Rojas Mauricio" in cliente.get("/publicadores").text
    assert "siervo ministerial" in cliente.get("/publicadores/1").text
    assert "15" in cliente.get("/publicadores/1/tarjeta/2025").text


def test_omitir_un_archivo_no_escribe_nada(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]

    cliente.post(f"/importar/{lote}", data={"destino_0": "omitir"}, follow_redirects=True)

    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_deshacer_revierte_el_lote(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]
    cliente.post(
        f"/importar/{lote}",
        data={"destino_0": "nuevo", "mes_0_9": "1"},
        follow_redirects=True,
    )

    cliente.post(f"/importar/{lote}/deshacer", follow_redirects=True)

    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_el_historial_lista_el_lote_aplicado(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]
    cliente.post(f"/importar/{lote}", data={"destino_0": "nuevo"}, follow_redirects=True)

    assert lote in cliente.get("/importar").text


def test_importar_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/importar", follow_redirects=False).status_code == 303
