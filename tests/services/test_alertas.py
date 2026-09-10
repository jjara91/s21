from datetime import date

from app.services import alertas, publicadores, registros


def test_la_ventana_son_los_seis_meses_completos_anteriores():
    assert alertas.ventana(date(2026, 3, 15)) == [
        (2025, 9),
        (2025, 10),
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    ]


def test_la_ventana_cruza_bien_el_cambio_de_anio():
    assert alertas.ventana(date(2026, 1, 5))[0] == (2025, 7)
    assert alertas.ventana(date(2026, 1, 5))[-1] == (2025, 12)


def _informar(sesion, publicador_id, meses):
    for anio, mes in meses:
        registros.guardar_mes(
            sesion,
            anio,
            mes,
            [registros.EntradaMes(publicador_id=publicador_id, participo=True)],
        )


def test_quien_informo_los_seis_meses_no_genera_alerta(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15)))

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []


def test_quien_falto_un_mes_es_irregular(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15))[:-1])

    resultado = alertas.calcular(sesion, date(2026, 3, 15))

    assert len(resultado) == 1
    assert resultado[0].estado == "irregular"
    assert resultado[0].meses_sin_informar == [(2026, 2)]


def test_quien_no_informo_ninguno_de_los_seis_es_inactivo(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")

    resultado = alertas.calcular(sesion, date(2026, 3, 15))

    assert resultado[0].estado == "inactivo"
    assert len(resultado[0].meses_sin_informar) == 6


def test_una_fila_con_participo_false_cuenta_como_no_informado(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    for anio, mes in alertas.ventana(date(2026, 3, 15)):
        registros.guardar_mes(
            sesion,
            anio,
            mes,
            [registros.EntradaMes(publicador_id=ana.id, participo=False)],
        )

    assert alertas.calcular(sesion, date(2026, 3, 15))[0].estado == "inactivo"


def test_informar_solo_el_mes_mas_antiguo_deja_irregular_no_inactivo(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15))[:1])

    assert alertas.calcular(sesion, date(2026, 3, 15))[0].estado == "irregular"


def test_el_mes_en_curso_no_entra_en_la_ventana(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15)))
    # informar marzo no cambia nada: marzo aún no termina
    _informar(sesion, ana.id, [(2026, 3)])

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []


def test_los_registros_fuera_de_la_ventana_no_cuentan(sesion):
    """Informar mucho antes de la ventana no evita la alerta, y la consulta
    acotada no debe dejar fuera ningún mes que sí pertenezca a ella."""
    ana = publicadores.crear(sesion, "Perez Ana")
    _informar(sesion, ana.id, [(2020, 5), (2021, 8)])  # muy anteriores
    _informar(sesion, ana.id, alertas.ventana(date(2026, 3, 15))[:2])

    resultado = alertas.calcular(sesion, date(2026, 3, 15))

    assert resultado[0].estado == "irregular"
    assert len(resultado[0].meses_sin_informar) == 4


def test_las_bajas_no_generan_alertas(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    publicadores.dar_de_baja(sesion, ana.id, date(2026, 1, 10), "mudado")

    assert alertas.calcular(sesion, date(2026, 3, 15)) == []
