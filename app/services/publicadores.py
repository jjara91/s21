"""Alta, búsqueda y baja de publicadores."""

import unicodedata
from datetime import date

from sqlalchemy import or_
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
    # `nombre_normalizado` se deriva siempre de `nombre_completo`: aceptar uno
    # suelto lo dejaría desincronizado con el nombre real y rompería el
    # emparejamiento por nombre al importar.
    campos.pop("nombre_normalizado", None)
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
    activos_en: date | None = None,
) -> list[Publicador]:
    """`activos_en` responde "¿seguía activo en esta fecha?": incluye a quien
    nunca se dio de baja y a quien se dio de baja en o después de esa fecha.
    Sin esto, dar de baja a alguien a mitad de un período reescribe en
    silencio los informes y exportaciones de ese período que ya se habían
    presentado. Se ignora si `incluir_bajas` es True, que ya trae a todos.
    """
    consulta = select(Publicador)
    if not incluir_bajas:
        if activos_en is not None:
            consulta = consulta.where(
                or_(Publicador.fecha_baja.is_(None), Publicador.fecha_baja >= activos_en)
            )
        else:
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


def con_privilegio(
    sesion: Session,
    lista: list[Publicador],
    privilegio: str | None,
    hoy: date,
) -> list[Publicador]:
    """Filtra la lista dejando a quienes tienen ese nombramiento vigente hoy."""
    if not privilegio:
        return lista
    from app.services import nombramientos

    return [
        publicador
        for publicador in lista
        if privilegio
        in nombramientos.tipos_en_mes(sesion, publicador.id, hoy.year, hoy.month)
    ]
