/** Genera js/mini.js (motor del playground) desde la biblioteca TypeScript ts/src.
 *
 *     node --no-warnings tools/build_js.mjs            # escribe js/mini.js
 *     node --no-warnings tools/build_js.mjs --check    # sale con 1 si js/mini.js no está al día
 *
 * El navegador recibe así la misma implementación que aprueba la suite de conformidad
 * (un único comportamiento verificable). Cada módulo de ts/src se despoja de tipos con
 * `stripTypeScriptTypes` de Node (≥ 22.13), se envuelve en su propio ámbito y se enlaza por
 * orden topológico de sus importaciones relativas; el resultado es un UMD sin dependencias
 * que expone el global `MINI` (navegador) o `module.exports` (Node/CommonJS).
 * Determinismo: el resultado no depende de los finales de línea de los fuentes (se leen con LF), pero SÍ puede depender de
 * la versión de Node, porque `stripTypeScriptTypes` (amaro) decide cómo quedan los huecos de los tipos. Solo se verificó con
 * Node 22.14.0 (la otra versión no estaba instalada), que es la que fija .github/workflows/ci.yml; al subirla hay que
 * regenerar js/mini.js, revisar el diff y cambiar el número en ci.yml y sitio.yml a la vez.
 * Solo se incluyen los módulos alcanzables desde ENTRY: registry.ts usa `import.meta` y
 * node:fs, que no existen en un script clásico de navegador.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import fs from 'node:fs';
import path from 'node:path';
import { stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SRC = path.join(ROOT, 'ts', 'src');
export const OUTPUT = path.join(ROOT, 'js', 'mini.js');
const ENTRY = ['errors', 'values', 'codec', 'contract', 'parser', 'serializer', 'prompt', 'stream', 'repair', 'schema'];

const IMPORT_RE = /^\s*import\s+([^;]*?)\s+from\s+['"]\.\/([\w-]+)\.ts['"];?/gm;
const EXPORT_RE = /^export\s+((?:async\s+)?(?:function\*?|class|const|let|var))\s+([A-Za-z_$][\w$]*)/gm;

/** Lee un fuente de ts/src con finales de línea LF, sea cual sea su codificación en disco.
 *  Sin esto el bundle depende de `core.autocrlf` del checkout: un `.ts` en CRLF dejaba CR sueltos
 *  y líneas de solo espacios en js/mini.js (auditoría V5). */
function readSource(file) {
  return fs.readFileSync(file, 'utf8').replace(/\r\n?/g, '\n');
}

function readModule(name) {
  const source = readSource(path.join(SRC, `${name}.ts`));
  let code = stripTypeScriptTypes(source, { mode: 'strip' });
  const deps = [];
  code = code.replace(IMPORT_RE, (_all, clause, dep) => {
    deps.push(dep);
    const c = clause.trim();
    const ns = /^\*\s+as\s+([\w$]+)$/.exec(c);
    if (ns) return `const ${ns[1]} = __m[${JSON.stringify(dep)}];`;
    const named = /^\{([\s\S]*)\}$/.exec(c);
    if (!named) throw new Error(`${name}.ts: unsupported import clause '${c}'`);
    const parts = named[1].split(',').map(s => s.trim()).filter(Boolean)
      .map(s => s.replace(/^([\w$]+)\s+as\s+([\w$]+)$/, '$1: $2'));
    return `const { ${parts.join(', ')} } = __m[${JSON.stringify(dep)}];`;
  });
  if (/^\s*import\s/m.test(code) || /\bimport\.meta\b/.test(code)) {
    throw new Error(`${name}.ts: only relative './x.ts' imports can be bundled for the browser`);
  }
  const exports = [];
  code = code.replace(EXPORT_RE, (_all, kind, id) => {
    exports.push(id);
    return `${kind} ${id}`;
  });
  if (/^export\s/m.test(code)) throw new Error(`${name}.ts: unsupported export form`);
  return { name, code, deps, exports };
}

/** Devuelve el texto de js/mini.js generado desde ts/src. */
export function buildBundle() {
  const modules = new Map();
  const order = [];
  const visiting = new Set();
  const visit = name => {
    if (modules.has(name)) return;
    if (visiting.has(name)) throw new Error(`import cycle through ${name}.ts`);
    visiting.add(name);
    const mod = readModule(name);
    for (const dep of mod.deps) visit(dep);
    visiting.delete(name);
    modules.set(name, mod);
    order.push(mod);
  };
  for (const name of ENTRY) visit(name);
  const api = new Map();
  for (const mod of order) {
    for (const id of mod.exports) {
      if (api.has(id)) throw new Error(`export '${id}' defined in ${api.get(id)}.ts and ${mod.name}.ts`);
      api.set(id, mod.name);
    }
  }
  const index = readSource(path.join(SRC, 'index.ts'));
  const constant = key => {
    const m = new RegExp(`export const ${key} = '([^']+)'`).exec(index);
    if (!m) throw new Error(`index.ts does not define ${key}`);
    return m[1];
  };
  const body = order.map(mod => [
    `  // ---------------------------------------------------------------- ${mod.name}.ts`,
    `  __m[${JSON.stringify(mod.name)}] = (function () {`,
    mod.code.replace(/^\/\*[\s\S]*?\*\/\s*/, '').trimEnd().split('\n').map(l => (l ? '    ' + l : l)).join('\n'),
    `    return { ${mod.exports.join(', ')} };`,
    '  })();',
  ].join('\n')).join('\n\n');
  const members = [...api].map(([id, mod]) => `    ${id}: __m[${JSON.stringify(mod)}].${id},`).join('\n');
  return `/* mini.js — motor JavaScript de .mini para el navegador (playground) y CommonJS.
 * ARCHIVO GENERADO por tools/build_js.mjs desde ts/src (@mini-format/core ${constant('VERSION')}, SPEC ${constant('SPEC_VERSION')}).
 * No se edita a mano: se modifica ts/src y se ejecuta \`node --no-warnings tools/build_js.mjs\`.
 * tests/test_js_port.mjs comprueba que está al día y ejecuta toda la suite de conformidad contra él.
 * Expone el global \`MINI\` (navegador) o \`module.exports\` (Node) con la API de la biblioteca:
 *   parse(text, contract, {strict}) -> Document {prefix, header, records, errors, canonical()}
 *   dumps(obj, contract), specBlock(contract, lang, example), checkFork(child, parent),
 *   normalizeContract(json), signature(contract), createReader(contract, options), ...
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MINI = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const __m = {};

${body}

  return Object.freeze({
${members}
    VERSION: ${JSON.stringify(constant('VERSION'))},
    SPEC_VERSION: ${JSON.stringify(constant('SPEC_VERSION'))},
  });
});
`;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const text = buildBundle();
  if (process.argv.includes('--check')) {
    const current = fs.existsSync(OUTPUT) ? fs.readFileSync(OUTPUT, 'utf8').replace(/\r\n/g, '\n') : '';
    if (current !== text) {
      console.error('js/mini.js is out of date: run node --no-warnings tools/build_js.mjs');
      process.exit(1);
    }
    console.log('js/mini.js is up to date');
  } else {
    fs.writeFileSync(OUTPUT, text, 'utf8');
    console.log(`Built ${path.relative(ROOT, OUTPUT)} (${Buffer.byteLength(text)} bytes, ${text.split('\n').length} lines)`);
  }
}
