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
