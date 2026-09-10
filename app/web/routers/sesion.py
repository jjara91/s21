from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app import auth
from app.web.plantillas import plantillas

router = APIRouter()


@router.get("/entrar")
def formulario(request: Request):
    return plantillas.TemplateResponse(request, "login.html", {"error": None})


@router.post("/entrar")
def entrar(request: Request, usuario: str = Form(...), clave: str = Form(...)):
    if not auth.credenciales_validas(usuario, clave):
        return plantillas.TemplateResponse(
            request,
            "login.html",
            {"error": "Usuario o clave incorrectos"},
            status_code=401,
        )
    auth.iniciar_sesion(request, usuario)
    return RedirectResponse("/", status_code=303)


@router.post("/salir")
def salir(request: Request):
    auth.cerrar_sesion(request)
    return RedirectResponse("/entrar", status_code=303)
