"""CRUD de grupos de predicación."""

from sqlmodel import Session, select

from app.models import Grupo, Publicador


class GrupoNoEncontrado(Exception):
    pass


def crear(sesion: Session, nombre: str, superintendente_id: int | None = None) -> Grupo:
    grupo = Grupo(nombre=nombre.strip(), superintendente_id=superintendente_id)
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    return grupo


def obtener(sesion: Session, grupo_id: int) -> Grupo:
    grupo = sesion.get(Grupo, grupo_id)
    if grupo is None:
        raise GrupoNoEncontrado(f"no existe el grupo {grupo_id}")
    return grupo


def listar(sesion: Session) -> list[Grupo]:
    return list(sesion.exec(select(Grupo).order_by(Grupo.nombre)).all())


def actualizar(sesion: Session, grupo_id: int, **campos) -> Grupo:
    grupo = obtener(sesion, grupo_id)
    for nombre, valor in campos.items():
        setattr(grupo, nombre, valor)
    sesion.add(grupo)
    sesion.commit()
    sesion.refresh(grupo)
    return grupo


def eliminar(sesion: Session, grupo_id: int) -> None:
    grupo = obtener(sesion, grupo_id)
    integrantes = sesion.exec(
        select(Publicador).where(Publicador.grupo_id == grupo_id)
    ).all()
    for publicador in integrantes:
        publicador.grupo_id = None
        sesion.add(publicador)
    sesion.delete(grupo)
    sesion.commit()
