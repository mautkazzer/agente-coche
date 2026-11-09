# agente-coche

Un agente **ReAct** que lleva el mantenimiento de mi coche: sabe qué servicios le
he hecho, cuántos kilómetros trae y qué dice el manual del fabricante. Las
herramientas se exponen por **MCP**, así que las consume tanto el bucle de este
repo como cualquier cliente MCP externo.

El bucle está escrito a mano, sin framework de agentes. La gracia del proyecto no
es que funcione: es que está medido y que sabe cuándo no responder.

```
▸ ¿Ya me toca cambio de aceite?

  Pensamiento: Necesito el kilometraje de hoy.
  Acción: kilometraje_actual()                                   390 ms
  Observación: 68,400 km, registrado el 2026-11-09.
  Pensamiento: Ahora cuándo fue el último cambio.
  Acción: historial_servicios(tipo='aceite')                     355 ms
  Observación: #7 cambio de aceite — 60,000 km · 2026-08-14 · Agencia ...
  Pensamiento: Falta el intervalo que marca el manual.
  Acción: leer_manual(consulta='intervalo cambio de aceite')     402 ms
  Observación: [manual-mantenimiento.md › Cambio de aceite y filtro]
    Cada 10,000 km o 12 meses, lo que ocurra primero...

  Sí, y con margen: llevas 8,400 km desde el último (a los 60,000) y el
  manual lo pide cada 10,000. Si manejas puro tráfico de ciudad, el manual
  considera eso uso severo y baja el intervalo a 5,000 km.

  (4 pasos · fin: respondio)
```

Esa respuesta necesitó tres fuentes distintas. Nadie programó esa secuencia: el
modelo la armó porque cada observación le reveló qué le faltaba.

## Por qué ReAct

No hay un grafo fijo. El modelo decide en cada vuelta qué herramienta usa y
cuándo ya tiene con qué responder. Un RAG normal habría buscado en el manual y
respondido el intervalo, sin saber si al coche ya le tocaba.

Eso le da flexibilidad y también tres formas características de romperse, que es
justo lo que este repo mide.

## Guardrails

Viven en el código, no en el prompt. Un prompt se puede ignorar; un `while` no.

| Falla | Defensa |
|---|---|
| Se cicla repitiendo la misma consulta | Huella de `(herramienta, argumentos)`; a la segunda, corta |
| No sabe parar y sigue consultando | Solo `Respuesta:` cierra el turno; tope de iteraciones |
| Inventa cuando no encuentra | El prompt obliga a negarse, y los evals lo verifican |
| Escribe sin permiso | Toda herramienta de escritura pasa por confirmación humana |
| Llama una herramienta que no existe o con argumentos malos | Se le devuelve como observación para que se corrija, no revienta |

Además hay reglas del dominio que no dependen del modelo: el odómetro nunca va
hacia atrás, y registrar un servicio viejo no lo mueve.

Los argumentos se leen con `ast.literal_eval`, nunca con `eval`.

## Evals

30 casos dorados en [`evals/casos.yaml`](evals/casos.yaml). Siete son
adversariales: preguntas cuya respuesta correcta es *no lo sé* — la presión de
llantas, el año del coche, cuánto cuesta un servicio. Nada de eso está en el
manual ni en el historial, y el agente tiene que decirlo en vez de completar el
hueco.

Cuatro métricas:

- **Selección** — ¿usó las herramientas correctas, y solo esas?
- **Eficiencia** — pasos usados contra pasos mínimos. Un agente que tarda nueve
  vueltas en algo de tres es un agente caro.
- **Terminación** — ¿paró bien, sin agotar el tope ni ciclarse?
- **Negativa** — en los adversariales, ¿dijo que no sabía en vez de inventar?

```bash
python evals/run_evals.py --etiqueta v1
```

Deja un JSON por corrida en `evals/resultados/`, para comparar versiones.

### Resultados

| Versión | Aprobados | Selección | Eficiencia | Terminación | Negativa | Pasos prom. |
|---|---|---|---|---|---|---|
| v1 | | | | | | |

> Corre los evals con tu propio modelo y llena la tabla. Las cifras dependen del
> modelo y del prompt, así que publicar las mías no te diría nada de las tuyas.

## Servidor MCP

| Herramienta | Tipo |
|---|---|
| `kilometraje_actual` | lectura |
| `historial_servicios` | lectura |
| `leer_manual` | lectura, texto completo con FTS5 |
| `registrar_servicio` | escritura |
| `actualizar_kilometraje` | escritura |

Para conectarlo a Claude Desktop, en su archivo de configuración:

```json
{
  "mcpServers": {
    "agente-coche": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/ruta/a/agente-coche"
    }
  }
}
```

Las herramientas de escritura no llevan confirmación propia dentro del servidor:
el control vive en el cliente. El bucle de este repo la pide; Claude Desktop pide
la suya.

## Cómo correrlo

```bash
pip install -r requirements.txt
cp .env.example .env          # pon tu API key, o usa Ollama en local
python -m src.db              # crea la base e indexa el manual
python -m src.cli "¿ya me toca cambio de aceite?"
python -m src.cli             # modo conversación
pytest -q                     # 18 pruebas (guardrails, dominio y servidor MCP)
```

Funciona con la API de Anthropic o con Ollama en local (`PROVEEDOR=ollama`), y
trae un proveedor `stub` para probar el bucle sin gastar tokens.

## Cómo está armado

```
src/
  react.py          el bucle y los guardrails
  herramientas.py   las cinco herramientas
  mcp_server.py     servidor MCP
  db.py             SQLite + índice FTS5 del manual
  llm.py            Anthropic / Ollama / stub
  cli.py            consola con rastro y confirmación
evals/              casos dorados y arnés de medición
notas/              el manual de mantenimiento en markdown
tests/              guardrails y reglas del dominio
```

Sin dependencias de más: SQLite trae FTS5 de fábrica, así que la búsqueda de
texto completo no necesita un motor aparte ni una base vectorial.

## Los datos

El historial de `src/db.py` y el manual de `notas/` son de ejemplo. Cámbialos por
los de tu coche: el manual de cualquier fabricante trae el programa de servicio,
y pasarlo a markdown es media hora.

## Qué sigue

El agente único se atora cuando la pregunta abarca varios servicios a la vez
(«¿qué tengo vencido?»): recorre el manual sección por sección y se queda sin
iteraciones. El siguiente paso es partirlo en especialistas con un router, y
medir si baja el promedio de pasos.

## Licencia

MIT
