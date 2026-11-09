"""Servidor MCP que expone las mismas cinco herramientas del agente.

Sirve para dos cosas:
  1. El bucle ReAct de este repo las consume.
  2. Cualquier cliente MCP (Claude Desktop, Claude Code) también puede usarlas,
     lo que demuestra que las herramientas viven fuera de la aplicación.

El esquema de cada herramienta sale de las anotaciones de tipo: el SDK las lee
y arma el JSON Schema solo, así que la firma de la función es la única fuente
de verdad.

Arranque:  python -m src.mcp_server
"""
from __future__ import annotations

import threading

from mcp.server.mcpserver import MCPServer

from .db import inicializar
from .herramientas import ErrorHerramienta, registro

con = inicializar()
HERRAMIENTAS = registro(con)

# El SDK atiende cada herramienta en un hilo de trabajo. La conexión se abre con
# check_same_thread=False y este lock serializa el acceso.
_candado = threading.Lock()

servidor = MCPServer(
    name="agente-coche",
    instructions=(
        "Mantenimiento del coche: historial de servicios, kilometraje y el manual "
        "del fabricante. Para saber si un servicio ya toca hacen falta tres cosas: "
        "el kilometraje de hoy, cuándo se hizo por última vez, y el intervalo del "
        "manual."
    ),
)


def _llamar(nombre: str, **kwargs) -> str:
    """Invoca la herramienta y convierte sus errores en texto para el cliente."""
    with _candado:
        try:
            return HERRAMIENTAS[nombre].fn(**kwargs)
        except (ErrorHerramienta, TypeError) as exc:
            return f"Error: {exc}"


@servidor.tool()
def kilometraje_actual() -> str:
    """Kilometraje registrado hoy. Solo lectura."""
    return _llamar("kilometraje_actual")


@servidor.tool()
def historial_servicios(tipo: str = "", limite: int = 20) -> str:
    """Servicios ya hechos, del más reciente al más viejo. Solo lectura.

    Args:
        tipo: filtra por tipo, por ejemplo 'aceite'. Vacío trae todos.
        limite: máximo de registros a devolver.
    """
    return _llamar("historial_servicios", tipo=tipo, limite=limite)


@servidor.tool()
def leer_manual(consulta: str) -> str:
    """Busca intervalos y recomendaciones en el manual del fabricante. Solo lectura.

    Args:
        consulta: términos a buscar, por ejemplo 'intervalo cambio de aceite'.
    """
    return _llamar("leer_manual", consulta=consulta)


@servidor.tool()
def registrar_servicio(
    tipo: str,
    km: int,
    fecha: str = "",
    taller: str = "",
    costo: int | None = None,
    notas: str = "",
) -> str:
    """Apunta un servicio recién hecho. MODIFICA DATOS.

    Args:
        tipo: qué se hizo, por ejemplo 'cambio de aceite'.
        km: kilometraje al que se hizo.
        fecha: AAAA-MM-DD. Hoy si se omite.
        taller: dónde se hizo.
        costo: en pesos, entero.
        notas: cualquier detalle extra.
    """
    return _llamar(
        "registrar_servicio",
        tipo=tipo,
        km=km,
        fecha=fecha,
        taller=taller,
        costo=costo,
        notas=notas,
    )


@servidor.tool()
def actualizar_kilometraje(km: int) -> str:
    """Pone al día el odómetro. No puede ir hacia atrás. MODIFICA DATOS.

    Args:
        km: kilometraje actual.
    """
    return _llamar("actualizar_kilometraje", km=km)


if __name__ == "__main__":
    servidor.run("stdio")
