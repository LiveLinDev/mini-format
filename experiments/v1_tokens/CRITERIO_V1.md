# Criterio documental de V1 y su interpretación (fijada antes del análisis)

Fecha de fijación: 2026-09-30. Autor: equipo de implementación (flujo v1).
Estado: **sujeta a aprobación del asesor**. La versión legible por máquina es
[`criterio_v1.json`](criterio_v1.json); el código de análisis
(`experiments/v1_tokens/criterio.py`) la lee de ahí y no contiene otro umbral.

## Meta documental

Ahorro de tokens >= 30 % de .mini frente a JSON compacto en >= 10 de los 14 dominios
y con tres tokenizadores (o200k_base, cl100k_base, r50k_base).

## Interpretación primaria

* Serie: n = 100, variante `muestreo`. Unidad: texto del documento transmitido (sin contrato,
  sin mapa, sin prompt).
* Ahorro del dominio = 100 · (1 − ΣT(.mini) / ΣT(JSON compacto)), sumando los tokens de todos
  los documentos de ese dominio en la serie primaria. Se compara sin redondear con 30,0.
* `cumple` solo si, **para cada uno** de los tres tokenizadores, al menos 10 dominios alcanzan
  el 30 %; `no_cumple` si alguno de los tres no lo logra.
* Un formato solo entra en una comparación si objeto → texto → objeto se verificó para ese
  documento (JSON compacto con `json.loads`, .mini con `minifmt.parse`).

## Declaración de procedencia de la lectura

La fijó el equipo de implementación el 2026-09-30 antes de ejecutar el análisis de este
flujo. Las cifras exploratorias de la auditoría previa (lectura de media por dominio sobre
los resultados archivados: 12, 10 y 8 dominios con ahorro >= 30 % para o200k_base,
cl100k_base y r50k_base) **ya eran conocidas**. No se eligió esta lectura por su resultado
ni se descarta ninguna otra: las lecturas alternativas se publican siempre (media por dominio
frente a agregado por suma, n = 12, `ciclo`, intersección de dominios y efecto de n).

## Advertencias que acompañan a cualquier cifra

* Para n > 12 los 12 registros base de cada dominio se repiten con identificadores nuevos
  (`replicacion_de_base: true`): n = 100 no son 100 muestras independientes.
* Los 14 dominios son conjuntos escritos a mano (sintéticos); `q` extiende a `a`.
* Los tres tokenizadores son de la misma familia BPE de OpenAI; no sustituyen a un
  tokenizador independiente (Anthropic, Google, DeepSeek), para los que tiktoken es solo una
  aproximación.
