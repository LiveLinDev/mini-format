# Estudio de formatos con modelos reales

La misma aplicación de soporte (`examples/flujo-soporte`: 20 mensajes, la misma tarea y el mismo contrato `ticket`) se ejecuta con modelos reales de dos proveedores en dos formatos de salida:

- **JSON con contrato**: la instrucción de claves y tipos de la aplicación y el lector habitual (`json.loads`). Si la respuesta no se puede leer o algún registro no cumple el contrato, se pide una vez la respuesta completa de nuevo.
- **.mini**: el prompt del contrato .mini y `Workflow.process` de mini-format, con los ajustes locales deterministas y una ronda de corrección selectiva (solo las líneas inválidas).

Solo cambia el componente que lee la respuesta; los mensajes, la tarea y el modelo son los mismos.

## Ejecución del 19/11/2026

| Proveedor | Modelo | Cliente | Esfuerzo de razonamiento |
|---|---|---|---|
| Anthropic | Claude Opus 5.5 (`claude-opus-5-5`) | Claude Code 2.1.314 (`claude -p`, sin herramientas) | bajo |
| Anthropic | Claude Haiku 5.5 (`claude-haiku-5-5`) | Claude Code 2.1.314 (`claude -p`, sin herramientas) | bajo |
| Moonshot AI | Kimi K3.1 Pro (`kimi-code/k3.1-pro`) | Kimi Code 2.5.2 (`kimi -p`, agente sin herramientas) | bajo |

3 modelos × 2 formatos × 3 repeticiones = **18 corridas, todas completas**; una corrida (Haiku, .mini, repetición 2) necesitó la ronda de corrección. Las llamadas usaron las suscripciones de los autores, no la API: el costo que se informa es el equivalente a precios de API.

### Resultados

`python experiments/estudio_formatos/ver.py todo`

| Modelo | Formato | Tokens de salida (media) | Validez inicial (IC 95 %) | Validez tras corrección | Latencia media (p95) | USD por 1 000 registros válidos |
|---|---|---|---|---|---|---|
| Claude Opus 5.5 | JSON | 934 | 100 % (94,0–100) | 100 % | 18,5 s (18,6) | 0,934 |
| Claude Opus 5.5 | .mini | 506 (−45,9 %) | 100 % (94,0–100) | 100 % | 6,1 s (6,3) | 0,506 (−45,9 %) |
| Claude Haiku 5.5 | JSON | 966 | 100 % (94,0–100) | 100 % | 15,8 s (16,0) | 0,024 |
| Claude Haiku 5.5 | .mini | 1 330 (+37,8 %) | 66,7 % (54,1–77,3) | 100 % | 7,6 s (7,8) | 0,042 (+74,7 %) |
| Kimi K3.1 Pro | JSON | 875 | 100 % (94,0–100) | 100 % | 18,5 s (27,6) | tarifa no verificada |
| Kimi K3.1 Pro | .mini | 537 (−38,6 %) | 100 % (94,0–100) | 100 % | 14,2 s (17,8) | tarifa no verificada |

`python experiments/estudio_formatos/cortes.py --todas experiments/estudio_formatos/corridas`

| Lector | Registros completos antes del corte | Recuperados |
|---|---|---|
| .mini con la señal de corte del proveedor | 1 518 | 1 516 (99,9 %) |
| JSON con `json.loads` | 1 534 | 0 (0,0 %) |

Observaciones:

- **Tokens.** Con Opus y Kimi, .mini reduce los tokens de salida un 45,9 % y un 38,6 %. Con Haiku los aumenta un 37,8 %: con el prompt .mini el modelo razona (815 tokens de razonamiento de media frente a 0 en JSON), aunque la respuesta visible es más corta. Es el mismo comportamiento que se registró en V2.
- **Validez.** En la repetición 2, Haiku escribió el título del prompt («# Contrato de dominio .mini») antes de la cabecera. Esa respuesta cuenta con 0 registros válidos y la corrección del modelo la dejó con 20 de 20. Las otras 17 corridas entregaron sus 20 registros válidos sin corrección.
- **Cortes.** La pareja Haiku/repetición 2 se omite en `cortes.py` porque su respuesta .mini completa no se puede leer sin la corrección. En las 8 parejas restantes, .mini conserva todos los registros completos salvo 2 que terminaban justo en el corte sin salto de línea: con la señal de corte, esa última línea se descarta por precaución.
- **Latencia.** Es tiempo de reloj medido alrededor del cliente de línea de comandos e incluye su arranque. Sirve para comparar formatos con el mismo modelo, no como latencia de la API.
- **Costo.** Se calcula como tokens de salida de todas las llamadas × tarifa de salida / registros válidos finales. Las tarifas se consultaron el 19/11/2026 con `tools/tarifas.py` (`tarifas/`): Opus 5.5 a 20 USD por millón y Haiku 5.5 a 0,50 USD por millón, ambas verificadas. La página oficial de Kimi dibuja su tabla de precios con JavaScript y la versión Markdown no la incluye, por lo que su tarifa queda **no verificada** y no se calcula su costo.
- **Alcance.** Con 3 repeticiones por celda, los intervalos son amplios: el estudio muestra el comportamiento de la aplicación con modelos reales, no estima tasas de error poco frecuentes.

## Consulta sin proveedor

Las corridas grabadas están en `corridas/<modelo>/<formato>/<repetición>/`. Cada carpeta contiene:

- `respuesta_1.mini` o `respuesta_1.json`: la respuesta tal como llegó;
- `respuesta_N_correccion.txt` o `respuesta_N.json`: la corrección, si hubo;
- `evaluacion.json`: tokens, latencia y diagnóstico de cada llamada.

`corridas/resultados.json` reúne todo.

```powershell
python experiments/estudio_formatos/ver.py tokens       # tokens de salida por modelo y formato
python experiments/estudio_formatos/ver.py validez      # registros válidos con intervalo de Wilson al 95 %
python experiments/estudio_formatos/ver.py reparacion   # validez antes y después de la corrección
python experiments/estudio_formatos/ver.py latencia     # media y p95 por modelo y formato
python experiments/estudio_formatos/ver.py costo        # USD por mil registros válidos con tarifas verificadas
python experiments/estudio_formatos/cortes.py experiments/estudio_formatos/corridas/claude-opus-5-5/mini/1/respuesta_1.mini experiments/estudio_formatos/corridas/claude-opus-5-5/json/1/respuesta_1.json
python experiments/estudio_formatos/cortes.py --todas experiments/estudio_formatos/corridas
```

Para actualizar las tarifas a la fecha de la consulta:

```powershell
python tools/tarifas.py --directorio experiments/estudio_formatos/tarifas consultar
python tools/tarifas.py --directorio experiments/estudio_formatos/tarifas mostrar
```

## Repetir el estudio con un proveedor

`proveedores.json` declara los proveedores, sin claves. Hay tres corredores:

- `cli-claude`: Claude Code con la sesión iniciada. Si la configuración no está en la carpeta por defecto, se indica con `MINI_CLAUDE_CONFIG_DIR`.
- `cli-kimi`: Kimi Code con la sesión iniciada.
- `openai-compatible`: cualquier servidor Chat Completions (OpenAI, DeepSeek, Groq, Ollama, vLLM). La URL y el modelo van en `proveedores.json`; la clave, si el servidor la pide, en la variable de entorno que indica `clave_env`.

```powershell
python experiments/estudio_formatos/medir.py --repeticiones 3
python experiments/estudio_formatos/medir.py --ids claude-haiku-5-5 --formatos mini --repeticiones 1
python experiments/estudio_formatos/medir.py --proveedores mis_proveedores.json --salida mis_corridas
python experiments/estudio_formatos/ver.py todo --resultados mis_corridas/resultados.json
```

`medir.py` es reanudable: no vuelve a pedir una corrida que ya tiene `evaluacion.json`. Una corrida fallida (error del cliente, cuota agotada, tiempo agotado) queda registrada como `fallida_<fecha>.json` y se reintenta en la siguiente ejecución. Las llamadas a un proveedor tienen el costo de ese proveedor.

## Archivos

| Archivo | Contenido |
|---|---|
| `medir.py` | ejecución del estudio y corredores |
| `proveedores.json` | proveedores del estudio y dos ejemplos inactivos (`openai-compatible`), sin claves |
| `ver.py` | tokens, validez, reparación, latencia y costo |
| `cortes.py` | recuperación de registros completos en 20 cortes |
| `tarifas/` | fuentes, tarifas y consulta del 19/11/2026 (`tools/tarifas.py`) |
| `corridas/` | las 18 corridas grabadas y `resultados.json` |

Las pruebas de `ver.py` y `cortes.py` están en `tests/test_estudio_formatos.py`.
