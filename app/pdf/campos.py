"""Único lugar del proyecto que conoce los nombres de campo del formulario S-21.

Formulario de referencia: S-21-S 11/23. Si aparece una versión nueva, se ajusta
este archivo y nada más.
"""

CABECERA_TEXTO = {
    "nombre": "900_1_Text_SanSerif",
    "fecha_nacimiento": "900_2_Text_SanSerif",
    "fecha_bautismo": "900_5_Text_SanSerif",
    "anio_servicio": "900_13_Text_C_SanSerif",
}

CABECERA_SEXO = {"H": "900_3_CheckBox", "M": "900_4_CheckBox"}

CABECERA_ESPERANZA = {
    "otras_ovejas": "900_6_CheckBox",
    "ungido": "900_7_CheckBox",
}

CABECERA_NOMBRAMIENTOS = {
    "anciano": "900_8_CheckBox",
    "siervo_ministerial": "900_9_CheckBox",
    "precursor_regular": "900_10_CheckBox",
    "precursor_especial": "900_11_CheckBox",
    "misionero_campo": "900_12_CheckBox",
}

FILA = {
    "participo": "901_{i}_CheckBox",
    "cursos_biblicos": "902_{i}_Text_C_SanSerif",
    "precursor_auxiliar": "903_{i}_CheckBox",
    "horas": "904_{i}_S21_Value",
    "notas": "905_{i}_Text_SanSerif",
}

TOTAL = {"horas": "904_32_S21_Value", "notas": "905_32_Text_SanSerif"}

# El año de servicio empieza en septiembre: la fila 20 es septiembre y la 31, agosto.
MESES_ORDENADOS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
MES_A_FILA = {mes: 20 + i for i, mes in enumerate(MESES_ORDENADOS)}

FILAS_DE_CASILLA = ("participo", "precursor_auxiliar")

MARCADA = "/Yes"
DESMARCADA = "/Off"


def campo_fila(clave: str, mes: int) -> str:
    """Nombre del campo `clave` para el mes calendario `mes` (1-12)."""
    return FILA[clave].format(i=MES_A_FILA[mes])


def _construir_conjuntos() -> tuple[frozenset[str], frozenset[str]]:
    texto = set(CABECERA_TEXTO.values()) | set(TOTAL.values())
    casilla = (
        set(CABECERA_SEXO.values())
        | set(CABECERA_ESPERANZA.values())
        | set(CABECERA_NOMBRAMIENTOS.values())
    )
    for mes in MESES_ORDENADOS:
        for clave in FILA:
            destino = casilla if clave in FILAS_DE_CASILLA else texto
            destino.add(campo_fila(clave, mes))
    return frozenset(texto), frozenset(casilla)


CAMPOS_TEXTO, CAMPOS_CASILLA = _construir_conjuntos()
TODOS_LOS_CAMPOS = CAMPOS_TEXTO | CAMPOS_CASILLA
