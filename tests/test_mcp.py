"""El servidor MCP expone las herramientas y las ejecuta desde su hilo de trabajo.

Esta prueba existe por un error real: el SDK atiende cada herramienta en un hilo
distinto al que abrió la conexión SQLite, y eso tiraba `ProgrammingError` en
cuanto se llamaba cualquier herramienta desde un cliente MCP.

    pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ESPERADAS = {
    "kilometraje_actual",
    "historial_servicios",
    "leer_manual",
    "registrar_servicio",
    "actualizar_kilometraje",
}


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    # La base del servidor vive en el repo; se aísla para no ensuciarla al probar.
    import src.db as db

    db.RUTA_DB = tmp_path_factory.mktemp("mcp") / "prueba.db"
    import src.mcp_server as m

    return m.servidor


def texto(resultado) -> str:
    return resultado.content[0].text


@pytest.mark.anyio
async def test_expone_las_cinco(servidor):
    nombres = {t.name for t in await servidor.list_tools()}
    assert nombres == ESPERADAS


@pytest.mark.anyio
async def test_esquemas_marcan_lo_obligatorio(servidor):
    req = {t.name: set(t.input_schema.get("required", [])) for t in await servidor.list_tools()}
    assert req["leer_manual"] == {"consulta"}
    assert req["registrar_servicio"] == {"tipo", "km"}
    assert req["actualizar_kilometraje"] == {"km"}
    assert req["kilometraje_actual"] == set()


@pytest.mark.anyio
async def test_lectura_desde_el_hilo_del_sdk(servidor):
    """Si la conexión SQLite tuviera afinidad de hilo, esto fallaría."""
    assert "km" in texto(await servidor.call_tool("kilometraje_actual", {}))


@pytest.mark.anyio
async def test_escritura_desde_el_hilo_del_sdk(servidor):
    salida = texto(
        await servidor.call_tool("registrar_servicio", {"tipo": "filtro de cabina", "km": 68500})
    )
    assert "68,500" in salida
    assert "filtro de cabina" in texto(
        await servidor.call_tool("historial_servicios", {"tipo": "cabina"})
    )


@pytest.mark.anyio
async def test_error_de_dominio_llega_como_texto(servidor):
    """El cliente MCP debe ver el motivo, no una excepción."""
    salida = texto(await servidor.call_tool("actualizar_kilometraje", {"km": 10}))
    assert "hacia atrás" in salida


@pytest.mark.anyio
async def test_busqueda_sin_resultados(servidor):
    assert "Sin resultados" in texto(
        await servidor.call_tool("leer_manual", {"consulta": "turbocompresor"})
    )


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"
