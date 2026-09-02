// Builds a dependency-free browser bundle (IIFE, global `TOON`) of the official
// TOON reference implementation from its TypeScript sources, using Node's
// built-in type stripping. No external tooling required.
//   node build_bundle.mjs  ->  toon.bundle.js
import { stripTypeScriptTypes } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(new URL('.', import.meta.url).pathname, 'vendor/toon/src');
const files = [];
(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p); else if (p.endsWith('.ts')) files.push(p);
  }
})(SRC);

function transform(file) {
  let code = stripTypeScriptTypes(fs.readFileSync(file, 'utf8'), { mode: 'strip' });
  const id = path.relative(SRC, file).replace(/\\/g, '/');
  const dir = path.posix.dirname(id);
  const resolve = (spec) => path.posix.normalize(path.posix.join(dir, spec));
  // import { a, b as c } from './x.ts'
  code = code.replace(/^[ \t]*import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"][ \t]*;?/gm, (m, names, spec) => {
    const list = names.split(',').map(s => s.trim()).filter(Boolean).map(s => {
      const [a, b] = s.split(/\s+as\s+/); return b ? `${a}: ${b}` : a;
    }).join(', ');
    return `const { ${list} } = __require('${resolve(spec)}');`;
  });
  // side-effect / type-only imports (already stripped) -> nothing
  code = code.replace(/^[ \t]*import\s+['"][^'"]+['"][ \t]*;?/gm, '');
  // export { a, b as c } from './x.ts'   |  export { a, b }
  code = code.replace(/^[ \t]*export\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"][ \t]*;?/gm, (m, names, spec) => {
    const parts = names.split(',').map(s => s.trim()).filter(Boolean).map(s => {
      const [a, b] = s.split(/\s+as\s+/); return `exports.${b || a} = __require('${resolve(spec)}').${a};`;
    });
    return parts.join('\n');
  });
  code = code.replace(/^[ \t]*export\s*\{([^}]*)\}[ \t]*;?/gm, (m, names) => names.split(',').map(s => s.trim()).filter(Boolean).map(s => {
    const [a, b] = s.split(/\s+as\s+/); return `exports.${b || a} = ${a};`;
  }).join('\n'));
  // export * from './x.ts'
  code = code.replace(/^[ \t]*export\s*\*\s*from\s*['"]([^'"]+)['"][ \t]*;?/gm, (m, spec) => `Object.assign(exports, __require('${resolve(spec)}'));`);
  // export function f / export async function / export class / export const|let|var
  code = code.replace(/^(\s*)export\s+(async\s+function\*?|function\*?|class)\s+([A-Za-z_$][\w$]*)/gm, (m, ws, kind, name) => `${ws}${kind} ${name}/*EXPORT:${name}*/`);
  code = code.replace(/^(\s*)export\s+(const|let|var)\s+([A-Za-z_$][\w$]*)/gm, (m, ws, kind, name) => `${ws}${kind} ${name}/*EXPORT:${name}*/`);
  code = code.replace(/^[ \t]*export\s+default\s+/gm, 'exports.default = ');
  const names = [...code.matchAll(/\/\*EXPORT:([\w$]+)\*\//g)].map(m => m[1]);
  code = code.replace(/\/\*EXPORT:[\w$]+\*\//g, '');
  code += '\n' + names.map(n => `exports.${n} = ${n};`).join('\n');
  return { id, code };
}

const modules = files.map(transform);
let out = `/* TOON reference implementation (https://github.com/toon-format/toon, MIT) — browser bundle built from the TypeScript sources with Node's type stripping. Global: TOON */\n`;
out += `var TOON = (function(){\nconst __defs = {};\nconst __cache = {};\nfunction __require(id){ if (__cache[id]) return __cache[id]; const m = {exports:{}}; __cache[id] = m.exports; __defs[id](m.exports, m); return m.exports; }\n`;
for (const m of modules) {
  out += `__defs['${m.id}'] = function(exports, module){\n${m.code}\n};\n`;
}
out += `return __require('index.ts');\n})();\nif (typeof module !== 'undefined') module.exports = TOON;\n`;
fs.writeFileSync(path.resolve(new URL('.', import.meta.url).pathname, 'toon.bundle.js'), out);
console.log('bundled', modules.length, 'modules,', out.length, 'bytes');
