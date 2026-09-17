# Mesa de ayuda: datos del caso de integración

Una aplicación de soporte pide a un LLM que convierta mensajes de clientes en tickets. El componente que
interpreta la respuesta del modelo tiene dos implementaciones con la misma interfaz: una lee JSON, la otra lee
`.mini` con este contrato. Todo lo demás —dominio, base de datos, interfaz— es idéntico.

Esta carpeta contiene los datos del caso y la plantilla de la página `/mesa-de-ayuda/`, que los ejecuta en el
navegador con `js/mini.js`, el mismo motor del playground.

| Archivo | Qué es |
|---|---|
| `ticket.schema.json` | El JSON Schema que la aplicación ya tenía. El contrato `tk` se genera de aquí con `mini from-schema`. |
| `mensajes.json` | Los diez mensajes de clientes que entran a la mesa de ayuda. |
| `grabaciones/mini/*.mini`, `grabaciones/json/*.json` | Tres respuestas grabadas de un modelo en cada formato: `ok` (correcta), `error` (la línea 6 trae una categoría que no existe) y `cortada` (la respuesta se truncó al 75 %). |
| `mediciones.json` | Resultados medidos: los del proveedor simulado (reproducibles con las grabaciones) y los de una corrida real con `deepseek-chat`. |
| `plantilla.html` | La página; `sitio/construir.py` le inyecta el contrato, los datos y el motor. |

La aplicación completa —Flask, SQLite, conectores de proveedor y pruebas— vive en el repositorio de la tesis,
en `demo_clase/sistema-tickets`. Aquí solo están los datos necesarios para reproducir el caso en el sitio.

## Reproducir las cifras

```bash
mini from-schema examples/mesa-de-ayuda/ticket.schema.json -p tk --out contrato_tk.json
mini tokens examples/mesa-de-ayuda/grabaciones/json/ok.json
mini tokens examples/mesa-de-ayuda/grabaciones/mini/ok.mini
mini validate examples/mesa-de-ayuda/grabaciones/mini/cortada.mini --contract contrato_tk.json --lenient
```

Las cifras de `mediciones.json` salen de la aplicación de soporte, no de la página: el proveedor simulado lee
estas mismas grabaciones y la corrida real llamó a `deepseek-chat` el 17-sep-2026 con temperatura 0.
