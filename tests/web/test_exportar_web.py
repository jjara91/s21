from io import BytesIO

from pypdf import PdfReader

from tests.fixtures.sintetico import crear_s21_sintetico


def _subir_plantilla(cliente, tmp_path):
    ruta = crear_s21_sintetico(tmp_path / "para_subir.pdf")
    return cliente.post(
        "/plantilla",
        files={"archivo": ("s21.pdf", ruta.read_bytes(), "application/pdf")},
        follow_redirects=True,
    )


def test_sin_plantilla_exportar_redirige_al_bootstrap(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/plantilla"


def test_subir_la_plantilla_y_exportar(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert "Perez Ana - 2026.pdf" in respuesta.headers["content-disposition"]
    assert len(PdfReader(BytesIO(respuesta.content)).get_fields() or {}) == 75


def test_exportar_aplanado(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf", params={"aplanado": "1"})

    assert PdfReader(BytesIO(respuesta.content)).get_fields() in (None, {})


def test_la_vista_de_tarjeta_muestra_los_doce_meses(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026")

    assert "Septiembre" in respuesta.text
    assert "Agosto" in respuesta.text


def test_exportar_en_lote_devuelve_un_zip(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/publicadores", data={"nombre_completo": "Soto Luis"})

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "zip"}
    )

    assert respuesta.headers["content-type"] == "application/zip"


def test_exportar_en_lote_incluye_a_quien_se_dio_de_baja_a_mitad_de_anio(cliente, tmp_path):
    """El año de servicio 2026 corre de sep-2025 a ago-2026: alguien dado de
    baja en marzo de 2026 estuvo activo la mayor parte del año y su tarjeta
    hay que imprimirla y archivarla igual que la de todos los demás."""
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Baja Marzo"})
    cliente.post(
        "/publicadores/1/baja", data={"fecha_baja": "2026-03-10", "motivo_baja": "mudado"}
    )

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "combinado"}
    )

    assert len(PdfReader(BytesIO(respuesta.content)).pages) == 1


def test_exportar_en_lote_excluye_a_quien_ya_se_habia_dado_de_baja_antes_del_anio(
    cliente, tmp_path
):
    from zipfile import ZipFile

    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Baja Anterior"})
    cliente.post(
        "/publicadores/1/baja", data={"fecha_baja": "2025-06-01", "motivo_baja": "mudado"}
    )

    respuesta = cliente.post("/exportar", data={"anio_servicio": "2026", "formato": "zip"})

    assert ZipFile(BytesIO(respuesta.content)).namelist() == []


def test_exportar_en_lote_combinado_devuelve_un_pdf(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/publicadores", data={"nombre_completo": "Soto Luis"})

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "combinado"}
    )

    assert len(PdfReader(BytesIO(respuesta.content)).pages) == 2


def test_nombre_con_comilla_tipografica_descarga_ok(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    # comilla tipográfica U+2019, como la que deja pegar texto desde Word o Docs
    cliente.post("/publicadores", data={"nombre_completo": "O’Higgins Riquelme Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/2026.pdf")

    assert respuesta.status_code == 200
    assert "filename*=utf-8''" in respuesta.headers["content-disposition"]


def test_anio_fuera_de_rango_da_400_en_espanol(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/publicadores/1/tarjeta/99999.pdf")

    assert respuesta.status_code == 400
    assert "out of range" not in respuesta.text
    assert "fuera de rango" in respuesta.text


def test_subir_algo_que_no_es_pdf_da_mensaje_en_espanol(cliente):
    respuesta = cliente.post(
        "/plantilla",
        files={"archivo": ("no-es-pdf.pdf", b"esto no es un PDF", "application/pdf")},
    )

    assert respuesta.status_code == 400
    texto = respuesta.text.lower()
    assert "stream" not in texto
    assert "unexpectedly" not in texto


def test_archivo_demasiado_grande_se_rechaza(cliente):
    enorme = b"%" * (20 * 1024 * 1024 + 1)

    respuesta = cliente.post(
        "/plantilla",
        files={"archivo": ("grande.pdf", enorme, "application/pdf")},
    )

    assert respuesta.status_code == 400
    assert "MB" in respuesta.text
