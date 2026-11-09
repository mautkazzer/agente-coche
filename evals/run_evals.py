"""Corre los casos dorados y reporta cuatro métricas.

    selección   ¿usó las herramientas correctas?
    eficiencia  ¿en cuántos pasos, contra el mínimo necesario?
    terminación ¿paró cuando debía, sin agotar el tope ni entrar en bucle?
    negativa    en los adversariales, ¿dijo que no lo sabía en vez de inventar?

Uso:
    python evals/run_evals.py                 todos
    python evals/run_evals.py --caso 7        uno solo
    python evals/run_evals.py --etiqueta v1   guarda el JSON con esa etiqueta
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.db import inicializar  # noqa: E402
from src.herramientas import registro  # noqa: E402
from src.llm import desde_entorno  # noqa: E402
from src.react import ejecutar  # noqa: E402

NEGATIVAS = [
    "no lo sé", "no lo se", "no tengo", "no aparece", "no encontré", "no encontre",
    "no está", "no esta", "no hay", "no dice", "no puedo", "no figura", "sin información",
    "sin informacion", "no se menciona", "no consta",
]


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def contiene(texto: str, fragmento: str) -> bool:
    return normalizar(fragmento) in normalizar(texto)


def evaluar(caso: dict, resultado) -> dict:
    usadas = set(resultado.herramientas_usadas)
    esperadas = set(caso.get("herramientas_esperadas", []))
    n = len(resultado.pasos)

    seleccion = None
    if esperadas:
        seleccion = esperadas.issubset(usadas) and not (usadas - esperadas)

    eficiencia = None
    if (minimo := caso.get("pasos_minimos")) is not None:
        # +1 por el paso final en el que responde
        eficiencia = n <= minimo + 1
    if (maximo := caso.get("pasos_maximos")) is not None:
        eficiencia = n <= maximo

    fin_esperado = caso.get("fin_esperado", "respondio")
    terminacion = resultado.motivo_fin == fin_esperado

    negativa = None
    if caso.get("debe_negarse"):
        negativa = any(contiene(resultado.respuesta, f) for f in NEGATIVAS)

    contenido = None
    if fragmentos := caso.get("debe_contener"):
        contenido = all(contiene(resultado.respuesta, f) for f in fragmentos)

    checks = [c for c in (seleccion, eficiencia, terminacion, negativa, contenido) if c is not None]
    return {
        "id": caso["id"],
        "pregunta": caso["pregunta"],
        "pasos": n,
        "motivo_fin": resultado.motivo_fin,
        "herramientas": resultado.herramientas_usadas,
        "respuesta": resultado.respuesta,
        "seleccion": seleccion,
        "eficiencia": eficiencia,
        "terminacion": terminacion,
        "negativa": negativa,
        "contenido": contenido,
        "aprobado": all(checks),
    }


def porcentaje(filas: list[dict], clave: str) -> str:
    aplicables = [f[clave] for f in filas if f[clave] is not None]
    if not aplicables:
        return "n/a"
    return f"{sum(aplicables)}/{len(aplicables)}  ({100 * sum(aplicables) // len(aplicables)}%)"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--caso", type=int)
    p.add_argument("--etiqueta", default=datetime.now().strftime("%Y%m%d-%H%M"))
    args = p.parse_args()

    casos = yaml.safe_load((RAIZ / "evals" / "casos.yaml").read_text(encoding="utf-8"))
    if args.caso:
        casos = [c for c in casos if c["id"] == args.caso]

    modelo = desde_entorno()
    filas = []

    for caso in casos:
        # Base limpia por caso: las escrituras no deben contaminar al siguiente.
        con = inicializar(":memory:")
        herramientas = registro(con)
        autoriza = caso.get("confirmar", True)
        r = ejecutar(
            caso["pregunta"], modelo, herramientas, confirmar=lambda h, a: autoriza
        )
        fila = evaluar(caso, r)
        filas.append(fila)
        marca = "ok  " if fila["aprobado"] else "FALL"
        print(f"  {marca} #{fila['id']:>2}  {fila['pasos']} pasos  {caso['pregunta'][:58]}")

    total = len(filas)
    aprobados = sum(f["aprobado"] for f in filas)
    pasos_prom = sum(f["pasos"] for f in filas) / total if total else 0

    print(f"\n  Aprobados    {aprobados}/{total}  ({100 * aprobados // total if total else 0}%)")
    print(f"  Selección    {porcentaje(filas, 'seleccion')}")
    print(f"  Eficiencia   {porcentaje(filas, 'eficiencia')}")
    print(f"  Terminación  {porcentaje(filas, 'terminacion')}")
    print(f"  Negativa     {porcentaje(filas, 'negativa')}")
    print(f"  Pasos promedio  {pasos_prom:.1f}")

    salida = RAIZ / "evals" / "resultados"
    salida.mkdir(exist_ok=True)
    destino = salida / f"{args.etiqueta}.json"
    destino.write_text(
        json.dumps(
            {
                "etiqueta": args.etiqueta,
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "total": total,
                "aprobados": aprobados,
                "pasos_promedio": round(pasos_prom, 2),
                "casos": filas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  Guardado en {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
