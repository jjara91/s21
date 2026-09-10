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


def test_exportar_en_lote_combinado_devuelve_un_pdf(cliente, tmp_path):
    _subir_plantilla(cliente, tmp_path)
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/publicadores", data={"nombre_completo": "Soto Luis"})

    respuesta = cliente.post(
        "/exportar", data={"anio_servicio": "2026", "formato": "combinado"}
    )

    assert len(PdfReader(BytesIO(respuesta.content)).pages) == 2
