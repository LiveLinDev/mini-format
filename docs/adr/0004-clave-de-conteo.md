# ADR 0004. Clave de conteo `n` y `count_key`

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §5 y §8 (E03, E04, E07)

## Contexto y problema

Una salida generada puede truncarse (límite de tokens) o sufrir colisiones de
delimitador dentro de una lista (ADR 0002). Sin información redundante, un documento
truncado en un límite de línea y una lista con un elemento de más son textos
sintácticamente válidos: la corrupción pasa inadvertida.

## Alternativas consideradas

1. **Sin recuento**: confiar en la sintaxis.
2. **Marcador de fin de documento.**
3. **Recuento declarado en la cabecera** (`n`) y, para listas de longitud fija, una
   clave de cabecera que fija la aridad exacta (`count_key`).

## Decisión

Se adopta la alternativa 3. `n` es obligatorio (E03 si falta) y debe coincidir con el
número de líneas de registro (E04). Un campo de lista puede declarar
`count_key: "k"`; cada registro debe tener exactamente `k` elementos (E07).

## Consecuencias

* El truncamiento en límite de línea se detecta (E04) y el diagnóstico informa de los
  registros faltantes (`missing_records`).
* Una colisión de delimitador en una lista con `count_key` se convierte en un error de
  aridad detectable en lugar de una corrupción silenciosa.
* El modelo debe emitir `n` coherente; los reparadores no reescriben `n` para no ocultar
  truncamientos.

## Evidencia

* [generative/results/ablation.csv](../../generative/results/ablation.csv): las 5 muestras
  inválidas del borrador solo con barra invertida se detectan precisamente por la clave
  de conteo («E07 line 12 [options]: list has 5 elements but header k=4»).
* [tests/test_lenient.py](../../tests/test_lenient.py): una cabecera con 5 de 12 registros
  informa `missing_records == 7`.
* [experiments/generativo/README.md](../../experiments/generativo/README.md): la reparación
  por fusión «nunca reescribe `n`», de modo que la advertencia E04 de un truncamiento
  sigue visible.
* [FORKING.md](../../FORKING.md): recomienda la clave de conteo para toda lista de longitud
  fija porque convierte las colisiones de delimitador en errores detectables.
* Casos de conformidad: `list-count-key-*`, `trunc-*` y `hdr-e03-*`/`hdr-e04-*` en
  [conformance/cases/](../../conformance/cases/).
