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


def test_los_formularios_de_filtro_quedan_marcados_para_limpiar_la_url(cliente):
    """`filtros.js` deshabilita los campos vacíos durante el envío para que
    «Todos» no deje un `grupo_id=` colgando en la URL. Solo actúa sobre los
    formularios marcados, así que la marca es parte del contrato."""
    for ruta, params in (
        ("/grilla", {"anio": 2026, "mes": 1}),
        ("/publicadores", {}),
        ("/informe", {"anio": 2026, "mes": 1}),
    ):
        texto = cliente.get(ruta, params=params).text
        assert "data-filtro" in texto, ruta
        assert '/static/filtros.js' in texto, ruta
