# ADR 0030. Alias de enumeración y diccionarios por documento (propuesta, no implementada)

* Estado: **Propuesta (no vigente)**. No hay decisión tomada, ni SPEC 1.2, ni implementación.
* Fecha: 2026-09-30
* Especificación: [SPEC.md](../../SPEC.md) §5, §6 y §8 (cambio propuesto para una futura SPEC 1.2)
* Evidencia: corrida `opt-20260930t191636z` del estudio OPT ([manifiesto](../../evidencia/corridas/opt-20260930t191636z/manifiesto.json),
  [simulación](../../evidencia/corridas/opt-20260930t191636z/propuesta_simulacion.csv)); diseño en
  [experiments/optimizacion](../../experiments/optimizacion/README.md)

## Contexto y problema

El estudio OPT diseñó, dentro de SPEC 1.1 y sin ampliar el formato, una configuración especializada: códigos cortos de
enumeración, identificador numérico con prefijo constante, enteros escalados y hora en minutos. La equivalencia
código↔etiqueta vive en la **aplicación** como un mapa explícito (`mapa.json`), que además se imprime en la instrucción
(así sus tokens se cuentan) y se verifica con una ida y vuelta exacta de todos los registros. Dos límites motivan este registro:

1. Cada aplicación reimplementa el mapa y su decodificador. El objeto canónico que entrega `parse` lleva el código, no la
   etiqueta, y `spec_block` no imprime la `desc` de los campos `enum` (`src/minifmt/prompt.py`, rama de las enumeraciones): el
   mapa viaja como texto libre en la `description` del contrato.
2. El único diccionario que existe hoy es la cabecera `e=` del perfil `mini-domain/1` (solo Python, sin `js/mini.js`, sin
   casos de conformidad, errores `D_*`).

## Alternativas consideradas

1. **No ampliar** (estado actual): el mapa sigue en la aplicación.
2. **Alias de enumeración en el contrato**: cada valor de un `enum` puede declarar un `code` único dentro del campo; el
   documento escribe el código, el objeto canónico contiene la etiqueta y `spec_block` imprime `código=etiqueta`.
3. **Diccionario por documento en la cabecera**: una clave reservada declara, para columnas de texto repetido, la lista de
   valores del documento; las filas llevan el índice entero. Sin contrato adicional.
4. **Portar `mini-domain/1` a TypeScript** y a `js/mini.js` con sus casos de conformidad.

## Decisión

Ninguna. Este registro es una propuesta para discusión: no cambia SPEC.md ni SPEC.es.md, ni el código. Se sugiere evaluar la
alternativa 2 por separado de la 3, porque resuelven problemas distintos.

## Ganancia potencial medida por simulación (NO implementada)

* **Alternativa 2.** Por construcción el texto del documento sería el mismo que el de la configuración especializada ya
  medida (el alias es el código del mapa): los tokens de **salida** serían idénticos a los de la columna «Especializado a mano»
  de la tabla siguiente. La propuesta **no añade ahorro de tokens**: añade portabilidad (mapa dentro del contrato, validación E10
  sobre alias, instrucción generada con los alias y decodificación en ambas implementaciones).
* **Alternativa 3.** Simulación sobre el perfil general (contrato de `mini from-schema`) con la regla de `mini build` (columna
  `str` o `enum`, 2 a 64 valores distintos, al menos 3 filas por valor, al menos 6 filas, ahorro neto en bytes). El diccionario
  viaja completo en cada documento y su coste está contado; no incluye el coste de instruir al modelo sobre la sintaxis.
  Es un techo para estos datos, no una predicción.

| Dominio | Salida general (tokens) | General con diccionario simulado | Ahorro potencial | Especializado a mano | Columnas del diccionario |
|---|--:|--:|--:|--:|---|
| tickets (representativo) | 2652 | 2608 | +1.7 % | 2382 | prioridad, categoria |
| eventos de planta (FAVORABLE) | 3950 | 3108 | +21.3 % | 1621 | planta, tipo_evento, severidad, estado |
| comentarios (texto libre; ahorro pequeño) | 5954 | — | — | 5955 | ninguna: ninguna columna cumple la regla (se repite poco o ahorra menos de lo que cuesta declararla) |

Lectura: un diccionario automático por documento recupera una parte del ahorro que hoy exige diseñar a mano los códigos,
solo donde las columnas repiten mucho; donde el texto es libre o casi no se repite (tickets, comentarios) no aplica o
aporta poco. Las cifras son del perfil general frente a sí mismo con diccionario; no mezclan el ahorro frente a JSON.

## Consecuencias si se aceptara

* **Versión:** SPEC 1.2 (regla nueva de §5 o §6). Un documento 1.1 no cambia. Un contrato con alias requiere una
  implementación 1.2; una implementación 1.1 que lea ese contrato debería fallar de forma visible (E10 al validar un código),
  no degradar en silencio: debe comprobarse, porque hoy `Field.from_dict` ignora claves desconocidas.
* **Casos de conformidad necesarios** (`conformance/generate.py`): alias válido y canónico con etiqueta; código desconocido
  (E10); alias repetido dentro del campo (E20); alias igual a la etiqueta de otro valor (E20); alias con separador o
  escape (E20); ida y vuelta `dumps`/`parse`; estabilidad de texto para un documento emitido por el serializador; alias en
  elementos de lista y en claves de cabecera; y, para la alternativa 3, índice fuera de rango, diccionario duplicado y
  escape dentro del diccionario.
* **Implementaciones:** Python (`contract.py`, `parser.py`, `serializer.py`, `prompt.py`) y TypeScript (`ts/src/*`),
  regenerar `js/mini.js` y las copias del motor del sitio; actualizar `mini to-schema`/`from-schema` (`x-mini`).
* **Pruebas:** paridad Python/TypeScript sobre los casos nuevos, fuzz de ida y vuelta con alias y mapeo inverso, y una prueba
  de que `spec_block` imprime código y etiqueta (hoy omite los valores de enumeraciones dentro de tuplas).
* **Riesgo:** un alias corto mnemotécnico puede confundirse entre campos (p. ej. `a` en dos enumeraciones); la adherencia
  de un modelo a códigos cortos NO está medida (este estudio no hizo llamadas a modelos) y debe validarse con V2/V3.

## Evidencia

* Corrida [`opt-20260930t191636z`](../../evidencia/corridas/opt-20260930t191636z/manifiesto.json), archivo `propuesta_simulacion.csv`.
* [experiments/optimizacion/README.md](../../experiments/optimizacion/README.md): diseño, lo que no funcionó y límites.
* [src/minifmt/prompt.py](../../src/minifmt/prompt.py): qué imprime hoy `spec_block` (no imprime la `desc` de los campos `enum` ni los valores de
  enumeraciones dentro de tuplas).
