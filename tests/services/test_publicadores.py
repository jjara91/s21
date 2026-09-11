from datetime import date

import pytest

from app.models import Grupo
from app.services import publicadores


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Rojas Vega Mauricio", "rojas vega mauricio"),
        ("ROJAS  VEGA   MAURICIO", "rojas vega mauricio"),
        ("Pérez Gómez Ana María", "perez gomez ana maria"),
        ("  Núñez Muñoz José  ", "nunez munoz jose"),
    ],
)
def test_normalizar_quita_tildes_mayusculas_y_espacios(entrada, esperado):
    assert publicadores.normalizar(entrada) == esperado


def test_crear_guarda_el_nombre_normalizado(sesion):
    creado = publicadores.crear(sesion, "Pérez Gómez Ana María", sexo="M")

    assert creado.id is not None
    assert creado.nombre_completo == "Pérez Gómez Ana María"
    assert creado.nombre_normalizado == "perez gomez ana maria"


def test_buscar_por_nombre_ignora_tildes_y_mayusculas(sesion):
    creado = publicadores.crear(sesion, "Pérez Gómez Ana María")

    assert publicadores.buscar_por_nombre(sesion, "PEREZ GOMEZ ANA MARIA").id == creado.id


def test_buscar_por_nombre_devuelve_none_si_no_hay(sesion):
    assert publicadores.buscar_por_nombre(sesion, "Nadie Aqui") is None


def test_actualizar_recalcula_el_nombre_normalizado(sesion):
    creado = publicadores.crear(sesion, "Perez Ana")

    actualizado = publicadores.actualizar(
        sesion, creado.id, nombre_completo="Pérez Soto Ana"
    )

    assert actualizado.nombre_normalizado == "perez soto ana"


def test_actualizar_ignora_un_nombre_normalizado_suelto(sesion):
    """`nombre_normalizado` se deriva siempre de `nombre_completo`: aceptar
    uno suelto lo dejaría desincronizado y rompería el emparejamiento por
    nombre al importar."""
    creado = publicadores.crear(sesion, "Perez Ana")

    actualizado = publicadores.actualizar(
        sesion, creado.id, nombre_normalizado="cualquier cosa", sexo="M"
    )

    assert actualizado.nombre_normalizado == "perez ana"
    assert actualizado.sexo == "M"


def test_listar_excluye_las_bajas_por_defecto(sesion):
    activo = publicadores.crear(sesion, "Activo Uno")
    baja = publicadores.crear(sesion, "Baja Dos")
    publicadores.dar_de_baja(sesion, baja.id, date(2026, 1, 15), "mudado")

    assert [p.id for p in publicadores.listar(sesion)] == [activo.id]
    assert len(publicadores.listar(sesion, incluir_bajas=True)) == 2


def test_listar_activos_en_incluye_a_quien_se_dio_de_baja_despues_de_esa_fecha(sesion):
    """Alguien dado de baja en marzo debe seguir contando en un informe o
    exportación de un período anterior a marzo: si no, dar de baja a alguien
    reescribe en silencio lo que ya se había presentado."""
    baja_en_marzo = publicadores.crear(sesion, "Baja Uno")
    publicadores.dar_de_baja(sesion, baja_en_marzo.id, date(2026, 3, 10), "mudado")

    activos_en_enero = publicadores.listar(sesion, activos_en=date(2026, 1, 31))

    assert [p.id for p in activos_en_enero] == [baja_en_marzo.id]


def test_listar_activos_en_excluye_a_quien_ya_se_habia_dado_de_baja_antes(sesion):
    baja_en_enero = publicadores.crear(sesion, "Baja Uno")
    publicadores.dar_de_baja(sesion, baja_en_enero.id, date(2026, 1, 5), "mudado")

    activos_en_marzo = publicadores.listar(sesion, activos_en=date(2026, 3, 31))

    assert activos_en_marzo == []


def test_listar_activos_en_no_afecta_a_quien_nunca_se_dio_de_baja(sesion):
    siempre_activo = publicadores.crear(sesion, "Activo Uno")

    assert [p.id for p in publicadores.listar(sesion, activos_en=date(2026, 1, 31))] == [
        siempre_activo.id
    ]


def test_listar_filtra_por_grupo(sesion):
    grupo = Grupo(nombre="Centro")
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    dentro = publicadores.crear(sesion, "Dentro Uno", grupo_id=grupo.id)
    publicadores.crear(sesion, "Fuera Dos")

    assert [p.id for p in publicadores.listar(sesion, grupo_id=grupo.id)] == [dentro.id]


def test_listar_busca_por_texto_sin_tildes(sesion):
    encontrado = publicadores.crear(sesion, "Núñez Muñoz José")
    publicadores.crear(sesion, "Otro Distinto")

    assert [p.id for p in publicadores.listar(sesion, texto="nunez")] == [encontrado.id]


def test_listar_ordena_alfabeticamente(sesion):
    publicadores.crear(sesion, "Zapata Luis")
    publicadores.crear(sesion, "Alvarez Ana")

    assert [p.nombre_completo for p in publicadores.listar(sesion)] == [
        "Alvarez Ana",
        "Zapata Luis",
    ]


def test_obtener_lanza_si_no_existe(sesion):
    with pytest.raises(publicadores.PublicadorNoEncontrado):
        publicadores.obtener(sesion, 999)


def test_con_privilegio_filtra_por_nombramiento_vigente_hoy(sesion):
    from datetime import date

    from app.services import nombramientos

    precursora = publicadores.crear(sesion, "Precursora Una")
    publicadores.crear(sesion, "Comun Dos")
    nombramientos.crear(sesion, precursora.id, "precursor_regular", date(2025, 9, 1))

    lista = publicadores.listar(sesion)
    filtrada = publicadores.con_privilegio(
        sesion, lista, "precursor_regular", date(2026, 1, 15)
    )

    assert [p.id for p in filtrada] == [precursora.id]


def test_con_privilegio_sin_valor_devuelve_la_lista_entera(sesion):
    from datetime import date

    publicadores.crear(sesion, "Comun Dos")
    lista = publicadores.listar(sesion)

    assert publicadores.con_privilegio(sesion, lista, None, date(2026, 1, 15)) == lista
