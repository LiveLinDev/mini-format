# @mini-format/core — biblioteca TypeScript de `.mini`

Versión de software 1.1.0. Implementación TypeScript modular y tipada del núcleo
`.mini` (SPEC 1.1):
parser, serializador, bloque de especificación para prompts, registro de familias
(forks) y una API de lectura en streaming para respuestas de modelos token a token.
Sin dependencias.

Incluye las catorce familias del núcleo. Los contratos adaptados a muestras JSON
por `mini build` usan otro perfil, `mini-domain/1`, y el parser Python que se genera
con ellos; esta biblioteca no interpreta ese perfil. Consulta la
[guía del constructor](https://mini-format.pmoluna.com/docs/build/) y la
[especificación del perfil generado](https://mini-format.pmoluna.com/docs/profile/).

Autores: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). Licencia MIT.

## Instalación del paquete

Necesitas Node.js ≥ 22.6. Descarga `mini-format-core-1.1.0.tgz` desde Descargas
o extrae ese archivo del ZIP del toolkit. Instala el archivo local:

```sh
npm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.1.0.tgz
```

El archivo contiene JavaScript ESM compilado en `dist/`, los contratos de las
catorce familias y fuentes TypeScript para tipos. Se importa desde
`@mini-format/core`: no necesita ejecutar TypeScript dentro de `node_modules`,
usar `--experimental-strip-types` ni conectarse al registro npm.

## Desarrollo desde las fuentes

Las fuentes `ts/src/` usan TypeScript borrable, sin `enum`, `namespace` ni
parámetros-propiedad, e imports con extensión `.ts`. Node.js ≥ 22.6 puede ejecutar
estas fuentes con `--experimental-strip-types`; esto es distinto del paquete
distribuido, que ya contiene JavaScript. Pruebas verificadas con Node.js 22.14.0.

Para generar ESM desde la raíz del repositorio, utiliza Node.js ≥ 22.13:

```sh
node --no-warnings tools/build_node.mjs
```

El script elimina tipos y convierte imports relativos `.ts` a `.js` en
`ts/dist/`. La distribución incluye las fuentes tipadas; este paso no genera
archivos `.d.ts`.

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
import { Registry, parse, dumps, specBlock, createReader } from '@mini-format/core';

const reg = Registry.load();            // carga las familias incluidas en el paquete
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

Para ejecutar el ejemplo directamente desde `ts/` durante el desarrollo,
cambia el import por `./src/index.ts` y activa `--experimental-strip-types`.

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

## Pruebas y tipos

```
cd ts
npm test
# o bien
node --experimental-strip-types --no-warnings --test test/*.test.ts
```

El chequeo estricto de la API pública y sus módulos importados pasa con
TypeScript 7.0.2. Desde la raíz del repositorio:

```sh
npx --yes --package typescript@7.0.2 tsc --noEmit --strict --module NodeNext --moduleResolution NodeNext --target ES2022 --allowImportingTsExtensions ts/src/index.ts
```

Este comando puede descargar el compilador si no está en la caché; la instalación
y ejecución del `.tgz` no lo requieren. El borrado de tipos de Node no sustituye
este chequeo.

La suite de conformidad compartida se lee de `../conformance/cases/` (o de la ruta en
`MINI_CONFORMANCE_DIR`); si la carpeta no existe, la suite se omite. El runner
reproduce la lógica de `conformance/run_python.py`. Única correspondencia de API:
en modo tolerante la referencia lanza excepción cuando el documento no se puede
construir (E01); TS devuelve un `Document` sin cabecera con E01, y el runner lo
trata como «no construido».

Como en la referencia, los escapes se validan también en modo tolerante (E09 y
el registro se descarta), un escape inválido en la cabecera es E09 dentro de la
validación y una línea rechazada no reserva su valor `unique`.

## Implementaciones y motor del playground

`js/mini.js`, el motor del playground, ya no es un port escrito a mano: desde 1.2.0
se genera desde `ts/src` con `node --no-warnings tools/build_js.mjs` (un paquete UMD
sin dependencias que expone el global `MINI`). `node tests/test_js_port.mjs` falla si
el archivo versionado no está al día y ejecuta todos los casos de conformidad contra
él (`node conformance/run_js.mjs` imprime el mismo informe por categoría). Así, el
navegador valida exactamente como esta biblioteca.

Diferencias que quedan entre la referencia Python y TypeScript (criterio: si la SPEC
decide, se sigue la SPEC; si no, se sigue la referencia Python):

| Tema | Python | TS y `js/mini.js` |
|---|---|---|
| Documento vacío en modo tolerante | lanza siempre | devuelve `Document` con E01 (SPEC §8) |
| `clave\=valor` en cabecera (tolerante) | clave rota | E12 (primer `=` no escapado, SPEC §3.2) |
| Prefijo con letras no ASCII | acepta | rechaza (SPEC §4) |
| Firma/spec de `float` con `max: 3.0` | `3.0` | `3` (JSON.parse no distingue) |
| Enteros fuera de ±2^53 | exactos | pierden precisión (usa `decimal` para valores exactos) |

## Limitaciones

- Enteros fuera de ±2^53 pierden precisión (números de JavaScript).
- `Registry.load` requiere Node (usa `process.getBuiltinModule`); el resto de la
  biblioteca no depende de Node.
