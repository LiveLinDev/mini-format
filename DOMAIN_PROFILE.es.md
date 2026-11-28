# Perfil de dominio generado: mini-domain/1

[English](DOMAIN_PROFILE.md) · [Guía de integración](BUILD_GUIDE.es.md)

Este documento especifica el perfil JSON generado por la versión 1.2.3 del
software. No sustituye la [SPEC 1.1 del núcleo](SPEC.es.md). Las familias clásicas
y sus pruebas mantienen sintaxis y parsers propios. El perfil generado se procesa
con el parser de `mini build` o con `minifmt.domain`.

## Contrato

`contract.json` contiene `profile: "mini-domain/1"`, prefijo, versión `1`, esquema
recursivo, `record_path` (lista de claves de objeto o null) y `schema_id`. La huella
son los primeros doce caracteres hexadecimales SHA-256 del JSON compacto UTF-8
con, en este orden, `profile`, `prefix`, `version`, `schema`, `record_path`.
El orden de campos importa; las cantidades informativas de muestras no cambian
la identidad. Usa contratos de una construcción confiable: la huella es un
control de compatibilidad, no autenticación criptográfica.

Tipos: object, array, string, integer, number, boolean y `json` abierto. Los
objetos tienen campos ordenados `name`, `optional`, `schema`; las listas, `items`;
`nullable` permite null. Las claves desconocidas de objetos son errores. Un nodo
JSON abierto conserva deliberadamente cualquier JSON, incluidas claves nuevas.

La inferencia combina todos los documentos completos. Los miembros ausentes se
vuelven opcionales; null observado permite null. Campos sólo null, elementos de
listas vacías y tipos heterogéneos quedan como JSON abierto. Mezclas numéricas
amplían integer a number. Valores constantes observados nunca se convierten en
valores predeterminados permanentes del dominio.

## Documento transmitido

UTF-8, líneas físicas separadas por LF, con un LF final opcional:

```text
phone|v=1|n=2|h=<schema_id>
<celdas del registro 1>
<celdas del registro 2>
```

Cabecera: prefijo y `v`, `n`, `h` obligatorios; `m`, `d` y `e` opcionales.
Claves desconocidas o duplicadas producen error. `n` coincide exactamente con los
registros. Una huella distinta falla: no se intenta adivinar otro esquema.

Las filas usan celdas separadas por `|`, sin repetir una etiqueta por registro.
Objetos obligatorios no-nullables se aplanan recursivamente en orden del esquema;
objetos vacíos obligatorios se reconstruyen desde éste. Objetos opcionales o
nullables conservan una celda posicional. Registros escalares, listas, JSON abierto
u objetos nullables se representan en una celda completa. Una fila sin columnas
transmitidas se escribe `-`.

Escape de cada celda: `\\` representa barra inversa; `\|`, separador; `\n`, salto
de línea; `\r`, retorno. Otros escapes son inválidos. Los espacios son datos.

## Valores de celda

`?` significa miembro opcional ausente; `~`, null. No equivalen a cadena vacía,
cero o false. Las cadenas normalmente no llevan comillas. Cadena vacía, `?` o
`~` literales, y cadenas que empiezan por comillas se codifican como cadenas JSON;
después se aplica el escape exterior. Se rechazan números no finitos y claves
JSON duplicadas. Los valores numéricos no se convierten a otro tipo.

Objetos anidados son listas JSON posicionales en orden del esquema; `{}` marca
un miembro opcional ausente dentro de esas listas. Un nodo JSON abierto envuelve
su valor no-null como `[valor]`, evitando confundir un objeto vacío real con
ausencia. Las listas transforman sus elementos recursivamente; null sigue siendo
null. Primero se codifica JSON y después se escapa la celda exterior.

Si la colección está dentro de un objeto, `m` transmite todo el envoltorio como
JSON posicional con la colección sustituida por `[]`. Los metadatos viajan en el
documento, no se recuperan de las muestras. Listas raíz no llevan `m`; otras
raíces tienen exactamente un registro y tampoco llevan `m`.

## Optimización explícita por documento

`d` contiene JSON `[[indiceColumna, celdaCodificada], ...]`, índices desde cero.
Esas columnas se omiten de todas las filas y se restauran desde la cabecera.
Se calculan con el documento actual y se validan contra el mismo esquema.

`e` contiene JSON `[[indiceColumna, [celdaCadenaCodificada, ...]], ...]`. Cada
columna con diccionario sigue presente en la fila, mediante un índice decimal
desde cero. Sólo se permite para columnas string. Los diccionarios completos se
transmiten: no hay vocabulario oculto aprendido de las muestras. Una columna no
puede estar en `d` y `e` a la vez. Índices inválidos o duplicados producen error.
El JSON de cabecera recibe el mismo escape exterior.

El codificador aplica estas opciones cuando su estimación de bytes es favorable.
`encode(valor, contrato, shared=False)` desactiva `d`;
`encode(valor, contrato, dictionaries=False)` desactiva `e`. Pasa ambos argumentos
para desactivar las dos optimizaciones. Ahorrar bytes no garantiza ahorrar tokens
con cualquier tokenizador.

## Filas compactas para la respuesta del modelo

Para una lista raíz de objetos planos con campos escalares obligatorios y sin
nulos, puedes pedir que el modelo devuelva solo las filas. Elige una columna de
texto para el final e indica cuántas filas debe recibir la aplicación.

El kit recomienda una columna en `setup.json` bajo `compact_last_text_field`
cuando la muestra admite filas compactas. La coloca al final para ahorrar
comillas y escapes. Puedes pasar esa recomendación al flujo.

```python
data = flow.run(generate, tarea, expected_records=20, last_text_field="titulo")
```

En el `workflow.mjs` generado usa `{expectedRecords: 20, lastTextField: "titulo"}`.
El flujo valida las columnas, los tipos y el recuento con el contrato del kit.
`last_run["mini"]` en Python y `lastRun.mini` en Node contienen el documento
`.mini` con cabecera. `encode_rows` y `decode_rows` permiten usar las filas
directamente con el contrato. Para elegir el modo, mide el prompt, la respuesta y
los reintentos con tu modelo y tus datos.

Si la aplicación ya conoce columnas como el ID y la tarea conserva el orden de
entrada, pásalas por fila. El modelo escribe únicamente las columnas restantes.
El flujo valida los valores conocidos y los reincorpora por posición antes de
entregar el JSON completo.

```python
data = flow.run(
    generate, tarea, expected_records=2, last_text_field="titulo",
    known_rows=[{"id": 91}, {"id": 7}],
)
```

En Node, usa `{expectedRecords: 2, lastTextField: "titulo", knownRows: [{id: 91}, {id: 7}]}`.
Cada fila conocida debe tener las mismas columnas. Conserva los IDs en la
respuesta del modelo para tareas que puedan reordenar las filas.

Para las columnas planas de texto, enteros y booleanos, el prompt en español
lista una vez las columnas que debe generar el modelo y muestra cómo escribir
una barra inversa literal. Si esperas de una a 24 filas y usas `known_rows`,
el prompt agrupa los valores por línea y muestra un ejemplo con el orden de
las columnas. Si queda un solo campo, pide una cadena JSON por fila. Al comparar
con JSON o CSV, cuenta la instrucción, la respuesta y los reintentos hasta
obtener el JSON correcto.

Para 25 a 48 filas con dos campos de texto pendientes, el flujo en español pide
un array JSON por línea. Así los espacios de un campo se conservan dentro de
ese campo. El toolkit valida ambos textos y restaura los campos conocidos antes
de devolver el JSON.

Para una fila con dos campos de texto pendientes, el flujo en español puede
pedir una fila CSV compacta. Usa las cadenas JSON separadas por espacios cuando
la tarea incluye secuencias de escape distintas de las comillas. En ambos casos
valida el resultado, repone los campos conocidos y guarda el documento `.mini`.

### Filas posicionales con esquema del proveedor

Para las mismas listas planas, `flow.run_positional(generate, tarea, expected_records=20)`
pide un array JSON de filas sin claves y reconstruye los objetos con su nombre
de campo. `generate(prompt, schema)` envía el esquema al proveedor. Por ejemplo,
en Ollama se usa como valor de `format`. En Node el método equivalente es
`flow.runPositional(generate, tarea, {expectedRecords: 20})`. El flujo comprueba
los tipos y las cantidades y guarda un documento `.mini` validado en el historial.

## Transporte compacto de JSON existente

`minifmt.transport.dumps(objeto, count=contador)` elige la representación de
menor costo entre JSON compacto, filas con contrato compacto y secciones
tabulares. Las secuencias, valores constantes, grupos y fragmentos comunes se
incluyen solo si reducen el conteo. `loads(texto)` reconstruye el JSON y puede
validarlo con un contrato de dominio. Esta ruta sirve para preparar datos que
la aplicación ya tiene.

En tablas de valores simples, el encabezado puede declarar una secuencia de
enteros con su inicio y paso. El descodificador repone esos valores en el orden
de las filas.

```sh
python -m minifmt.transport encode datos.json --tokenizer o200k_base > datos.txt
python -m minifmt.transport decode datos.txt
```

Sin tokenizador se minimizan bytes UTF-8. Para elegir por tokens desde Python,
pasa una función que devuelva el conteo de tu modelo. El CLI necesita
`tiktoken` para `--tokenizer`.

## Validación y evolución

Se comprueban identidad, escapes, columnas, tipos, nullabilidad, campos requeridos,
envoltorio y cantidad de registros. Los errores exponen código estable `D_*`,
línea física y ruta JSON. `diagnose` distingue líneas recuperables e inválidas.
`repair` corrige envoltorios de transporte, incluido el encabezado Markdown
exacto del prompt del contrato cuando aparece antes del documento.
`apply_replacements` incorpora líneas corregidas externamente y valida todo el
documento.

Si la primera respuesta del modelo llega como un array u objeto JSON completo,
el flujo habitual puede validarla con el mismo contrato y el recuento esperado
y convertirla a .mini localmente. El historial conserva la respuesta original
como JSON. Si el proveedor señala un corte, el flujo prioriza esa señal.

No se ignoran campos nuevos silenciosamente. Reconstruye en otra carpeta con
ejemplos representativos y distribuye prompt, contrato y parser juntos. Validar
estructura no demuestra veracidad del modelo ni cumplimiento de reglas del negocio.
