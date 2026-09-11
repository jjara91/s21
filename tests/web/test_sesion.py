def test_sin_sesion_la_raiz_redirige_al_login(cliente_anonimo):
    respuesta = cliente_anonimo.get("/", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/entrar"


def test_el_login_muestra_el_formulario(cliente_anonimo):
    respuesta = cliente_anonimo.get("/entrar")

    assert respuesta.status_code == 200
    assert "Iniciar sesión" in respuesta.text


def test_credenciales_correctas_entran(cliente_anonimo):
    respuesta = cliente_anonimo.post(
        "/entrar",
        data={"usuario": "prueba", "clave": "secreta"},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"


def test_credenciales_incorrectas_no_entran(cliente_anonimo):
    respuesta = cliente_anonimo.post(
        "/entrar", data={"usuario": "prueba", "clave": "equivocada"}
    )

    assert respuesta.status_code == 401
    assert "Usuario o clave incorrectos" in respuesta.text


def test_con_sesion_la_raiz_responde(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "Año de servicio" in respuesta.text


def test_sin_plantilla_el_inicio_avisa_y_enlaza_a_subirla(cliente):
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert 'href="/plantilla"' in respuesta.text


def test_con_plantilla_el_inicio_no_avisa(cliente, tmp_path):
    from tests.fixtures.sintetico import crear_s21_sintetico

    ruta = crear_s21_sintetico(tmp_path / "para_subir.pdf")
    cliente.post(
        "/plantilla",
        files={"archivo": ("s21.pdf", ruta.read_bytes(), "application/pdf")},
        follow_redirects=True,
    )

    respuesta = cliente.get("/")

    assert 'href="/plantilla"' not in respuesta.text


def test_salir_cierra_la_sesion(cliente):
    cliente.post("/salir", follow_redirects=False)

    assert cliente.get("/", follow_redirects=False).status_code == 303


def test_la_salud_no_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/salud").status_code == 200
