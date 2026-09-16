# Protocolo de bifurcación

Una **familia** es un nuevo contrato `.mini`. Todo el sentido de `.mini` es que se
adapta al proyecto: en vez de doblegar un formato de propósito general a tus
registros, declaras *tus* registros una vez y todas las herramientas obedecen.

## 1. Decide qué es un registro

Un registro `.mini` es una línea de campos escalares, listas, listas marcadas y
tuplas de un nivel. Si tus datos son una lista de cosas con la misma forma —
ítems, tarjetas, filas, eventos, criterios, casos, anotaciones — encajan. Si un
registro necesita jerarquía profunda, divídelo en dos familias relacionadas por un
identificador (el patrón relacional: los registros `card` apuntan a ítems `a`).

## 2. Parte del padre más cercano, o en blanco

```bash
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
mini new-fork ticket --add "id:str" "title:str" "labels:list<str>" "priority:enum{low|high}"
```

Con `--from`, el núcleo de la hija es la lista completa de campos del padre (núcleo +
extensiones) y tus campos nuevos pasan a ser extensiones. Sin él defines el núcleo
tú mismo.

## 3. Edita `forks/<prefix>/contract.json`

* `prefix` — corto, único, `[A-Za-z][A-Za-z0-9_-]*`; es el primer token de cada
  documento de la familia.
* `header.keys` — metadatos tipados (`n` es implícita y obligatoria). Usa una
  **clave de recuento** (`"count_key": "k"` en un campo de lista, con `k` declarada
  en la cabecera) siempre que una lista tenga longitud fija: convierte las colisiones
  de delimitador en errores detectables.
* `core` — campos requeridos en orden. Tipos: `str`, `int`, `float`, `bool`,
  `enum` (+`values`), `list` (+`item`, `min`, `max`), `mlist` (+`marker`:
  `exactly_one` | `at_least_one` | `at_most_one` | `any`, y nombres `json`
  `{items, selected}`), `tuple` (+`items`).
* `extensions` — campos opcionales al final; los parsers de versiones anteriores
  los ignoran.
* `list_separator` — `,` por defecto; elige `;` para listas con mucho texto si tu
  contenido está lleno de comas (las familias heredadas deben conservar el del padre).

## 4. Añade fixtures

`fixtures/valid.mini` y `fixtures/canonical.json` deben hacer ida y vuelta en ambas
direcciones byte a byte (`dumps(canonical) == valid.mini`). Añade
`escaping.mini` (+`escaping.json`) con cada carácter reservado, y casos negativos
`bad_count.mini`, `bad_arity.mini`, `bad_type.mini` (`bad_marker.mini` cuando uses
una lista marcada). `benchmark/make_forks.py` muestra cómo los generan las familias
incluidas.

## 5. Comprueba los invariantes

```bash
mini check-forks
```

| # | Invariante | Lo comprueba |
|---|---|---|
| I1 | una línea = un registro completo e independientemente válido | el parser |
| I2 | cabecera con prefijo y `n`; las claves requeridas del padre siguen requeridas | el registro |
| I3 | campos heredados: mismos nombres, orden, tipos y separador de lista | el registro (`E21`) |
| I4 | campos nuevos añadidos tras los heredados, opcionales | el registro |
| I5 | los fixtures hacen ida y vuelta, los negativos se rechazan | `check-forks` |

Un cambio que reordene, retipifique o elimine un campo heredado es un **prefijo
nuevo**, nunca una versión nueva del mismo prefijo. El crecimiento compatible
(añadir campos, añadir claves de cabecera opcionales) incrementa `version`.

## 6. Enséñasela a un modelo

```bash
mini prompt <prefix> --lang en   # o --lang es
```

El bloque se genera desde el contrato y es lo que pegas en el prompt de sistema.
Declara la cabecera, el orden de campos, las reglas de escape y comillas, la regla
del marcador y un ejemplo de un registro. En nuestra validación, modelos que nunca
habían visto una familia produjeron documentos 100 % analizables y con 100 % de ida
y vuelta solo con este bloque (36/36 en tres familias no vistas y dos modelos), y
modelos a los que se pidió *escribir un parser* desde él pasaron todos los fixtures
en 15 de 16 intentos.

## 7. Publica

Abre un pull request que añada `forks/<prefix>/` (contrato, README, fixtures).
CI ejecuta `mini check-forks`, la suite Python y la prueba de conformidad JS.
