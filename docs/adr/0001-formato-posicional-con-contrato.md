# ADR 0001. Formato posicional con contrato compartido

* Estado: aceptada
* Fecha: 2026-09-01 (SPEC 1.0); registro retrospectivo del 2026-09-16
* Especificación: [SPEC.md](../../SPEC.md) §1, §6, §7 y §11 («Position instead of names»)

## Contexto y problema

Las salidas estructuradas de un modelo generativo en un dominio cerrado repiten en
cada registro los nombres de campo, llaves, corchetes y comillas del formato de
transporte (JSON, YAML, XML). En un dominio cerrado el emisor y el receptor conocen
el esquema, por lo que esa estructura repetida no aporta información y consume
tokens de salida. Se requiere una notación que reduzca el coste estructural sin
perder la validación por registro ni la conversión determinista a JSON.

## Alternativas consideradas

1. **JSON (compacto o indentado)**, con o sin modo de salida estructurada del proveedor.
2. **YAML o XML.**
3. **CSV aplanado**: posicional, pero sin tipado, sin listas marcadas ni validación
   por contrato, y con reglas de comillas dependientes de la implementación.
4. **TOON** (tabular), en su forma oficial o aplanada.
5. **Notación posicional con contrato**: una cabecera que nombra el contrato y el
   recuento, y un registro por línea con campos separados por `|` cuyo significado
   lo da la posición.

## Decisión

Se adopta la alternativa 5. El esquema se declara una sola vez en un contrato
(`forks/<prefijo>/contract.json`); el documento solo transporta la cabecera y los
valores en orden. El parser y el serializador interpretan el contrato y producen o
consumen el objeto canónico de §7.

## Consecuencias

* El coste por registro se aproxima al del contenido; el ahorro frente a JSON
  depende de la forma del registro, del tokenizador y del número de registros.
* Frente a CSV y TOON aplanados el ahorro es pequeño o nulo; la justificación frente
  a ellos es la validación local tipada, las listas marcadas y el protocolo de
  bifurcación, no la compacidad.
* El contrato pasa a ser un artefacto obligatorio: sin él el documento no es
  interpretable (§12, limitaciones).
* El bloque de especificación que requiere el modelo tiene un coste fijo que solo
  se amortiza a partir de cierto número de registros.

## Evidencia

* [experiments/README.md](../../experiments/README.md), §1 (reproducción con n = 12,
  o200k_base, media de 14 dominios): .mini frente a JSON compacto −33,8 % (rango por
  dominio −39,5 a −27,3 %); frente a TOON oficial −37,4 %; frente a TOON aplanado
  −7,0 %; frente a CSV aplanado +5,0 % publicado y +5,1 % reproducido.
* [experiments/README.md](../../experiments/README.md), §2.1 (n = 100, media [IC 95 %]):
  ahorro frente a JSON compacto 34,8 [32,7; 36,9] con o200k_base; frente a CSV
  aplanado −2,6 [−4,7; −0,4]; frente a TOON aplanado 2,0 [−0,1; 4,4].
* [benchmark/results/summary_12.csv](../../benchmark/results/summary_12.csv): tokens por
  dominio y formato con n = 12.
* [generative/results/e4_breakeven.csv](../../generative/results/e4_breakeven.csv):
  bloque de especificación .mini de 640 tokens, 62,68 tokens por registro; punto de
  equilibrio de 10,4 registros frente a JSON, 493,4 frente a CSV y 158,1 frente a TOON.
* [generative/results/e1_summary.csv](../../generative/results/e1_summary.csv): con
  Haiku (n = 10), Sonnet (n = 10) y Opus (n = 6), .mini obtuvo 100,0 % de documentos
  analizables y de ida y vuelta en los tres modelos.
