"""Sesión de un solo usuario, con las credenciales en variables de entorno."""

import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import cargar_config

CLAVE_SESION = "usuario"


class SinSesion(Exception):
    """Se convierte en redirección al login en el manejador de app.main."""


def credenciales_validas(usuario: str, clave: str) -> bool:
    config = cargar_config()
    # Las dos comparaciones se evalúan siempre, sin cortocircuito: un `and`
    # entre ellas se saltaría la segunda cuando el usuario no coincide, y el
    # tiempo de respuesta delataría si el nombre de usuario existe.
    usuario_ok = secrets.compare_digest(usuario, config.auth_user)
    clave_ok = secrets.compare_digest(clave, config.auth_pass)
    return usuario_ok and clave_ok


def iniciar_sesion(request: Request, usuario: str) -> None:
    request.session[CLAVE_SESION] = usuario


def cerrar_sesion(request: Request) -> None:
    request.session.pop(CLAVE_SESION, None)


def requerir_sesion(request: Request) -> str:
    usuario = request.session.get(CLAVE_SESION)
    if not usuario:
        raise SinSesion()
    return usuario


def redirigir_al_login() -> RedirectResponse:
    return RedirectResponse("/entrar", status_code=303)
