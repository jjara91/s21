import os
import time
from datetime import date, datetime
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.pdf import campos
from app.services import importacion, nombramientos, publicadores, registros

AHORA = datetime(2026, 9, 9, 12, 0, 0)


def _pdf(ruta, valores: dict[str, str]) -> bytes:
    escritor = PdfWriter(clone_from=str(ruta))
    escritor.update_page_form_field_values(escritor.pages[0], valores, auto_regenerate=False)
    buffer = BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def tarjeta_mauricio_horas_20(plantilla_sintetica):
    return _pdf(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025",
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "20",
        },
    )


@pytest.fixture
def tarjeta_mauricio(plantilla_sintetica):
    return _pdf(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["fecha_nacimiento"]: "14.03.1985",
            campos.CABECERA_TEXTO["fecha_bautismo"]: "07.06.2002",
            campos.CABECERA_TEXTO["anio_servicio"]: "2025",
            campos.CABECERA_SEXO["H"]: campos.MARCADA,
            campos.CABECERA_ESPERANZA["otras_ovejas"]: campos.MARCADA,
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("precursor_auxiliar", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
    )


@pytest.fixture
def tarjeta_mauricio_sin_anio(plantilla_sintetica):
    """La misma tarjeta, pero con el año de servicio escrito a mano de forma
    ilegible para el sistema (un rango, en vez de un solo año)."""
    return _pdf(
        plantilla_sintetica,
        {
            campos.CABECERA_TEXTO["nombre"]: "Mauricio Andrés Rojas Vega",
            campos.CABECERA_TEXTO["anio_servicio"]: "2024-2025",
            campos.CABECERA_NOMBRAMIENTOS["siervo_ministerial"]: campos.MARCADA,
            campos.campo_fila("participo", 9): campos.MARCADA,
            campos.campo_fila("precursor_auxiliar", 9): campos.MARCADA,
            campos.campo_fila("horas", 9): "15",
        },
    )


def _decision_total(propuesta, publicador_id=None):
    return importacion.Decision(
        propuesta=propuesta,
        publicador_id=publicador_id if publicador_id is not None else propuesta.publicador_id,
        aceptar_campos={d.campo for d in propuesta.diferencias},
        aceptar_nombramientos=list(propuesta.nombramientos),
        aceptar_meses={fila.mes for fila in propuesta.datos.meses},
    )


def test_analizar_no_escribe_nada_en_la_base(sesion, tarjeta_mauricio):
    importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert publicadores.listar(sesion) == []


def test_analizar_encuentra_al_publicador_existente(sesion, tarjeta_mauricio):
    existente = publicadores.crear(sesion, "MAURICIO ANDRÉS ROJAS VEGA")

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.publicador_id == existente.id


def test_analizar_propone_crear_si_no_hay_coincidencia(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.publicador_id is None
    assert propuesta.datos.nombre == "Mauricio Andrés Rojas Vega"


def test_diferencias_solo_lista_los_campos_que_cambian(sesion, tarjeta_mauricio):
    publicadores.crear(
        sesion,
        "Mauricio Andrés Rojas Vega",
        sexo="H",
        fecha_bautismo=date(2002, 6, 7),
    )

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    campos_distintos = {d.campo for d in propuesta.diferencias}
    assert "fecha_nacimiento" in campos_distintos
    assert "sexo" not in campos_distintos
    assert "fecha_bautismo" not in campos_distintos


def test_propone_el_nombramiento_desde_el_inicio_del_anio_de_servicio(
    sesion, tarjeta_mauricio
):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.nombramientos == [
        importacion.NombramientoPropuesto("siervo_ministerial", date(2024, 9, 1))
    ]


def test_no_propone_un_nombramiento_que_ya_existe(sesion, tarjeta_mauricio):
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    nombramientos.crear(sesion, mauricio.id, "siervo_ministerial", date(2024, 7, 1))

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.nombramientos == []


def test_sin_anio_legible_la_propuesta_no_trae_meses_ni_nombramientos(
    sesion, tarjeta_mauricio_sin_anio
):
    """Diseño: año de servicio vacío o no numérico se pide en la pantalla de
    revisión. Sin `anio_servicio_manual`, analizar no debe inventar nada."""
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio_sin_anio)

    assert propuesta.datos.anio_servicio is None
    assert propuesta.datos.anio_servicio_crudo == "2024-2025"
    assert propuesta.nombramientos == []
    assert propuesta.meses_en_conflicto == []


def test_anio_servicio_manual_completa_la_propuesta(sesion, tarjeta_mauricio_sin_anio):
    """Con el año que el usuario escribió a mano, la propuesta debe quedar
    igual que si la tarjeta lo hubiera traído: mismos nombramientos
    propuestos y mismo mes en conflicto."""
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=mauricio.id, horas=99)]
    )
    nombramientos.crear(sesion, mauricio.id, "precursor_regular", date(2020, 1, 1))

    propuesta = importacion.analizar(
        sesion, "mauricio.pdf", tarjeta_mauricio_sin_anio, anio_servicio_manual=2025
    )

    assert propuesta.datos.anio_servicio == 2025
    assert propuesta.nombramientos == [
        importacion.NombramientoPropuesto("siervo_ministerial", date(2024, 9, 1))
    ]
    assert propuesta.meses_en_conflicto == [9]


def test_anio_servicio_manual_no_pisa_el_que_trae_la_tarjeta(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(
        sesion, "mauricio.pdf", tarjeta_mauricio, anio_servicio_manual=1999
    )

    assert propuesta.datos.anio_servicio == 2025


def test_marca_los_meses_que_pisarian_un_valor_distinto(sesion, tarjeta_mauricio):
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=mauricio.id, horas=99)]
    )

    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert propuesta.meses_en_conflicto == [9]


def test_avisa_si_el_archivo_ya_se_importo(sesion, tarjeta_mauricio):
    primera = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(primera), lote="L1", ahora=AHORA)

    segunda = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    assert segunda.ya_importado == AHORA


def test_aplicar_crea_publicador_nombramientos_y_registros(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)

    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    mauricio = publicadores.buscar_por_nombre(sesion, "Mauricio Andrés Rojas Vega")
    assert mauricio is not None
    assert mauricio.fecha_bautismo == date(2002, 6, 7)
    assert nombramientos.tipos_en_anio(sesion, mauricio.id, 2025) == {"siervo_ministerial"}
    del_anio = registros.registros_del_anio(sesion, mauricio.id, 2025)
    assert del_anio[9].horas == 15
    assert del_anio[9].precursor_auxiliar is True


def test_aplicar_respeta_los_campos_no_aceptados(sesion, tarjeta_mauricio):
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    decision = importacion.Decision(
        propuesta=propuesta,
        publicador_id=mauricio.id,
        aceptar_campos={"fecha_bautismo"},
        aceptar_nombramientos=[],
        aceptar_meses=set(),
    )

    importacion.aplicar(sesion, decision, lote="L1", ahora=AHORA)

    actualizado = publicadores.obtener(sesion, mauricio.id)
    assert actualizado.fecha_bautismo == date(2002, 6, 7)
    assert actualizado.fecha_nacimiento is None


def test_aplicar_solo_escribe_los_meses_aceptados(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    decision = importacion.Decision(
        propuesta=propuesta,
        publicador_id=None,
        aceptar_campos=set(),
        aceptar_nombramientos=[],
        aceptar_meses={10},
    )

    importacion.aplicar(sesion, decision, lote="L1", ahora=AHORA)

    mauricio = publicadores.buscar_por_nombre(sesion, "Mauricio Andrés Rojas Vega")
    assert registros.registros_del_anio(sesion, mauricio.id, 2025).keys() == {10}


def test_deshacer_borra_el_publicador_creado_por_el_lote(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    deshechos = importacion.deshacer(sesion, "L1")

    assert deshechos == 1
    assert publicadores.listar(sesion) == []


def test_deshacer_devuelve_los_registros_a_su_valor_anterior(sesion, tarjeta_mauricio):
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    nombramientos.crear(sesion, mauricio.id, "precursor_regular", date(2020, 1, 1))
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=mauricio.id, horas=99)]
    )
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta, mauricio.id), lote="L1", ahora=AHORA)
    assert registros.registros_del_anio(sesion, mauricio.id, 2025)[9].horas == 15

    importacion.deshacer(sesion, "L1")

    assert publicadores.obtener(sesion, mauricio.id) is not None
    assert registros.registros_del_anio(sesion, mauricio.id, 2025)[9].horas == 99


def test_deshacer_devuelve_al_publicador_existente_sus_campos_anteriores(
    sesion, tarjeta_mauricio
):
    mauricio = publicadores.crear(
        sesion,
        "Mauricio Andrés Rojas Vega",
        fecha_bautismo=date(2000, 1, 1),
    )
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)
    assert publicadores.obtener(sesion, mauricio.id).fecha_bautismo == date(2002, 6, 7)

    importacion.deshacer(sesion, "L1")

    assert publicadores.obtener(sesion, mauricio.id).fecha_bautismo == date(2000, 1, 1)


def test_deshacer_restaura_el_valor_original_no_el_intermedio(
    sesion, tarjeta_mauricio, tarjeta_mauricio_horas_20
):
    mauricio = publicadores.crear(sesion, "Mauricio Andrés Rojas Vega")
    nombramientos.crear(sesion, mauricio.id, "precursor_regular", date(2020, 1, 1))
    registros.guardar_mes(
        sesion, 2024, 9, [registros.EntradaMes(publicador_id=mauricio.id, horas=99)]
    )

    primera = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(
        sesion, _decision_total(primera, mauricio.id), lote="L1", ahora=AHORA
    )
    assert registros.registros_del_anio(sesion, mauricio.id, 2025)[9].horas == 15

    segunda = importacion.analizar(sesion, "mauricio2.pdf", tarjeta_mauricio_horas_20)
    importacion.aplicar(
        sesion, _decision_total(segunda, mauricio.id), lote="L1", ahora=AHORA
    )
    assert registros.registros_del_anio(sesion, mauricio.id, 2025)[9].horas == 20

    importacion.deshacer(sesion, "L1")

    assert registros.registros_del_anio(sesion, mauricio.id, 2025)[9].horas == 99


def test_deshacer_dos_veces_no_hace_nada_la_segunda(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    importacion.deshacer(sesion, "L1")

    assert importacion.deshacer(sesion, "L1") == 0


def test_historial_agrupa_por_lote(sesion, tarjeta_mauricio):
    propuesta = importacion.analizar(sesion, "mauricio.pdf", tarjeta_mauricio)
    importacion.aplicar(sesion, _decision_total(propuesta), lote="L1", ahora=AHORA)

    assert importacion.historial(sesion) == [("L1", AHORA, 1)]


def test_guardar_y_leer_un_lote_conserva_nombre_y_contenido(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    lote = importacion.guardar_lote([("a.pdf", b"uno"), ("b.pdf", b"dos")])

    assert importacion.archivos_del_lote(lote) == [("a.pdf", b"uno"), ("b.pdf", b"dos")]


def test_archivos_del_lote_de_un_lote_inexistente_esta_vacio(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    assert importacion.archivos_del_lote("0" * 12) == []


def test_archivos_del_lote_rechaza_un_identificador_con_forma_invalida(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    with pytest.raises(importacion.LoteInvalido):
        importacion.archivos_del_lote("..")


def test_borrar_lote_con_travesia_de_directorios_no_borra_nada(tmp_path, monkeypatch):
    # Es el caso que de verdad importa: sin la validación de la forma del
    # identificador, esto habría hecho rmtree sobre todo `data/` (la base,
    # la plantilla y las tarjetas subidas), porque ".." resuelve al propio
    # directorio de datos.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    centinela = tmp_path / "centinela.txt"
    centinela.write_text("no tocar")

    with pytest.raises(importacion.LoteInvalido):
        importacion.borrar_lote("..")

    assert centinela.exists()


def test_purgar_lotes_viejos_borra_los_vencidos_y_deja_los_recientes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    viejo = importacion.guardar_lote([("a.pdf", b"uno")])
    reciente = importacion.guardar_lote([("b.pdf", b"dos")])

    directorio_viejo = tmp_path / "subidas" / viejo
    vencido = time.time() - (importacion.DIAS_RETENCION_LOTES + 1) * 86400
    os.utime(directorio_viejo, (vencido, vencido))

    borrados = importacion.purgar_lotes_viejos()

    assert borrados == 1
    assert not directorio_viejo.exists()
    assert (tmp_path / "subidas" / reciente).exists()
