import os
import time
from io import BytesIO

from pypdf import PdfWriter

from app.pdf import campos
from app.services import importacion as servicio_importacion
from app.web.routers import importar as router_importar
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


def test_un_lote_con_forma_invalida_no_revienta(cliente, tmp_path):
    # ".." decodificado desde %2e%2e: antes de validar la forma del
    # identificador, esto resolvía a data/subidas/.. -> data/ y terminaba en
    # un 500 al intentar partir por "_" el nombre de un archivo que ya
    # estuviera ahí (p. ej. s21.db). Hace falta que data/subidas/ ya exista
    # -de una importación anterior, como en cualquier instalación real- para
    # que la resolución de ".." tenga algo que listar.
    _subir(cliente, tmp_path, ["Rojas Mauricio"])

    assert cliente.get("/importar/%2e%2e", follow_redirects=False).status_code == 303
    assert cliente.post("/importar/%2e%2e", follow_redirects=False).status_code == 303
    assert (
        cliente.post("/importar/%2e%2e/deshacer", follow_redirects=False).status_code == 303
    )
    assert (
        cliente.post("/importar/%2e%2e/descartar", follow_redirects=False).status_code == 303
    )


def test_descartar_borra_los_archivos_sin_tocar_la_base(cliente, tmp_path):
    revision = _subir(cliente, tmp_path, ["Rojas Mauricio"])
    lote = revision.text.split('action="/importar/')[1].split('"')[0]

    respuesta = cliente.post(f"/importar/{lote}/descartar", follow_redirects=False)

    assert respuesta.status_code == 303
    # el lote ya no existe en disco: revisarlo de nuevo redirige a /importar
    assert cliente.get(f"/importar/{lote}", follow_redirects=False).status_code == 303
    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_subir_rechaza_un_archivo_que_supera_el_limite(cliente, tmp_path, monkeypatch):
    monkeypatch.setattr(router_importar, "LIMITE_SUBIDA", 10)

    respuesta = _subir(cliente, tmp_path, ["Rojas Mauricio"])

    assert respuesta.status_code == 400
    assert "supera el límite" in respuesta.text
    # nada se guardó: ni en disco (no hay lote que revisar) ni en la base
    assert "No hay publicadores" in cliente.get("/publicadores").text


def test_importar_purga_los_lotes_abandonados_al_entrar(cliente, tmp_path):
    lote = servicio_importacion.guardar_lote([("a.pdf", b"contenido")])
    directorio = tmp_path / "subidas" / lote
    vencido = time.time() - (servicio_importacion.DIAS_RETENCION_LOTES + 1) * 86400
    os.utime(directorio, (vencido, vencido))

    cliente.get("/importar")

    assert not directorio.exists()
