import pytest

from app.web.errores import DatosInvalidos, anio_valido, mes_valido


@pytest.mark.parametrize("mes", [1, 6, 12])
def test_mes_valido_acepta_el_rango_1_a_12(mes):
    assert mes_valido(mes) == mes


@pytest.mark.parametrize("mes", [0, 13, -1])
def test_mes_valido_rechaza_fuera_de_rango_en_espanol(mes):
    with pytest.raises(DatosInvalidos) as info:
        mes_valido(mes)
    assert "no es válido" in info.value.mensaje


@pytest.mark.parametrize("anio", [1950, 2026, 2100])
def test_anio_valido_acepta_el_rango(anio):
    assert anio_valido(anio) == anio


@pytest.mark.parametrize("anio", [1949, 2101, 999999])
def test_anio_valido_rechaza_fuera_de_rango_en_espanol(anio):
    with pytest.raises(DatosInvalidos) as info:
        anio_valido(anio)
    assert "fuera de rango" in info.value.mensaje
