# Especificación .mini

**Versión:** 1.1 · **Fecha:** 2026-09-17 · **Estado:** Estable; reemplaza a 1.0 y mantiene válido todo documento 1.0 (§13) · **Licencia:** MIT
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
objeto igual (§9, ida y vuelta), y rechaza todo objeto que no sea válido bajo el
contrato con el código de error de §9. Una **familia conforme** satisface los
invariantes de §10. La suite de conformidad (`conformance/`) fija el resultado
esperado de cada regla; las decisiones de diseño que sustentan las reglas, con su
evidencia, se registran en `docs/adr/`.

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
| `\,` | una coma literal, sea cual sea el separador de lista (por tanto, un separador de lista literal cuando el separador es `,`) |
| `\<sep>` para el separador del contrato | un separador de lista literal |
| `\*` | un asterisco literal (necesario solo cuando un elemento terminaría en `*`) |
| `\"` | una comilla literal (necesaria solo cuando un elemento empezaría por `"`) |
| `\\` | una barra invertida literal |
| `\n` | un salto de línea dentro de un valor |

Los parsers MUST reconocer las secuencias de escape en toda posición. Un generador MUST escapar
`|`, `\` y los saltos de línea en cada valor, y MUST proteger el separador de lista
y un `*` final dentro de elementos de lista, ya sea con los escapes de arriba o con
comillas (§3.4). Escapar el separador de lista en un campo escalar es innecesario
pero inofensivo (el sobre-escape es idempotente). `\,` es válido en todo contrato,
también cuando el separador de lista es otro carácter (sobre-escapar una coma nunca
invalida un documento); `\<sep>` solo es válido para el separador propio del
contrato, de modo que `\;` en un contrato cuyo separador es `,` es E09. Una barra
invertida seguida de cualquier otro carácter, o una barra invertida al final, es un
error (E09).

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

Un elemento de lista vacío puede escribirse sin comillas (`a,,b`, o con un
separador final como en `a,`) o entrecomillado (`""`); ambas formas denotan la
cadena vacía. Un campo que contiene un único elemento vacío sin comillas no se
distingue de un campo vacío (§6), por lo que el serializador canónico escribe todo
elemento que sea la cadena vacía como `""`: `[""]` se emite como `""` y vuelve a
analizarse como `[""]`. Es el único caso en que el serializador emite comillas.

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
escape     ::= "\" ( "|" | "," | SEP | "*" | '"' | "\" | "n" )
char       ::= any Unicode scalar except "|", "\", LF
```

Formas léxicas de los tipos escalares (§6), aplicadas al valor una vez resueltos
los escapes y recortados los blancos exteriores:

```
int        ::= "-"? DIGIT+
float      ::= "-"? DIGIT+ ( "." DIGIT+ )? ( ( "e" | "E" ) ( "+" | "-" )? DIGIT+ )?
bool       ::= "true" | "false" | "1" | "0"
date       ::= DIGIT DIGIT DIGIT DIGIT "-" DIGIT DIGIT "-" DIGIT DIGIT
decimal    ::= "-"? DIGIT+ ( "." DIGIT+ )?
DIGIT      ::= "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"   -- solo ASCII
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
* Una clave MUST NOT aparecer más de una vez en la cabecera. Cada aparición
  repetida es E12; cuenta la primera aparición (un parser tolerante conserva su
  valor).
* Un valor de una clave tipada que no coincide con su tipo se reporta en la línea
  de cabecera con el código de esa violación (E06, E07, E10, E13), igual que en un
  registro. En particular, `n=abc` o un `n=` vacío es E06, no E03: E03 significa que
  `n` no está. Si `n` está presente pero es inválido, no se comprueba el recuento de
  registros (no hay E04). E12 queda para entradas sin `=`, claves requeridas
  ausentes y claves repetidas.

## 6. Registros y tipos de campo

Un contrato define una lista ordenada de campos **nucleares** seguida de una lista
ordenada de campos de **extensión**. Un registro MUST contener cada campo nuclear
(E05) y MAY contener un prefijo de los campos de extensión; las extensiones
ausentes son null. Si `v` de la cabecera es menor o igual que la versión del
contrato, el registro MUST NOT contener más campos que los declarados (E05). Si la
cabecera del mismo prefijo declara un `v` mayor, el parser MUST validar léxicamente
el registro completo, decodificar el prefijo de campos conocido e ignorar únicamente
los campos finales desconocidos.

| Tipo | Forma textual | JSON canónico | Notas |
|---|---|---|---|
| `str` | texto literal | string | |
| `int` | `-?[0-9]+` | integer | `min`/`max` opcionales (E13); dígitos ASCII; se admiten ceros a la izquierda; sin `+` |
| `float` | número JSON | number | los valores enteros MAY omitir `.0`; se admiten ceros a la izquierda; `+1`, `.5`, `1.`, `NaN`, `Infinity` son E06 |
| `bool` | `true` / `false` | boolean | `1`/`0` aceptados a la entrada; ninguna otra forma (`yes`, `y`, `t`, `True`) se acepta (E06) |
| `enum` | uno de los valores declarados | string | E10 en caso contrario |
| `date` | `AAAA-MM-DD` | string | un día existente del calendario gregoriano proléptico, de 0001-01-01 a 9999-12-31 (E06); `min`/`max` opcionales como `"AAAA-MM-DD"` (E13) |
| `decimal` | `-?[0-9]+(\.[0-9]+)?` | string | número exacto en base 10, sin exponente (E06); `min`/`max` opcionales como cadenas decimales o enteros, comparados exactamente (E13) |
| `list<T>` | `e1,e2,…` | array | aridad `min`/`max`/`count_key` (E07) |
| `mlist<T>` | `e1*,e2,…` | array **más** una clave hermana `selected` | regla del marcador: `exactly_one` (por defecto), `at_least_one`, `at_most_one`, `any` (E08) |
| `tuple(a:T,b:U,…)` | `a,b,…` | objeto `{a:…, b:…}` | aridad fija (E07); un nivel de anidamiento sin sintaxis de anidamiento |

Un campo vacío denota null y solo es válido para campos opcionales (E06). Esto
vale para todo tipo: una lista, lista marcada o tupla opcional vacía es null (en una
lista marcada, ambas claves hermanas son null). Una lista o lista marcada
*requerida* vacía denota la lista vacía, sujeta a `min` y a la regla del marcador
(E07, E08); una tupla requerida vacía es E07. Por tanto, el valor canónico de una
lista opcional vacía es null, nunca `[]`. Un campo declarado `unique` MUST NOT
repetir su valor dentro de un documento (E11).

Los elementos de listas y tuplas se decodifican con su tipo de elemento o de
componente. Un elemento de lista vacío es la cadena vacía para elementos `str` y un
error de tipo para cualquier otro tipo de elemento (E06; E10 para elementos
`enum`). Un componente de tupla vacío es null si el componente es opcional y E06 en
caso contrario.

`date` y `decimal` viajan como cadenas en el objeto canónico para que ninguna
implementación los convierta mediante coma flotante binaria o una zona horaria. El
`date` canónico es el propio texto. El `decimal` canónico elimina los ceros a la
izquierda de la parte entera y el signo de un valor cero, y conserva todos los
dígitos fraccionarios, porque la escala puede ser significativa (`007.50` →
`"7.50"`, `-0.0` → `"0.0"`). En un contrato, `min`/`max` de un `date` son cadenas
`"AAAA-MM-DD"` y los de un `decimal` son cadenas decimales o enteros con valor
absoluto menor que 2^53; cualquier otro límite invalida el contrato (E20).

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

`records_key` la declara el contrato (p. ej. `items`, `cases`). Los valores de
campos `date` y `decimal` son cadenas (§6). Una lista marcada
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
| E05 | el registro tiene menos campos que el núcleo, o tiene campos excedentes sin declarar una versión de documento posterior a la del contrato |
| E06 | el valor escalar (en un registro o en una entrada de cabecera tipada) no coincide con su tipo (§4, §6), o un valor requerido está vacío |
| E07 | aridad de lista / tupla fuera de `min`/`max`, o ≠ `count_key`, o ≠ tamaño de tupla |
| E08 | el recuento de marcadores viola la regla de la lista marcada |
| E09 | secuencia de escape inválida o barra invertida al final |
| E10 | valor fuera de la enumeración |
| E11 | valor duplicado en un campo `unique` |
| E12 | entrada de cabecera sin `=`, clave de cabecera requerida ausente o clave de cabecera repetida |
| E13 | valor numérico, decimal o de fecha fuera de `min`/`max` |
| E20 | el contrato mismo es inválido |
| E21 | invariante de familia violado |
## 9. Ida y vuelta

Para cada contrato *C* y cada objeto canónico *o* válido bajo *C*:
`parse(dumps(o, C), C) = o` y `dumps(parse(t, C), C) = t` para cada documento *t*
emitido por el serializador. Esta propiedad — no la compacidad — es el criterio de
aceptación de una familia `.mini`: una compresión que no hace ida y vuelta es una
abreviatura, no una serialización.

Un serializador MUST NOT emitir un documento que el parser rechazaría. Ante un
objeto que no es válido bajo el contrato, MUST fallar con un error que lleve el
código que el parser reporta para la misma violación (§8) y la línea física que la
entrada ocuparía en la salida: 1 para la cabecera e *i* + 2 para el registro en la
posición *i* (base 0). Por ejemplo, un valor requerido nulo o ausente es E06, un
valor fuera de la enumeración E10, un valor fuera de `min`/`max` E13, una lista de
longitud incorrecta E07, una selección que incumple la regla del marcador o no es
un índice válido E08, un valor `unique` repetido E11 y una clave de cabecera
requerida ausente E12. Un serializador MAY aceptar equivalentes no canónicos de un
valor válido (por ejemplo `[]` para una lista opcional vacía, que escribe como campo
vacío y que vuelve a analizarse como null).

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

Consecuencias. Un parser de versión anterior lee documentos posteriores del
**mismo prefijo** cuando la cabecera declara un `v` mayor: valida la línea completa,
decodifica los campos que conoce e ignora la cola desconocida. Una bifurcación usa
otro prefijo: el registro se analiza primero con el contrato hijo elegido por el
despacho del registro y luego la aplicación MAY proyectar su prefijo heredado al
esquema del padre; esto no equivale a analizar directamente el documento hijo con
el contrato padre. El contrato hijo también admite registros sin sus extensiones
opcionales cuando se emiten bajo el prefijo hijo. Reordenar, retipificar o eliminar
un campo heredado es un cambio incompatible y MUST publicarse bajo un **prefijo
nuevo**, nunca como una versión nueva del mismo prefijo. El crecimiento compatible
(añadir extensiones o claves de cabecera opcionales) incrementa `v`.

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
* **Decisiones registradas.** Cada regla anterior que implicó una elección (contrato
  posicional, escapes y comillas, marcador, clave de recuento, modo tolerante,
  bifurcación, cola de versión, las precisiones de 1.1 y los tipos `date`/`decimal`)
  tiene un registro de decisión de arquitectura con su contexto, alternativas y
  evidencia en `docs/adr/`.
* **Evolución solo por añadido.** La misma disciplina de los protocolos binarios y los
  esquemas evolucionables (campos nuevos solo al final; los lectores anteriores
  ignoran la cola únicamente si el mismo prefijo declara un `v` posterior) da
  compatibilidad hacia adelante y hacia atrás sin negociación adicional.

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

## 13. Cambios en 1.1

La versión 1.1 (2026-09-17) fija los puntos que 1.0 dejó sin definir y añade dos
tipos escalares. Cada cambio tiene una regla normativa en las secciones anteriores,
al menos un caso en la suite de conformidad y un registro de decisión.

| Punto abierto en 1.0 | Regla en 1.1 | Sección | ADR |
|---|---|---|---|
| `\,` cuando el separador no es `,` | siempre una coma literal; `\<sep>` solo para el separador del contrato | §3.3 | 0009 |
| Booleanos distintos de `true`/`false`/`1`/`0`, enteros con `+`, floats como `.5` o `1.` | rechazados (E06); solo dígitos ASCII | §4, §6 | 0010 |
| Código de un valor de cabecera mal tipado (`n=abc`) | código de la violación de tipo (E06…), sin E03 | §5 | 0011 |
| Claves de cabecera repetidas | E12; cuenta la primera aparición | §5 | 0012 |
| Elementos de lista vacíos (`a,,b`, separador final) e ida y vuelta de `[""]` | la cadena vacía; se serializa como `""` | §3.4, §6 | 0013 |
| Lista opcional vacía | null (como todo campo opcional) | §6 | 0014 |
| Código de error del serializador ante objetos inválidos | el código del parser y la línea que ocuparía la entrada | §9 | 0015 |
| Fechas y decimales exactos | tipos nuevos `date` y `decimal`, JSON canónico string | §6 | 0016 |

**Compatibilidad.** Un documento válido según 1.0 es válido según 1.1 y produce el
mismo objeto canónico. Los cambios solo afectan entradas cuyo resultado 1.0 no
definía: formas ajenas a la tabla de §6 que las implementaciones aceptaban
(`yes`, `+5`, `.5`), cabeceras con una clave repetida (cuyo objeto canónico 1.0 no
determinaba) y el código de error de documentos y objetos que ya eran inválidos.
`\,` con otro separador y los elementos vacíos sin comillas ya se aceptaban, y 1.1
fija su significado sin rechazarlos; una lista opcional vacía pasa a ser null, como
ya decía la frase de 1.0 «un campo vacío denota null». Los 303 casos de la suite de
conformidad 1.0 siguen en la suite 1.1 con las mismas expectativas; cinco casos del
serializador ahora también fijan el código de error, y el caso de contrato inválido
que usaba `date` como tipo desconocido ahora usa `datetime`. Un contrato 1.0 sigue
siendo un contrato 1.1 válido; un contrato que usa `date` o `decimal` requiere una
implementación 1.1.
