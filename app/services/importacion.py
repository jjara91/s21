"""Comparación de una tarjeta contra la base, aplicación y deshacer.

`analizar` no escribe nada: devuelve una propuesta que la pantalla de revisión
muestra al usuario. Solo `aplicar` toca la base, y guarda el estado anterior de
todo lo que modifica para que `deshacer` pueda restaurarlo con exactitud.
"""

import hashlib
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session, select

from app.config import cargar_config
from app.dominio import DatosTarjeta, rango_anio_servicio
from app.models import Importacion, Nombramiento, Publicador, RegistroMensual
from app.pdf.importar import leer_tarjeta
from app.services import nombramientos, publicadores, registros

CAMPOS_CABECERA = (
    ("fecha_nacimiento", "Fecha de nacimiento"),
    ("fecha_bautismo", "Fecha de bautismo"),
    ("sexo", "Sexo"),
    ("esperanza", "Esperanza"),
)


@dataclass
class Diferencia:
    campo: str
    etiqueta: str
    valor_actual: object
    valor_tarjeta: object


@dataclass(frozen=True)
class NombramientoPropuesto:
    tipo: str
    desde: date


@dataclass
class Propuesta:
    archivo: str
    sha256: str
    datos: DatosTarjeta
    publicador_id: int | None
    diferencias: list[Diferencia] = field(default_factory=list)
    nombramientos: list[NombramientoPropuesto] = field(default_factory=list)
    meses_en_conflicto: list[int] = field(default_factory=list)
    ya_importado: datetime | None = None


@dataclass
class Decision:
    propuesta: Propuesta
    publicador_id: int | None
    aceptar_campos: set[str]
    aceptar_nombramientos: list[NombramientoPropuesto]
    aceptar_meses: set[int]


def _anio_calendario(anio_servicio: int, mes: int) -> int:
    return anio_servicio - 1 if mes >= 9 else anio_servicio


def analizar(
    sesion: Session,
    archivo: str,
    contenido: bytes,
    *,
    anio_servicio_manual: int | None = None,
) -> Propuesta:
    """`anio_servicio_manual` es lo que el usuario escribió a mano en la
    pantalla de revisión cuando la tarjeta no traía año de servicio legible.
    Solo se usa si la tarjeta de verdad no trae año: nunca pisa uno que sí
    venga en el PDF.
    """
    datos = leer_tarjeta(contenido)
    if datos.anio_servicio is None and anio_servicio_manual is not None:
        datos.anio_servicio = anio_servicio_manual
    sha = hashlib.sha256(contenido).hexdigest()

    previa = sesion.exec(
        select(Importacion)
        .where(Importacion.sha256 == sha, Importacion.deshecho == False)  # noqa: E712
        .order_by(Importacion.fecha.desc())
    ).first()

    existente = publicadores.buscar_por_nombre(sesion, datos.nombre) if datos.nombre else None
    propuesta = Propuesta(
        archivo=archivo,
        sha256=sha,
        datos=datos,
        publicador_id=existente.id if existente else None,
        ya_importado=previa.fecha if previa else None,
    )

    for campo, etiqueta in CAMPOS_CABECERA:
        actual = getattr(existente, campo) if existente is not None else None
        nuevo = getattr(datos, campo)
        if nuevo is not None and nuevo != actual:
            propuesta.diferencias.append(Diferencia(campo, etiqueta, actual, nuevo))

    if datos.anio_servicio is not None:
        inicio, fin = rango_anio_servicio(datos.anio_servicio)
        vigentes = (
            nombramientos.tipos_en_anio(sesion, existente.id, datos.anio_servicio)
            if existente
            else set()
        )
        propuesta.nombramientos = [
            NombramientoPropuesto(tipo, inicio)
            for tipo in sorted(datos.nombramientos - vigentes)
        ]

        if existente is not None:
            guardados = registros.registros_del_anio(
                sesion, existente.id, datos.anio_servicio
            )
            for fila in datos.meses:
                previo = guardados.get(fila.mes)
                if previo is None:
                    continue
                distinto = (
                    previo.participo != fila.participo
                    or previo.cursos_biblicos != fila.cursos_biblicos
                    or previo.precursor_auxiliar != fila.precursor_auxiliar
                    or previo.horas != fila.horas
                    or (previo.notas or "") != (fila.notas or "")
                )
                if distinto:
                    propuesta.meses_en_conflicto.append(fila.mes)

    return propuesta


def _snapshot_publicador(publicador: Publicador) -> dict:
    return {
        "nombre_completo": publicador.nombre_completo,
        "fecha_nacimiento": publicador.fecha_nacimiento.isoformat()
        if publicador.fecha_nacimiento
        else None,
        "fecha_bautismo": publicador.fecha_bautismo.isoformat()
        if publicador.fecha_bautismo
        else None,
        "sexo": publicador.sexo,
        "esperanza": publicador.esperanza,
    }


def _snapshot_registro(registro: RegistroMensual | None) -> dict | None:
    if registro is None:
        return None
    return {
        "participo": registro.participo,
        "cursos_biblicos": registro.cursos_biblicos,
        "precursor_auxiliar": registro.precursor_auxiliar,
        "horas": registro.horas,
        "notas": registro.notas,
    }


def _meses_a_tocar(
    sesion: Session,
    publicador_id: int,
    datos: DatosTarjeta,
    anio_servicio: int | None,
    aceptar_meses: set[int],
) -> list[dict]:
    """Estado actual de cada mes que la importación va a sobrescribir."""
    if anio_servicio is None:
        return []
    tocados = []
    for fila in datos.meses:
        if fila.mes not in aceptar_meses:
            continue
        anio = _anio_calendario(anio_servicio, fila.mes)
        actual = sesion.exec(
            select(RegistroMensual).where(
                RegistroMensual.publicador_id == publicador_id,
                RegistroMensual.anio == anio,
                RegistroMensual.mes == fila.mes,
            )
        ).first()
        tocados.append(
            {"anio": anio, "mes": fila.mes, "previo": _snapshot_registro(actual)}
        )
    return tocados


def aplicar(
    sesion: Session, decision: Decision, lote: str, ahora: datetime
) -> Importacion:
    datos = decision.propuesta.datos
    anio_servicio = datos.anio_servicio

    if decision.publicador_id is None:
        publicador = publicadores.crear(sesion, datos.nombre)
        accion = "creado"
        previo_publicador = None
    else:
        publicador = publicadores.obtener(sesion, decision.publicador_id)
        accion = "actualizado"
        previo_publicador = _snapshot_publicador(publicador)

    # El respaldo se escribe ANTES de tocar nada. Los servicios que se llaman
    # más abajo hacen commit por su cuenta, así que si el proceso muriera a
    # mitad de camino y esta fila no existiera todavía, los valores pisados se
    # habrían perdido sin rastro. Escribiéndola primero, deshacer siempre puede
    # restaurarlos. Lo único que puede quedar huérfano es un publicador recién
    # creado o un nombramiento, que se borran a mano y no son datos perdidos.
    registros_tocados = _meses_a_tocar(
        sesion, publicador.id, datos, anio_servicio, decision.aceptar_meses
    )
    registro = Importacion(
        archivo=decision.propuesta.archivo,
        sha256=decision.propuesta.sha256,
        fecha=ahora,
        lote=lote,
        publicador_id=publicador.id,
        anio_servicio=anio_servicio,
        accion=accion,
        estado_previo=json.dumps(
            {
                "publicador_creado": previo_publicador is None,
                "publicador": previo_publicador,
                "nombramientos_creados": [],
                "registros": registros_tocados,
            }
        ),
    )
    sesion.add(registro)
    sesion.commit()
    sesion.refresh(registro)

    cambios = {
        campo: getattr(datos, campo)
        for campo, _etiqueta in CAMPOS_CABECERA
        if campo in decision.aceptar_campos
    }
    if cambios:
        publicador = publicadores.actualizar(sesion, publicador.id, **cambios)

    nombramientos_creados = []
    for propuesto in decision.aceptar_nombramientos:
        creado = nombramientos.crear(
            sesion, publicador.id, propuesto.tipo, propuesto.desde
        )
        nombramientos_creados.append(creado.id)

    if anio_servicio is not None:
        for fila in datos.meses:
            if fila.mes not in decision.aceptar_meses:
                continue
            anio = _anio_calendario(anio_servicio, fila.mes)
            registros.guardar_mes(
                sesion,
                anio,
                fila.mes,
                [
                    registros.EntradaMes(
                        publicador_id=publicador.id,
                        participo=fila.participo,
                        cursos_biblicos=fila.cursos_biblicos,
                        precursor_auxiliar=fila.precursor_auxiliar,
                        horas=fila.horas,
                        notas=fila.notas,
                    )
                ],
            )

    # Los ids de los nombramientos solo existen una vez creados, así que esta
    # parte del respaldo se completa al final. Si el proceso muriera aquí, lo
    # peor que queda es un nombramiento huérfano: ningún dato anterior se pierde.
    estado = json.loads(registro.estado_previo or "{}")
    estado["nombramientos_creados"] = nombramientos_creados
    registro.estado_previo = json.dumps(estado)
    sesion.add(registro)
    sesion.commit()
    sesion.refresh(registro)
    return registro


def _restaurar(sesion: Session, registro: Importacion) -> None:
    estado = json.loads(registro.estado_previo or "{}")

    for nombramiento_id in estado.get("nombramientos_creados", []):
        nombramiento = sesion.get(Nombramiento, nombramiento_id)
        if nombramiento is not None:
            sesion.delete(nombramiento)

    for tocado in estado.get("registros", []):
        fila = sesion.exec(
            select(RegistroMensual).where(
                RegistroMensual.publicador_id == registro.publicador_id,
                RegistroMensual.anio == tocado["anio"],
                RegistroMensual.mes == tocado["mes"],
            )
        ).first()
        if fila is None:
            continue
        if tocado["previo"] is None:
            sesion.delete(fila)
            continue
        for nombre, valor in tocado["previo"].items():
            setattr(fila, nombre, valor)
        sesion.add(fila)

    publicador = (
        sesion.get(Publicador, registro.publicador_id) if registro.publicador_id else None
    )
    if publicador is None:
        return
    if estado.get("publicador_creado"):
        registro.publicador_id = None
        sesion.add(registro)
        sesion.flush()
        sesion.delete(publicador)
    elif estado.get("publicador"):
        previo = estado["publicador"]
        publicadores.actualizar(
            sesion,
            publicador.id,
            nombre_completo=previo["nombre_completo"],
            fecha_nacimiento=date.fromisoformat(previo["fecha_nacimiento"])
            if previo["fecha_nacimiento"]
            else None,
            fecha_bautismo=date.fromisoformat(previo["fecha_bautismo"])
            if previo["fecha_bautismo"]
            else None,
            sexo=previo["sexo"],
            esperanza=previo["esperanza"],
        )


def deshacer(sesion: Session, lote: str) -> int:
    # Del más nuevo al más viejo. Si dos archivos del mismo lote tocaron el
    # mismo mes del mismo publicador, deshacer en orden de inserción dejaría el
    # valor intermedio en vez del original.
    pendientes = sesion.exec(
        select(Importacion)
        .where(
            Importacion.lote == lote,
            Importacion.deshecho == False,  # noqa: E712
        )
        .order_by(Importacion.id.desc())
    ).all()

    for registro in pendientes:
        _restaurar(sesion, registro)
        registro.deshecho = True
        sesion.add(registro)
    sesion.commit()
    return len(pendientes)


def historial(sesion: Session) -> list[tuple[str, datetime, int]]:
    """(lote, fecha, archivos) de las importaciones no deshechas, la más nueva primero."""
    filas = sesion.exec(
        select(Importacion)
        .where(Importacion.deshecho == False)  # noqa: E712
        .order_by(Importacion.fecha.desc())
    ).all()
    por_lote: dict[str, tuple[datetime, int]] = {}
    for fila in filas:
        fecha, cantidad = por_lote.get(fila.lote, (fila.fecha, 0))
        por_lote[fila.lote] = (min(fecha, fila.fecha), cantidad + 1)
    return [(lote, fecha, cantidad) for lote, (fecha, cantidad) in por_lote.items()]


class LoteInvalido(Exception):
    pass


PATRON_LOTE = re.compile(r"[0-9a-f]{12}")

DIAS_RETENCION_LOTES = 7


def _directorio_lotes() -> Path:
    return cargar_config().data_dir / "subidas"


def _directorio_de_lote(lote: str) -> Path:
    """Ruta del lote, validando la forma del identificador.

    `lote` llega desde la URL y se usa para construir una ruta en disco. Sin
    esta comprobación, un valor como ".." apuntaría al propio directorio de
    datos, y `borrar_lote` haría rmtree sobre la base y las tarjetas subidas.
    """
    if not PATRON_LOTE.fullmatch(lote):
        raise LoteInvalido(f"identificador de lote inválido: {lote!r}")
    return _directorio_lotes() / lote


def guardar_lote(archivos: list[tuple[str, bytes]]) -> str:
    """Deja los PDF subidos en disco y devuelve el identificador del lote."""
    lote = uuid.uuid4().hex[:12]
    destino = _directorio_lotes() / lote
    destino.mkdir(parents=True, exist_ok=True)
    for indice, (nombre, contenido) in enumerate(archivos):
        # el índice conserva el orden y evita choques de nombre
        (destino / f"{indice:03d}_{Path(nombre).name}").write_bytes(contenido)
    return lote


def archivos_del_lote(lote: str) -> list[tuple[str, bytes]]:
    directorio = _directorio_de_lote(lote)
    if not directorio.exists():
        return []
    return [
        (ruta.name.split("_", 1)[1], ruta.read_bytes())
        for ruta in sorted(directorio.iterdir())
    ]


def borrar_lote(lote: str) -> None:
    shutil.rmtree(_directorio_de_lote(lote), ignore_errors=True)


def purgar_lotes_viejos(dias: int = DIAS_RETENCION_LOTES) -> int:
    """Borra los lotes subidos que nadie confirmó ni descartó.

    Son PDF con datos personales de la congregación: no deben quedarse en
    disco indefinidamente solo porque alguien cerró la pestaña.
    """
    directorio = _directorio_lotes()
    if not directorio.exists():
        return 0
    limite = time.time() - dias * 86400
    borrados = 0
    for hijo in directorio.iterdir():
        if hijo.is_dir() and PATRON_LOTE.fullmatch(hijo.name) and hijo.stat().st_mtime < limite:
            shutil.rmtree(hijo, ignore_errors=True)
            borrados += 1
    return borrados
