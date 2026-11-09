"""Las cinco herramientas del agente del coche.

Tres de lectura y dos de escritura. Las de escritura NO se ejecutan solas: el
bucle las frena, muestra qué va a cambiar y espera confirmación humana.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Callable


class ErrorHerramienta(Exception):
    """La herramienta no pudo completarse; el agente debe verlo como observación."""


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict[str, str]
    escritura: bool
    fn: Callable[..., str]

    def firma(self) -> str:
        args = ", ".join(f"{k}: {v}" for k, v in self.parametros.items())
        marca = "  [ESCRITURA — requiere confirmación]" if self.escritura else ""
        return f"{self.nombre}({args}) — {self.descripcion}{marca}"


# --------------------------------------------------------------------------- #
# Lectura
# --------------------------------------------------------------------------- #

def kilometraje_actual(con: sqlite3.Connection) -> str:
    fila = con.execute("SELECT km, fecha FROM odometro WHERE id = 1").fetchone()
    if not fila:
        return "No hay kilometraje registrado."
    return f"{fila['km']:,} km, registrado el {fila['fecha']}."


def historial_servicios(con: sqlite3.Connection, tipo: str = "", limite: int = 20) -> str:
    """Historial de servicios, del más reciente al más viejo."""
    sql = "SELECT id, tipo, km, fecha, taller, costo, notas FROM servicios"
    args: list = []
    if tipo:
        sql += " WHERE tipo LIKE ?"
        args.append(f"%{tipo}%")
    sql += " ORDER BY km DESC, id DESC LIMIT ?"
    args.append(max(1, min(limite, 100)))

    filas = con.execute(sql, args).fetchall()
    if not filas:
        return f"Sin servicios registrados{' de ese tipo' if tipo else ''}."
    lineas = []
    for f in filas:
        costo = f" · ${f['costo']:,}" if f["costo"] is not None else ""
        taller = f" · {f['taller']}" if f["taller"] else ""
        notas = f" · {f['notas']}" if f["notas"] else ""
        lineas.append(
            f"#{f['id']} {f['tipo']} — {f['km']:,} km · {f['fecha']}{taller}{costo}{notas}"
        )
    return "\n".join(lineas)


def leer_manual(con: sqlite3.Connection, consulta: str) -> str:
    """Busca en el manual de mantenimiento del fabricante (SQLite FTS5)."""
    if not consulta.strip():
        raise ErrorHerramienta("la consulta no puede ir vacía")
    terminos = " OR ".join(f'"{t}"' for t in consulta.split() if t.strip())
    filas = con.execute(
        "SELECT archivo, seccion, contenido FROM manual "
        "WHERE manual MATCH ? ORDER BY rank LIMIT 3",
        (terminos,),
    ).fetchall()
    if not filas:
        return "Sin resultados en el manual."
    return "\n\n".join(
        f"[{f['archivo']} › {f['seccion']}]\n{f['contenido']}" for f in filas
    )


# --------------------------------------------------------------------------- #
# Escritura
# --------------------------------------------------------------------------- #

def registrar_servicio(
    con: sqlite3.Connection,
    tipo: str,
    km: int,
    fecha: str = "",
    taller: str = "",
    costo: int | None = None,
    notas: str = "",
) -> str:
    if not isinstance(km, int) or km < 0:
        raise ErrorHerramienta("km debe ser un entero positivo")
    fecha = fecha or date.today().isoformat()
    cur = con.execute(
        "INSERT INTO servicios (tipo, km, fecha, taller, costo, notas) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tipo, km, fecha, taller or None, costo, notas or None),
    )
    # El odómetro nunca va hacia atrás.
    actual = con.execute("SELECT km FROM odometro WHERE id = 1").fetchone()
    aviso = ""
    if actual is None or km > actual["km"]:
        con.execute(
            "INSERT OR REPLACE INTO odometro (id, km, fecha) VALUES (1, ?, ?)", (km, fecha)
        )
        aviso = f" El odómetro queda en {km:,} km."
    con.commit()
    return f"Registrado: {tipo} a los {km:,} km el {fecha} (#{cur.lastrowid}).{aviso}"


def actualizar_kilometraje(con: sqlite3.Connection, km: int) -> str:
    if not isinstance(km, int) or km < 0:
        raise ErrorHerramienta("km debe ser un entero positivo")
    fila = con.execute("SELECT km FROM odometro WHERE id = 1").fetchone()
    if fila and km < fila["km"]:
        raise ErrorHerramienta(
            f"el odómetro marca {fila['km']:,} km y no puede ir hacia atrás a {km:,}"
        )
    hoy = date.today().isoformat()
    con.execute("INSERT OR REPLACE INTO odometro (id, km, fecha) VALUES (1, ?, ?)", (km, hoy))
    con.commit()
    anterior = f" (antes {fila['km']:,})" if fila else ""
    return f"Odómetro actualizado a {km:,} km{anterior}."


# --------------------------------------------------------------------------- #

def registro(con: sqlite3.Connection) -> dict[str, Herramienta]:
    defs = [
        Herramienta(
            "kilometraje_actual",
            "Devuelve el kilometraje registrado hoy.",
            {},
            False,
            lambda **kw: kilometraje_actual(con, **kw),
        ),
        Herramienta(
            "historial_servicios",
            "Servicios ya hechos, del más reciente al más viejo. Filtra por tipo si lo pasas.",
            {"tipo": "str opcional, p.ej. 'aceite'", "limite": "int opcional"},
            False,
            lambda **kw: historial_servicios(con, **kw),
        ),
        Herramienta(
            "leer_manual",
            "Busca intervalos y recomendaciones en el manual del fabricante.",
            {"consulta": "str"},
            False,
            lambda **kw: leer_manual(con, **kw),
        ),
        Herramienta(
            "registrar_servicio",
            "Apunta un servicio recién hecho.",
            {
                "tipo": "str",
                "km": "int",
                "fecha": "AAAA-MM-DD, opcional",
                "taller": "str opcional",
                "costo": "int opcional",
                "notas": "str opcional",
            },
            True,
            lambda **kw: registrar_servicio(con, **kw),
        ),
        Herramienta(
            "actualizar_kilometraje",
            "Pone al día el odómetro.",
            {"km": "int"},
            True,
            lambda **kw: actualizar_kilometraje(con, **kw),
        ),
    ]
    return {h.nombre: h for h in defs}


def catalogo(herramientas: dict[str, Herramienta]) -> str:
    return "\n".join(f"- {h.firma()}" for h in herramientas.values())
