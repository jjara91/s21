import sqlite3


def test_el_informe_del_mes_carga(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/grilla",
        data={"anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
              "cursos_1": "3"},
        follow_redirects=True,
    )

    respuesta = cliente.get("/informe", params={"anio": 2026, "mes": 1})

    assert respuesta.status_code == 200
    assert "Publicadores" in respuesta.text
    assert "Enero de 2026" in respuesta.text


def test_el_informe_anual_trae_los_doce_meses(cliente):
    respuesta = cliente.get("/informe/anual", params={"anio_servicio": 2026})

    assert "Septiembre" in respuesta.text
    assert "Agosto" in respuesta.text


def test_alertas_lista_a_los_inactivos(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/alertas")

    assert "Perez Ana" in respuesta.text
    assert "inactivo" in respuesta.text


def test_respaldo_descarga_la_base(cliente, tmp_path):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/respaldo")

    assert respuesta.status_code == 200
    assert "s21.db" in respuesta.headers["content-disposition"]

    # El respaldo debe abrir como una base SQLite válida y contener los
    # datos: mirar solo la cabecera no detectaría un archivo con páginas a
    # medio escribir, que también empieza con "SQLite format 3".
    copia = tmp_path / "respaldo.db"
    copia.write_bytes(respuesta.content)
    conexion = sqlite3.connect(copia)
    try:
        nombres = [
            fila[0]
            for fila in conexion.execute("SELECT nombre_completo FROM publicador")
        ]
    finally:
        conexion.close()
    assert "Perez Ana" in nombres


def test_respaldo_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/respaldo", follow_redirects=False).status_code == 303


def test_el_informe_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/informe", follow_redirects=False).status_code == 303


def test_el_informe_con_mes_fuera_de_rango_no_revienta(cliente):
    respuesta = cliente.get("/informe", params={"anio": 2026, "mes": 13})

    assert respuesta.status_code == 400


def test_el_informe_muestra_sin_cargar_por_separado_de_no_informaron(cliente):
    """Un mes que nadie ha cargado (los meses futuros del año en curso, en
    /informe/anual) no debe mostrarse como si toda la congregación hubiera
    dejado de predicar."""
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get("/informe", params={"anio": 2026, "mes": 1})

    assert respuesta.status_code == 200
    assert "Sin cargar" in respuesta.text


def test_el_informe_anual_muestra_la_columna_sin_cargar(cliente):
    respuesta = cliente.get("/informe/anual", params={"anio_servicio": 2026})

    assert "Sin cargar" in respuesta.text


def test_los_filtros_vacios_del_informe_no_rompen(cliente):
    """Borrar el año del formulario manda anio= y mes= vacíos; deben caer en
    el mes en curso, no en un error de validación."""
    respuesta = cliente.get("/informe?anio=&mes=")

    assert respuesta.status_code == 200


def test_el_ano_de_servicio_vacio_no_rompe(cliente):
    respuesta = cliente.get("/informe/anual?anio_servicio=")

    assert respuesta.status_code == 200
