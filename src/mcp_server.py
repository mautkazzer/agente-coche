"""Servidor MCP que expone las mismas cinco herramientas del agente.

Sirve para dos cosas:
  1. El bucle ReAct de este repo las consume.
  2. Cualquier cliente MCP (Claude Desktop, Claude Code) también puede usarlas,
     lo que demuestra que las herramientas viven fuera de la aplicación.

Arranque:  python -m src.mcp_server
"""
from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .db import inicializar
from .herramientas import ErrorHerramienta, registro

con = inicializar()
HERRAMIENTAS = registro(con)
servidor = Server("agente-coche")

ESQUEMAS = {
    "kilometraje_actual": {"type": "object", "properties": {}},
    "historial_servicios": {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "description": "Filtra por tipo, p. ej. 'aceite'."},
            "limite": {"type": "integer", "description": "Máximo de registros."},
        },
    },
    "leer_manual": {
        "type": "object",
        "properties": {"consulta": {"type": "string", "description": "Términos a buscar."}},
        "required": ["consulta"],
    },
    "registrar_servicio": {
        "type": "object",
        "properties": {
            "tipo": {"type": "string"},
            "km": {"type": "integer"},
            "fecha": {"type": "string", "description": "AAAA-MM-DD; hoy si se omite."},
            "taller": {"type": "string"},
            "costo": {"type": "integer", "description": "En pesos."},
            "notas": {"type": "string"},
        },
        "required": ["tipo", "km"],
    },
    "actualizar_kilometraje": {
        "type": "object",
        "properties": {"km": {"type": "integer"}},
        "required": ["km"],
    },
}


@servidor.list_tools()
async def listar() -> list[Tool]:
    return [
        Tool(
            name=h.nombre,
            description=h.descripcion
            + (" Modifica datos." if h.escritura else " Solo lectura."),
            inputSchema=ESQUEMAS[h.nombre],
        )
        for h in HERRAMIENTAS.values()
    ]


@servidor.call_tool()
async def invocar(nombre: str, argumentos: dict) -> list[TextContent]:
    herramienta = HERRAMIENTAS.get(nombre)
    if herramienta is None:
        return [TextContent(type="text", text=f"No existe la herramienta '{nombre}'.")]
    try:
        salida = herramienta.fn(**(argumentos or {}))
    except (ErrorHerramienta, TypeError) as exc:
        salida = f"Error: {exc}"
    return [TextContent(type="text", text=salida)]


async def principal() -> None:
    async with stdio_server() as (lectura, escritura):
        await servidor.run(lectura, escritura, servidor.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(principal())
