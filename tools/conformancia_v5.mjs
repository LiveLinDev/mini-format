/* Conformidad de js/mini.js con total, por categoría y por familia, en JSON (para tools/ejecutar_v5.py).
 *
 *     node --no-warnings tools/conformancia_v5.mjs
 *
 * Reutiliza conformance/run_js.mjs (loadCases, runCase) sin duplicar su lógica; solo agrupa los resultados.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { loadCases, loadEngine, runCase } = await import(pathToFileURL(path.join(ROOT, 'conformance', 'run_js.mjs')).href);

const MINI = loadEngine();
const porCategoria = {};
const porFamilia = {};
const fallos = [];
let total = 0;
for (const k of loadCases()) {
  total++;
  const msg = runCase(MINI, k);
  const familia = k.family ?? (k.contract && k.contract.prefix ? `contrato:${k.contract.prefix}` : 'contrato_embebido');
  for (const [grupo, clave] of [[porCategoria, k.category], [porFamilia, familia]]) {
    const c = (grupo[clave] ||= { pass: 0, fail: 0 });
    if (msg === null) c.pass++;
    else c.fail++;
  }
  if (msg !== null) fallos.push([k.id, msg]);
}
process.stdout.write(JSON.stringify({ total, pasan: total - fallos.length, fallos, por_categoria: porCategoria, por_familia: porFamilia }) + '\n');
process.exit(fallos.length ? 1 : 0);
