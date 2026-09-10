from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfReader

from app.pdf import importar
from app.services import nombramientos, publicadores, registros, tarjetas


@pytest.fixture(autouse=True)
def plantilla_en_data(tmp_path, monkeypatch, plantilla_sintetica):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import cargar_config

    (tmp_path / "plantilla_s21.pdf").write_bytes(plantilla_sintetica.read_bytes())
    return cargar_config()


def _ana(sesion):
    ana = publicadores.crear(
        sesion, "Pérez Gómez Ana María", sexo="M", fecha_bautismo=date(2010, 4, 3)
    )
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 9, 1))
    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)]
    )
    return ana


def test_hay_plantilla(plantilla_en_data):
    assert tarjetas.hay_plantilla() is True


def test_pdf_de_devuelve_nombre_y_contenido(sesion):
    ana = _ana(sesion)

    nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert nombre == "Pérez Gómez Ana María - 2026.pdf"
    leida = importar.leer_tarjeta(contenido)
    assert leida.nombre == "Pérez Gómez Ana María"
    assert leida.mes(9).horas == 52
    assert leida.nombramientos == {"precursor_regular"}


def test_pdf_aplanado_no_tiene_formulario(sesion):
    ana = _ana(sesion)

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026, aplanado=True)

    assert PdfReader(BytesIO(contenido)).get_fields() in (None, {})


def test_zip_trae_un_pdf_por_publicador(sesion):
    ana = _ana(sesion)
    luis = publicadores.crear(sesion, "Soto Luis")

    contenido = tarjetas.zip_de(sesion, [ana.id, luis.id], 2026)

    with ZipFile(BytesIO(contenido)) as archivo:
        assert sorted(archivo.namelist()) == [
            "Pérez Gómez Ana María - 2026.pdf",
            "Soto Luis - 2026.pdf",
        ]


def test_pdf_combinado_tiene_una_pagina_por_publicador(sesion):
    ana = _ana(sesion)
    luis = publicadores.crear(sesion, "Soto Luis")

    contenido = tarjetas.pdf_combinado(sesion, [ana.id, luis.id], 2026)

    assert len(PdfReader(BytesIO(contenido)).pages) == 2


def test_exportar_escribe_la_nota_de_cambio_de_privilegio(sesion):
    ana = _ana(sesion)  # nombrada precursora regular el 01.09.2025

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert importar.leer_tarjeta(contenido).mes(9).notas == "nombrado precursor regular"


def test_exportar_no_pisa_una_nota_escrita_a_mano(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52,
                              notas="escrito a mano")],
    )

    _nombre, contenido = tarjetas.pdf_de(sesion, ana.id, 2026)

    assert importar.leer_tarjeta(contenido).mes(9).notas == "escrito a mano"


def test_sin_plantilla_lanza(sesion, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "vacio"))
    ana = _ana(sesion)

    with pytest.raises(tarjetas.PlantillaAusente):
        tarjetas.pdf_de(sesion, ana.id, 2026)


def test_guardar_plantilla_la_deja_en_blanco(tmp_path, monkeypatch, plantilla_sintetica):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "nueva"))

    tarjetas.guardar_plantilla(plantilla_sintetica.read_bytes())

    assert tarjetas.hay_plantilla() is True
