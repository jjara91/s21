from datetime import date

import pytest

from app.services import nombramientos, publicadores


@pytest.fixture
def mauricio(sesion):
    return publicadores.crear(sesion, "Rojas Vega Mauricio")


def test_un_nombramiento_que_empieza_en_septiembre_marca_el_anio_siguiente(sesion, mauricio):
    nombramientos.crear(sesion, mauricio.id, "precursor_regular", date(2025, 9, 1))

    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2025) == set()
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2026) == {"precursor_regular"}


def test_un_nombramiento_cerrado_el_31_de_agosto_marca_ese_anio_y_no_el_siguiente(
    sesion, mauricio
):
    nombramientos.crear(
        sesion, mauricio.id, "anciano", date(2020, 1, 1), hasta=date(2025, 8, 31)
    )

    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2025) == {"anciano"}
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2026) == set()


def test_un_nombramiento_a_caballo_marca_los_dos_anios(sesion, mauricio):
    nombramientos.crear(
        sesion, mauricio.id, "precursor_regular", date(2025, 7, 15), hasta=date(2025, 9, 20)
    )

    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2025) == {"precursor_regular"}
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2026) == {"precursor_regular"}


def test_un_nombramiento_vigente_marca_todos_los_anios_desde_su_inicio(sesion, mauricio):
    nombramientos.crear(sesion, mauricio.id, "siervo_ministerial", date(2025, 7, 1))

    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2024) == set()
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2025) == {"siervo_ministerial"}
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2030) == {"siervo_ministerial"}


def test_tipos_en_mes_usa_el_mes_completo(sesion, mauricio):
    # termina el 5 de marzo: marzo sigue contando, abril ya no
    nombramientos.crear(
        sesion, mauricio.id, "precursor_regular", date(2026, 1, 1), hasta=date(2026, 3, 5)
    )

    assert nombramientos.tipos_en_mes(sesion, mauricio.id, 2026, 3) == {"precursor_regular"}
    assert nombramientos.tipos_en_mes(sesion, mauricio.id, 2026, 4) == set()


def test_nota_sugerida_al_ser_nombrado(sesion, mauricio):
    nombramientos.crear(sesion, mauricio.id, "siervo_ministerial", date(2025, 7, 10))

    assert nombramientos.notas_sugeridas(sesion, mauricio.id, 2025) == {
        7: "nombrado siervo ministerial"
    }


def test_nota_sugerida_al_dejar_el_privilegio(sesion, mauricio):
    nombramientos.crear(
        sesion, mauricio.id, "precursor_regular", date(2024, 1, 1), hasta=date(2026, 2, 28)
    )

    assert nombramientos.notas_sugeridas(sesion, mauricio.id, 2026) == {
        2: "deja de ser precursor regular"
    }


def test_no_sugiere_nada_fuera_del_anio_de_servicio(sesion, mauricio):
    nombramientos.crear(sesion, mauricio.id, "anciano", date(2020, 3, 1))

    assert nombramientos.notas_sugeridas(sesion, mauricio.id, 2026) == {}


def test_dos_cambios_en_el_mismo_mes_se_unen(sesion, mauricio):
    nombramientos.crear(
        sesion, mauricio.id, "precursor_regular", date(2024, 1, 1), hasta=date(2026, 5, 31)
    )
    nombramientos.crear(sesion, mauricio.id, "siervo_ministerial", date(2026, 5, 12))

    sugeridas = nombramientos.notas_sugeridas(sesion, mauricio.id, 2026)

    assert sugeridas[5] == (
        "deja de ser precursor regular · nombrado siervo ministerial"
    )


def test_cerrar_pone_la_fecha_de_termino(sesion, mauricio):
    creado = nombramientos.crear(sesion, mauricio.id, "anciano", date(2020, 1, 1))

    cerrado = nombramientos.cerrar(sesion, creado.id, date(2026, 4, 30))

    assert cerrado.hasta == date(2026, 4, 30)


def test_crear_rechaza_un_tipo_desconocido(sesion, mauricio):
    with pytest.raises(ValueError):
        nombramientos.crear(sesion, mauricio.id, "capitan", date(2026, 1, 1))


def test_crear_rechaza_un_rango_invertido(sesion, mauricio):
    with pytest.raises(ValueError):
        nombramientos.crear(
            sesion, mauricio.id, "anciano", date(2026, 5, 1), hasta=date(2026, 4, 1)
        )
