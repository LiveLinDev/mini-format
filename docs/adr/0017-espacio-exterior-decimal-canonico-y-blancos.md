# ADR 0017. Espacio exterior, escape de elementos de lista, decimal canónico, valores por omisión, registros vacíos y conjunto de blancos

* Estado: **Propuesta (no vigente)**. No cambia SPEC 1.1 ni el comportamiento de ninguna implementación.
* Fecha: 2026-09-30 (auditoría V5)
* Especificación: [SPEC.md](../../SPEC.md) §3.4, §3.5, §6, §9
* Hallazgos de origen: D-1, D-2, D-4 y B-1 de la auditoría del núcleo, y D-10 y D-11 hallados al escribir las pruebas de propiedades

Este registro describe seis puntos donde la norma vigente y el comportamiento de las
implementaciones no coinciden del todo, o donde la norma calla. Son decisiones de norma:
ninguna se ha aplicado al código. Si se acepta alguna, hace falta una versión nueva de la
especificación (1.2), casos de conformidad escritos desde la regla, Python y TypeScript y
regenerar `js/mini.js` ([README](README.md)).

## Contexto y problema

### D-1. Cadenas con espacio exterior (y vacío en un campo opcional)

SPEC §3.5 recorta el espacio exterior de todo campo, elemento de lista y valor de cabecera, y
§9 exige `parse(dumps(o)) = o` para todo objeto canónico `o` válido. Pero el serializador acepta
cadenas con espacio exterior y las emite tal cual; al leerlas, el parser las recorta:

| Objeto | Texto emitido | Objeto leído |
|---|---|---|
| `id = " a"` | `␠a` | `"a"` |
| `id = "hola "` | `hola␠` | `"hola"` |
| `id = "\tx"`, NBSP, U+2028 | igual, sin protección | `"x"` |
| campo opcional `""` | campo vacío | `null` |
| `"a\rb"`, `"a\r\nb"` | `a\nb` | `"a\nb"` |
| lista `[" a", "b "]` | `␠a,b␠` | `["a", "b"]` |
| lista `[" "]` (opcional) | `␠` | `null` |

En ningún caso hay error ni aviso. Las pruebas de ida y vuelta existentes evitan el problema a
propósito (`.strip()` en `tests/test_mini.py`). Python y TypeScript se comportan igual.

### D-2. Elementos de lista que el serializador no puede escribir

`escape_element` solo protege la primera y la última posición del texto ya escapado. Un elemento
válido con espacio exterior delante de la comilla o del asterisco hace que `dumps` falle con un
código que no describe la causa:

| Elemento | Resultado de `dumps` |
|---|---|
| `' "a'` | E09 «unbalanced double quote» |
| `'a* '` | E08 «marker * not allowed in a plain list» |
| tupla con componente `' '` | E06 «tuple component is empty» |

Es la misma causa que D-1: el espacio exterior no sobrevive al recorte de §3.5, y la protección
de `"` y `*` se aplica antes de que ese recorte cambie lo que el parser ve.

### D-4. `decimal` no canónico en el serializador

§6 define el `decimal` canónico (sin ceros a la izquierda ni signo en el cero, conservando la
escala). El parser lo normaliza. El serializador, en cambio, escribe la cadena recibida:
`"007.50"` sale como `007.50` y `"-0.0"` como `-0.0`. El documento emitido no es estable:
`dumps(parse(t)) ≠ t` para un `t` emitido por el serializador, lo que contradice la segunda
cláusula de §9. §9 sí permite que el serializador acepte equivalentes no canónicos, pero no dice
en qué forma los escribe.

### D-10. Claves de cabecera con `default` rompen `dumps(parse(t)) = t`

El contrato puede declarar un `default` para una clave de cabecera (la SPEC solo menciona el valor por
omisión de `v`, que el serializador omite expresamente). Si el documento no trae la clave, el parser la
añade al objeto canónico con ese valor y el serializador la escribe: el texto emitido `p|n=0` se lee como
`{k: "es"}` y `dumps` de ese objeto da `p|n=0|k=es`, distinto del texto original (segunda cláusula de §9).
Ninguna familia oficial lo sufre (solo `v` tiene `default`), pero cualquier contrato propio sí. Hallado por
la prueba de propiedades `tests/test_nucleo_propiedades.py`, que por eso escribe siempre esas claves.

### D-11. Registros que solo tienen campos vacíos

Un registro cuyos campos se escriben todos vacíos es una línea en blanco, y §3.1 omite las líneas en blanco. Ocurre
con un contrato cuyo único campo del núcleo es una lista (o una tupla con un solo componente opcional) y un valor vacío:
`dumps` escribe una línea vacía y el parser la ignora (E04: el documento declara `n=1` y tiene 0 registros).
Con más campos pasa algo parecido en un campo de tupla de un solo componente opcional y valor null: el campo vacío se lee como
tupla vacía (E07 «tuple expects 1 components, got 0»). En ambos casos el serializador falla de forma visible (verifica su
propia salida), pero con un código que no describe la causa; §9 pide el código del parser y la línea de la entrada, y la
entrada es válida para el contrato. Hallado por `tests/test_nucleo_propiedades.py`, cuyos contratos generados evitan estos casos.

### B-1. Conjunto «whitespace» sin definir

§3.5 dice «whitespace» sin decir cuáles son los caracteres. Python recorta lo que `str.isspace()`
considera espacio y TypeScript reproduce esa lista a mano (`ts/src/codec.ts`: incluye U+001C a
U+001F, U+0085, U+00A0, U+1680, U+2000–U+200A, U+2028, U+2029, U+202F, U+205F y U+3000). Una
tercera implementación que use `\s` de JavaScript difiere en U+001C–U+001F y U+0085 (y en U+FEFF,
que `\s` sí recorta y `isspace` no).

## Alternativas consideradas

**Para D-1 y D-2 (mismo origen):**

1. **El serializador rechaza con E06** toda cadena que no sobreviviría a la lectura: espacio
   exterior, `\r` fuera de un salto `\n`, y cadena vacía en un campo opcional. Sin cambiar el
   formato, solo el conjunto de objetos aceptados por `dumps`; ningún documento existente cambia.
   D-2 desaparece: los elementos problemáticos tienen todos espacio exterior y se rechazan con
   un código que describe la causa.
2. **Definir un escape para el espacio** (por ejemplo `\s` o `\␠`) y hacer que el serializador lo
   use en los extremos. Conserva el objeto, pero añade una secuencia a §3.3: los lectores 1.1
   la rechazarían con E09, y cada documento nuevo con espacio exterior dejaría de ser legible
   por ellos.
3. **Solo documentar**: declarar en §3.5 y §9 que un valor `str` con espacio exterior no es un
   objeto canónico, sin cambiar el código. Es la alternativa más barata y deja el defecto
   silencioso.
4. **El serializador recorta en silencio.** Descartada: altera datos sin avisar.

**Para D-4:**

1. **El serializador normaliza** con la misma función que el parser (`007.50` → `7.50`), como
   permite §9 para los equivalentes no canónicos.
2. **El serializador rechaza** con E06 toda cadena decimal no canónica.

**Para D-10:**

1. **El serializador omite toda clave de cabecera igual a su `default`**, como ya hace con `v`.
   Hace estable el texto, pero un valor explícito igual al predeterminado deja de escribirse.
2. **El parser no añade los valores por omisión** al objeto canónico. Cambia el objeto canónico que
   hoy devuelven las dos implementaciones y varios casos de conformidad (`hdr-typed`, `hdr-unknown-keys`).
3. **La SPEC declara que `default` no es canónico** y que un contrato que lo use no cumple §9.

**Para D-11:**

1. **La SPEC declara no representables** los registros totalmente vacíos y las tuplas de un único componente opcional
   (un contrato que los admita es inválido, E20). Es la más simple y no cambia ningún documento válido.
2. **Escribir una marca para el registro vacío** (por ejemplo una línea `-`), lo que añade un elemento léxico nuevo.
3. **Dejarlo como está** y documentar que el serializador lo rechaza con el código del parser.

**Para B-1:**

1. **Fijar el conjunto actual**: los caracteres que `str.isspace()` considera espacio, listados
   uno a uno en la SPEC (sin depender de la versión de Unicode de cada lenguaje).
2. **Propiedad Unicode `White_Space`**: excluye U+001C–U+001F y cambiaría el comportamiento de
   las dos implementaciones.
3. **Solo ASCII** (espacio y tabulador): el más simple, pero dejaría de recortar NBSP y similares,
   que hoy se recortan.

## Decisión propuesta

* D-1 y D-2: alternativa 1 (rechazo con E06), complementada con la frase de la alternativa 3 en
  §3.5 («un valor con espacio exterior no es canónico»). Es la única que no cambia ningún
  documento válido ni exige un escape nuevo.
* D-4: alternativa 1 (normalizar al serializar): no rechaza objetos que hoy se aceptan y hace
  estable `dumps(parse(t)) = t`.
* B-1: alternativa 1 (fijar el conjunto actual con la lista explícita de puntos de código).
* D-11: alternativa 1 (declarar no representables esos contratos) y validar el caso al cargar el contrato (E20).
* D-10: alternativa 1 (omitir la clave igual a su `default` al serializar): extiende a todas las claves
  lo que el serializador ya hace con `v` y no cambia el objeto canónico.

## Compatibilidad

* Documentos existentes: ninguno cambia de significado con la propuesta. D-4 cambia el texto que
  emite `dumps` solo para decimales de entrada no canónica; los documentos ya emitidos siguen
  siendo válidos y se leen igual.
* Objetos: los que hoy `dumps` acepta con espacio exterior pasarían a ser error E06. Es un
  cambio visible para quien serialice cadenas sin recortar; hoy esos objetos ya pierden datos.
* Conformidad 1.1: los 376 casos vigentes no contienen ninguno de estos objetos.
* B-1 no cambia el comportamiento; solo lo escribe.

## Prueba de aceptación

Si se acepta, deben cumplirse y figurar en `conformance/generate.py` con la expectativa escrita
desde la regla (no calculada ejecutando código), en los tres ejecutores:

1. `dumps` de `" a"`, `"hola "`, `"\tx"`, NBSP, `"a\rb"` y de `""` en un campo opcional devuelve
   E06 con la línea del registro; lo mismo para los elementos de lista `' "a'`, `'a* '`, `' '` y el
   componente de tupla `' '`.
2. `dumps(parse(t)) = t` para un contrato con una clave de cabecera con `default` y un texto sin esa clave.
3. `dumps` de `"007.50"` es `7.50` y `dumps(parse(t)) = t` para todo `t` emitido por el serializador.
4. Un contrato cuyo único campo del núcleo admite el valor vacío (una lista, o una tupla de un componente opcional) se rechaza al cargarlo (E20).
5. Un caso por carácter del conjunto B-1 (recortado en cada extremo de un campo, de un elemento
   de lista y de un valor de cabecera) y uno por carácter vecino que no es espacio (U+200B, U+FEFF
   intermedio, U+180E, U+0086) que **no** se recorta.
6. Las pruebas `expectedFailure` de [tests/test_nucleo_propuestas.py](../../tests/test_nucleo_propuestas.py)
   dejan de ser fallos esperados y se convierten en pruebas ordinarias (si no, la suite avisa de
   un «éxito inesperado»).

## Evidencia

* Reproducción de D-1, D-2 y D-4: [tests/test_nucleo_propuestas.py](../../tests/test_nucleo_propuestas.py)
  (pruebas `expectedFailure` que afirman lo que §9 ya exige).
* Conjunto actual de blancos, fijado como comportamiento de referencia (no normativo) en
  [tests/test_nucleo_propuestas.py](../../tests/test_nucleo_propuestas.py) y
  [ts/test/defectos.test.ts](../../ts/test/defectos.test.ts).
* Código: `escape_element` y `strip_toks` en [src/minifmt/codec.py](../../src/minifmt/codec.py);
  `encode_scalar` en [src/minifmt/values.py](../../src/minifmt/values.py);
  [ts/src/codec.ts](../../ts/src/codec.ts).
