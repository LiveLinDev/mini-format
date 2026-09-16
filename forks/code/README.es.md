# `.mini-code` — Ejercicios de programación con pruebas

**Prefijo:** `code`  **Versión:** 1  **Padre:** —  **Dominio:** educación / programación

Ejercicios de programación autocalificables: enunciado, lenguaje, expresiones de prueba, tipo esperado y pistas.

## Estructura del registro

```
id:str | bloom:enum{L1|L2|L3|L4|L5|L6} | topic:str | statement:str | lang:enum{python|javascript|java|sql|c|cpp|go} | tests:list<str>[1..10] | expected:str | hints:list<str>[0..5]
```

| # | campo | tipo | notas |
|---|---|---|---|
| 1 | `id` | `str` | núcleo |
| 2 | `bloom` | `enum{L1|L2|L3|L4|L5|L6}` | núcleo |
| 3 | `topic` | `str` | núcleo |
| 4 | `statement` | `str` | núcleo |
| 5 | `lang` | `enum{python|javascript|java|sql|c|cpp|go}` | núcleo |
| 6 | `tests` | `list<str>[1..10]` | núcleo; expresiones booleanas de prueba |
| 7 | `expected` | `str` | núcleo |
| 8 | `hints` | `list<str>[0..5]` | núcleo |

## Claves de cabecera

| clave | tipo | requerida | descripción |
|---|---|---|---|
| `d` | `str` | no | fecha de generación AAAAMMDD |
| `l` | `str` | no | código de idioma |
| `t` | `str` | no |  |
| `n` | `int` | sí | número de registros |
| `v` | `int` | no | versión del contrato |

## Ejemplo

```
code|n=12|d=20260603|l=en|t=Intro programming lab 3
c1|L3|lists|Write a function maximum(xs) that returns the largest number in a non-empty list.|python|maximum([2\,8\,3])==8,maximum([-1\,-5])==-1|int or float|iterate once,track the best so far
c2|L3|strings|Write is_palindrome(s) ignoring case and spaces.|python|is_palindrome('Anita lava la tina'),not is_palindrome('hello')|bool|normalize first
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (ida y vuelta), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, y los casos negativos `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Bloque de prompt

Genera la especificación transferible con `mini prompt code`.
