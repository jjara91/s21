from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.services import grupos, registros
from app.web.errores import DatosInvalidos, IdOpcional, anio_valido, mes_valido
from app.web.plantillas import plantillas

router = APIRouter(prefix="/grilla")


def _entero(valor: str | None) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


@dataclass
class _FilaEnviada:
    """Espeja los atributos de RegistroMensual para poder devolver a la
    plantilla lo que el usuario escribió, sin haber guardado nada."""

    participo: bool
    cursos_biblicos: str
    precursor_auxiliar: bool
    horas: str
    notas: str


@router.get("")
def ver(
    request: Request,
    anio: int | None = None,
    mes: int | None = None,
    grupo_id: IdOpcional = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio = anio_valido(anio) if anio is not None else hoy.year
    mes = mes_valido(mes) if mes is not None else hoy.month
    return plantillas.TemplateResponse(
        request,
        "grilla.html",
        {
            "anio": anio,
            "mes": mes,
            "grupo_id": grupo_id,
            "grupos": grupos.listar(sesion),
            "filas": registros.filas_del_mes(sesion, anio, mes, grupo_id=grupo_id),
            "errores": [],
        },
    )


@router.post("")
async def guardar(
    request: Request,
    anio: int = Form(...),
    mes: int = Form(...),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    anio = anio_valido(anio)
    mes = mes_valido(mes)
    formulario = await request.form()

    ids_enviados = []
    for crudo in formulario.getlist("publicadores"):
        try:
            ids_enviados.append(int(crudo))
        except ValueError:
            raise DatosInvalidos(
                f"El formulario envió un identificador de publicador inválido: {crudo!r}."
            ) from None

    filas = registros.filas_del_mes(sesion, anio, mes, grupo_id=grupo_id)
    publicador_por_id = {publicador.id: publicador for publicador, _, _ in filas}

    errores = []
    for publicador_id in ids_enviados:
        publicador = publicador_por_id.get(publicador_id)
        nombre = publicador.nombre_completo if publicador else f"id {publicador_id}"
        for campo, etiqueta in (("cursos", "los cursos bíblicos"), ("horas", "las horas")):
            crudo = (formulario.get(f"{campo}_{publicador_id}") or "").strip()
            if crudo and _entero(crudo) is None:
                errores.append(
                    f"{nombre}: {etiqueta} deben ser un número, se recibió {crudo!r}."
                )

    if errores:
        filas_enviadas = []
        for publicador, _, horas_habilitadas in filas:
            fila_enviada = _FilaEnviada(
                participo=formulario.get(f"participo_{publicador.id}") is not None,
                cursos_biblicos=(formulario.get(f"cursos_{publicador.id}") or "").strip(),
                precursor_auxiliar=formulario.get(f"auxiliar_{publicador.id}") is not None,
                horas=(formulario.get(f"horas_{publicador.id}") or "").strip(),
                notas=(formulario.get(f"notas_{publicador.id}") or "").strip(),
            )
            # En la respuesta de error las horas se habilitan también por la casilla
            # de auxiliar recién marcada: si solo se mirara la base, quien marque
            # auxiliar y escriba mal las horas recibiría el campo deshabilitado y no
            # podría corregir el error que se le está señalando.
            habilitadas = horas_habilitadas or fila_enviada.precursor_auxiliar
            filas_enviadas.append((publicador, fila_enviada, habilitadas))
        return plantillas.TemplateResponse(
            request,
            "grilla.html",
            {
                "anio": anio,
                "mes": mes,
                "grupo_id": grupo_id,
                "grupos": grupos.listar(sesion),
                "filas": filas_enviadas,
                "errores": errores,
            },
            status_code=400,
        )

    entradas = []
    for publicador_id in ids_enviados:
        entradas.append(
            registros.EntradaMes(
                publicador_id=publicador_id,
                participo=formulario.get(f"participo_{publicador_id}") is not None,
                cursos_biblicos=_entero(formulario.get(f"cursos_{publicador_id}")),
                precursor_auxiliar=formulario.get(f"auxiliar_{publicador_id}") is not None,
                horas=_entero(formulario.get(f"horas_{publicador_id}")),
                notas=(formulario.get(f"notas_{publicador_id}") or "").strip() or None,
            )
        )
    registros.guardar_mes(sesion, anio, mes, entradas)

    destino = f"/grilla?anio={anio}&mes={mes}"
    if grupo_id:
        destino += f"&grupo_id={grupo_id}"
    return RedirectResponse(destino, status_code=303)
