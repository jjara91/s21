def test_la_lista_esta_vacia_al_principio(cliente):
    respuesta = cliente.get("/publicadores")

    assert respuesta.status_code == 200
    assert "No hay publicadores" in respuesta.text


def test_crear_un_publicador_desde_el_formulario(cliente):
    cliente.post(
        "/publicadores",
        data={
            "nombre_completo": "Pérez Gómez Ana María",
            "sexo": "M",
            "esperanza": "otras_ovejas",
            "fecha_bautismo": "2010-04-03",
        },
        follow_redirects=True,
    )

    assert "Pérez Gómez Ana María" in cliente.get("/publicadores").text


def test_el_buscador_filtra(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Núñez José"})
    cliente.post("/publicadores", data={"nombre_completo": "Otro Distinto"})

    respuesta = cliente.get("/publicadores", params={"texto": "nunez"})

    assert "Núñez José" in respuesta.text
    assert "Otro Distinto" not in respuesta.text


def test_el_detalle_muestra_los_nombramientos(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2025-09-01"},
    )

    respuesta = cliente.get("/publicadores/1")

    assert "precursor regular" in respuesta.text
    assert "2025-09-01" in respuesta.text


def test_cerrar_un_nombramiento(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "anciano", "desde": "2020-01-01"},
    )

    cliente.post("/publicadores/1/nombramientos/1/cerrar", data={"hasta": "2026-04-30"})

    assert "2026-04-30" in cliente.get("/publicadores/1").text


def test_dar_de_baja_saca_al_publicador_de_la_lista(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    cliente.post("/publicadores/1/baja", data={"fecha_baja": "2026-05-01", "motivo_baja": "mudado"})

    assert "Perez Ana" not in cliente.get("/publicadores").text
    assert "Perez Ana" in cliente.get("/publicadores", params={"incluir_bajas": "1"}).text


def test_los_grupos_se_crean_y_se_asignan(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana", "grupo_id": "1"})

    assert "Centro" in cliente.get("/publicadores").text


def test_filtrar_la_lista_por_privilegio(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Precursora Una"})
    cliente.post("/publicadores", data={"nombre_completo": "Comun Dos"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "2020-01-01"},
    )

    respuesta = cliente.get("/publicadores", params={"privilegio": "precursor_regular"})

    assert "Precursora Una" in respuesta.text
    assert "Comun Dos" not in respuesta.text


def test_publicadores_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/publicadores", follow_redirects=False).status_code == 303


def test_editar_un_publicador(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.post(
        "/publicadores/1",
        data={"nombre_completo": "Perez Ana Maria", "sexo": "M"},
        follow_redirects=True,
    )

    assert "Perez Ana Maria" in respuesta.text


def test_la_pagina_de_grupos_lista_los_grupos(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})

    respuesta = cliente.get("/grupos")

    assert respuesta.status_code == 200
    assert "Centro" in respuesta.text


def test_editar_un_grupo_y_asignar_superintendente(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post("/grupos", data={"nombre": "Centro"})

    respuesta = cliente.post(
        "/grupos/1",
        data={"nombre": "Sur", "superintendente_id": "1"},
        follow_redirects=True,
    )

    assert "Sur" in respuesta.text


def test_eliminar_un_grupo(cliente):
    cliente.post("/grupos", data={"nombre": "Centro"})

    respuesta = cliente.post("/grupos/1/eliminar", follow_redirects=True)

    assert "Centro" not in respuesta.text


def test_crear_nombramiento_con_fecha_imposible_devuelve_400(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "precursor_regular", "desde": "31-02-2020"},
    )

    assert respuesta.status_code == 400
    assert "no es una fecha válida" in respuesta.text


def test_cerrar_nombramiento_con_fecha_anterior_devuelve_400(cliente):
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})
    cliente.post(
        "/publicadores/1/nombramientos",
        data={"tipo": "anciano", "desde": "2020-01-01"},
    )

    respuesta = cliente.post(
        "/publicadores/1/nombramientos/1/cerrar", data={"hasta": "2019-01-01"}
    )

    assert respuesta.status_code == 400


def test_publicador_inexistente_devuelve_404(cliente):
    respuesta = cliente.get("/publicadores/999")

    assert respuesta.status_code == 404
    assert "500" not in respuesta.text


def test_el_filtro_de_grupo_en_todos_no_rompe(cliente):
    """Mismo caso que en la grilla: «Todos» viaja como grupo_id vacío."""
    cliente.post("/publicadores", data={"nombre_completo": "Perez Ana"})

    respuesta = cliente.get(
        "/publicadores", params={"texto": "", "grupo_id": "", "privilegio": ""}
    )

    assert respuesta.status_code == 200
    assert "Perez Ana" in respuesta.text
