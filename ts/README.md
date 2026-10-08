# @mini-format/core — biblioteca TypeScript de `.mini`

Versión de software 1.3.3. Implementación TypeScript modular y tipada del núcleo
`.mini` (SPEC 1.1):
parser, serializador, bloque de especificación para prompts, registro de familias
(forks), una API de lectura en streaming para respuestas de modelos token a token,
reparación selectiva, contratos desde Zod / JSON Schema y adaptadores de modelos
intercambiables (OpenAI, Anthropic, Groq, simulado) sobre `fetch`. Sin dependencias
de ejecución; todo salvo `Registry.load` funciona también en el navegador.

Incluye las catorce familias del núcleo. Los contratos adaptados a muestras JSON
por `mini build` usan otro perfil, `mini-domain/1`, y el parser Python que se genera
con ellos; esta biblioteca no interpreta ese perfil. Consulta la
[guía del constructor](https://mini-format.pmoluna.com/docs/build/) y la
[especificación del perfil generado](https://mini-format.pmoluna.com/docs/profile/).

Autores: A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC). Licencia MIT.

## Instalación del paquete

Necesitas Node.js ≥ 22.6. Descarga `mini-format-core-1.3.3.tgz` desde Descargas
o extrae ese archivo del ZIP del toolkit. Instala el archivo local:

```sh
npm install --offline --ignore-scripts --no-audit --no-fund ./mini-format-core-1.3.3.tgz
```

El archivo contiene JavaScript ESM compilado y declaraciones `.d.ts` en `dist/`
(`exports.types` apunta a `dist/index.d.ts`), los contratos de las catorce familias
y las fuentes TypeScript. Se importa desde
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
`ts/dist/`, y después emite las declaraciones `.d.ts` con el compilador de
TypeScript instalado en `ts/node_modules` (ejecuta antes `npm ci` en `ts/`).
`--no-types` genera solo el JavaScript. Desde `ts/`, `npm run build` hace lo mismo.

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
│   ├── repair.ts      extractDocument, repairRequest, mergeRepair (reparación selectiva)
│   ├── schema.ts      fromJsonSchema, fromZod
│   ├── adapters.ts    ModelAdapter, OpenAI/Responses/Anthropic/Groq/Simulated, streamRecords
│   ├── sse.ts         parseSSE (Server-Sent Events sobre fetch)
│   └── index.ts       API pública
├── tsconfig.json      chequeo estricto de src/ (tsconfig.test.json añade test/)
└── test/
    ├── fixtures.test.ts     paridad con forks/*/fixtures y reglas de validación
    ├── repair.test.ts       reparación selectiva y paridad con minifmt.ai.repair (fixtures/)
    ├── schema.test.ts       contratos desde esquemas Zod reales
    ├── adapters.test.ts     proveedores con fetch simulado y flujos SSE sintéticos (sin red)
    ├── dist.test.ts         ESM compilado sin APIs de Node y declaraciones .d.ts
    ├── roundtrip.test.ts    parse(dumps(obj)) == obj, codec, formato numérico
    ├── stream.test.ts       fragmentos aleatorios de 1–7 caracteres == parse
    ├── truncation.test.ts   salidas truncadas
    ├── conformance.test.ts  runner de ../conformance/ (se omite si no existe)
    ├── cortes.test.ts       cortes de bytes en cada frontera (ts/src y js/mini.js) == parse
    ├── defectos.test.ts     defectos corregidos tras la auditoría V5 (unique en la reparación, max 0, finalRecords) y propuestas del ADR 0017
    ├── bigint.test.ts       comportamiento actual con enteros fuera de ±2^53 (ADR 0018, propuesta)
    ├── esquema_ramas.test.ts  ramas de fromJsonSchema/fromZod
    ├── registro.test.ts     Registry sobre disco y en memoria, roundtripOk
    └── helpers.ts
```

## Uso

```ts
import { Registry, parse, dumps, specBlock, createReader } from '@mini-format/core';

const reg = Registry.load('./forks');   // ZIP opcional de familias extraído
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
res.finalRecords;  // registros que completó end() (última línea válida sin LF); ya cuentan en valid/records
res.terminated;    // el flujo terminó en LF
```

Un registro se emite en cuanto su línea se cierra con LF. `readRecords(iterable, contrato)`
envuelve lo mismo como generador asíncrono. El lector usa el mismo motor por
líneas que `parse`, por lo que el resultado final es idéntico sin importar cómo
se fragmente la entrada.

Nota: si la última línea no termina en LF y su último campo sigue siendo válido
(por ejemplo, un texto cortado), el registro es indistinguible de uno completo;
en ese caso `terminated` es `false` y conviene tratarlo como sospechoso.

### En el navegador

`dist/` solo importa sus propios módulos relativos (sin `node:`, `require` ni
`Buffer`), así que puede servirse tal cual e importarse desde una página:

```html
<script type="module">
  import { parse } from './mini-format/dist/index.js';
  const contrato = await (await fetch('./forks/cls/contract.json')).json();
  const doc = parse(texto, contrato, { strict: false });
  console.log(doc.records, doc.errors.map(String));
</script>
```

Pasa los contratos como objetos (`fetch` + `json()`) o con `Registry.from([...])`:
`Registry.load`, `loadContract` y `defaultForksDir` leen el disco y requieren Node.
`test/dist.test.ts` lo verifica cargando `dist` en un contexto `vm` que solo tiene
`TextEncoder`, `TextDecoder` y `URL`.

### Reparación selectiva

Mismo algoritmo y mismo texto de solicitud que `minifmt.ai.repair` (Python),
verificado con fixtures de paridad:

```ts
import { repairRequest, mergeRepair } from '@mini-format/core';

const req = repairRequest(respuestaDelModelo, contrato, 'es');   // solo las líneas inválidas y sus códigos
if (req.needed) {
  const fix = await adaptador.generate({ system: req.system, user: req.user, maxTokens: req.maxTokensHint * 2, temperature: 0 });
  const fusion = mergeRepair(respuestaDelModelo, fix.text, contrato, req);
  fusion.text; fusion.ok; fusion.replaced; fusion.dropped; fusion.unresolved;
}
```

`extractDocument` quita la prosa y las cercas de código previas a la cabecera;
`mergeRepair` acepta una corrección solo si es válida por sí sola, conserva el orden
original y nunca reescribe `n` (los registros perdidos siguen visibles como E04).

### Contratos desde Zod o JSON Schema

```ts
import { z } from 'zod';
import { fromZod } from '@mini-format/core';

const Ticket = z.object({
  id: z.string(),
  prioridad: z.number().int().min(1).max(5),
  estado: z.enum(['abierto', 'cerrado']),
  etiquetas: z.array(z.string()).max(4),
  nota: z.string().optional(),
});
const contrato = fromZod(Ticket, { prefix: 'tk', unique: ['id'] });
```

Zod no es dependencia: `fromZod` llama a `toJSONSchema()` del esquema (Zod v4) o al
conversor pasado en `options.toJSONSchema`, y luego a `fromJsonSchema`. Solo se
admiten registros planos (SPEC §12): string, integer (con `minimum`/`maximum`),
number, boolean, enums/literales de texto, listas de escalares
(`minItems`/`maxItems`) y campos opcionales, anulables o con valor por defecto. Los
objetos anidados, listas de objetos, uniones y fechas lanzan `MiniError` E20; las
restricciones que `.mini` no valida (`pattern`, `format`, `minLength`...) también,
salvo con `unsupported: 'ignore'` (entonces se informan en `warnings`). Un campo
vacío se decodifica como `null`: en campos `.optional()` que no son `.nullable()`,
elimina las claves `null` antes de llamar a `parse` de Zod.

### Adaptadores de modelos

Todos los proveedores implementan la misma interfaz, de modo que reemplazar uno
no cambia el resto del código:

```ts
import { AnthropicAdapter, OpenAIAdapter, streamRecords, specBlock } from '@mini-format/core';
import type { ModelAdapter } from '@mini-format/core';

const adaptador: ModelAdapter = new OpenAIAdapter('gpt-4.1-mini');   // o new AnthropicAdapter('claude-...')
const solicitud = { system: specBlock(contrato, 'es'), user: 'Clasifica...', maxTokens: 2000, temperature: 0 };

const it = streamRecords(adaptador, contrato, solicitud);   // SSE -> createReader: registros a medida que llegan
let paso = await it.next();
for (; !paso.done; paso = await it.next()) mostrar(paso.value.record);
paso.value.reader;       // ReaderResult (documento, errores, truncated...)
paso.value.generation;   // { text, inputTokens, outputTokens, stopReason, ... }
```

| Clase | Endpoint | Clave |
|---|---|---|
| `OpenAIAdapter` | Chat Completions `/v1/chat/completions` | `OPENAI_API_KEY` |
| `OpenAIResponsesAdapter` | Responses `/v1/responses` | `OPENAI_API_KEY` |
| `AnthropicAdapter` | Messages `/v1/messages` (`browser: true` para llamadas directas desde el navegador) | `ANTHROPIC_API_KEY` |
| `GroqAdapter` | compatible con OpenAI `/openai/v1/chat/completions` | `GROQ_API_KEY` |
| `SimulatedAdapter` | sin red: respuestas fijas o calculadas, troceado determinista | ninguna |

`generate(solicitud)` devuelve el resultado completo; `stream(solicitud)` devuelve
un iterable asíncrono de fragmentos de texto más `result`. Opciones: `apiKey` (si
no, la variable de entorno, cuando existe `process.env`), `fetch` (inyectable),
`url`, `retries`, `sleep`, `structured`, `sendTemperature`, `extraBody`, `headers`.
`responseFormat` (`{type: 'json_schema', name, schema}`) se traduce al modo
estructurado de cada proveedor. Los mensajes de error están depurados: las claves
nunca aparecen en ellos. `getAdapter(proveedor, modelo, opciones)` crea adaptadores
por nombre. `streamRecords` descarta de forma incremental la prosa y las cercas
iniciales (como `extractDocument`); `extract: false` lo desactiva. En el navegador,
no expongas claves: usa un proxy propio mediante `url`.

## Pruebas y tipos

```
cd ts
npm ci             # typescript, zod y @types/node (solo desarrollo)
npm test
npm run typecheck  # tsc con strict: true sobre src/ y test/
```

`npm test` no usa red ni claves: los adaptadores se prueban con un `fetch`
simulado y flujos SSE sintéticos por proveedor. Sin `npm ci`, se omiten las pruebas
con Zod y la verificación de `.d.ts`. Los fixtures de paridad de la reparación se
regeneran desde la referencia Python con
`PYTHONPATH=src python ts/test/fixtures/gen_repair_parity.py`.

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
| Prefijo con letras no ASCII | acepta | rechaza (SPEC §4) |
| Firma/spec de `float` con `max: 3.0` | `3.0` | `3` (JSON.parse no distingue) |
| Enteros fuera de ±2^53 | exactos | pierden precisión **sin error ni aviso** (usa `decimal` para valores exactos); decisión pendiente: ADR 0018 (propuesta), comportamiento fijado por `ts/test/bigint.test.ts` |

## Limitaciones

- Enteros fuera de ±2^53 pierden precisión (números de JavaScript).
- `Registry.load` requiere Node (usa `process.getBuiltinModule`); el resto de la
  biblioteca no depende de Node.
- `fromZod`/`fromJsonSchema` no generan campos `mlist` ni `tuple`.
- `SimulatedAdapter` no reproduce los perfiles de fallas del simulador Python:
  devuelve respuestas fijas o calculadas (para pruebas y demostraciones).
