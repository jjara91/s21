from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth import requerir_sesion
from app.db import obtener_sesion
from app.services import grupos, registros
from app.web.plantillas import plantillas

router = APIRouter(prefix="/grilla")


def _entero(valor: str | None) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor.isdigit() else None


@router.get("")
def ver(
    request: Request,
    anio: int | None = None,
    mes: int | None = None,
    grupo_id: int | None = None,
    sesion: Session = Depends(obtener_sesion),
    _usuario: str = Depends(requerir_sesion),
):
    hoy = date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    return plantillas.TemplateResponse(
        request,
        "grilla.html",
        {
            "anio": anio,
            "mes": mes,
            "grupo_id": grupo_id,
            "grupos": grupos.listar(sesion),
            "filas": registros.filas_del_mes(sesion, anio, mes, grupo_id=grupo_id),
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
    formulario = await request.form()
    entradas = []
    for crudo in formulario.getlist("publicadores"):
        publicador_id = int(crudo)
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
