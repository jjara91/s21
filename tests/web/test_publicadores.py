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
