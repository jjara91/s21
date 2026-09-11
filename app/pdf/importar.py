"""Lectura de una tarjeta S-21 a objetos de dominio. No toca la base de datos."""

from datetime import date, datetime

from app.dominio import DatosTarjeta, FilaMes
from app.pdf import campos
from app.pdf.plantilla import TarjetaInvalida, leer_campos, validar_es_s21

FORMATOS_FECHA = ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d")


def parsear_fecha(texto: str | None) -> tuple[date | None, str | None]:
    """Devuelve (fecha, None) si se pudo interpretar, (None, texto) si no."""
    limpio = (texto or "").strip()
    if not limpio:
        return None, None
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(limpio, formato).date(), None
        except ValueError:
            continue
    return None, limpio


def _entero(texto: str | None) -> tuple[int | None, str | None]:
    """Devuelve (numero, None) o (None, texto) si el contenido no es numérico."""
    limpio = (texto or "").strip()
    if not limpio:
        return None, None
    try:
        return int(limpio), None
    except ValueError:
        return None, limpio


def _valores(contenido: bytes) -> dict[str, str]:
    return {nombre: campo.get("/V") for nombre, campo in leer_campos(contenido).items()}


def _marcada(valores: dict[str, str], nombre: str) -> bool:
    return str(valores.get(nombre) or "") == campos.MARCADA


def _texto(valores: dict[str, str], nombre: str) -> str:
    return str(valores.get(nombre) or "").strip()


def _unir_notas(*partes: str | None) -> str | None:
    presentes = [parte.strip() for parte in partes if parte and parte.strip()]
    return " · ".join(presentes) if presentes else None


def leer_tarjeta(contenido: bytes) -> DatosTarjeta:
    validar_es_s21(contenido)
    valores = _valores(contenido)

    nacimiento, nacimiento_crudo = parsear_fecha(
        _texto(valores, campos.CABECERA_TEXTO["fecha_nacimiento"])
    )
    bautismo, bautismo_crudo = parsear_fecha(
        _texto(valores, campos.CABECERA_TEXTO["fecha_bautismo"])
    )
    anio, anio_crudo = _entero(_texto(valores, campos.CABECERA_TEXTO["anio_servicio"]))

    sexo = next(
        (clave for clave, campo in campos.CABECERA_SEXO.items() if _marcada(valores, campo)),
        None,
    )
    esperanza = next(
        (
            clave
            for clave, campo in campos.CABECERA_ESPERANZA.items()
            if _marcada(valores, campo)
        ),
        None,
    )
    nombramientos = {
        clave
        for clave, campo in campos.CABECERA_NOMBRAMIENTOS.items()
        if _marcada(valores, campo)
    }

    meses = []
    for mes in campos.MESES_ORDENADOS:
        horas, horas_crudas = _entero(_texto(valores, campos.campo_fila("horas", mes)))
        cursos, cursos_crudos = _entero(
            _texto(valores, campos.campo_fila("cursos_biblicos", mes))
        )
        meses.append(
            FilaMes(
                mes=mes,
                participo=_marcada(valores, campos.campo_fila("participo", mes)),
                cursos_biblicos=cursos,
                precursor_auxiliar=_marcada(
                    valores, campos.campo_fila("precursor_auxiliar", mes)
                ),
                horas=horas,
                # un valor no numérico se conserva en las notas en vez de perderse
                notas=_unir_notas(
                    _texto(valores, campos.campo_fila("notas", mes)) or None,
                    horas_crudas,
                    cursos_crudos,
                ),
            )
        )

    return DatosTarjeta(
        nombre=_texto(valores, campos.CABECERA_TEXTO["nombre"]),
        anio_servicio=anio,
        fecha_nacimiento=nacimiento,
        fecha_bautismo=bautismo,
        fecha_nacimiento_cruda=nacimiento_crudo,
        fecha_bautismo_cruda=bautismo_crudo,
        anio_servicio_crudo=anio_crudo,
        sexo=sexo,
        esperanza=esperanza,
        nombramientos=nombramientos,
        meses=meses,
    )
