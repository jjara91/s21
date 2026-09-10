"""Carga de los informes mensuales y armado de la tarjeta de un año."""

from dataclasses import dataclass

from sqlmodel import Session, select

from app.dominio import DatosTarjeta, FilaMes, TIPOS_CON_HORAS, meses_del_anio
from app.models import Publicador, RegistroMensual
from app.services import nombramientos, publicadores


@dataclass
class EntradaMes:
    publicador_id: int
    participo: bool = False
    cursos_biblicos: int | None = None
    precursor_auxiliar: bool = False
    horas: int | None = None
    notas: str | None = None


def _registro(
    sesion: Session, publicador_id: int, anio: int, mes: int
) -> RegistroMensual | None:
    consulta = select(RegistroMensual).where(
        RegistroMensual.publicador_id == publicador_id,
        RegistroMensual.anio == anio,
        RegistroMensual.mes == mes,
    )
    return sesion.exec(consulta).first()


def guardar_mes(
    sesion: Session, anio: int, mes: int, entradas: list[EntradaMes]
) -> int:
    """Crea o actualiza la fila de cada publicador para ese mes calendario.

    Sobrescribe la fila entera, `notas` incluidas. Quien llame debe reenviar el
    valor actual de cada campo que no quiera perder: guardar una `EntradaMes`
    con `notas=None` borra la nota que hubiera, sea escrita a mano o sugerida
    por un cambio de privilegio.
    """
    for entrada in entradas:
        fila = _registro(sesion, entrada.publicador_id, anio, mes) or RegistroMensual(
            publicador_id=entrada.publicador_id, anio=anio, mes=mes
        )
        fila.participo = entrada.participo
        fila.cursos_biblicos = entrada.cursos_biblicos
        fila.precursor_auxiliar = entrada.precursor_auxiliar
        fila.horas = entrada.horas
        fila.notas = entrada.notas
        sesion.add(fila)
    sesion.commit()
    return len(entradas)


def filas_del_mes(
    sesion: Session, anio: int, mes: int, *, grupo_id: int | None = None
) -> list[tuple[Publicador, RegistroMensual | None, bool]]:
    """Una fila por publicador activo, con su registro del mes si existe.

    El tercer elemento indica si el campo de horas corresponde: hay nombramiento
    de precursor o misionero vigente ese mes, o la fila está marcada como
    precursor auxiliar.
    """
    filas = []
    for publicador in publicadores.listar(sesion, grupo_id=grupo_id):
        registro = _registro(sesion, publicador.id, anio, mes)
        tipos = nombramientos.tipos_en_mes(sesion, publicador.id, anio, mes)
        con_horas = bool(tipos & set(TIPOS_CON_HORAS)) or bool(
            registro and registro.precursor_auxiliar
        )
        filas.append((publicador, registro, con_horas))
    return filas


def registros_del_anio(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> dict[int, RegistroMensual]:
    """Registros del año de servicio, indexados por mes calendario."""
    encontrados = {}
    for anio, mes in meses_del_anio(anio_servicio):
        fila = _registro(sesion, publicador_id, anio, mes)
        if fila is not None:
            encontrados[mes] = fila
    return encontrados


def tarjeta(sesion: Session, publicador_id: int, anio_servicio: int) -> DatosTarjeta:
    publicador = publicadores.obtener(sesion, publicador_id)
    del_anio = registros_del_anio(sesion, publicador_id, anio_servicio)

    datos = DatosTarjeta.vacia(publicador.nombre_completo, anio_servicio)
    datos.fecha_nacimiento = publicador.fecha_nacimiento
    datos.fecha_bautismo = publicador.fecha_bautismo
    datos.sexo = publicador.sexo
    datos.esperanza = publicador.esperanza
    datos.nombramientos = nombramientos.tipos_en_anio(
        sesion, publicador_id, anio_servicio
    )

    for fila in datos.meses:
        registro = del_anio.get(fila.mes)
        if registro is None:
            continue
        fila.participo = registro.participo
        fila.cursos_biblicos = registro.cursos_biblicos
        fila.precursor_auxiliar = registro.precursor_auxiliar
        fila.horas = registro.horas
        fila.notas = registro.notas

    return datos


def aplicar_notas_sugeridas(
    sesion: Session, publicador_id: int, anio_servicio: int
) -> int:
    """Escribe la nota de cambio de privilegio donde la nota esté vacía.

    Nunca pisa un texto escrito por el usuario. Devuelve cuántas notas escribió.
    """
    sugeridas = nombramientos.notas_sugeridas(sesion, publicador_id, anio_servicio)
    escritas = 0
    for anio, mes in meses_del_anio(anio_servicio):
        propuesta = sugeridas.get(mes)
        if not propuesta:
            continue
        fila = _registro(sesion, publicador_id, anio, mes)
        # Solo se anota sobre un mes ya cargado. Crear la fila aquí la dejaría
        # con participo=False, indistinguible de "cargado y no informó", y las
        # alertas se apoyan en esa diferencia. No se pierde nada: esta función
        # corre al ver y al exportar la tarjeta, así que la nota aparecerá sola
        # en cuanto el mes se cargue.
        if fila is None:
            continue
        if (fila.notas or "").strip():
            continue
        fila.notas = propuesta
        sesion.add(fila)
        escritas += 1
    sesion.commit()
    return escritas
