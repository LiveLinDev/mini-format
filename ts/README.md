# @mini-format/core — biblioteca TypeScript de `.mini`

Implementación TypeScript modular y tipada de la notación `.mini` (SPEC 1.0):
parser, serializador, bloque de especificación para prompts, registro de familias
(forks) y una API de lectura en streaming para respuestas de modelos token a token.
Sin dependencias.

Autores: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). Licencia MIT.

## Requisitos

- Node.js ≥ 22.6 (probado con 22.23). El código se ejecuta directamente con
  `--experimental-strip-types`; no hace falta compilar.
- La sintaxis se limita a TypeScript «borrable» (sin `enum`, `namespace` ni
  parámetros-propiedad; imports con extensión `.ts` explícita), de modo que el
  mismo código compila con `tsc` cuando se quiera generar `.js` y `.d.ts`.

## Estructura

```
ts/
├── package.json
├── src/
│   ├── errors.ts      MiniError (código, línea, campo), MiniValidationError, códigos E01–E21
│   ├── contract.ts    tipos ContractJSON/Contract/Field, normalizeContract, firmas, checkFork
│   ├── codec.ts       tokenización, escapes, comillas, división de campos y listas
│   ├── values.ts      decodificación/codificación de escalares, formatNumber
│   ├── parser.ts      parse, Document, LineEngine (motor por líneas), detectPrefix
│   ├── serializer.ts  dumps
│   ├── prompt.ts      specBlock(contract, lang)
│   ├── registry.ts    Registry (desde objetos o desde forks/ con node:fs)
│   ├── stream.ts      createReader, readRecords
│   └── index.ts       API pública
└── test/
    ├── fixtures.test.ts     paridad con forks/*/fixtures y reglas de validación
    ├── roundtrip.test.ts    parse(dumps(obj)) == obj, codec, formato numérico
    ├── stream.test.ts       fragmentos aleatorios de 1–7 caracteres == parse
    ├── truncation.test.ts   salidas truncadas
    ├── conformance.test.ts  runner de ../conformance/ (se omite si no existe)
    └── helpers.ts
```

## Uso

```ts
import { Registry, parse, dumps, specBlock, createReader } from './src/index.ts';

const reg = Registry.load();            // descubre ../forks/*/contract.json
const a = reg.get('a');

const doc = parse(texto, a);            // estricto: lanza MiniValidationError con todos los errores
doc.records;                            // registros válidos
doc.toCanonical();                      // { prefix, header, items: [...] }

const lenient = parse(texto, a, { strict: false });
lenient.errors;                         // MiniError[] con code, line, field, message
lenient.invalidLines();                 // líneas rechazadas (las que hay que regenerar)
lenient.missingRecords;                 // n − líneas de registro (mínimo 0)
lenient.diagnostics();                  // informe con las mismas claves que la referencia Python

const texto2 = dumps(doc.toCanonical(), a);   // ida y vuelta exacta
const prompt = specBlock(a, 'es');            // bloque para el prompt de sistema
```

Los contratos pueden pasarse como objeto `contract.json` o ya normalizados
(`normalizeContract`); todas las funciones aceptan ambos.

### Streaming

```ts
const reader = createReader(a, {           // strict: false por defecto
  onRecord: ({ record, line, index }) => mostrar(record),
  onError: (e) => console.warn(String(e)),
});
for await (const token of respuestaDelModelo) reader.push(token);   // string o Uint8Array
const res = reader.end();
res.document;      // idéntico a parse(textoCompleto, a, { strict: false })
res.expected;      // n declarado en la cabecera
res.received;      // líneas de registro recibidas
res.missing;       // registros que faltan respecto de n
res.incomplete;    // última línea sin LF que no validó (texto, línea, errores) o null
res.truncated;     // incompleto o menos líneas que n
res.terminated;    // el flujo terminó en LF
```

Un registro se emite en cuanto su línea se cierra con LF. `readRecords(iterable, contrato)`
envuelve lo mismo como generador asíncrono. El lector usa el mismo motor por
líneas que `parse`, por lo que el resultado final es idéntico sin importar cómo
se fragmente la entrada.

Nota: si la última línea no termina en LF y su último campo sigue siendo válido
(por ejemplo, un texto cortado), el registro es indistinguible de uno completo;
en ese caso `terminated` es `false` y conviene tratarlo como sospechoso.

## Pruebas

```
cd ts
npm test
# o bien
node --experimental-strip-types --no-warnings --test test/*.test.ts
```

La suite de conformidad compartida se lee de `../conformance/cases/` (o de la ruta en
`MINI_CONFORMANCE_DIR`); si la carpeta no existe, la suite se omite. El runner
reproduce la lógica de `conformance/run_python.py`. Única correspondencia de API:
en modo tolerante la referencia lanza excepción cuando el documento no se puede
construir (E01); TS devuelve un `Document` sin cabecera con E01, y el runner lo
trata como «no construido».

Como en la referencia, los escapes se validan también en modo tolerante (E09 y
el registro se descarta), un escape inválido en la cabecera es E09 dentro de la
validación y una línea rechazada no reserva su valor `unique`.

## Decisiones donde `js/mini.js`, la referencia Python y la SPEC difieren

Criterio: si la SPEC decide, se sigue la SPEC; si no, se sigue la referencia Python.

| Tema | Python | JS | TS |
|---|---|---|---|
| Documento vacío en modo tolerante | lanza siempre | devuelve documento sin `canonical()` | devuelve `Document` con E01 (SPEC §8) |
| Escape inválido en la cabecera | E09 dentro de la validación (corregido) | `MiniError` crudo fuera de `parse` | E09 dentro de la validación |
| Escape inválido en un registro, modo tolerante | E09 y registro descartado (corregido) | conserva el texto literal | E09 y registro descartado |
| Línea rechazada con valor `unique` | no lo reserva (corregido) | lo reserva | no lo reserva |
| `\n` final en un entero/flotante (`5\n`) | acepta (`$` de `re` + `int()`) | rechaza | rechaza, E06 (SPEC: `-?[0-9]+`) |
| Dígitos Unicode en números | acepta (`\d` Unicode) | rechaza | rechaza |
| `clave\=valor` en cabecera (tolerante) | clave rota | E12 | E12 (primer `=` no escapado, SPEC §3.2) |
| Espacio en blanco | `str.isspace()` | `\s` de JS | `str.isspace()` |
| Validación del contrato (tipos desconocidos, separador, marcador, tuplas) | estricta (E20) | laxa | estricta (E20) |
| Prefijo con letras no ASCII | acepta | rechaza | rechaza (SPEC §4) |
| Formato de flotantes (1e21, 1e-7) | expande sin exponente cuando es exacto | `String(x)` | como Python |
| Firma/spec de `float` con `max: 3.0` | `3.0` | `3` | `3` (JSON.parse no distingue) |
| Rango de listas en `specBlock` con `max: 0` | `∞` | `0` | como Python |
| Claves `__proto__` en cabecera/registros | se conservan | se pierden | se conservan |

## Limitaciones

- No hay chequeo de tipos en este entorno (no hay `tsc`); los tipos se escribieron
  para `strict` pero no se han verificado con el compilador.
- Enteros fuera de ±2^53 pierden precisión (números de JavaScript).
- `Registry.load` requiere Node (usa `process.getBuiltinModule`); el resto de la
  biblioteca no depende de Node.
