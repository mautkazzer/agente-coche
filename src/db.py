"""Base de datos: historial de servicios del coche e índice del manual."""
from __future__ import annotations

import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB = RAIZ / "agente.db"
RUTA_MANUAL = RAIZ / "notas"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS servicios (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo     TEXT NOT NULL,
    km       INTEGER NOT NULL CHECK (km >= 0),
    fecha    TEXT NOT NULL,
    taller   TEXT,
    costo    INTEGER,              -- en pesos, entero
    notas    TEXT
);

CREATE TABLE IF NOT EXISTS odometro (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    km       INTEGER NOT NULL CHECK (km >= 0),
    fecha    TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS manual USING fts5(
    archivo, seccion, contenido, tokenize = 'unicode61 remove_diacritics 2'
);
"""


def conectar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    return con


def crear_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    con.commit()


def trocear_markdown(texto: str) -> list[tuple[str, str]]:
    trozos: list[tuple[str, str]] = []
    seccion, cuerpo = "(inicio)", []
    for linea in texto.splitlines():
        if linea.startswith("## "):
            if cuerpo:
                trozos.append((seccion, "\n".join(cuerpo).strip()))
            seccion, cuerpo = linea[3:].strip(), []
        else:
            cuerpo.append(linea)
    if cuerpo:
        trozos.append((seccion, "\n".join(cuerpo).strip()))
    return [(s, c) for s, c in trozos if c]


def indexar_manual(con: sqlite3.Connection, carpeta: Path = RUTA_MANUAL) -> int:
    con.execute("DELETE FROM manual")
    total = 0
    for archivo in sorted(carpeta.glob("*.md")):
        for seccion, contenido in trocear_markdown(archivo.read_text(encoding="utf-8")):
            con.execute(
                "INSERT INTO manual (archivo, seccion, contenido) VALUES (?, ?, ?)",
                (archivo.name, seccion, contenido),
            )
            total += 1
    con.commit()
    return total


SERVICIOS_EJEMPLO = [
    ("cambio de aceite", 45000, "2025-11-18", "Taller Reyes", 1450, "Aceite 5W-30 sintético"),
    ("rotación de llantas", 45000, "2025-11-18", "Taller Reyes", 300, None),
    ("balatas delanteras", 52000, "2026-03-07", "Taller Reyes", 2800, None),
    ("cambio de aceite", 55000, "2026-04-22", "Taller Reyes", 1500, "Aceite 5W-30 sintético"),
    ("filtro de aire", 55000, "2026-04-22", "Taller Reyes", 420, None),
    ("afinación menor", 60000, "2026-08-14", "Agencia", 4100, "Bujías y filtro de gasolina"),
    ("cambio de aceite", 60000, "2026-08-14", "Agencia", 1680, "Aceite 5W-30 sintético"),
]

KM_ACTUAL = (68400, "2026-11-09")


def sembrar(con: sqlite3.Connection) -> None:
    if con.execute("SELECT count(*) FROM servicios").fetchone()[0]:
        return
    for tipo, km, fecha, taller, costo, notas in SERVICIOS_EJEMPLO:
        con.execute(
            "INSERT INTO servicios (tipo, km, fecha, taller, costo, notas) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tipo, km, fecha, taller, costo, notas),
        )
    con.execute(
        "INSERT OR REPLACE INTO odometro (id, km, fecha) VALUES (1, ?, ?)", KM_ACTUAL
    )
    con.commit()


def inicializar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    con = conectar(ruta)
    crear_esquema(con)
    sembrar(con)
    indexar_manual(con)
    return con


if __name__ == "__main__":
    c = inicializar()
    s = c.execute("SELECT count(*) FROM servicios").fetchone()[0]
    m = c.execute("SELECT count(*) FROM manual").fetchone()[0]
    km = c.execute("SELECT km FROM odometro WHERE id = 1").fetchone()[0]
    print(f"Base lista en {RUTA_DB}: {s} servicios, {m} secciones del manual, {km:,} km.")
