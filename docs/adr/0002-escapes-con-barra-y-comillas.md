# ADR 0002. Protección del separador con barra invertida y comillas CSV

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §3.3, §3.4 y §11 («Two equivalent protections for the list separator»)

## Contexto y problema

Dentro de un campo de tipo lista, el separador de lista (`,` por defecto) delimita
elementos. Un texto generado que contiene ese carácter produce una colisión de
delimitador: la lista gana elementos y el registro se corrompe sin que el formato lo
detecte. La notación necesita una forma de proteger el separador (y el `*` final)
que los modelos generativos apliquen de manera fiable.

## Alternativas consideradas

1. **Solo comillas estilo CSV** (versión 0, 2026-06).
2. **Solo escapes con barra invertida** (borrador de la versión 1).
3. **Ambas notaciones como equivalentes**, con la forma escapada como canónica y una
   clave de conteo que haga detectable cualquier colisión residual (ADR 0004).

## Decisión

Se adopta la alternativa 3. Un elemento de lista puede protegerse con escapes
(`\,`, `\*`, `\"`) o entrecomillarse al estilo CSV (`"a, b"*`, con `""` como
comilla literal); ambas formas denotan el mismo valor. `|`, `\` y los saltos de
línea se escapan siempre. El serializador canónico emite la forma escapada.

## Consecuencias

* El parser acepta dos notaciones, lo que exige casos de conformidad para su
  interacción (marcador dentro o fuera de las comillas, escapes activos dentro de
  comillas, texto tras la comilla de cierre = E09).
* La salida canónica es única (forma escapada), por lo que la ida y vuelta
  `dumps(parse(t)) = t` se cumple sobre documentos emitidos por el serializador.
* El bloque de especificación del prompt describe ambas notaciones
  ([src/minifmt/prompt.py](../../src/minifmt/prompt.py)).

## Evidencia

* [generative/results/ablation.csv](../../generative/results/ablation.csv): con Haiku 4.5 y
  el borrador solo con barra invertida (`v1-draft (backslash only)`), 1 de 6 muestras
  es analizable y hace ida y vuelta (muestra 5); las otras 5 fallan con
  «E07 line 12 [options]: list has 5 elements but header k=4». Con la especificación
  1.0 (`v1.0 (quotes or escapes + count key)`), 10 de 10 muestras son válidas. Las
  proporciones se obtienen contando las filas del archivo;
  [benchmark/make_figures.py](../../benchmark/make_figures.py) (figura 8) las calcula
  como `100 * sum(g) / len(g)`.
* Salidas crudas del borrador: [generative/raw/e1_ablation/](../../generative/raw/e1_ablation/);
  índice de experimentos en [generative/README.md](../../generative/README.md).
* La versión 0 (solo comillas) figura en [benchmark/make_figures.py](../../benchmark/make_figures.py)
  (figura 8) con los valores 80,0 (DeepSeek-V3, n = 30) y 100,0 (DeepSeek-R1, n = 20)
  escritos en el código; el repositorio no contiene las salidas crudas de esa ronda,
  por lo que esta evidencia es secundaria.
* Casos de conformidad: categorías `escapes` y `quotes` en
  [conformance/cases/](../../conformance/cases/).
