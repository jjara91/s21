from pypdf import PdfReader

from app.pdf import campos


def test_hay_exactamente_75_campos():
    assert len(campos.TODOS_LOS_CAMPOS) == 75


def test_texto_y_casillas_no_se_solapan():
    assert campos.CAMPOS_TEXTO & campos.CAMPOS_CASILLA == frozenset()
    assert campos.CAMPOS_TEXTO | campos.CAMPOS_CASILLA == campos.TODOS_LOS_CAMPOS


def test_900_5_es_texto_no_casilla():
    # la fecha de bautismo va entre dos bloques de casillas; es fácil contarla mal
    assert "900_5_Text_SanSerif" in campos.CAMPOS_TEXTO


def test_septiembre_es_la_fila_20_y_agosto_la_31():
    assert campos.MES_A_FILA[9] == 20
    assert campos.MES_A_FILA[8] == 31
    assert campos.MESES_ORDENADOS == [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]


def test_campo_fila_arma_el_nombre():
    assert campos.campo_fila("notas", 7) == "905_30_Text_SanSerif"


def test_el_sintetico_expone_los_mismos_campos(plantilla_sintetica):
    presentes = set(PdfReader(plantilla_sintetica).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)


def test_el_formulario_real_expone_los_mismos_campos(plantilla_real):
    presentes = set(PdfReader(plantilla_real).get_fields() or {})
    assert presentes == set(campos.TODOS_LOS_CAMPOS)


def test_convension_de_nombres_valida_clasificacion():
    # todo campo de casilla del S-21 termina en _CheckBox, ningún campo de texto lo hace
    # un typo en FILAS_DE_CASILLA mandaría un campo al conjunto equivocado sin romper
    # el conteo ni el test de no-solapamiento
    assert all(nombre.endswith("_CheckBox") for nombre in campos.CAMPOS_CASILLA)
    assert not any(nombre.endswith("_CheckBox") for nombre in campos.CAMPOS_TEXTO)
