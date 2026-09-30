# evidencia/ — resultados trazables de los estudios de validación

Una sola fuente de datos para el centro de evidencia del sitio (`/validacion/`), la calculadora
de costos, la documentación y los documentos académicos. **Nada se escribe a mano aquí**: los
resúmenes se regeneran desde los resultados y `tools/evidencia.py verificar` falla si alguna cifra
publicada no coincide con sus datos.

| Ruta | Contenido |
|---|---|
| `esquemas/corrida.schema.json` | contrato `mini-format/corrida/1` de cada ejecución |
| `corridas/<run_id>/manifiesto.json` | una ejecución: estudio, procedencia, fecha UTC, commit o snapshot, entorno, datasets+hash, contratos+hash, tokenizador+versión, modelo, prompts, parámetros, conteos, resumen, estado |
| `corridas/<run_id>/…` | resultados crudos (JSON/CSV), logs e informe de esa corrida |
| `tarifas/` | tarifas oficiales consultadas (proveedor, modelo exacto, fecha, URL, extracto, estado) |
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
