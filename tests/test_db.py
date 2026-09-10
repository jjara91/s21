from datetime import date

from sqlmodel import Session, select

from app import db, models


def test_aplicar_migraciones_deja_la_version_en_uno(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    assert db.aplicar_migraciones(engine) == 1


def test_aplicar_migraciones_es_idempotente(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)
    assert db.aplicar_migraciones(engine) == 1


def test_se_puede_guardar_y_leer_un_publicador_con_registros(tmp_path):
    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        grupo = models.Grupo(nombre="Centro")
        sesion.add(grupo)
        sesion.commit()
        sesion.refresh(grupo)

        publicador = models.Publicador(
            nombre_completo="Rojas Vega Mauricio",
            nombre_normalizado="rojas vega mauricio",
            fecha_bautismo=date(2002, 6, 7),
            sexo="H",
            esperanza="otras_ovejas",
            grupo_id=grupo.id,
        )
        sesion.add(publicador)
        sesion.commit()
        sesion.refresh(publicador)

        sesion.add(
            models.Nombramiento(
                publicador_id=publicador.id,
                tipo="siervo_ministerial",
                desde=date(2025, 7, 1),
            )
        )
        sesion.add(
            models.RegistroMensual(
                publicador_id=publicador.id,
                anio=2025,
                mes=9,
                participo=True,
                precursor_auxiliar=True,
                horas=15,
            )
        )
        sesion.commit()

    with Session(engine) as sesion:
        leido = sesion.exec(select(models.Publicador)).one()
        assert leido.nombre_completo == "Rojas Vega Mauricio"
        registros = sesion.exec(select(models.RegistroMensual)).all()
        assert len(registros) == 1
        assert registros[0].horas == 15


def test_un_publicador_no_puede_tener_dos_registros_del_mismo_mes(tmp_path):
    import sqlalchemy.exc
    import pytest

    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        publicador = models.Publicador(
            nombre_completo="Perez Ana", nombre_normalizado="perez ana"
        )
        sesion.add(publicador)
        sesion.commit()
        sesion.refresh(publicador)

        sesion.add(
            models.RegistroMensual(publicador_id=publicador.id, anio=2025, mes=9)
        )
        sesion.commit()
        sesion.add(
            models.RegistroMensual(publicador_id=publicador.id, anio=2025, mes=9)
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            sesion.commit()


def test_las_claves_foraneas_estan_activas(tmp_path):
    import sqlalchemy.exc
    import pytest

    engine = db.crear_engine(tmp_path / "s21.db")
    db.aplicar_migraciones(engine)

    with Session(engine) as sesion:
        sesion.add(models.RegistroMensual(publicador_id=999, anio=2025, mes=9))
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            sesion.commit()
