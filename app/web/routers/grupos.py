from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.services import grupos as servicio
from app.services import publicadores
from app.web.plantillas import plantillas

router = APIRouter(prefix="/grupos")


@router.get("")
def lista(
    request: Request,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    return plantillas.TemplateResponse(
        request,
        "grupos.html",
        {
            "grupos": servicio.listar(sesion),
            "publicadores": publicadores.listar(sesion),
        },
    )


@router.post("")
def crear(
    nombre: str = Form(...),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.crear(sesion, nombre)
    return RedirectResponse("/grupos", status_code=303)


@router.post("/{grupo_id}")
def editar(
    grupo_id: int,
    nombre: str = Form(...),
    superintendente_id: int | None = Form(None),
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.actualizar(
        sesion, grupo_id, nombre=nombre, superintendente_id=superintendente_id
    )
    return RedirectResponse("/grupos", status_code=303)


@router.post("/{grupo_id}/eliminar")
def eliminar(
    grupo_id: int,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    servicio.eliminar(sesion, grupo_id)
    return RedirectResponse("/grupos", status_code=303)
