# Especificación .mini

**Versión:** 1.0 · **Fecha:** 2026-09-01 · **Estado:** Estable · **Licencia:** MIT
**Autores:** Adrián E. J. Palma Obispo, Erick J. Palomino Santa Cruz (Universidad Peruana de Ciencias Aplicadas)

---

## 1. Resumen

`.mini` es una notación de texto posicional, orientada a líneas y bifurcable para
salidas estructuradas producidas por modelos generativos de lenguaje en **dominios
cerrados**. Un documento `.mini` es una línea de cabecera que nombra un *contrato*
(un prefijo de familia) y declara el recuento de registros, seguida de exactamente
un registro por línea cuyos campos están separados por `|` y cuyo significado lo da
la posición. Como emisor y receptor comparten el contrato, el documento nunca repite
nombres de campo, llaves, corchetes, comillas ni indentación; su coste estructural es
el mínimo necesario para mantener cada registro independientemente validable y
convertible de forma determinista a un objeto JSON canónico.

`.mini` no es un formato único sino una **familia de contratos** gobernada por un
protocolo de bifurcación. Cualquier dominio orientado a registros — ítems de
evaluación, tarjetas, rúbricas, ítems de encuesta, casos de prueba, eventos de log,
anotaciones de entidades, filas de catálogo, salidas de clasificación, historias de
usuario — obtiene su propio contrato sin escribir un parser: la implementación de
referencia interpreta el contrato.

## 2. Conformidad

Las palabras clave MUST, MUST NOT, SHOULD y MAY se interpretan como en RFC
2119. Un **parser conforme** acepta todo documento válido bajo un contrato,
rechaza todo documento inválido con al menos uno de los códigos de error de §8, y
produce el objeto canónico de §7. Un **serializador conforme** produce, para cada
objeto canónico válido bajo un contrato, un documento que el parser devuelve a un
objeto igual (§9, ida y vuelta). Una **familia conforme** satisface los invariantes
de §10.

## 3. Estructura léxica

### 3.1 Codificación y líneas

Un documento es texto UTF-8. Los parsers MUST ignorar una marca de orden de bytes
inicial y opcional. Las líneas se separan con LF (U+000A); los parsers MUST ignorar
un CR (U+000D) inmediatamente anterior a un LF. Las líneas vacías o que solo contienen
blancos no son significativas y MUST omitirse. La primera línea significativa es la **cabecera**;
cada línea significativa siguiente es un **registro**.

### 3.2 Caracteres estructurales

| Carácter | Papel | Alcance |
|---|---|---|
| `\|` | separador de campos | cabecera y registros |
| *separador de lista* (`,` por defecto; un carácter fijado por el contrato) | separa elementos de una lista, lista marcada o tupla | solo dentro de campos de tipo lista |
| `*` | marcador de selección | solo como último carácter de un elemento de lista |
| `\` | carácter de escape | en todas partes |
| `"` | delimitador de elemento entrecomillado | solo como primer carácter de un elemento de lista |
| `=` | separador clave/valor | entradas de cabecera, primera ocurrencia no escapada |

Ningún otro carácter tiene significado estructural. Los dos puntos, corchetes,
llaves, espacios y tabuladores son contenido literal; una comilla que no sea el
primer carácter de un elemento de lista es literal.

### 3.3 Secuencias de escape

| Secuencia | Denota |
|---|---|
| `\|` | una barra vertical literal |
| `\,` (o `\<sep>` para el separador del contrato) | un separador de lista literal |
| `\*` | un asterisco literal (necesario solo cuando un elemento terminaría en `*`) |
| `\"` | una comilla literal (necesaria solo cuando un elemento empezaría por `"`) |
| `\\` | una barra invertida literal |
| `\n` | un salto de línea dentro de un valor |

Los parsers MUST reconocer las secuencias de escape en toda posición. Un generador MUST escapar
`|`, `\` y los saltos de línea en cada valor, y MUST proteger el separador de lista
y un `*` final dentro de elementos de lista, ya sea con los escapes de arriba o con
comillas (§3.4). Escapar el separador de lista en un campo escalar es innecesario
pero inofensivo (el sobre-escape es idempotente). Una barra invertida seguida de
cualquier otro carácter, o una barra invertida al final, es un error (E09).

### 3.4 Elementos de lista entrecomillados

Un elemento de lista MAY entrecomillarse con comillas dobles, estilo CSV: `"impacto, justicia
y evidencia"*`. Dentro de las comillas el separador de lista y `*` son literales y una
comilla doble `""` denota una comilla; el marcador de selección, si lo hay, sigue a
la comilla de cierre (`"…"*`) o, equivalentemente, la precede inmediatamente
(`"…*"`); un asterisco literal en esa posición se escribe `\*`. Los escapes de barra
invertida siguen activos dentro de las comillas (`|` y `\` aún deben escaparse). Una
comilla sin cerrar, o texto entre la comilla de cierre y el siguiente separador, es
un error (E09). Entrecomillar y escapar son notaciones equivalentes del mismo valor;
el serializador canónico emite la forma escapada.

### 3.5 Blancos

Los blancos iniciales y finales de un campo, de un elemento de lista y de un valor
de cabecera no son significativos y MUST recortarse. Los blancos internos se preservan.
Los campos escalares nunca van entrecomillados.

## 4. Gramática

```
document   ::= header ( LF record )* LF?
header     ::= prefix ( "|" entry )*
entry      ::= key "=" value
prefix     ::= [A-Za-z] [A-Za-z0-9_-]*
key        ::= [A-Za-z_] [A-Za-z0-9_]*
record     ::= value ( "|" value )*
value      ::= ( char | escape )*                 -- may be empty
list       ::= ( element ( SEP element )* )?       -- interpretation of a list-typed value
element    ::= ( bare | quoted ) "*"?
bare       ::= value                               -- must not start with an unescaped '"'
quoted     ::= '"' ( qchar | '""' | escape )* '"'
qchar      ::= any Unicode scalar except '"', "|", "\", LF
escape     ::= "\" ( "|" | SEP | "*" | '"' | "\" | "n" )
char       ::= any Unicode scalar except "|", "\", LF
```

`SEP` es el separador de lista del contrato. La gramática es regular a nivel de
línea: un registro se reconoce con una sola pasada de izquierda a derecha que
resuelve escapes y divide por `|` no escapados; un campo de tipo lista se divide
después por `SEP` no escapados. No se necesita anticipación más allá de un carácter,
así que el análisis es determinista y lineal en la longitud de la línea.
## 5. Cabecera

La cabecera es `prefix|key=value|key=value…`.

* `prefix` nombra el contrato (familia). MUST coincidir con un contrato registrado.
* `n` MUST estar presente y MUST ser igual al número de líneas de registro (E03/E04).
* `v` MAY estar presente y nombra la versión del contrato (por defecto 1).
* Las demás claves las tipifica el contrato (escalar, lista o tupla). Las claves
  desconocidas se aceptan y se conservan como strings, lo que permite a los
  productores adjuntar procedencia (modelo, fecha, idioma, tema) sin cambiar el
  contrato.
* Una clave de cabecera MAY actuar como **clave de recuento**: un campo de lista
  cuya entrada de contrato declara `count_key: "k"` MUST tener exactamente `k`
  elementos en cada registro (E07). Esto convierte una colisión de delimitador
  dentro de una lista en un error detectable.

## 6. Registros y tipos de campo

Un contrato define una lista ordenada de campos **nucleares** seguida de una lista
ordenada de campos de **extensión**. Un registro MUST contener cada campo nuclear
(E05) y MAY contener un prefijo de los campos de extensión; las extensiones
ausentes son null. Un registro MUST NOT contener más campos que los que declara el
contrato (E05).

| Tipo | Forma textual | JSON canónico | Notas |
|---|---|---|---|
| `str` | texto literal | string | |
| `int` | `-?[0-9]+` | integer | `min`/`max` opcionales (E13) |
| `float` | número JSON | number | los valores enteros MAY omitir `.0` |
| `bool` | `true` / `false` | boolean | `1`/`0` aceptados a la entrada |
| `enum` | uno de los valores declarados | string | E10 en caso contrario |
| `list<T>` | `e1,e2,…` | array | aridad `min`/`max`/`count_key` (E07) |
| `mlist<T>` | `e1*,e2,…` | array **más** una clave hermana `selected` | regla del marcador: `exactly_one` (por defecto), `at_least_one`, `at_most_one`, `any` (E08) |
| `tuple(a:T,b:U,…)` | `a,b,…` | objeto `{a:…, b:…}` | aridad fija (E07); un nivel de anidamiento sin sintaxis de anidamiento |

Un campo vacío denota null y solo es válido para campos opcionales (E06). Un campo
declarado `unique` MUST NOT repetir su valor dentro de un documento (E11).

La **lista marcada** es el modismo que reemplaza a un campo "respuesta" separado: el
elemento seleccionado lleva un sufijo de un carácter, lo que mantiene la selección
pegada a su contenido. Para `exactly_one`/`at_most_one` el valor canónico de
`selected` es un índice (o null); para `at_least_one`/`any` es una lista ascendente
de índices.

## 7. Objeto canónico

Un parser MUST producir:

```json
{ "prefix": "<prefix>",
  "header": { "n": <int>, "v": <int>, ...typed header entries... },
  "<records_key>": [ { "<field>": <value>, ... }, ... ] }
```

`records_key` la declara el contrato (p. ej. `items`, `cases`). Una lista marcada
`options` con clave de selección `correct` produce dos claves hermanas
`"options": [...]` y `"correct": <index>`. Una tupla produce un objeto anidado.
Los números canónicos se comparan numéricamente (`-1` ≡ `-1.0`).

## 8. Validación y códigos de error

La validación es **local** (cada registro se comprueba en su propia línea) y
**global** (recuento y unicidad). Un parser MUST reportar el número de línea 1-based
de cada error. Los parsers estrictos recogen todos los errores y rechazan el
documento; los parsers tolerantes devuelven los registros válidos junto con la lista
de errores, lo que permite la recuperación parcial de salidas generadas largas.

| Código | Condición |
|---|---|
| E01 | falta la línea de cabecera |
| E02 | el prefijo de la cabecera no coincide con el contrato |
| E03 | la cabecera no trae `n` |
| E04 | número de líneas de registro ≠ `n` |
| E05 | el registro tiene menos campos que el núcleo, o más que núcleo + extensiones |
| E06 | el valor escalar no coincide con su tipo, o un valor requerido está vacío |
| E07 | aridad de lista / tupla fuera de `min`/`max`, o ≠ `count_key`, o ≠ tamaño de tupla |
| E08 | el recuento de marcadores viola la regla de la lista marcada |
| E09 | secuencia de escape inválida o barra invertida al final |
| E10 | valor fuera de la enumeración |
| E11 | valor duplicado en un campo `unique` |
| E12 | entrada de cabecera malformada o requerida ausente |
| E13 | valor numérico fuera de `min`/`max` |
| E20 | el contrato mismo es inválido |
| E21 | invariante de familia violado |
## 9. Ida y vuelta

Para cada contrato *C* y cada objeto canónico *o* válido bajo *C*:
`parse(dumps(o, C), C) = o` y `dumps(parse(t, C), C) = t` para cada documento *t*
emitido por el serializador. Esta propiedad — no la compacidad — es el criterio de
aceptación de una familia `.mini`: una compresión que no hace ida y vuelta es una
abreviatura, no una serialización.

## 10. Protocolo de bifurcación

Una **familia** es un contrato nuevo derivado de un padre. Conserva la analizabilidad
por construcción si satisface cinco invariantes, todos comprobables por máquina por
el registro de referencia (`mini check-forks`):

| # | Invariante | Regla |
|---|---|---|
| I1 | Línea local | una línea = un registro completo e independientemente válido |
| I2 | Cabecera | prefijo y `n` obligatorios; las claves de cabecera requeridas del padre siguen requeridas |
| I3 | Núcleo estable | la lista de campos de la hija empieza con la lista completa de campos del padre (núcleo + extensiones), mismos nombres, mismo orden, mismos tipos, mismo separador de lista |
| I4 | Extensión al final | los campos nuevos se añaden tras los heredados y son opcionales |
| I5 | Ida y vuelta | la hija incluye fixtures (`valid.mini` ↔ `canonical.json`, `escaping.mini`, casos negativos) que pasan §9 |

Consecuencias. Un parser del padre lee el prefijo heredado de cada registro de la
hija (despacho por prefijo, luego truncado a la aridad del padre); un parser de la
hija lee documentos del padre (las extensiones ausentes son null). Reordenar,
retipificar o eliminar un campo heredado es un cambio incompatible y MUST publicarse
bajo un **prefijo nuevo**, nunca como una versión nueva del mismo prefijo. El
crecimiento compatible (añadir extensiones o claves de cabecera opcionales)
incrementa `v`.

Una familia se publica como una carpeta `forks/<prefix>/` con `contract.json`,
`README.md` y `fixtures/`. El bloque de especificación que un modelo generativo
necesita para producir la familia se deriva mecánicamente del contrato
(`mini prompt <prefix>`); una familia, por tanto, consiste en datos, no código.

## 11. Fundamento del diseño

* **Posición en vez de nombres.** En un dominio cerrado ambos lados conocen el
  esquema; repetir `"statement"`, `"options"`, `"correct"` en cada registro es
  sobrecarga pura. Llevar el esquema al contrato, declarado una vez, es lo que hace
  que el coste por registro se acerque al contenido mismo.
* **Un byte, un papel.** `|` nunca aparece dentro de listas, el separador nunca
  aparece a nivel de campo, y `*` es solo un sufijo. Esta estricta separación de
  niveles es lo que mantiene la gramática regular y el parser de una pasada.
* **Dos protecciones equivalentes para el separador de lista.** La versión 0 (2026-06)
  usaba solo comillas estilo CSV; la validación generativa mostró que un modelo más
  débil a veces omitía las comillas y producía colisiones silenciosas de delimitador. Un
  borrador de la versión 1 reemplazó las comillas solo por escapes de barra invertida;
  una segunda ronda de validación mostró que la misma clase de modelo ignora un escape
  desconocido pero aplica con fiabilidad las comillas CSV, que ha visto en enormes
  cantidades de datos de entrenamiento. La versión 1.0, por tanto, acepta ambas
  notaciones (§3.3, §3.4), emite canónicamente la forma escapada, y añade la clave de
  recuento de §5, que convierte cualquier colisión residual en un error de aridad
  detectable en vez de una corrupción silenciosa.
* **Marcador como sufijo.** La selección viaja con su contenido, lo que evita
  desalineaciones índice/contenido durante la generación y permite la verificación local.
* **Evolución solo por añadido.** La misma disciplina de los protocolos binarios y los
  esquemas evolucionables (campos nuevos solo al final; los lectores ignoran colas
  desconocidas) da compatibilidad hacia adelante y hacia atrás sin negociación.

## 12. Limitaciones (por diseño)

`.mini` no representa jerarquías profundas, relaciones muchos-a-muchos dentro de un
registro, registros heterogéneos en un documento, o esquemas que evolucionan durante
una conversación. Las relaciones se expresan con el patrón relacional (una segunda
familia cuyos registros referencian identificadores de la primera, p. ej. registros
`card` que apuntan a ítems `a`) o con campos `tuple` de un nivel. Los estándares
formales de interoperabilidad (p. ej. QTI para evaluación) siguen siendo el destino
del objeto canónico, no del formato de transporte. Los ahorros de tokens dependen del
tokenizador y del idioma; el benchmark de referencia reporta el tokenizador, el corpus,
los serializadores y la línea base de cada figura.
