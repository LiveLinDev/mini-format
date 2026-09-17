# ADR 0005. Modo tolerante y recuperación parcial

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §8

## Contexto y problema

En salidas largas, un único registro defectuoso o un corte al final invalida el
documento completo si el análisis es todo o nada. Regenerar el documento entero
multiplica el coste; lo deseable es conservar los registros válidos y regenerar solo
las líneas rechazadas.

## Alternativas consideradas

1. **Solo análisis estricto**: rechazar el documento ante cualquier error.
2. **Reparación heurística** del texto (completar, reinterpretar) antes de validar.
3. **Modo tolerante**: la validación es local por línea; el parser devuelve los
   registros válidos junto con la lista completa de errores y un diagnóstico de las
   líneas que deben regenerarse.

## Decisión

Se adopta la alternativa 3 como complemento del modo estricto. El modo tolerante
aplica exactamente las mismas reglas que el estricto (incluidos los escapes, E09) y
descarta solo los registros inválidos; una línea rechazada no reserva su valor
`unique`. El diagnóstico expone `invalid_lines` y `missing_records`.

## Consecuencias

* Los registros devueltos en modo tolerante son los que el modo estricto aceptaría.
* La regeneración puede limitarse a las líneas indicadas.
* Los formatos con estructura envolvente (JSON, XML) no admiten esta recuperación sin
  reparación del texto.

## Evidencia

* [generative/results/e5_truncation.csv](../../generative/results/e5_truncation.csv) (200 cortes
  por dominio): eficiencia de recuperación de .mini 99,6 (`a`), 99,0 (`tc`) y 99,4 (`log`);
  JSON y XML 0,0 con 100,0 % de cortes sin recuperación; YAML 78,8 (`a`) con 22,5 % sin
  recuperación.
* [generative/results/e2_summary.csv](../../generative/results/e2_summary.csv):
  `mean_recovered_pct` 100,0 en las seis combinaciones de modelo y familia.
* [tests/test_lenient.py](../../tests/test_lenient.py): último registro truncado → 11
  registros recuperados y E05 en la línea 13.
* Las cifras de recuperación de [experiments/generativo/README.md](../../experiments/generativo/README.md)
  (V3) provienen de un adaptador simulado y ese documento indica que no deben citarse
  como evidencia; no se usan aquí.
* Casos de conformidad: categorías `lenient` y `truncation` en
  [conformance/cases/](../../conformance/cases/).
