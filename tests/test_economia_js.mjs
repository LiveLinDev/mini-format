// Economía: sitio/economia-calculo.js debe dar EXACTAMENTE las mismas cadenas que
// experiments/economia/calculo.py para los vectores dorados de evidencia/vectores/economia.json.
//   node tests/test_economia_js.mjs
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const E = require('../sitio/economia-calculo.js');
const docVec = JSON.parse(fs.readFileSync(path.join(ROOT, 'evidencia/vectores/economia.json'), 'utf8'));

let checks = 0, fails = 0;
function fail(msg) { fails++; console.log('FAIL ' + msg); }

// 1. Vectores dorados: resultado idéntico (comparación profunda estricta).
const ids = new Set();
for (const v of docVec.vectores) {
  checks++;
  if (ids.has(v.id)) { fail('id de vector repetido ' + v.id); continue; }
  ids.add(v.id);
  if (v.error) {
    try { E.ejecutar(v.operacion, v.entrada); fail(v.id + ': debía lanzar un error'); } catch (e) { /* esperado */ }
    continue;
  }
  let obtenido;
  try { obtenido = E.ejecutar(v.operacion, v.entrada); } catch (e) { fail(v.id + ': lanzó ' + e.message); continue; }
  try { assert.deepStrictEqual(JSON.parse(JSON.stringify(obtenido)), v.salida); }
  catch (e) { fail(v.id + ': la salida difiere de la dorada\n' + e.message.split('\n').slice(0, 12).join('\n')); }
}

// 2. Cobertura mínima de casos obligatorios (el archivo no puede perder los casos difíciles).
const obligatorios = [
  'solicitud_razonamiento_aparte', 'solicitud_categorias_sin_solape_razonamiento_incluido', 'solicitud_cache_lectura_y_escritura',
  'solicitud_tarifa_no_verificada', 'total_cero_validos', 'equilibrio_inexistente', 'redondeo_limite_half_up', 'razon_sin_ahorro',
  'escenario_a_solo_salida', 'escenario_b_perfiles_1000_usd',
];
for (const id of obligatorios) { checks++; if (!ids.has(id)) fail('falta el vector obligatorio ' + id); }

// 3. Propiedades que no dependen de los vectores.
checks++;
try { E.redondear(0.5, 2); fail('un Number no entero debe rechazarse'); } catch (e) { assert.ok(e instanceof TypeError); }
checks++;
assert.equal(E.redondear('0.0000005', 6), '0.000001');
assert.equal(E.redondear('-0.0000005', 6), '-0.000001');
assert.equal(E.redondear('123456789012345678901234567890.1234565', 6), '123456789012345678901234567890.123457'); // más allá de 2^53
assert.equal(E.razonYAhorro(650, 1000).ahorro_salida_pct, '35.0000');
const r0 = E.razonYAhorro(10, 0);
assert.equal(r0.razon, null); assert.equal(r0.ahorro_salida_pct, null); assert.equal(r0.estado, 'no_definido');
const sinTarifa = E.costoSolicitud({ id: 'x', intentos: [{ fase: 'generacion', modelo: 'm', proveedor: 'p', usage: { entrada_sin_cache: 1, salida: 1, razonamiento: 0, razonamiento_incluido_en_salida: true } }] }, []);
assert.equal(sinTarifa.costo_usd, null); assert.equal(sinTarifa.estado, 'tarifa_no_verificada');

console.log(`economia-calculo.js: ${checks - fails}/${checks} comprobaciones, ${docVec.vectores.length} vectores dorados`);
if (fails) { console.log(fails + ' fallo(s)'); process.exit(1); }
console.log('OK');
