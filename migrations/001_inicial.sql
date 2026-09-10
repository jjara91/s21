CREATE TABLE grupo (
    id                  INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL,
    superintendente_id  INTEGER REFERENCES publicador(id) ON DELETE SET NULL
);

CREATE TABLE publicador (
    id                  INTEGER PRIMARY KEY,
    nombre_completo     TEXT NOT NULL,
    nombre_normalizado  TEXT NOT NULL,
    fecha_nacimiento    DATE,
    fecha_bautismo      DATE,
    sexo                TEXT CHECK (sexo IN ('H', 'M')),
    esperanza           TEXT CHECK (esperanza IN ('otras_ovejas', 'ungido')),
    grupo_id            INTEGER REFERENCES grupo(id) ON DELETE SET NULL,
    fecha_baja          DATE,
    motivo_baja         TEXT
);

CREATE INDEX ix_publicador_nombre_normalizado ON publicador (nombre_normalizado);

CREATE TABLE nombramiento (
    id             INTEGER PRIMARY KEY,
    publicador_id  INTEGER NOT NULL REFERENCES publicador(id) ON DELETE CASCADE,
    tipo           TEXT NOT NULL CHECK (tipo IN (
                       'anciano', 'siervo_ministerial', 'precursor_regular',
                       'precursor_especial', 'misionero_campo')),
    desde          DATE NOT NULL,
    hasta          DATE
);

CREATE INDEX ix_nombramiento_publicador ON nombramiento (publicador_id);

CREATE TABLE registromensual (
    id                  INTEGER PRIMARY KEY,
    publicador_id       INTEGER NOT NULL REFERENCES publicador(id) ON DELETE CASCADE,
    anio                INTEGER NOT NULL,
    mes                 INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    participo           BOOLEAN NOT NULL DEFAULT 0,
    cursos_biblicos     INTEGER,
    precursor_auxiliar  BOOLEAN NOT NULL DEFAULT 0,
    horas               INTEGER,
    notas               TEXT,
    UNIQUE (publicador_id, anio, mes)
);

CREATE INDEX ix_registromensual_periodo ON registromensual (anio, mes);

CREATE TABLE importacion (
    id             INTEGER PRIMARY KEY,
    archivo        TEXT NOT NULL,
    sha256         TEXT NOT NULL,
    fecha          DATETIME NOT NULL,
    lote           TEXT NOT NULL,
    publicador_id  INTEGER REFERENCES publicador(id) ON DELETE SET NULL,
    anio_servicio  INTEGER,
    accion         TEXT NOT NULL CHECK (accion IN ('creado', 'actualizado', 'descartado')),
    estado_previo  TEXT,
    deshecho       BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX ix_importacion_sha256 ON importacion (sha256);
CREATE INDEX ix_importacion_lote ON importacion (lote);
