from datetime import date

import pytest

from app import dominio


@pytest.mark.parametrize(
    "anio,mes,esperado",
    [(2025, 9, 2026), (2025, 12, 2026), (2026, 1, 2026), (2026, 8, 2026), (2026, 9, 2027)],
)
def test_anio_servicio_arranca_en_septiembre(anio, mes, esperado):
    assert dominio.anio_servicio_de(anio, mes) == esperado


def test_rango_del_anio_de_servicio():
    assert dominio.rango_anio_servicio(2026) == (date(2025, 9, 1), date(2026, 8, 31))


def test_meses_del_anio_van_de_septiembre_a_agosto():
    meses = dominio.meses_del_anio(2026)
    assert len(meses) == 12
    assert meses[0] == (2025, 9)
    assert meses[3] == (2025, 12)
    assert meses[4] == (2026, 1)
    assert meses[-1] == (2026, 8)


def test_tarjeta_vacia_tiene_doce_meses_en_orden():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    assert [fila.mes for fila in tarjeta.meses] == [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    assert all(fila.horas is None for fila in tarjeta.meses)


def test_total_horas_ignora_los_meses_sin_horas():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    tarjeta.meses[0].horas = 15
    tarjeta.meses[2].horas = 30
    assert tarjeta.total_horas() == 45


def test_total_horas_es_none_si_ningun_mes_tiene_horas():
    tarjeta = dominio.DatosTarjeta.vacia(nombre="Perez Ana", anio_servicio=2026)
    assert tarjeta.total_horas() is None
