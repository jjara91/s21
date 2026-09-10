from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.dominio import TIPOS_NOMBRAMIENTO
from app.services import grupos, nombramientos
from app.services import publicadores as servicio
from app.web.errores import fecha_obligatoria, fecha_opcional
from app.web.plantillas import plantillas

router = APIRouter(prefix="/publicadores")


def _vacio_a_none(valor: str | None) -> str | None:
    return valor or None


@router.get("")
def lista(
    request: Request,
    texto: str | None = None,
    grupo_id: int | None = None,
    privilegio: str | None = None,
    incluir_bajas: bool = False,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    encontrados = servicio.listar(
        sesion, texto=texto, grupo_id=grupo_id, incluir_bajas=incluir_bajas
    )
    encontrados = servicio.con_privilegio(sesion, encontrados, privilegio, date.today())
    todos_los_grupos = grupos.listar(sesion)
    return plantillas.TemplateResponse(
        request,
        "publicadores_lista.html",
        {
            "publicadores": encontrados,
            "grupos": {grupo.id: grupo for grupo in todos_los_grupos},
            "todos_los_grupos": todos_los_grupos,
            "etiquetas": nombramientos.ETIQUETAS,
            "tipos": TIPOS_NOMBRAMIENTO,
            "texto": texto or "",
            "grupo_id": grupo_id,
            "privilegio": privilegio or "",
            "incluir_bajas": incluir_bajas,
        },
    )


@router.post("")
def crear(
    nombre_completo: str = Form(...),
    sexo: str | None = Form(None),
    esperanza: str | None = Form(None),
    fecha_nacimiento: str | None = Form(None),
    fecha_bautismo: str | None = Form(None),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.crear(
        sesion,
        nombre_completo,
        sexo=_vacio_a_none(sexo),
        esperanza=_vacio_a_none(esperanza),
        fecha_nacimiento=fecha_opcional(fecha_nacimiento, "La fecha de nacimiento"),
        fecha_bautismo=fecha_opcional(fecha_bautismo, "La fecha de bautismo"),
        grupo_id=grupo_id,
    )
    return RedirectResponse("/publicadores", status_code=303)


@router.get("/{publicador_id}")
def detalle(
    publicador_id: int,
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request,
        "publicador_detalle.html",
        {
            "publicador": servicio.obtener(sesion, publicador_id),
            "nombramientos": nombramientos.listar(sesion, publicador_id),
            "etiquetas": nombramientos.ETIQUETAS,
            "tipos": TIPOS_NOMBRAMIENTO,
            "grupos": grupos.listar(sesion),
        },
    )


@router.post("/{publicador_id}")
def editar(
    publicador_id: int,
    nombre_completo: str = Form(...),
    sexo: str | None = Form(None),
    esperanza: str | None = Form(None),
    fecha_nacimiento: str | None = Form(None),
    fecha_bautismo: str | None = Form(None),
    grupo_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.actualizar(
        sesion,
        publicador_id,
        nombre_completo=nombre_completo,
        sexo=_vacio_a_none(sexo),
        esperanza=_vacio_a_none(esperanza),
        fecha_nacimiento=fecha_opcional(fecha_nacimiento, "La fecha de nacimiento"),
        fecha_bautismo=fecha_opcional(fecha_bautismo, "La fecha de bautismo"),
        grupo_id=grupo_id,
    )
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)


@router.post("/{publicador_id}/baja")
def baja(
    publicador_id: int,
    fecha_baja: str = Form(...),
    motivo_baja: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.dar_de_baja(
        sesion, publicador_id, fecha_obligatoria(fecha_baja, "La fecha de baja"), motivo_baja
    )
    return RedirectResponse("/publicadores", status_code=303)


@router.post("/{publicador_id}/nombramientos")
def agregar_nombramiento(
    publicador_id: int,
    tipo: str = Form(...),
    desde: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    nombramientos.crear(
        sesion, publicador_id, tipo, fecha_obligatoria(desde, "La fecha de inicio")
    )
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)


@router.post("/{publicador_id}/nombramientos/{nombramiento_id}/cerrar")
def cerrar_nombramiento(
    publicador_id: int,
    nombramiento_id: int,
    hasta: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    nombramientos.cerrar(
        sesion, nombramiento_id, fecha_obligatoria(hasta, "La fecha de término")
    )
    return RedirectResponse(f"/publicadores/{publicador_id}", status_code=303)
