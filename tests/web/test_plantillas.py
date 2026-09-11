from app.web.plantillas import plantillas


def test_mes_nombre_traduce_los_doce_meses():
    filtro = plantillas.env.filters["mes_nombre"]
    assert filtro(1) == "Enero"
    assert filtro(12) == "Diciembre"


def test_mes_nombre_degrada_en_vez_de_reventar_con_un_mes_invalido():
    """Defensa en profundidad: las rutas ya validan el mes, pero si algo se
    cuela fuera de 1-12 esto no debe lanzar KeyError."""
    filtro = plantillas.env.filters["mes_nombre"]
    assert filtro(13) == "13"
    assert filtro(0) == "0"
