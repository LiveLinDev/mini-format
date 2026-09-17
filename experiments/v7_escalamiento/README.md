# V7 · Escalamiento por lote: cuántos registros caben en una respuesta y qué cuesta cada formato

Responde tres preguntas con llamadas reales:

1. **¿Cuánto dinero cuesta cada formato?** Tokens de salida por registro y costo de procesar un volumen
   dado, con los precios publicados que registra `experiments/v4_costos/precios.json`.
2. **¿Desde cuántos registros por llamada la respuesta sale mal?** El límite de tokens de salida del
   modelo es finito: a partir de cierto tamaño de lote la respuesta se corta. El barrido localiza ese
   punto en cada formato.
3. **¿Qué se puede aprovechar cuando sale mal?** En JSON el documento es un único valor y una respuesta
   cortada no se puede leer; en `.mini` cada línea es un registro y las completas se conservan.

## Diseño

| | |
|---|---|
| Tarea | Convertir mensajes de clientes en tickets de soporte (prioridad, categoría, resumen y horas) |
| Contrato | `tk`, generado al vuelo desde `examples/mesa-de-ayuda/ticket.schema.json` con `from_json_schema` |
| Brazos | **json** (el JSON Schema en la instrucción, leído con `json.loads`) y **mini** (bloque de prompt del contrato, leído con `parse(..., strict=False)`) |
| Variable independiente | registros por llamada: 10, 25, 50, 100, 150, 200, 300, 400 |
| Entrada | mensajes sintéticos por plantilla, deterministas para una semilla (`--semilla`, por defecto 20260917) |
| Modelo | `deepseek-chat` (DeepSeek) o `openai/gpt-oss-20b` (Groq), temperatura 0, `max_tokens` al máximo publicado |
| Repeticiones | 3 por celda en el barrido; en la fase de volumen, tantos lotes como haga falta para el objetivo |

Por llamada se registran los tokens de entrada y salida **que informa el proveedor**, el motivo de parada,
los registros completos recibidos, los válidos contra el contrato, los aprovechables sin volver a pedir
nada, la latencia y el costo con los precios de V4.

Un registro cuenta como **aprovechado** si la aplicación lo puede usar sin una llamada adicional. En JSON
un solo valor fuera del esquema invalida el lote, porque `json.loads` no indica en qué registro está el
error: así lo trata una aplicación real y así se cuenta aquí.

## Cómo se ejecuta

```bash
# 1. Estimar llamadas, tokens y costo (no llama a nada)
python experiments/v7_escalamiento/correr.py --dry-run

# 2. Barrido de tamaños de lote (48 llamadas)
export DEEPSEEK_API_KEY=...
python experiments/v7_escalamiento/correr.py --proveedor deepseek --confirmar-real --max-costo-usd 1

# 3. Volumen: 20 000 registros por formato al mayor lote sin pérdida que haya dado el barrido
python experiments/v7_escalamiento/correr.py --proveedor deepseek --confirmar-real \
       --tamanos <lote> --objetivo-registros 20000 --max-costo-usd 4 --paralelo 6

# 4. Tablas
python experiments/v7_escalamiento/analizar.py --resultados experiments/v7_escalamiento/results/deepseek
```

`--max-costo-usd` corta antes de empezar si la estimación lo supera, y durante la ejecución en cuanto el
gasto acumulado según los tokens informados lo pasa. Cada llamada se escribe en `llamadas.jsonl` con
`fsync`, así que relanzar el mismo comando salta lo ya hecho. Las claves se leen solo del entorno; no se
imprimen ni se guardan en los resultados.

## Proveedores y límites

`deepseek-chat` admite el barrido completo. El **nivel gratuito de Groq no sirve** para este experimento:
8 000 tokens por minuto y 1 000 peticiones al día, y un lote de 200 registros necesita más de 14 000 tokens
entre entrada y salida, de modo que las celdas grandes devuelven 429 siempre. En `results/groq` quedan las
celdas pequeñas que sí se completaron, declaradas como parciales en su `meta.json`.

En los modelos GPT-OSS el arnés fija `reasoning_effort: low`: son modelos de razonamiento y, sin eso, gastan
parte del límite de salida antes de escribir la respuesta (con un tope bajo devuelven el texto vacío).

## Resultados

`results/<proveedor>/llamadas.jsonl` (una línea por llamada), `por_lote.csv`, `resumen.csv` y `meta.json`
con el modelo, los precios usados, la semilla y el gasto. Las cifras publicadas en los documentos del
proyecto deben citar el `meta.json` de la corrida correspondiente.
