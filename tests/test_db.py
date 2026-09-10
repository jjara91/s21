import shutil
from datetime import date

from sqlalchemy import text
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


def test_una_migracion_que_falla_a_mitad_no_deja_ddl_a_medias(tmp_path, monkeypatch):
    """Regresión: pysqlite solo abre transacción implícita antes de un DML, así
    que un CREATE TABLE emitido sin transacción abierta quedaba confirmado en
    autocommit aunque el resto del script fallara después. Una migración 002
    con una primera sentencia válida y una segunda rota no debe dejar ni la
    tabla creada ni la versión avanzada; y una vez corregido el script, debe
    poder aplicarse sin necesitar reparar la base a mano.
    """
    import sqlalchemy.exc
    import pytest

    migraciones_tmp = tmp_path / "migrations"
    migraciones_tmp.mkdir()
    shutil.copy(
        db.DIRECTORIO_MIGRACIONES / "001_inicial.sql",
        migraciones_tmp / "001_inicial.sql",
    )
    monkeypatch.setattr(db, "DIRECTORIO_MIGRACIONES", migraciones_tmp)

    engine = db.crear_engine(tmp_path / "s21.db")
    assert db.aplicar_migraciones(engine) == 1

    # Solo ahora aparece la migración 002, rota, para que la primera llamada
    # (que deja la versión en 1) no la vea.
    script_002 = migraciones_tmp / "002_rota.sql"
    script_002.write_text(
        "CREATE TABLE nueva_tabla (id INTEGER PRIMARY KEY);\n"
        "ESTO NO ES SQL VALIDO;\n",
        encoding="utf-8",
    )

    with pytest.raises(sqlalchemy.exc.OperationalError):
        db.aplicar_migraciones(engine)

    with engine.connect() as conexion:
        tabla = conexion.execute(
            text("SELECT name FROM sqlite_master WHERE name = 'nueva_tabla'")
        ).first()
        assert tabla is None, "el CREATE TABLE de la migración rota no debe persistir"

        version = conexion.execute(text("SELECT version FROM schema_version")).scalar()
        assert version == 1, "schema_version no debe avanzar si la migración falló"

    script_002.write_text(
        "CREATE TABLE nueva_tabla (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    assert db.aplicar_migraciones(engine) == 2

    with engine.connect() as conexion:
        tabla = conexion.execute(
            text("SELECT name FROM sqlite_master WHERE name = 'nueva_tabla'")
        ).first()
        assert tabla is not None
