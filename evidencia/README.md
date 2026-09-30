# evidencia/ — resultados trazables de los estudios de validación

Una sola fuente de datos para el centro de evidencia del sitio (`/validacion/`), la calculadora
de costos, la documentación y los documentos académicos. **Nada se escribe a mano aquí**: los
resúmenes se regeneran desde los resultados y `tools/evidencia.py verificar` falla si alguna cifra
publicada no coincide con sus datos.

| Ruta | Contenido |
|---|---|
| `esquemas/corrida.schema.json` | contrato `mini-format/corrida/1` de cada ejecución |
| `esquemas/estudio.schema.json` | contrato `mini-format/estudios/1` del registro de estudios |
| `estudios.json` | registro de V1, V2, V3a, V3b, V4, V5, V6a, V6b (y los exploratorios V7 y V8): pregunta, criterio con interpretación fijada, componentes requeridos, limitaciones, HU, estado y resultado |
| `derivados/` | **generado** por `tools/evidencia.py regenerar` (JSON y CSV deterministas); de aquí salen las cifras del sitio y de los documentos |
| `vectores/economia.json` | vectores dorados del cálculo de economía (Python y JavaScript deben coincidir exactamente) |
| `corridas/<run_id>/manifiesto.json` | una ejecución: estudio, procedencia, fecha UTC, commit o snapshot, entorno, datasets+hash, contratos+hash, tokenizador+versión, modelo, prompts, parámetros, conteos, resumen, estado |
| `corridas/<run_id>/…` | resultados crudos (JSON/CSV), logs e informe de esa corrida |
| `tarifas/` | tarifas oficiales consultadas (`tarifas.json`), cómo consultarlas (`fuentes.json`) y cada consulta (`consultas/<UTC>.json`) |
| `restringida/` | evidencia que NO se publica (ignorada por git): datos personales, claves, sesiones con participantes |

## Dos ejes y una procedencia

* **Estado de ejecución:** `pendiente` · `bloqueado` · `parcial` · `ejecutado`.
* **Resultado:** `no_evaluable` · `cumple` · `no_cumple`. Solo una corrida `ejecutado`, con criterio
  fijado de antemano y procedencia real (`reproducido_local`, `api_real`, `participantes`), puede
  declararse `cumple` o `no_cumple`. Lo `simulado`, `asistido_ia` o `reportado_historico` es
  siempre `no_evaluable` como evidencia del criterio.
* **Procedencia:** `reportado_historico` · `reproducido_local` · `simulado` · `asistido_ia` ·
  `api_real` · `participantes`.

Un script, una suite verde o una cifra citada no vuelven verde ningún estudio: lo decide el
manifiesto y lo comprueba `tools/evidencia_lib.validar_corrida`.

## Uso

```python
from tools import evidencia_lib as ev          # o: import evidencia_lib con tools/ en sys.path
m = ev.nueva_corrida("V1", "reproducido_local", "python experiments/v1_tokens/run.py", conjuntos=[...], resumen={...})
ev.guardar_corrida(m, archivos=[...])          # valida y escribe evidencia/corridas/<run_id>/manifiesto.json
```

Si el árbol de trabajo tenía cambios, el manifiesto conserva `codigo.snapshot_sha256` (hash del
contenido exacto probado) y `arbol_limpio: false`: esa corrida describe ese snapshot y debe
reejecutarse contra el commit que se publique.

## Comandos

```
python tools/evidencia.py validar       # manifiestos: estructura, SHA-256 de resultados, run_id = carpeta, sin secretos
python tools/evidencia.py estudios      # registro de estudios: los dos ejes y las reglas de honestidad
python tools/evidencia.py estudios --contrato   # qué debe registrar cada corrida (componentes y campos del resumen)
python tools/evidencia.py regenerar     # escribe evidencia/derivados/*.json y *.csv (sin marcas de tiempo)
python tools/evidencia.py verificar     # validar + estudios + derivados al día; falla si algo difiere

python tools/tarifas.py consultar       # descarga las páginas oficiales y actualiza el estado de cada tarifa
python tools/tarifas.py consultar --solo-comprobar   # registra la consulta sin tocar tarifas.json
python tools/tarifas.py verificar       # sin red: estructura, hashes y antigüedad (más de 14 días = desactualizada)
python tools/tarifas.py mostrar         # tabla de tarifas (--proveedor, --estado, --json)

python -m pytest -q -p no:cacheprovider tests/test_infra_economia.py tests/test_infra_tarifas.py tests/test_infra_evidencia.py
node tests/test_economia_js.mjs
```

`verificar` regenera los derivados en memoria y falla si difieren de lo versionado: **ninguna cifra se edita a mano**.
Cuando cambie una corrida o el registro, ejecute `regenerar`, revise el cambio y confírmelo.

## Reglas de honestidad del registro de estudios

* **Dos ejes.** `estado_ejecucion` (pendiente, bloqueado, parcial, ejecutado) y `resultado` (no_evaluable, cumple,
  no_cumple). El registro guarda lo declarado; `estudios` recalcula ambos desde las corridas y compara.
* **`ejecutado`** exige corridas `ejecutado` de procedencia real (`reproducido_local`, `api_real`, `participantes`) para
  **todos** los componentes del estudio (`componentes`, con `minimo_corridas`). Lo `simulado`, `asistido_ia` o
  `reportado_historico` se lista pero no cuenta. Si falta algún componente el estudio es `parcial` o `pendiente`;
  `bloqueado` exige una causa y un desbloqueo.
* **`cumple` / `no_cumple`** solo con estado `ejecutado`, con el criterio **fijado antes** de la primera corrida
  (`criterio.fijado_utc`) y **recalculados** desde los predicados sobre el `resumen` de las corridas que cuentan. Si lo
  declarado difiere, es un error. Un dato que falta hace el resultado `no_evaluable` (nunca un cero).
* Un registro que queda **por detrás** de las corridas (por ejemplo declara `pendiente` y ya hay corridas) es una
  advertencia de "registro desactualizado"; uno que queda **por delante** (declara más de lo que hay) es un error.
* Los **antecedentes** (`reportado_historico`, p. ej. V7 y V8) se citan con su fuente; las cifras con `verificacion` se
  recalculan desde los archivos del repositorio. Nunca cuentan como evidencia del criterio.
* Los estudios exploratorios (V7, V8) no tienen criterio de cumplimiento.
* Las interpretaciones de los criterios están marcadas `aprobado_por_equipo: false` hasta que el equipo las confirme.

## Cómo registra una corrida quien ejecuta un estudio

Use `tools/evidencia_lib.py` y añada `parametros.componente` (el `id` de un componente del estudio; es opcional solo si el
estudio tiene un único componente) y las cifras que pide el criterio en `resumen`:

```python
m = ev.nueva_corrida("V1", "reproducido_local", "python experiments/v1_tokens/run.py",
                     parametros={"componente": "tokens_por_dominio_y_tokenizador"},
                     resumen={"dominios_que_superan_umbral_min_tokenizador": 12, "tokenizadores_medidos": 3, "dominios_medidos": 14, "ahorro_medio_pct": 34.99})
ev.guardar_corrida(m, archivos=[...])
```

`python tools/evidencia.py estudios --contrato` imprime, por estudio, los componentes, las procedencias admitidas y las rutas
exactas del `resumen` (o del manifiesto, p. ej. `modelo.proveedor`, `entorno.so`, `parametros.sistema`) que leen los
predicados.

**Predicados.** Cada predicado lee un valor de `resumen` (`fuente: resumen`) o del propio manifiesto (`fuente: corridas`,
p. ej. `modelo.proveedor`) en las corridas que cuentan y lo agrega con `min`, `max`, `suma`, `unico` (exactamente una corrida
lo aporta; si no, no evaluable), `conteo_distintos`, `conteo_distintos_familia` (p. ej. familias de sistema operativo) o
`conteo_claves`. Si el valor es un objeto `{tokenizador: n}` aporta sus valores (el peor tokenizador con `min`). Comparan con
`>=`, `<=`, `>`, `<` o `==`. Sin datos el predicado no es evaluable (nunca 0).

## Tarifas

`tarifas/tarifas.json` guarda, por `(proveedor, modelo_api_id)`, los cuatro precios en USD por millón de tokens como
**cadenas decimales** (o `null`), el estado (`verificada` | `no_verificada`), la fecha UTC de consulta, la URL oficial y el
extracto con su SHA-256. Una tarifa es `verificada` solo si la página oficial la mostró en esa consulta; si la consulta falla
(red, bloqueo, redirección a otra página, JavaScript, formato cambiado) pasa a `no_verificada` con la causa y **sin precios
activos**: el costo se calcula entonces como "tarifa no verificada", nunca con un precio viejo. Bloqueos conocidos:
`groq.com/pricing` redirige a la portada (se usa `console.groq.com/docs/models` y la página de cada modelo); OpenAI y Google
solo entregan la tabla completa en su versión `.md`. DeepSeek publica tarifa de pico (la que se registra) y de fuera de pico
(la mitad). Los modelos retirados (`deepseek-chat`, `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`) figuran como
`no_verificada` con precio `null`.

**Tokenizadores.** `tiktoken` (o200k_base, cl100k_base, r50k_base) es una **aproximación** salvo para texto plano de los
modelos de OpenAI que tiktoken mapea; para Anthropic, Google, DeepSeek y los modelos de Groq que no son gpt-oss solo valen el
`usage` de la respuesta o el endpoint de conteo del proveedor. Un conteo local de texto, el conteo de solicitud del proveedor
y el `usage` de una llamada real son tres cosas distintas: no se suman ni se sustituyen, y se cuentan los textos completos
enviados (no fragmentos tokenizados por separado).

## Economía

`experiments/economia/calculo.py` (y su espejo `sitio/economia-calculo.js`) calcula razón, ahorro, costo por categorías,
costo por 1000 registros válidos, los escenarios A y B y el punto de equilibrio con aritmética exacta; ver
`experiments/economia/README.md`.
