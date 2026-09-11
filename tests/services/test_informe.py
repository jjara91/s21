from datetime import date

import pytest

from app.services import informe, nombramientos, publicadores, registros


@pytest.mark.parametrize(
    "tipos,auxiliar,esperado",
    [
        (set(), False, "publicador"),
        (set(), True, "precursor_auxiliar"),
        ({"precursor_regular"}, False, "precursor_regular"),
        # el regular que además fue auxiliar cuenta una sola vez, como regular
        ({"precursor_regular"}, True, "precursor_regular"),
        ({"precursor_especial", "precursor_regular"}, True, "precursor_especial"),
        ({"misionero_campo", "precursor_especial"}, True, "misionero_campo"),
        # anciano y siervo ministerial no son categorías de informe
        ({"anciano"}, False, "publicador"),
        ({"siervo_ministerial"}, True, "precursor_auxiliar"),
    ],
)
def test_precedencia_de_categorias(tipos, auxiliar, esperado):
    assert informe.categoria_de(tipos, auxiliar) == esperado


def test_informe_cuenta_solo_a_quienes_informaron(sesion):
    informo = publicadores.crear(sesion, "Informo Uno")
    callado = publicadores.crear(sesion, "Callado Dos")
    registros.guardar_mes(
        sesion,
        2026,
        1,
        [
            registros.EntradaMes(publicador_id=informo.id, participo=True, cursos_biblicos=3),
            registros.EntradaMes(publicador_id=callado.id, participo=False),
        ],
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 1
    assert resultado.no_informaron == 1
    assert resultado.total_cursos == 3


def test_un_mes_sin_ninguna_fila_cuenta_como_sin_cargar_no_como_no_informado(sesion):
    """Un mes que nadie ha cargado (típicamente un mes futuro del año en
    curso) no es lo mismo que un mes cargado donde nadie informó: mezclarlos
    hace que /informe/anual muestre los meses futuros como si toda la
    congregación hubiera dejado de predicar."""
    publicadores.crear(sesion, "Sin Fila")

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 0
    assert resultado.no_informaron == 0
    assert resultado.sin_cargar == 1


def test_un_publicador_cargado_sin_informar_cuenta_aparte_de_sin_cargar(sesion):
    cargado = publicadores.crear(sesion, "Cargado Sin Informar")
    publicadores.crear(sesion, "Sin Cargar")
    registros.guardar_mes(
        sesion, 2026, 1, [registros.EntradaMes(publicador_id=cargado.id, participo=False)]
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.no_informaron == 1
    assert resultado.sin_cargar == 1


def test_las_bajas_no_entran_en_el_informe(sesion):
    baja = publicadores.crear(sesion, "Baja Uno")
    publicadores.dar_de_baja(sesion, baja.id, date(2025, 12, 1), "mudado")

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.total_informaron == 0
    assert resultado.no_informaron == 0


def test_la_fila_de_publicadores_no_lleva_horas(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    registros.guardar_mes(
        sesion, 2026, 1, [registros.EntradaMes(publicador_id=ana.id, participo=True)]
    )

    fila = next(f for f in informe.informe_mensual(sesion, 2026, 1).filas if f.clave == "publicador")

    assert fila.informaron == 1
    assert fila.horas is None


def test_suma_horas_por_categoria_y_promedio_de_regulares(sesion):
    regular_uno = publicadores.crear(sesion, "Regular Uno")
    regular_dos = publicadores.crear(sesion, "Regular Dos")
    auxiliar = publicadores.crear(sesion, "Auxiliar Tres")
    nombramientos.crear(sesion, regular_uno.id, "precursor_regular", date(2025, 9, 1))
    nombramientos.crear(sesion, regular_dos.id, "precursor_regular", date(2025, 9, 1))
    registros.guardar_mes(
        sesion,
        2026,
        1,
        [
            registros.EntradaMes(publicador_id=regular_uno.id, participo=True, horas=70),
            registros.EntradaMes(publicador_id=regular_dos.id, participo=True, horas=64),
            registros.EntradaMes(
                publicador_id=auxiliar.id, participo=True, precursor_auxiliar=True, horas=30
            ),
        ],
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)
    por_clave = {fila.clave: fila for fila in resultado.filas}

    assert por_clave["precursor_regular"].informaron == 2
    assert por_clave["precursor_regular"].horas == 134
    assert por_clave["precursor_auxiliar"].horas == 30
    assert resultado.total_horas == 164
    assert resultado.promedio_horas_precursor_regular == 67


def test_promedio_redondea_medio_hacia_arriba(sesion):
    """66.5 debe salir 67. round() de Python daría 66 por redondeo bancario."""
    uno = publicadores.crear(sesion, "Regular Uno")
    dos = publicadores.crear(sesion, "Regular Dos")
    for p in (uno, dos):
        nombramientos.crear(sesion, p.id, "precursor_regular", date(2025, 9, 1))
    registros.guardar_mes(
        sesion,
        2026,
        1,
        [
            registros.EntradaMes(publicador_id=uno.id, participo=True, horas=65),
            registros.EntradaMes(publicador_id=dos.id, participo=True, horas=68),
        ],
    )

    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert resultado.promedio_horas_precursor_regular == 67


def test_promedio_es_none_sin_precursores_regulares(sesion):
    assert informe.informe_mensual(sesion, 2026, 1).promedio_horas_precursor_regular is None


def test_las_filas_salen_siempre_en_el_mismo_orden(sesion):
    resultado = informe.informe_mensual(sesion, 2026, 1)

    assert [fila.clave for fila in resultado.filas] == [
        "publicador",
        "precursor_auxiliar",
        "precursor_regular",
        "precursor_especial",
        "misionero_campo",
    ]


def test_informe_anual_trae_doce_meses_de_septiembre_a_agosto(sesion):
    anual = informe.informe_anual(sesion, 2026)

    assert len(anual) == 12
    assert (anual[0].anio, anual[0].mes) == (2025, 9)
    assert (anual[-1].anio, anual[-1].mes) == (2026, 8)
