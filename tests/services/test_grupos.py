import pytest

from app.services import grupos, publicadores


def test_crear_y_listar(sesion):
    grupos.crear(sesion, "Sur")
    grupos.crear(sesion, "Centro")

    assert [g.nombre for g in grupos.listar(sesion)] == ["Centro", "Sur"]


def test_asignar_superintendente(sesion):
    ana = publicadores.crear(sesion, "Perez Ana")
    grupo = grupos.crear(sesion, "Centro")

    actualizado = grupos.actualizar(sesion, grupo.id, superintendente_id=ana.id)

    assert actualizado.superintendente_id == ana.id


def test_eliminar_un_grupo_deja_a_sus_publicadores_sin_grupo(sesion):
    grupo = grupos.crear(sesion, "Centro")
    ana = publicadores.crear(sesion, "Perez Ana", grupo_id=grupo.id)

    grupos.eliminar(sesion, grupo.id)

    assert publicadores.obtener(sesion, ana.id).grupo_id is None


def test_obtener_lanza_si_no_existe(sesion):
    with pytest.raises(grupos.GrupoNoEncontrado):
        grupos.obtener(sesion, 999)
