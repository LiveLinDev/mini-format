# ADR 0006. Protocolo de bifurcación e invariantes I1–I5

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §10; guía en [FORKING.md](../../FORKING.md)

## Contexto y problema

Cada dominio cerrado necesita su propio contrato. Si cada contrato nuevo exigiera
escribir un parser, o si un contrato derivado pudiera alterar libremente los campos
de su padre, se perdería la interoperabilidad entre familias y la garantía de que
todo documento es analizable.

## Alternativas consideradas

1. **Formato único y extensible** con campos opcionales para todos los dominios.
2. **Contratos independientes** sin relación declarada.
3. **Familias derivadas por bifurcación** bajo invariantes verificables por máquina,
   interpretadas por un parser genérico.

## Decisión

Se adopta la alternativa 3. Una familia es un contrato de datos (`contract.json`,
`README.md`, `fixtures/`) que cumple cinco invariantes: I1 línea local, I2 cabecera
con prefijo y `n`, I3 núcleo heredado estable, I4 extensión solo al final e I5 ida y
vuelta de los fixtures. `mini check-forks` verifica I3/I4 (E21) e I5 sobre el
registro de familias. Un cambio incompatible exige un prefijo nuevo.

## Consecuencias

* Una familia nueva no requiere código: el parser interpreta el contrato y el bloque de
  especificación del prompt se deriva de él.
* Reordenar, retipificar o eliminar un campo heredado se rechaza (E21).
* Los fixtures publicados alimentan la suite de conformidad (categoría `fixtures`).

## Evidencia

* [forks/registry.json](../../forks/registry.json): 14 familias oficiales; `q` declara como
  padre a `a`.
* [FORKING.md](../../FORKING.md): documentos 100 % analizables y de ida y vuelta generados
  solo a partir del bloque («36/36 across three unseen forks and two models») y parsers
  escritos desde el bloque que aprueban todos los fixtures en 15 de 16 intentos.
* [generative/results/e2_summary.csv](../../generative/results/e2_summary.csv): Haiku y Sonnet
  sobre `cls`, `log` y `tc` con n = 6 cada uno, 100,0 % analizable y de ida y vuelta.
* [generative/results/e3_samples.csv](../../generative/results/e3_samples.csv): 15 de 16 filas
  con `all_ok=True`; la excepción es `opus,cls,1`.
* Implementación: `Contract.check_fork_of` en [src/minifmt/contract.py](../../src/minifmt/contract.py),
  `checkFork` en [ts/src/contract.ts](../../ts/src/contract.ts), registro en
  [src/minifmt/registry.py](../../src/minifmt/registry.py).
* Casos de conformidad: categoría `fork` en [conformance/cases/fork.json](../../conformance/cases/fork.json).
