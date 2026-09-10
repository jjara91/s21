from datetime import date

from app.services import nombramientos, publicadores, registros


def _ana(sesion):
    return publicadores.crear(
        sesion,
        "Pérez Gómez Ana María",
        sexo="M",
        esperanza="otras_ovejas",
        fecha_bautismo=date(2010, 4, 3),
    )


def test_guardar_mes_crea_las_filas(sesion):
    ana = _ana(sesion)

    guardadas = registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)],
    )

    assert guardadas == 1
    assert registros.registros_del_anio(sesion, ana.id, 2026)[9].horas == 52


def test_guardar_mes_actualiza_en_vez_de_duplicar(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, horas=52)]
    )

    registros.guardar_mes(
        sesion, 2025, 9, [registros.EntradaMes(publicador_id=ana.id, horas=60)]
    )

    del_anio = registros.registros_del_anio(sesion, ana.id, 2026)
    assert len(del_anio) == 1
    assert del_anio[9].horas == 60


def test_filas_del_mes_incluye_a_quien_no_tiene_registro(sesion):
    ana = _ana(sesion)

    filas = registros.filas_del_mes(sesion, 2025, 9)

    assert len(filas) == 1
    publicador, registro, horas_habilitadas = filas[0]
    assert publicador.id == ana.id
    assert registro is None
    assert horas_habilitadas is False


def test_las_horas_se_habilitan_para_un_precursor_regular(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 9, 1))

    _publicador, _registro, horas_habilitadas = registros.filas_del_mes(sesion, 2025, 9)[0]

    assert horas_habilitadas is True


def test_las_horas_se_habilitan_si_ese_mes_fue_precursor_auxiliar(sesion):
    ana = _ana(sesion)
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, precursor_auxiliar=True)],
    )

    _publicador, _registro, horas_habilitadas = registros.filas_del_mes(sesion, 2025, 9)[0]

    assert horas_habilitadas is True


def test_tarjeta_reune_cabecera_nombramientos_y_meses(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 1))
    registros.guardar_mes(
        sesion,
        2025,
        9,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, cursos_biblicos=2)],
    )
    registros.guardar_mes(
        sesion,
        2025,
        10,
        [registros.EntradaMes(publicador_id=ana.id, participo=True, horas=52)],
    )

    tarjeta = registros.tarjeta(sesion, ana.id, 2026)

    assert tarjeta.nombre == "Pérez Gómez Ana María"
    assert tarjeta.anio_servicio == 2026
    assert tarjeta.sexo == "M"
    assert tarjeta.fecha_bautismo == date(2010, 4, 3)
    assert tarjeta.nombramientos == {"precursor_regular"}
    assert tarjeta.mes(9).cursos_biblicos == 2
    assert tarjeta.mes(10).horas == 52
    assert tarjeta.mes(1).participo is False
    assert tarjeta.total_horas() == 52


def test_aplicar_notas_sugeridas_llena_solo_las_notas_vacias(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 5))
    nombramientos.crear(sesion, ana.id, "siervo_ministerial", date(2026, 3, 1))
    registros.guardar_mes(
        sesion,
        2026,
        3,
        [registros.EntradaMes(publicador_id=ana.id, notas="ya escrito a mano")],
    )

    escritas = registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)

    del_anio = registros.registros_del_anio(sesion, ana.id, 2026)
    assert escritas == 1
    assert del_anio[10].notas == "nombrado precursor regular"
    assert del_anio[3].notas == "ya escrito a mano"


def test_aplicar_notas_sugeridas_es_idempotente(sesion):
    ana = _ana(sesion)
    nombramientos.crear(sesion, ana.id, "precursor_regular", date(2025, 10, 5))

    registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)
    segunda = registros.aplicar_notas_sugeridas(sesion, ana.id, 2026)

    assert segunda == 0
