"""Genera un PDF con los mismos campos que el S-21 pero sin su contenido.

El formulario oficial no se distribuye en el repositorio. Las pruebas de la capa
PDF trabajan contra este sustituto, que tiene los 75 campos con los mismos
nombres y tipos.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.pdf import campos


def crear_s21_sintetico(destino: Path) -> Path:
    lienzo = canvas.Canvas(str(destino), pagesize=letter)
    formulario = lienzo.acroForm
    huecos = iter([(x, y) for x in (40, 210, 380) for y in range(760, 40, -14)])

    for nombre in sorted(campos.CAMPOS_TEXTO):
        x, y = next(huecos)
        formulario.textfield(
            name=nombre, x=x, y=y, width=150, height=11, fontSize=7, borderWidth=0
        )
    for nombre in sorted(campos.CAMPOS_CASILLA):
        x, y = next(huecos)
        formulario.checkbox(name=nombre, x=x, y=y, size=9)

    # showPage antes de save: sin esto reportlab deja la referencia a la página
    # sin resolver y falla con "forward reference to 'Page1'".
    lienzo.showPage()
    lienzo.save()
    return destino
