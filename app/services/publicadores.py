"""Alta, búsqueda y baja de publicadores."""

import unicodedata
from datetime import date

from sqlmodel import Session, select

from app.models import Publicador


class PublicadorNoEncontrado(Exception):
    pass


def normalizar(nombre: str) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados.

    Se usa solo para comparar nombres al importar; nunca se muestra en pantalla.
    """
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", nombre)
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def crear(sesion: Session, nombre_completo: str, **campos) -> Publicador:
    publicador = Publicador(
        nombre_completo=nombre_completo.strip(),
        nombre_normalizado=normalizar(nombre_completo),
        **campos,
    )
    sesion.add(publicador)
    sesion.commit()
    sesion.refresh(publicador)
    return publicador


def obtener(sesion: Session, publicador_id: int) -> Publicador:
    publicador = sesion.get(Publicador, publicador_id)
    if publicador is None:
        raise PublicadorNoEncontrado(f"no existe el publicador {publicador_id}")
    return publicador


def actualizar(sesion: Session, publicador_id: int, **campos) -> Publicador:
    publicador = obtener(sesion, publicador_id)
    for nombre, valor in campos.items():
        setattr(publicador, nombre, valor)
    if "nombre_completo" in campos:
        publicador.nombre_completo = campos["nombre_completo"].strip()
        publicador.nombre_normalizado = normalizar(campos["nombre_completo"])
    sesion.add(publicador)
    sesion.commit()
    sesion.refresh(publicador)
    return publicador


def buscar_por_nombre(sesion: Session, nombre: str) -> Publicador | None:
    consulta = select(Publicador).where(
        Publicador.nombre_normalizado == normalizar(nombre)
    )
    return sesion.exec(consulta).first()


def listar(
    sesion: Session,
    *,
    grupo_id: int | None = None,
    incluir_bajas: bool = False,
    texto: str | None = None,
) -> list[Publicador]:
    consulta = select(Publicador)
    if not incluir_bajas:
        consulta = consulta.where(Publicador.fecha_baja.is_(None))
    if grupo_id is not None:
        consulta = consulta.where(Publicador.grupo_id == grupo_id)
    if texto:
        consulta = consulta.where(
            Publicador.nombre_normalizado.contains(normalizar(texto))
        )
    consulta = consulta.order_by(Publicador.nombre_normalizado)
    return list(sesion.exec(consulta).all())


def dar_de_baja(
    sesion: Session, publicador_id: int, fecha: date, motivo: str
) -> Publicador:
    return actualizar(sesion, publicador_id, fecha_baja=fecha, motivo_baja=motivo)
