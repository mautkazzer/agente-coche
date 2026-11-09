"""Interfaz de consola. Muestra el rastro ReAct y pide confirmación antes de escribir.

Uso:  python -m src.cli  "¿ya me toca cambio de aceite?"
      python -m src.cli            (modo conversación)
      python -m src.cli --traza ... (guarda el rastro en JSON)
"""
from __future__ import annotations

import sys

from .db import inicializar
from .herramientas import Herramienta, registro
from .llm import desde_entorno
from .react import Paso, ejecutar

GRIS, AZUL, VERDE, AMAR, FIN = "\033[90m", "\033[94m", "\033[92m", "\033[93m", "\033[0m"


def pintar(paso: Paso) -> None:
    if paso.pensamiento:
        print(f"{GRIS}  Pensamiento: {paso.pensamiento}{FIN}")
    if paso.accion:
        args = ", ".join(f"{k}={v!r}" for k, v in paso.argumentos.items())
        print(f"{AZUL}  Acción: {paso.accion}({args}){FIN}  {GRIS}{paso.ms} ms{FIN}")
    if paso.observacion:
        texto = paso.observacion
        if len(texto) > 300:
            texto = texto[:300] + "…"
        sangrado = texto.replace("\n", "\n    ")
        print(f"{GRIS}  Observación: {sangrado}{FIN}")


def pedir_confirmacion(h: Herramienta, args: dict) -> bool:
    args_txt = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"\n{AMAR}  ⚠ El agente quiere ejecutar una escritura:{FIN}")
    print(f"{AMAR}    {h.nombre}({args_txt}){FIN}")
    print(f"{AMAR}    {h.descripcion}{FIN}")
    try:
        return input("    ¿Autorizas? [s/N] ").strip().lower() in ("s", "si", "sí")
    except (EOFError, KeyboardInterrupt):
        return False


def responder(pregunta: str, modelo, herramientas, traza: str | None = None) -> None:
    print(f"\n{VERDE}▸ {pregunta}{FIN}")
    r = ejecutar(pregunta, modelo, herramientas, confirmar=pedir_confirmacion, al_paso=pintar)
    print(f"\n{VERDE}{r.respuesta}{FIN}")
    print(f"{GRIS}({len(r.pasos)} pasos · fin: {r.motivo_fin}){FIN}\n")
    if traza:
        with open(traza, "w", encoding="utf-8") as f:
            f.write(r.como_json())
        print(f"{GRIS}Rastro guardado en {traza}{FIN}")


def main() -> None:
    args = sys.argv[1:]
    traza = None
    if "--traza" in args:
        i = args.index("--traza")
        traza = args[i + 1]
        del args[i : i + 2]

    con = inicializar()
    herramientas = registro(con)
    modelo = desde_entorno()

    if args:
        responder(" ".join(args), modelo, herramientas, traza)
        return

    print(f"{GRIS}Escribe una pregunta. Ctrl-D para salir.{FIN}")
    while True:
        try:
            pregunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if pregunta:
            responder(pregunta, modelo, herramientas)


if __name__ == "__main__":
    main()
