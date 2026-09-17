/* repair.test.ts — HU16: reparación selectiva (extractDocument, repairRequest, mergeRepair).
 * Paridad con la referencia Python mediante fixtures/repair_parity.json
 * (regenerar con: PYTHONPATH=src python ts/test/fixtures/gen_repair_parity.py).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { extractDocument, invalidItems, mergeRepair, parse, repairRequest } from '../src/index.ts';
import type { MergeResult, RepairRequest } from '../src/index.ts';
import { LF, REG, lf, read } from './helpers.ts';

const CLS = REG.get('cls');
const VALID = lf(read(path.join(REG.paths.get('cls') as string, 'fixtures', 'valid.mini'))).replace(/\n+$/, '');
const LINES = VALID.split(LF);

const sha = (s: string): string => createHash('sha256').update(s, 'utf8').digest('hex');
const doc = (ls: string[]): string => ls.join(LF);
/** En JavaScript JSON.parse no distingue 3.0 de 3: el bloque TS escribe [1.3..3] donde Python escribe [1.3..3.0]. */
const systemKey = (s: string): string => sha(s.replace(/(\d)\.0(?=\]|\.\.)/g, '$1'));

/** Documento de 10 registros con 2 registros inválidos (líneas físicas 4 y 9). */
function tenWithTwoInvalid(): { good: string[]; bad: string[] } {
  const good = [LINES[0].replace('n=12', 'n=10'), ...LINES.slice(1, 11)];
  const bad = [...good];
  bad[3] = bad[3].replace('question,', 'question|');    // separador de campo sin escapar -> E05
  bad[8] = bad[8].replace('|0.7|', '|x0.7|');            // tipo -> E06
  return { good, bad };
}

describe('HU16 escenario 1: la solicitud incluye solo las líneas inválidas', () => {
  test('10 registros, 2 inválidos -> 2 líneas con sus códigos', () => {
    const { good, bad } = tenWithTwoInvalid();
    const req = repairRequest(doc(bad), CLS, 'es');
    assert.equal(req.needed, true);
    assert.deepEqual(req.items.map(it => it.line), [4, 9]);
    assert.deepEqual(req.items.map(it => it.errors.map(e => e.code)), [['E05'], ['E06']]);
    assert.ok(req.user.includes('[L4] ' + bad[3]) && req.user.includes('[L9] ' + bad[8]));
    assert.ok(req.user.includes('    - E05: ') && req.user.includes('    - E06 [conf]: '));
    for (let i = 1; i < good.length; i++) {
      if (i !== 3 && i !== 8) assert.ok(!req.user.includes(bad[i]), `línea válida ${i + 1} reenviada`);
    }
    assert.ok(req.user.includes("'cls|n=2'"));
    assert.ok(req.system.includes('FORMATO .mini'));
  });

  test('documento válido: no hay nada que reparar', () => {
    const req = repairRequest(VALID, CLS, 'en');
    assert.equal(req.needed, false);
    assert.deepEqual(req.items, []);
    assert.deepEqual(req.lines, []);
  });

  test('extrae el documento de prosa y cercas de código', () => {
    assert.equal(extractDocument('Aquí tienes:\n```mini\n' + VALID + '\n```\nEspero que sirva.', CLS), VALID);
    assert.equal(extractDocument('```\nhola\n```', CLS), 'hola');
    const d = extractDocument('Resultado:\n' + VALID + '\nFin del documento', CLS);
    assert.deepEqual(invalidItems(d, CLS).map(it => it.text), ['Fin del documento']);
  });

  test('fragmentos de un registro partido se agrupan en un ítem', () => {
    const ls = [...LINES];
    ls[2] = ls[2].replace('flashcards, ', 'flashcards,\n');
    const req = repairRequest(doc(ls), CLS, 'es');
    assert.equal(req.items.length, 1);
    assert.deepEqual(req.items[0].lines, [3, 4]);
    assert.ok(req.user.includes('fragmentos de un mismo registro'));
  });
});

describe('HU16 escenario 2: la fusión conserva los 10 registros en el orden original', () => {
  test('respuesta con las 2 correcciones', () => {
    const { good, bad } = tenWithTwoInvalid();
    const answer = 'Claro:\n```\ncls|n=2\n' + good[3] + '\n' + good[8] + '\n```';
    const req = repairRequest('Nota\n' + doc(bad), CLS, 'es');
    const m = mergeRepair('Nota\n' + doc(bad), answer, CLS, req);
    assert.equal(m.ok, true);
    assert.deepEqual(m.replaced, [4, 9]);
    assert.deepEqual(m.unresolved, []);
    assert.equal(m.document?.records.length, 10);
    assert.deepEqual(m.document?.records, parse(doc(good), CLS).records);
    assert.deepEqual(m.document?.records.map(r => r.id), ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10']);
    assert.equal(m.text, doc(good));
  });

  test('una corrección inválida conserva la línea original', () => {
    const { good, bad } = tenWithTwoInvalid();
    const req = repairRequest(doc(bad), CLS, 'es');
    const m = mergeRepair(doc(bad), 'cls|n=2\n' + good[3] + '\nm8|sigue|mal|x|', CLS, req);
    assert.deepEqual(m.replaced, [4]);
    assert.deepEqual(m.unresolved, [9]);
    assert.ok(m.text.split(LF).includes(bad[8]));
    assert.equal(m.ok, false);
  });

  test('marca de eliminación y duplicados', () => {
    const ls = [...LINES];
    ls.splice(4, 0, 'Comentario del modelo sin barras');
    const req = repairRequest(doc(ls), CLS, 'es');
    const m = mergeRepair(doc(ls), 'cls|n=1\n-', CLS, req);
    assert.deepEqual(m.dropped, [5]);
    assert.equal(m.text, VALID);
    const dup = [...LINES];
    dup[3] = dup[3].replace('question,', 'question|');
    const m2 = mergeRepair(doc(dup), 'cls|n=1\n' + LINES[2], CLS, repairRequest(doc(dup), CLS));
    assert.deepEqual(m2.dropped, [4]);
    assert.ok(m2.notes.some(n => n.includes('duplicates')));
  });

  test('corrección de la cabecera', () => {
    const ls = [...LINES];
    ls[0] = 'cls|d=20260603|k=6';
    const req = repairRequest(doc(ls), CLS, 'es');
    assert.ok(req.items[0].isHeader && req.user.includes('cabecera'));
    const m = mergeRepair(doc(ls), 'cls|n=1\n' + LINES[0], CLS, req);
    assert.deepEqual(m.replaced, [1]);
    assert.equal(m.ok, true);
  });
});

// ------------------------------------------------------------ paridad con Python
type PyError = (string | number)[];
interface PyMerge {
  text_sha256: string; ok: boolean; replaced: number[]; dropped: number[]; unresolved: number[];
  notes: string[]; has_document: boolean; errors: PyError[];
}
interface PyCase {
  prefix: string; name: string; input: string; lang: string;
  options: { include_spec: boolean; context?: string; max_items?: number };
  extracted_sha256: string;
  request: {
    system_key: string; user: string; document_sha256: string; prefix: string; max_tokens_hint: number;
    needed: boolean; lines: number[];
    items: { line: number; text: string; is_header: boolean; lines: number[]; errors: PyError[] }[];
  };
  merges: { answer: string; result: PyMerge; result_no_request: PyMerge | null }[];
}

const PARITY = JSON.parse(read(fileURLToPath(new URL('./fixtures/repair_parity.json', import.meta.url)))) as { cases: PyCase[] };

function mergeView(m: MergeResult): PyMerge {
  return {
    text_sha256: sha(m.text), ok: m.ok, replaced: m.replaced, dropped: m.dropped, unresolved: m.unresolved,
    notes: m.notes, has_document: m.document !== null, errors: m.errors.map(e => [e.code, e.line, e.field]),
  };
}

function requestView(r: RepairRequest): PyCase['request'] {
  return {
    system_key: systemKey(r.system), user: r.user, document_sha256: sha(r.document), prefix: r.prefix,
    max_tokens_hint: r.maxTokensHint, needed: r.needed, lines: r.lines,
    items: r.items.map(it => ({
      line: it.line, text: it.text, is_header: it.isHeader, lines: it.lines,
      errors: it.errors.map(e => [e.code, e.line, e.field, e.message]),
    })),
  };
}

describe('paridad con minifmt.ai.repair (Python)', () => {
  assert.ok(PARITY.cases.length >= 100);
  for (const cs of PARITY.cases) {
    test(`${cs.prefix} · ${cs.name}`, () => {
      const c = REG.get(cs.prefix);
      assert.equal(sha(extractDocument(cs.input, c)), cs.extracted_sha256, 'extractDocument');
      const req = repairRequest(cs.input, c, cs.lang, {
        includeSpec: cs.options.include_spec, context: cs.options.context, maxItems: cs.options.max_items,
      });
      assert.deepEqual(requestView(req), cs.request);
      for (const [i, mg] of cs.merges.entries()) {
        assert.deepEqual(mergeView(mergeRepair(cs.input, mg.answer, c, req)), mg.result, `merge ${i}`);
        const expected = mg.result_no_request ?? mg.result;
        assert.deepEqual(mergeView(mergeRepair(cs.input, mg.answer, c)), expected, `merge ${i} sin solicitud`);
      }
    });
  }
});
