/* Servidor de consultas para las pruebas de propiedades: lee una línea JSON por consulta y responde con una línea.
 *
 *   {"op": "parse", "contrato": {...}, "dato": "texto .mini"}   ->  {"canon": {...}, "errs": [["E06", 2], ...]}
 *   {"op": "dumps", "contrato": {...}, "dato": {objeto canónico}} ->  {"texto": "..."}  o  {"error": ["E13", 2]}
 *
 * Usa js/mini.js (el motor que recibe el navegador). No abre red ni escribe archivos.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import readline from 'node:readline';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MINI = require(path.join(ROOT, 'js', 'mini.js'));
const cache = new Map();
const normalizar = json => {
  const k = JSON.stringify(json);
  if (!cache.has(k)) cache.set(k, MINI.normalizeContract(json));
  return cache.get(k);
};

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', linea => {
  let salida;
  try {
    const q = JSON.parse(linea);
    const c = normalizar(q.contrato);
    if (q.op === 'parse') {
      const doc = MINI.parse(q.dato, c, { strict: false });
      salida = { canon: doc.canonical(), errs: doc.errors.map(e => [e.code, e.line]) };
    } else if (q.op === 'dumps') {
      try {
        salida = { texto: MINI.dumps(q.dato, c) };
      } catch (e) {
        salida = e && e.code ? { error: [e.code, e.line] } : { excepcion: String(e && e.stack || e).slice(0, 200) };
      }
    } else {
      salida = { excepcion: 'operación desconocida' };
    }
  } catch (e) {
    salida = { excepcion: String((e && e.stack) || e).slice(0, 200) };
  }
  process.stdout.write(JSON.stringify(salida) + '\n');
});
