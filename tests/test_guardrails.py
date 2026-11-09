"""Pruebas de los guardrails del bucle ReAct y de las reglas del dominio.

    pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import inicializar  # noqa: E402
from src.herramientas import ErrorHerramienta, registro  # noqa: E402
from src.llm import Stub  # noqa: E402
from src.react import ejecutar  # noqa: E402


@pytest.fixture
def hs():
    return registro(inicializar(":memory:"))


# --- guardrails del bucle ----------------------------------------------------

def test_responde_y_termina(hs):
    modelo = Stub([
        "Pensamiento: veo el odómetro.\nAcción: kilometraje_actual()",
        "Pensamiento: ya está.\nRespuesta: Trae 68,400 km.",
    ])
    r = ejecutar("¿cuántos km trae?", modelo, hs)
    assert r.motivo_fin == "respondio"
    assert r.herramientas_usadas == ["kilometraje_actual"]


def test_corta_el_bucle(hs):
    modelo = Stub(['Pensamiento: otra vez\nAcción: historial_servicios(tipo="aceite")'] * 5)
    r = ejecutar("x", modelo, hs)
    assert r.motivo_fin == "bucle"


def test_respeta_el_tope(hs):
    modelo = Stub([f'Pensamiento: {i}\nAcción: leer_manual(consulta="t{i}")' for i in range(20)])
    r = ejecutar("x", modelo, hs, max_iteraciones=3)
    assert r.motivo_fin == "tope_iteraciones"
    assert len(r.pasos) == 3


def test_escritura_requiere_confirmacion(hs):
    modelo = Stub(['Pensamiento: apunto.\nAcción: registrar_servicio(tipo="aceite", km=68400)'])
    r = ejecutar("apunta el aceite", modelo, hs, confirmar=lambda h, a: False)
    assert r.motivo_fin == "cancelado"
    assert "68,400" not in hs["historial_servicios"].fn(tipo="aceite")


def test_escritura_confirmada_si_se_ejecuta(hs):
    modelo = Stub([
        'Pensamiento: apunto.\nAcción: registrar_servicio(tipo="cambio de aceite", km=68400)',
        "Pensamiento: listo.\nRespuesta: Registrado.",
    ])
    r = ejecutar("apunta el aceite", modelo, hs, confirmar=lambda h, a: True)
    assert r.motivo_fin == "respondio"
    assert "68,400" in hs["historial_servicios"].fn(tipo="aceite")


def test_herramienta_inexistente_es_observacion(hs):
    modelo = Stub([
        "Pensamiento: pruebo.\nAcción: borrar_historial()",
        "Pensamiento: no existe.\nAcción: kilometraje_actual()",
        "Pensamiento: listo.\nRespuesta: 68,400 km.",
    ])
    r = ejecutar("x", modelo, hs)
    assert "no existe la herramienta" in r.pasos[0].observacion
    assert r.motivo_fin == "respondio"


# --- reglas del dominio ------------------------------------------------------

def test_odometro_no_va_hacia_atras(hs):
    with pytest.raises(ErrorHerramienta, match="hacia atrás"):
        hs["actualizar_kilometraje"].fn(km=50000)


def test_registrar_servicio_adelanta_el_odometro(hs):
    hs["registrar_servicio"].fn(tipo="cambio de aceite", km=70000)
    assert "70,000" in hs["kilometraje_actual"].fn()


def test_registrar_servicio_viejo_no_mueve_el_odometro(hs):
    hs["registrar_servicio"].fn(tipo="balatas traseras", km=62000, fecha="2026-09-01")
    assert "68,400" in hs["kilometraje_actual"].fn()


def test_km_invalido_falla_claro(hs):
    with pytest.raises(ErrorHerramienta, match="entero positivo"):
        hs["actualizar_kilometraje"].fn(km=-5)


def test_manual_sin_resultado_no_inventa(hs):
    assert "Sin resultados" in hs["leer_manual"].fn(consulta="turbocompresor")


def test_servicio_inexistente_se_reporta(hs):
    assert "Sin servicios" in hs["historial_servicios"].fn(tipo="anticongelante")
