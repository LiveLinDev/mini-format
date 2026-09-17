# ADR 0003. Lista marcada con sufijo `*`

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §6 (tipo `mlist`), §7 y §11 («Marker as suffix»)

## Contexto y problema

Muchos dominios cerrados eligen uno o varios elementos de una lista: la alternativa
correcta de un ítem de evaluación, las etiquetas aplicables, la opción
seleccionada. La representación habitual es una lista y un campo aparte con el
índice o el contenido seleccionado, lo que obliga al modelo a mantener alineados dos
campos distantes.

## Alternativas consideradas

1. **Campo de índice separado** (`options` + `correct: 2`).
2. **Repetir el contenido seleccionado** en un campo aparte.
3. **Sufijo de un carácter** en el elemento seleccionado (`a,b*,c`), con una regla de
   marcador declarada en el contrato.

## Decisión

Se adopta la alternativa 3. El tipo `mlist` marca los elementos seleccionados con un
`*` final no escapado. El contrato declara la regla (`exactly_one`, `at_least_one`,
`at_most_one`, `any`) y su incumplimiento es E08. El objeto canónico expande la lista
en dos claves hermanas: los elementos y el índice (o la lista ascendente de índices)
seleccionado.

## Consecuencias

* La selección viaja pegada a su contenido y se verifica en la misma línea.
* `*` adquiere significado estructural solo como último carácter de un elemento; un
  asterisco literal final se escribe `\*` (ADR 0002).
* El objeto canónico conserva la forma habitual (lista + índice), por lo que los
  consumidores no dependen de la notación.

## Evidencia

* No existe en el repositorio un experimento que compare el sufijo `*` con un campo de
  índice separado (coste en tokens o errores de alineación); la decisión se apoya en el
  razonamiento de diseño de [SPEC.md](../../SPEC.md) §11.
* [generative/results/e3_samples.csv](../../generative/results/e3_samples.csv): los parsers
  escritos por modelos a partir del bloque de especificación rechazan los fixtures
  negativos, incluido `bad_marker.mini`, en todas las filas (p. ej. `opus,a,1,…,4/4`).
* [generative/results/e1_summary.csv](../../generative/results/e1_summary.csv): la familia
  `a` (con lista marcada `options`) obtuvo 100,0 % de ida y vuelta con los tres modelos.
* Casos de conformidad: categoría `mlist` en [conformance/cases/mlist.json](../../conformance/cases/mlist.json).
