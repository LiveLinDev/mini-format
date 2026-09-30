/* Lote de análisis tolerante con js/mini.js para tools/fuzz_diferencial.py.
 *
 *     node --no-warnings tools/fuzz_motor_js.mjs entrada.json salida.json [ruta/a/mini.js]
 *
 * Lee {"contracts": {...}, "inputs": [{"contract", "text"}, ...]} y escribe, por entrada,
 * {"canon", "errs"} o {"jsexc"} (excepción no controlada: siempre es un defecto).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [entrada, salida, motor = path.join(ROOT, 'js', 'mini.js')] = process.argv.slice(2);
const MINI = require(path.resolve(motor));
const datos = JSON.parse(fs.readFileSync(entrada, 'utf8'));
const normalizados = {};
const pares = errores => {
  const vistos = new Set(errores.map(e => `${e.code}@${e.line}`));
  return [...vistos].map(s => { const [a, b] = s.split('@'); return [a, Number(b)]; });
};
const resultados = [];
for (const it of datos.inputs) {
  if (!normalizados[it.contract]) normalizados[it.contract] = MINI.normalizeContract(datos.contracts[it.contract]);
  try {
    const doc = MINI.parse(it.text, normalizados[it.contract], { strict: false });
    resultados.push({ canon: doc.headerLine === 0 && doc.errors.some(e => e.code === 'E01') ? null : doc.canonical(), errs: pares(doc.errors) });
  } catch (e) {
    if (e && Array.isArray(e.errors)) resultados.push({ canon: null, errs: pares(e.errors) });
    else resultados.push({ jsexc: String((e && e.stack) || e).slice(0, 200) });
  }
}
fs.writeFileSync(salida, JSON.stringify(resultados));
