# Criterio documental V1: evaluación

Criterio `V1-documental-30-10-3`, fijado el 2026-09-30 antes del análisis; **sujeto a aprobación del asesor**.

## Veredicto con la interpretación primaria

Serie n=100, variante `muestreo`; ahorro del dominio = 1 − ΣT(.mini)/ΣT(JSON compacto) sobre todos los documentos del dominio; umbral 30 %; mínimo 10 dominios por tokenizador.

| Tokenizador | Dominios ≥ 30 % | ¿≥ 10? | Media por dominio (IC95) | Agregado por suma (IC95) | Mín–máx |
|---|---:|:---:|---|---|---|
| o200k_base | 12 / 14 | sí | 34,81 % [32,69; 36,89] | 34,31 % [32,30; 36,47] | 27,9–41,7 |
| cl100k_base | 10 / 14 | sí | 32,74 % [30,39; 35,09] | 31,71 % [29,67; 34,17] | 25,4–41,5 |
| r50k_base | 8 / 14 | no | 30,43 % [27,91; 32,97] | 29,17 % [27,05; 31,80] | 21,8–40,2 |

**Veredicto primario: `no_cumple`.**

Dominios por debajo del umbral (n=100 muestreo):

* o200k_base: code 27,9, sum 28,1
* cl100k_base: card 27,7, code 25,6, q 28,9, sum 25,4
* r50k_base: card 25,8, code 21,8, log 29,0, q 25,9, r 28,0, sum 24,0

## Lecturas alternativas (publicadas sin elegir la más alta)

| Serie | Lectura | o200k_base | cl100k_base | r50k_base | ¿cumple los tres? |
|---|---|---:|---:|---:|:---:|
| n100_muestreo | ≥ 10 dominios con ahorro ≥ 30 % | 12/14 | 10/14 | 8/14 | no |
| n100_muestreo | media por dominio ≥ 30 % | 34,81 % | 32,74 % | 30,43 % | sí |
| n100_muestreo | agregado por suma ≥ 30 % | 34,31 % | 31,71 % | 29,17 % | no |
| n100_muestreo | intersección de dominios ≥ 30 % con los tres | — | — | — | 8 dominios (no): a, cat, cls, map, ner, s, tc, us |
| n100_ciclo | ≥ 10 dominios con ahorro ≥ 30 % | 12/14 | 10/14 | 8/14 | no |
| n100_ciclo | media por dominio ≥ 30 % | 34,77 % | 32,70 % | 30,42 % | sí |
| n100_ciclo | agregado por suma ≥ 30 % | 34,29 % | 31,68 % | 29,18 % | no |
| n100_ciclo | intersección de dominios ≥ 30 % con los tres | — | — | — | 8 dominios (no): a, cat, cls, map, ner, s, tc, us |
| n12_ciclo | ≥ 10 dominios con ahorro ≥ 30 % | 12/14 | 9/14 | 7/14 | no |
| n12_ciclo | media por dominio ≥ 30 % | 33,80 % | 31,63 % | 29,47 % | no |
| n12_ciclo | agregado por suma ≥ 30 % | 33,53 % | 30,88 % | 28,56 % | no |
| n12_ciclo | intersección de dominios ≥ 30 % con los tres | — | — | — | 7 dominios (no): a, cat, cls, map, ner, tc, us |
| n12_muestreo | ≥ 10 dominios con ahorro ≥ 30 % | 12/14 | 9/14 | 7/14 | no |
| n12_muestreo | media por dominio ≥ 30 % | 33,82 % | 31,65 % | 29,47 % | no |
| n12_muestreo | agregado por suma ≥ 30 % | 33,54 % | 30,89 % | 28,56 % | no |
| n12_muestreo | intersección de dominios ≥ 30 % con los tres | — | — | — | 7 dominios (no): a, cat, cls, map, ner, tc, us |

## Efecto del tamaño n (variante `muestreo`; n > 12 repite los 12 registros base)

| n | o200k_base media / suma / dominios ≥ 30 | cl100k_base media / suma / dominios ≥ 30 | r50k_base media / suma / dominios ≥ 30 |
|---:|---|---|---|
| 1 | 27,0 / 28,1 / 4 | 24,0 / 25,0 / 2 | 22,6 / 24,0 / 2 |
| 5 | 32,5 / 32,4 / 11 | 30,0 / 29,6 / 9 | 28,0 / 27,6 / 3 |
| 10 | 33,5 / 33,2 / 11 | 31,3 / 30,6 / 9 | 29,2 / 28,3 / 7 |
| 12 | 33,8 / 33,5 / 12 | 31,6 / 30,9 / 9 | 29,5 / 28,6 / 7 |
| 25 | 34,4 / 34,0 / 12 | 32,3 / 31,4 / 9 | 30,1 / 29,0 / 8 |
| 50 | 34,6 / 34,2 / 12 | 32,6 / 31,6 / 9 | 30,3 / 29,1 / 8 |
| 100 | 34,8 / 34,3 / 12 | 32,7 / 31,7 / 10 | 30,4 / 29,2 / 8 |
| 250 | 34,9 / 34,4 / 12 | 32,8 / 31,8 / 10 | 30,5 / 29,2 / 8 |

Las cifras para n > 12 provienen de la replicación de los 12 registros base de cada dominio (`replicacion_de_base`): miden longitud de serialización, no diversidad semántica ni muestras independientes.
