"""Validación de que un PDF es una tarjeta S-21 y vaciado a plantilla."""

from io import BytesIO
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from app.pdf import campos


class TarjetaInvalida(Exception):
    def __init__(self, mensaje: str, faltantes: list[str] | None = None) -> None:
        super().__init__(mensaje)
        self.faltantes = faltantes or []


def _leer(contenido: bytes) -> PdfReader:
    try:
        return PdfReader(BytesIO(contenido))
    except (PdfReadError, OSError, ValueError) as error:
        # El texto de `error` viene de pypdf y sale en inglés (p. ej. "Stream
        # has ended unexpectedly"); no se expone al usuario. La causa original
        # queda igual disponible en la traza del log gracias al `from error`.
        raise TarjetaInvalida(
            "El archivo no se pudo abrir como PDF. Comprueba que subiste el "
            "formulario S-21 y que el archivo no está dañado."
        ) from error


def _nombre_cualificado(widget: DictionaryObject) -> str | None:
    """Nombre completo del campo del widget, uniendo con "." la cadena de /Parent."""
    partes: list[str] = []
    nodo: Any = widget
    visitados: set[int] = set()
    while isinstance(nodo, DictionaryObject) and id(nodo) not in visitados:
        visitados.add(id(nodo))
        parcial = nodo.get("/T")
        if parcial is not None:
            partes.append(str(parcial))
        padre = nodo.get("/Parent")
        nodo = padre.get_object() if padre is not None else None
    return ".".join(reversed(partes)) or None


def _campo_del_widget(widget: DictionaryObject) -> DictionaryObject:
    """Nodo que guarda el valor: el propio widget si va fundido con el campo,
    o el ancestro que lleve /V o /FT cuando el campo tiene varios widgets."""
    nodo: Any = widget
    visitados: set[int] = set()
    while isinstance(nodo, DictionaryObject) and id(nodo) not in visitados:
        visitados.add(id(nodo))
        if "/V" in nodo or "/FT" in nodo:
            return nodo
        padre = nodo.get("/Parent")
        nodo = padre.get_object() if padre is not None else None
    return widget


def leer_campos(contenido: bytes) -> dict[str, Any]:
    """Campos del formulario, aunque /AcroForm/Fields haya quedado incompleto.

    Vista Previa de macOS (Quartz PDFContext) reescribe ese array con una sola
    entrada al guardar la tarjeta rellenada: get_fields() ve entonces un campo y
    los otros 74 parecen no existir, pese a seguir intactos como anotaciones de
    la página. Se recorren los widgets para recuperarlos.
    """
    lector = _leer(contenido)
    encontrados: dict[str, Any] = dict(lector.get_fields() or {})
    for pagina in lector.pages:
        for anotacion in pagina.get("/Annots") or []:
            widget = anotacion.get_object()
            if not isinstance(widget, DictionaryObject):
                continue
            if widget.get("/Subtype") != "/Widget":
                continue
            nombre = _nombre_cualificado(widget)
            if nombre and nombre not in encontrados:
                encontrados[nombre] = _campo_del_widget(widget)
    return encontrados


def validar_es_s21(contenido: bytes) -> None:
    """Lanza TarjetaInvalida si el PDF no trae los 75 campos del S-21."""
    presentes = set(leer_campos(contenido))
    faltantes = sorted(campos.TODOS_LOS_CAMPOS - presentes)
    if faltantes:
        raise TarjetaInvalida(
            "el PDF no es una tarjeta S-21 rellenable "
            f"(faltan {len(faltantes)} campos, por ejemplo {faltantes[0]}); "
            "si es una tarjeta escaneada no sirve, hace falta el formulario original",
            faltantes,
        )


def _raiz_del_campo(widget: DictionaryObject) -> DictionaryObject | None:
    """Campo de más arriba del que cuelga el widget, que es lo que va en /Fields."""
    raiz: DictionaryObject | None = widget if "/T" in widget else None
    nodo: Any = widget.get("/Parent")
    visitados: set[int] = set()
    while isinstance(nodo := (nodo.get_object() if nodo is not None else None), DictionaryObject):
        if id(nodo) in visitados:
            break
        visitados.add(id(nodo))
        if "/T" in nodo:
            raiz = nodo
        nodo = nodo.get("/Parent")
    return raiz


def _reparar_fields(escritor: PdfWriter) -> None:
    """Reconstruye /AcroForm/Fields con los campos que cuelgan de las páginas.

    La tarjeta de origen puede traer ese array mutilado (ver leer_campos). Si se
    clonara tal cual, la plantilla —y con ella cada PDF que se exporte— quedaría
    con un formulario que otros lectores no saben recorrer.
    """
    referencia_formulario = escritor.root_object.get("/AcroForm")
    if referencia_formulario is None:
        return
    formulario = referencia_formulario.get_object()

    referencias = []
    vistas: set[int] = set()
    for pagina in escritor.pages:
        for anotacion in pagina.get("/Annots") or []:
            widget = anotacion.get_object()
            if not isinstance(widget, DictionaryObject):
                continue
            if widget.get("/Subtype") != "/Widget":
                continue
            raiz = _raiz_del_campo(widget)
            if raiz is None or raiz.indirect_reference is None:
                continue
            clave = raiz.indirect_reference.idnum
            if clave not in vistas:
                vistas.add(clave)
                referencias.append(raiz.indirect_reference)

    if referencias:
        formulario[NameObject("/Fields")] = ArrayObject(referencias)


def crear_plantilla(contenido: bytes) -> bytes:
    """Devuelve la misma tarjeta con los 75 campos en blanco."""
    validar_es_s21(contenido)
    escritor = PdfWriter(clone_from=BytesIO(contenido))
    escritor.set_need_appearances_writer(True)
    _reparar_fields(escritor)

    en_blanco: dict[str, str] = {nombre: "" for nombre in campos.CAMPOS_TEXTO}
    en_blanco.update({nombre: campos.DESMARCADA for nombre in campos.CAMPOS_CASILLA})
    for pagina in escritor.pages:
        escritor.update_page_form_field_values(pagina, en_blanco, auto_regenerate=False)

    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
