"""Bucle ReAct: Pensamiento → Acción → Observación, hasta responder o rendirse.

Los guardrails viven aquí, no en el prompt:

  1. Tope de iteraciones.
  2. Detección de bucles (misma acción con los mismos argumentos).
  3. Terminación explícita: solo 'Respuesta:' cierra el turno.
  4. Confirmación humana antes de cualquier herramienta de escritura.
  5. Una acción mal formada es una observación, no una excepción: el agente
     tiene que poder corregirse.
"""
from __future__ import annotations

import ast
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Callable

from .herramientas import ErrorHerramienta, Herramienta, catalogo

SISTEMA = """Eres un asistente del mantenimiento del coche del usuario. Respondes
consultando su historial de servicios, su kilometraje y el manual del fabricante.

Trabajas en ciclos. En cada turno escribes EXACTAMENTE uno de estos dos bloques:

Pensamiento: <una frase sobre qué te falta averiguar>
Acción: nombre_herramienta(arg="valor", otro=3)

...o bien, cuando ya tengas con qué responder:

Pensamiento: <por qué ya puedes responder>
Respuesta: <la respuesta para el usuario>

Herramientas disponibles:
{catalogo}

Reglas:
- Una sola acción por turno. Nunca escribas la Observación: te la doy yo.
- No inventes datos. Si el manual o el historial no lo dicen, responde que no lo sabes.
- Para saber si un servicio ya toca necesitas tres cosas: el kilometraje de hoy,
  cuándo se hizo por última vez, y el intervalo que marca el manual.
- Las herramientas marcadas como ESCRITURA le piden confirmación al usuario antes
  de ejecutarse. Propónlas igual cuando correspondan.
- Cuando ya tengas la información suficiente, responde. No sigas consultando.
"""

PATRON_ACCION = re.compile(r"^\s*Acci[oó]n:\s*(\w+)\s*\((.*)\)\s*$", re.M | re.S)
PATRON_RESPUESTA = re.compile(r"^\s*Respuesta:\s*(.+)", re.M | re.S)
PATRON_PENSAMIENTO = re.compile(r"^\s*Pensamiento:\s*(.+?)$", re.M)


@dataclass
class Paso:
    n: int
    pensamiento: str = ""
    accion: str = ""
    argumentos: dict = field(default_factory=dict)
    observacion: str = ""
    ms: int = 0


@dataclass
class Resultado:
    respuesta: str
    pasos: list[Paso]
    motivo_fin: str  # respondio | tope_iteraciones | bucle | cancelado

    @property
    def herramientas_usadas(self) -> list[str]:
        return [p.accion for p in self.pasos if p.accion]

    def como_json(self) -> str:
        return json.dumps(
            {
                "respuesta": self.respuesta,
                "motivo_fin": self.motivo_fin,
                "pasos": [asdict(p) for p in self.pasos],
            },
            ensure_ascii=False,
            indent=2,
        )


def _parsear_argumentos(crudo: str) -> dict:
    """Lee los argumentos de la llamada sin evaluar código arbitrario."""
    crudo = crudo.strip()
    if not crudo:
        return {}
    try:
        arbol = ast.parse(f"f({crudo})", mode="eval")
        llamada = arbol.body
        if llamada.args:
            raise ErrorHerramienta("usa argumentos con nombre, por ejemplo id=3")
        return {kw.arg: ast.literal_eval(kw.value) for kw in llamada.keywords}
    except ErrorHerramienta:
        raise
    except Exception as exc:
        raise ErrorHerramienta(f"no pude leer los argumentos ({exc})") from exc


def _aprobar_siempre(h: Herramienta, args: dict) -> bool:
    return True


def ejecutar(
    pregunta: str,
    modelo,
    herramientas: dict[str, Herramienta],
    *,
    max_iteraciones: int | None = None,
    confirmar: Callable[[Herramienta, dict], bool] = _aprobar_siempre,
    al_paso: Callable[[Paso], None] | None = None,
) -> Resultado:
    tope = max_iteraciones or int(os.getenv("MAX_ITERACIONES", "8"))
    sistema = SISTEMA.format(catalogo=catalogo(herramientas))
    mensajes = [{"role": "user", "content": pregunta}]
    pasos: list[Paso] = []
    vistas: set[tuple[str, str]] = set()

    for n in range(1, tope + 1):
        t0 = time.perf_counter()
        salida = modelo.completar(sistema, mensajes)
        paso = Paso(n=n, ms=int((time.perf_counter() - t0) * 1000))

        if m := PATRON_PENSAMIENTO.search(salida):
            paso.pensamiento = m.group(1).strip()

        # ¿Terminó?
        if m := PATRON_RESPUESTA.search(salida):
            pasos.append(paso)
            if al_paso:
                al_paso(paso)
            return Resultado(m.group(1).strip(), pasos, "respondio")

        m = PATRON_ACCION.search(salida)
        if not m:
            paso.observacion = (
                "No entendí tu turno. Escribe 'Acción: herramienta(args)' "
                "o 'Respuesta: ...'."
            )
            pasos.append(paso)
            if al_paso:
                al_paso(paso)
            mensajes += [
                {"role": "assistant", "content": salida},
                {"role": "user", "content": f"Observación: {paso.observacion}"},
            ]
            continue

        nombre, crudo = m.group(1), m.group(2)
        paso.accion = nombre

        # Guardrail 2: bucle.
        huella = (nombre, crudo.strip())
        if huella in vistas:
            paso.observacion = "Ya ejecutaste esta acción con estos argumentos."
            pasos.append(paso)
            if al_paso:
                al_paso(paso)
            return Resultado(
                "Me quedé repitiendo la misma consulta sin avanzar. "
                "Replantea la pregunta, por favor.",
                pasos,
                "bucle",
            )
        vistas.add(huella)

        try:
            args = _parsear_argumentos(crudo)
            paso.argumentos = args
            herramienta = herramientas.get(nombre)
            if herramienta is None:
                raise ErrorHerramienta(
                    f"no existe la herramienta '{nombre}'. "
                    f"Disponibles: {', '.join(herramientas)}"
                )
            # Guardrail 4: confirmación humana antes de escribir.
            if herramienta.escritura and not confirmar(herramienta, args):
                pasos.append(paso)
                if al_paso:
                    al_paso(paso)
                return Resultado(
                    "No ejecuté el cambio porque no lo confirmaste.", pasos, "cancelado"
                )
            paso.observacion = herramienta.fn(**args)
        except ErrorHerramienta as exc:
            paso.observacion = f"Error: {exc}"
        except TypeError as exc:
            paso.observacion = f"Error: argumentos incorrectos ({exc})"

        pasos.append(paso)
        if al_paso:
            al_paso(paso)
        mensajes += [
            {"role": "assistant", "content": salida},
            {"role": "user", "content": f"Observación: {paso.observacion}"},
        ]

    # Guardrail 1: se acabaron las iteraciones.
    return Resultado(
        "Llegué al límite de pasos sin poder responder con certeza.",
        pasos,
        "tope_iteraciones",
    )
