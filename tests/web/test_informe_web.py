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


def test_respaldo_descarga_la_base(cliente):
    respuesta = cliente.get("/respaldo")

    assert respuesta.status_code == 200
    assert respuesta.content[:15] == b"SQLite format 3"
    assert "s21.db" in respuesta.headers["content-disposition"]


def test_el_informe_pide_sesion(cliente_anonimo):
    assert cliente_anonimo.get("/informe", follow_redirects=False).status_code == 303


def test_el_informe_con_mes_fuera_de_rango_no_revienta(cliente):
    respuesta = cliente.get("/informe", params={"anio": 2026, "mes": 13})

    assert respuesta.status_code == 400
