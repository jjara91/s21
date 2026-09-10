from datetime import date

from app.dominio import DatosTarjeta
from app.pdf import exportar, importar


def _tarjeta_completa() -> DatosTarjeta:
    tarjeta = DatosTarjeta.vacia(nombre="Pérez Gómez Ana María", anio_servicio=2026)
    tarjeta.fecha_nacimiento = date(1988, 5, 12)
    tarjeta.fecha_bautismo = date(2010, 4, 3)
    tarjeta.sexo = "M"
    tarjeta.esperanza = "otras_ovejas"
    tarjeta.nombramientos = {"precursor_regular"}
    septiembre = tarjeta.mes(9)
    septiembre.participo = True
    septiembre.horas = 52
    septiembre.cursos_biblicos = 2
    octubre = tarjeta.mes(10)
    octubre.participo = True
    octubre.precursor_auxiliar = True
    octubre.horas = 30
    octubre.notas = "precursora auxiliar en marzo y abril"
    return tarjeta


def test_round_trip_devuelve_los_mismos_datos(plantilla_sintetica):
    original = _tarjeta_completa()

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), original)
    leida = importar.leer_tarjeta(pdf)

    assert leida.nombre == original.nombre
    assert leida.fecha_nacimiento == original.fecha_nacimiento
    assert leida.fecha_bautismo == original.fecha_bautismo
    assert leida.sexo == "M"
    assert leida.esperanza == "otras_ovejas"
    assert leida.nombramientos == {"precursor_regular"}
    assert leida.anio_servicio == 2026
    assert leida.mes(9).horas == 52
    assert leida.mes(9).cursos_biblicos == 2
    assert leida.mes(10).precursor_auxiliar is True
    assert leida.mes(10).notas == "precursora auxiliar en marzo y abril"


def test_los_meses_vacios_siguen_vacios(plantilla_sintetica):
    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    leida = importar.leer_tarjeta(pdf)

    assert leida.mes(1).participo is False
    assert leida.mes(1).horas is None
    assert leida.mes(1).cursos_biblicos is None
    assert leida.mes(1).notas is None


def test_cursos_en_cero_se_escribe_como_cero(plantilla_sintetica):
    tarjeta = DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    tarjeta.mes(9).cursos_biblicos = 0

    leida = importar.leer_tarjeta(
        exportar.rellenar(plantilla_sintetica.read_bytes(), tarjeta)
    )

    assert leida.mes(9).cursos_biblicos == 0


def test_escribe_el_total_de_horas(plantilla_sintetica):
    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())

    from pypdf import PdfReader
    from io import BytesIO
    from app.pdf import campos

    campos_leidos = PdfReader(BytesIO(pdf)).get_fields()
    assert campos_leidos[campos.TOTAL["horas"]].get("/V") == "82"
    assert (campos_leidos[campos.TOTAL["notas"]].get("/V") or "") == ""


def test_el_pdf_sigue_siendo_un_formulario(plantilla_sintetica):
    from pypdf import PdfReader
    from io import BytesIO

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), _tarjeta_completa())
    assert len(PdfReader(BytesIO(pdf)).get_fields() or {}) == 75


def test_nombre_de_archivo():
    assert exportar.nombre_archivo("Pérez Gómez Ana María", 2026) == (
        "Pérez Gómez Ana María - 2026.pdf"
    )


def test_nombre_de_archivo_sin_caracteres_de_ruta():
    assert exportar.nombre_archivo("Ana/María \\ Pérez", 2026) == (
        "Ana-María - Pérez - 2026.pdf"
    )


def test_fecha_ilegible_usa_fallback_crudo(plantilla_sintetica):
    """Verifica que _fecha(None, crudo) cae a crudo cuando la fecha no se pudo interpretar."""
    tarjeta = DatosTarjeta.vacia(nombre="Torres López Mauricio", anio_servicio=2025)
    tarjeta.fecha_nacimiento = None
    tarjeta.fecha_nacimiento_cruda = "29 de febrero de 1984"

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), tarjeta)
    leida = importar.leer_tarjeta(pdf)

    assert leida.fecha_nacimiento is None
    assert leida.fecha_nacimiento_cruda == "29 de febrero de 1984"


def test_casilla_desmarcada_escribe_off_en_pdf(plantilla_sintetica):
    """Verifica que /Off se escribe literalmente para meses sin participación."""
    from pypdf import PdfReader
    from io import BytesIO
    from app.pdf import campos

    tarjeta = DatosTarjeta.vacia(nombre="Morales Silva Carla", anio_servicio=2025)
    # No marcamos participación en mes 1 (queda False por defecto)

    pdf = exportar.rellenar(plantilla_sintetica.read_bytes(), tarjeta)
    campos_leidos = PdfReader(BytesIO(pdf)).get_fields()

    campo_participo_mes_1 = campos.campo_fila("participo", 1)
    assert campos_leidos[campo_participo_mes_1].get("/V") == campos.DESMARCADA
