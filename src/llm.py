"""Cliente de modelo. Tres proveedores: anthropic, ollama y stub (para pruebas)."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class Modelo(Protocol):
    def completar(self, sistema: str, mensajes: list[dict[str, str]]) -> str: ...


class Anthropic:
    def __init__(self, modelo: str | None = None) -> None:
        import anthropic  # import perezoso: solo si de verdad se usa

        self.cliente = anthropic.Anthropic()
        self.modelo = modelo or os.getenv("MODELO", "claude-sonnet-4-5")

    def completar(self, sistema: str, mensajes: list[dict[str, str]]) -> str:
        r = self.cliente.messages.create(
            model=self.modelo,
            max_tokens=1024,
            system=sistema,
            messages=mensajes,
            stop_sequences=["Observación:"],
        )
        return r.content[0].text


class Ollama:
    def __init__(self, modelo: str | None = None, url: str | None = None) -> None:
        self.modelo = modelo or os.getenv("MODELO", "llama3.1:8b")
        self.url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")

    def completar(self, sistema: str, mensajes: list[dict[str, str]]) -> str:
        cuerpo = json.dumps(
            {
                "model": self.modelo,
                "system": sistema,
                "messages": mensajes,
                "stream": False,
                "options": {"temperature": 0, "stop": ["Observación:"]},
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.url}/api/chat", data=cuerpo, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"]


class Stub:
    """Devuelve respuestas predefinidas. Sirve para probar el bucle sin gastar tokens."""

    def __init__(self, guion: list[str]) -> None:
        self.guion = list(guion)

    def completar(self, sistema: str, mensajes: list[dict[str, str]]) -> str:
        return self.guion.pop(0) if self.guion else "Respuesta: me quedé sin guion."


def desde_entorno() -> Modelo:
    proveedor = os.getenv("PROVEEDOR", "anthropic").lower()
    if proveedor == "ollama":
        return Ollama()
    if proveedor == "stub":
        return Stub([])
    return Anthropic()
