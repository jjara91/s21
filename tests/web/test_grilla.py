def _crear_publicador(cliente, nombre: str) -> None:
    cliente.post("/publicadores", data={"nombre_completo": nombre})


def test_la_grilla_lista_a_los_publicadores_activos(cliente):
    _crear_publicador(cliente, "Perez Ana")
    _crear_publicador(cliente, "Soto Luis")

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert respuesta.status_code == 200
    assert "Perez Ana" in respuesta.text
    assert "Soto Luis" in respuesta.text
    assert "Enero de 2026" in respuesta.text


def test_guardar_el_mes_completo(cliente):
    _crear_publicador(cliente, "Perez Ana")
    _crear_publicador(cliente, "Soto Luis")

    cliente.post(
        "/grilla",
        data={
            "anio": "2026",
            "mes": "1",
            "publicadores": ["1", "2"],
            "participo_1": "1",
            "cursos_1": "3",
            "notas_1": "visita del superintendente",
            # Soto Luis no informó: no manda participo_2
        },
        follow_redirects=True,
    )

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})
    assert 'name="cursos_1" value="3"' in respuesta.text
    assert "visita del superintendente" in respuesta.text


def _etiqueta_horas(texto: str, publicador_id: int) -> str:
    """El resto de la etiqueta <input> de horas, desde su atributo name."""
    return texto.split(f'name="horas_{publicador_id}"')[1].split(">")[0]


def test_las_horas_vienen_deshabilitadas_para_un_publicador_comun(cliente):
    _crear_publicador(cliente, "Perez Ana")

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert "disabled" in _etiqueta_horas(respuesta.text, 1)


def test_las_horas_se_habilitan_para_un_precursor_regular(cliente):
    _crear_publicador(cliente, "Perez Ana")
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert "disabled" not in _etiqueta_horas(respuesta.text, 1)


def test_guardar_dos_veces_no_duplica(cliente):
    _crear_publicador(cliente, "Perez Ana")
    datos = {"anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
             "cursos_1": "2"}

    cliente.post("/grilla", data=datos, follow_redirects=True)
    cliente.post("/grilla", data=datos, follow_redirects=True)

    texto = cliente.get("/grilla", params={"anio": 2026, "mes": 1}).text
    assert texto.count('name="cursos_1"') == 1


def test_filtrar_por_grupo(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})
    cliente.post("/publicadores", data={"nombre_completo": "Dentro Uno", "grupo_id": "1"})
    cliente.post("/publicadores", data={"nombre_completo": "Fuera Dos"})

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1, "grupo_id": 1})

    assert "Dentro Uno" in respuesta.text
    assert "Fuera Dos" not in respuesta.text


def test_la_grilla_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/grilla", follow_redirects=False).status_code == 303


def test_horas_invalidas_no_guardan_nada_y_avisan(cliente):
    _crear_publicador(cliente, "Perez Ana")
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )
    # estado previo válido, ya guardado
    cliente.post(
        "/grilla",
        data={
            "anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
            "cursos_1": "2", "horas_1": "10", "notas_1": "nota previa",
        },
        follow_redirects=True,
    )

    respuesta = cliente.post(
        "/grilla",
        data={
            "anio": "2026", "mes": "1", "publicadores": ["1"], "participo_1": "1",
            "cursos_1": "2", "horas_1": "abc", "notas_1": "nota previa",
        },
    )

    assert respuesta.status_code == 400
    assert "Perez Ana" in respuesta.text

    texto = cliente.get("/grilla", params={"anio": 2026, "mes": 1}).text
    assert 'name="horas_1" value="10"' in texto
    assert 'name="cursos_1" value="2"' in texto
    assert "nota previa" in texto


def test_error_conserva_lo_tecleado_en_la_respuesta(cliente):
    _crear_publicador(cliente, "Perez Ana")
    _crear_publicador(cliente, "Soto Luis")
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )

    respuesta = cliente.post(
        "/grilla",
        data={
            "anio": "2026", "mes": "1", "publicadores": ["1", "2"],
            "participo_1": "1", "cursos_1": "2", "horas_1": "abc",
            "notas_1": "nota nueva",
            "participo_2": "1", "cursos_2": "5",
        },
    )

    assert respuesta.status_code == 400
    assert 'name="horas_1" value="abc"' in respuesta.text
    assert 'name="cursos_1" value="2"' in respuesta.text
    assert "nota nueva" in respuesta.text
    assert 'name="cursos_2" value="5"' in respuesta.text


def test_publicador_no_numerico_da_error_en_espanol(cliente):
    respuesta = cliente.post(
        "/grilla",
        data={"anio": "2026", "mes": "1", "publicadores": ["no-existe"]},
    )

    assert respuesta.status_code == 400
    assert "identificador de publicador inválido" in respuesta.text
    assert "invalid literal" not in respuesta.text


def test_las_horas_se_habilitan_al_marcar_auxiliar_aunque_haya_error_en_esa_misma_fila(cliente):
    _crear_publicador(cliente, "Comun Uno")

    respuesta = cliente.post(
        "/grilla",
        data={
            "anio": "2026", "mes": "1", "publicadores": ["1"],
            "auxiliar_1": "1", "horas_1": "abc",
        },
    )

    assert respuesta.status_code == 400
    assert "disabled" not in _etiqueta_horas(respuesta.text, 1)


def test_grilla_con_mes_fuera_de_rango_da_400_en_espanol(cliente):
    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 13})

    assert respuesta.status_code == 400
    assert "no es válido" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_grilla_con_mes_cero_da_400_en_espanol(cliente):
    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 0})

    assert respuesta.status_code == 400
    assert "no es válido" in respuesta.text


def test_grilla_con_anio_fuera_de_rango_da_400_en_espanol(cliente):
    respuesta = cliente.get("/grilla", params={"anio": 999999, "mes": 1})

    assert respuesta.status_code == 400
    assert "fuera de rango" in respuesta.text
    assert "out of range" not in respuesta.text


def test_guardar_grilla_con_mes_fuera_de_rango_da_400_en_espanol(cliente):
    respuesta = cliente.post(
        "/grilla", data={"anio": "2026", "mes": "13", "publicadores": []}
    )

    assert respuesta.status_code == 400
    assert "no es válido" in respuesta.text


def test_guardar_grilla_con_anio_fuera_de_rango_da_400_en_espanol(cliente):
    respuesta = cliente.post(
        "/grilla", data={"anio": "999999", "mes": "1", "publicadores": []}
    )

    assert respuesta.status_code == 400
    assert "fuera de rango" in respuesta.text


def test_marcar_auxiliar_y_horas_en_el_mismo_envio_guarda_las_horas(cliente):
    """Contrato en el que se apoya el script de la grilla: habilitar el campo
    de horas en el navegador al marcar auxiliar no necesita un guardado previo,
    porque el servidor acepta ambos datos en el mismo envío."""
    _crear_publicador(cliente, "Perez Ana")

    cliente.post("/grilla", data={
        "anio": "2026", "mes": "1", "publicadores": ["1"],
        "participo_1": "1", "auxiliar_1": "1", "horas_1": "30",
    }, follow_redirects=True)

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1})

    assert 'name="horas_1" value="30"' in respuesta.text
    assert "disabled" not in _etiqueta_horas(respuesta.text, 1)


def test_el_filtro_de_grupo_en_todos_no_rompe(cliente):
    """«Todos» es un <option value=""> y el navegador envía grupo_id vacío.
    Sin coerción, Pydantic lo rechaza y la página muere en un 422 en inglés."""
    _crear_publicador(cliente, "Perez Ana")

    respuesta = cliente.get("/grilla", params={"anio": 2026, "mes": 1, "grupo_id": ""})

    assert respuesta.status_code == 200
    assert "Perez Ana" in respuesta.text


def test_los_filtros_de_fecha_vacios_no_rompen(cliente):
    """El año es un <input type="number"> que se puede dejar en blanco: sin
    coerción, «Ver» con el campo vacío muere en un 422 antes del endpoint."""
    _crear_publicador(cliente, "Perez Ana")

    respuesta = cliente.get("/grilla?anio=&mes=&grupo_id=")

    assert respuesta.status_code == 200
    assert "Perez Ana" in respuesta.text
