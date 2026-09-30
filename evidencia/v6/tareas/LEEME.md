# Repositorio de tareas de V6b (T1 a T4)

**Sin participantes: estudio pendiente, materiales listos.** Aquí hay tareas con respuestas congeladas y un
verificador objetivo; no hay ningún resultado.

Tareas del Plan de Validación v3 (tabla T10) y su tope. Suman 100 minutos; con 10 de introducción y 10 de
cuestionario, la sesión llega a 120 como máximo.

| Tarea | Actividad | Tope | Carpeta del participante |
|---|---|---|---|
| T1 JSON | Cliente pequeño que lee y valida una respuesta en JSON | 30 min | `participante/T1A_json/` o `T1B_json/` |
| T1 .mini | La tarea equivalente con la guía y el componente | 30 min | `participante/T1A_mini/` o `T1B_mini/` |
| T2 | Diagnosticar un registro inválido y repararlo | 15 min | `participante/T2/` |
| T3 | Tratar una respuesta incompleta (truncada) | 10 min | `participante/T3/` |
| T4 | Adaptar un contrato de otro dominio | 15 min | `participante/T4/` |

## Estructura

```
tareas/
  participante/    lo único que recibe el participante (una copia limpia por sesión, con entrega/ vacía)
  observador/      referencias, soluciones y contrato solución; NO se entregan
  respuestas_congeladas.json   manifiesto con el SHA-256 de cada archivo y su origen
  construir_tareas.py          regenera todo; --verificar falla si el disco difiere
  verificar_entrega.py         verificador objetivo (solo observador)
  hoja_observacion.md          ficha impresa
```

Regenerar y comprobar: `PYTHONPATH=src python evidencia/v6/tareas/construir_tareas.py [--verificar]`.

## De dónde salen los datos

| Material | Procedencia |
|---|---|
| T1 variante A: `respuesta.json`, `respuesta.mini`, `ticket.schema.json` | **Archivos reales del repositorio** (`examples/mesa-de-ayuda/…/error.*` y `ticket.schema.json`), copia literal |
| Contratos `tk` e `inc` | Generados con `minifmt.from_json_schema` (el mismo código de `mini from-schema`) |
| T1 variante B, T2, T3 y los casos de T4 | **Dataset sintético** redactado por el equipo. No son salida de ningún modelo ni datos de un sistema real |
| T4, contrato de partida | `forks/cat/contract.json` (catálogo de productos, otro dominio), copia literal |
| `participante/guia_mini.md` | Copia literal de `sitio/content/quickstart.es.md`; la guía que se entrega la fija el equipo |
| `observador/T2.corregido_esperado.mini`, `T3.completo_esperado.mini`, `*.referencia.json` | Derivados de las listas de registros escritas en `construir_tareas.py` (oráculo independiente de los analizadores) |
| `participante/T2/correccion_modelo.mini` | Respuesta de reparación **redactada por el equipo** con el formato de reparación de la biblioteca; no es de un modelo real |

## Las dos variantes de T1

Cada participante hace T1 en las dos condiciones con **tareas equivalentes** para controlar el aprendizaje
(Plan v3, P83): la variante A (tickets de soporte, contrato `tk`) y la B (incidencias de infraestructura,
contrato `inc`). Se generan con la misma forma (cadena, enumeración de 3, enumeración de 4, cadena, entero
acotado), 10 registros y un defecto del mismo tipo (valor fuera de la enumeración, código `E10`), pero con
**nombres de campo, valores y posición del defecto distintos**, de modo que el código de una condición no se
pueda reutilizar tal cual en la otra. `tools/analizar_v6.py contrabalanceo` asigna a cada participante el orden
(JSON primero o .mini primero) **y** qué variante se resuelve con cada formato, equilibrando las cuatro
combinaciones. La equivalencia es por construcción; su dificultad efectiva solo se conoce tras el piloto.

## Entregas y criterios de éxito (los decide `verificar_entrega.py`)

Cada criterio es objetivo: un archivo de entrega que se compara con una referencia congelada.

| Tarea | Entrega en `entrega/` | Éxito cuando… |
|---|---|---|
| T1 (A o B, JSON o .mini) | `salida_T1.json` = `{"validos": [...], "rechazados": [{"posicion": N, "motivo": "…"}]}` | (1) `validos` tiene los 9 registros buenos, en orden y con los mismos valores y tipos (un entero entregado como cadena falla); (2) `rechazados` contiene exactamente la posición del registro defectuoso (5 en A, 7 en B), sin duplicados ni posiciones de más |
| T2 | `T2_diagnostico.json` = `{"codigo_error": "E05", "linea": 8}` y `T2_corregido.mini` | (1) código y línea correctos; (2) el documento corregido valida sin errores; (3) sus 12 registros son los esperados (el defectuoso reparado sin inventar); (4) las otras 11 líneas están idénticas a las originales |
| T3 | `T3_recuperado.json` = `{"recuperados": [...], "sin_recuperar": N, "primer_no_recuperado": N}` | (1) recupera exactamente los 11 registros completos (el cortado no cuenta); (2) `sin_recuperar` = 4 de los 15 declarados; (3) `primer_no_recuperado` = 12 |
| T4 | `contrato_cambios.json` | (1) contrato que carga (perfil base); (2) prefijo `chg`; (3) campos con los nombres y el orden de la tabla; (4) acepta `caso_positivo.mini`; (5) sus registros salen con los valores esperados; (6) rechaza `caso_negativo.mini` con `E13` en la línea 3 |

Un participante que agota el tope **no** tiene éxito aunque su entrega quede casi bien: el cronómetro cierra
la tarea como tiempo agotado (censurado) y el verificador se ejecuta solo con fines de observación.

### Por qué cada tarea mide lo que dice

* **T1**: lee y valida; el defecto obliga a «tratar un fallo sin alterar válidos». En JSON exige escribir la
  validación por registro con la biblioteca de esquemas; en `.mini` la biblioteca da la lectura tolerante.
* **T2**: el defecto es una barra vertical sin escapar dentro de un texto: produce 6 campos (`E05`) y no un
  error de valor. Se puede reparar a mano o por el camino de la biblioteca (`repair_request` y
  `merge_repair` con la corrección congelada). No hay que inventar el valor: está en la corrección.
* **T3**: la respuesta termina a mitad de una línea. El diagnóstico de la biblioteca informa `missing_records`
  = 3 (registros que faltan **después** de las líneas presentes), pero lo que no se pudo recuperar son 4
  (el cortado también). La tarea pide lo segundo: es una trampa deliberada de lectura, no de formato.
* **T4**: el contrato de origen (catálogo de productos) no acepta el caso positivo sin adaptarlo. Un contrato
  «laxo» (todo cadena) acepta el positivo pero no rechaza el negativo: por eso el negativo es un error de rango.

## Verificación de los materiales (hechas y comprobables)

`tests/test_v6_tareas.py` comprueba, con `minifmt`, `jsonschema` y el motor JavaScript (`js/mini.js`):

* las respuestas correctas validan y las defectuosas fallan exactamente donde se dice (por ejemplo `E10` en la
  línea 6 de la variante A y en la 8 de la B; `E05` en la 8 de T2; `E05` en la 13 y `E04` en T3; `E13` en la 3 de T4);
* las versiones JSON y `.mini` de T1 llevan los mismos datos y las variantes A y B tienen la misma forma;
* el verificador acepta soluciones correctas (incluidas las soluciones de referencia de `observador/soluciones/`)
  y rechaza entregas defectuosas típicas (no detectar el fallo, posición equivocada, tumbar válidos, coaccionar
  tipos, contar el registro cortado, contrato sin rango, etc.);
* el paquete del participante no contiene referencias ni soluciones.

## Límites conocidos

* Los datasets sintéticos son pequeños (10 a 15 registros): miden integración y manejo de fallos, no rendimiento.
* No se ha probado con personas. Los topes vienen del plan; los tiempos reales los dirá el piloto.
* El verificador comprueba **resultados**, no el código del participante; el observador vigila que no se
  copien respuestas congeladas directamente.
* La condición JSON depende de las bibliotecas que se preinstalen (decisión del equipo en `protocolo.md`).
