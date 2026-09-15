/* fixtures.test.ts — paridad contra forks/*\/fixtures y reglas de validación (SPEC §8, §10).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MiniError, MiniValidationError, canonicalEqual, checkFork, contractToJSON, dumps, normalizeContract,
  parse, roundtripOk, signature, specBlock,
} from '../src/index.ts';
import type { Contract, ContractJSON } from '../src/index.ts';
import path from 'node:path';
import { ALL, BOM, BS, CR, FORKS, LF, REG, fixtures, lf, read } from './helpers.ts';

/** Código esperado según el nombre del fixture negativo, y línea en que debe aparecer. */
const EXPECTED: Record<string, { code: string; line: number }> = {
  'bad_arity.mini': { code: 'E05', line: 3 },
  'bad_count.mini': { code: 'E04', line: 0 },
  'bad_marker.mini': { code: 'E08', line: 2 },
  'bad_type.mini': { code: 'E06', line: 2 },
};

function codes(text: string, c: Contract): string[] {
  try {
    parse(text, c);
  } catch (e) {
    if (e instanceof MiniValidationError) return [...new Set(e.codes)].sort();
    throw e;
  }
  return [];
}

describe('registro de forks', () => {
  test('carga los 14 contratos y cumple los invariantes', () => {
    assert.ok(REG.size >= 14);
    assert.deepEqual(REG.check(), []);
  });

  test('el índice coincide con forks/registry.json', () => {
    const index = JSON.parse(read(path.join(FORKS, 'registry.json')));
    const byPrefix = new Map(REG.toIndex().map(e => [e.prefix, e]));
    for (const ref of index) {
      const mine = byPrefix.get(ref.prefix);
      assert.ok(mine, ref.prefix);
      assert.equal(mine.arity, ref.arity, ref.prefix);
      assert.equal(mine.extensions, ref.extensions, ref.prefix);
      assert.equal(mine.parent, ref.parent, ref.prefix);
      // única diferencia conocida: la referencia imprime 3.0 tal como está en el JSON; aquí 3
      assert.equal(mine.signature, ref.signature.replace('[1.3..3.0]', '[1.3..3]'), ref.prefix);
    }
  });

  test('lineage y get/has', () => {
    assert.deepEqual(REG.lineage('q'), ['q', 'a']);
    assert.ok(REG.has('a'));
    assert.throws(() => REG.get('zz'), (e: unknown) => e instanceof MiniError && e.code === 'E21');
  });
});

describe('paridad con fixtures', () => {
  for (const fx of ALL) {
    const c = fx.contract;
    describe(`familia ${c.prefix}`, () => {
      test('valid.mini -> canonical.json', () => {
        const doc = parse(fx.valid, c);
        assert.ok(canonicalEqual(doc.toCanonical(), fx.canonical));
        assert.ok(canonicalEqual(doc.canonical(), fx.canonical));
        assert.equal(doc.ok, true);
      });

      test('dumps(canonical.json) == valid.mini', () => {
        assert.equal(dumps(fx.canonical, c), lf(fx.valid).replace(/\n$/, ''));
        assert.ok(roundtripOk(fx.canonical, c));
      });

      if (fx.escaping !== null) {
        test('escaping.mini -> escaping.json', () => {
          const doc = parse(fx.escaping as string, c);
          assert.ok(canonicalEqual(doc.toCanonical(), fx.escapingCanonical));
          const again = parse(dumps(doc.toCanonical(), c), c);
          assert.ok(canonicalEqual(again.toCanonical(), fx.escapingCanonical));
        });
      }

      for (const bad of fx.bad) {
        test(`${bad.name} se rechaza con el código esperado`, () => {
          const exp = EXPECTED[bad.name];
          assert.ok(exp, `fixture negativo sin expectativa: ${bad.name}`);
          assert.throws(() => parse(bad.text, c), (e: unknown) => {
            assert.ok(e instanceof MiniValidationError);
            assert.deepEqual(e.errors.map(x => [x.code, x.line]), [[exp.code, exp.line]]);
            return true;
          });
          const lenient = parse(bad.text, c, { strict: false });
          assert.deepEqual(lenient.errors.map(x => x.code), [exp.code]);
          const validCount = (fx.canonical[c.records_key] as unknown[]).length;
          assert.equal(lenient.records.length, exp.code === 'E04' ? validCount : validCount - 1);
        });
      }

      test('specBlock menciona cada campo y la cabecera', () => {
        for (const lang of ['en', 'es']) {
          const block = specBlock(c, lang);
          for (const f of c.fields) assert.ok(block.includes(f.name), `${lang}: ${f.name}`);
          assert.ok(block.includes(c.prefix + '|'));
        }
      });
    });
  }
});

describe('validación (familia a)', () => {
  const A = REG.get('a');
  const A_TEXT = lf(fixtures(A).valid);

  test('documento válido', () => {
    const doc = parse(A_TEXT, A);
    assert.equal(doc.records.length, 12);
    assert.equal(doc.header.n, 12);
    assert.equal((doc.records[10].options as string[])[0], 'impacto, justicia y evidencia');
    assert.equal(doc.records[10].correct, 0);
    assert.deepEqual(doc.records[0].irt, { a: 0.9, b: -1, c: 0.25 });
    assert.equal(doc.version, 1);
    assert.equal(doc.lines, 13);
  });

  test('E04 conteo, E03 sin n, E02 prefijo', () => {
    assert.deepEqual(codes(A_TEXT.replace('n=12', 'n=13'), A), ['E04']);
    assert.ok(codes(A_TEXT.replace('|n=12', ''), A).includes('E03'));
    assert.ok(codes('zz' + A_TEXT.slice(1), A).includes('E02'));
  });

  test('E05 aridad por defecto y por exceso', () => {
    let lines = A_TEXT.trim().split(LF);
    lines[1] = lines[1].split('|').slice(0, 5).join('|');
    assert.deepEqual(codes(lines.join(LF), A), ['E05']);
    lines = A_TEXT.trim().split(LF);
    lines[1] = lines[1] + '|extra';
    assert.deepEqual(codes(lines.join(LF), A), ['E05']);
  });

  test('E08 reglas del marcador', () => {
    assert.deepEqual(codes(A_TEXT.replace('cloroplastos*', 'cloroplastos'), A), ['E08']);
    assert.deepEqual(codes(A_TEXT.replace('núcleo,', 'núcleo*,'), A), ['E08']);
  });

  test('E10 enum, E06 tipo, E13 rango, E11 único', () => {
    assert.deepEqual(codes(A_TEXT.replace('|L1|', '|L9|'), A), ['E10']);
    assert.deepEqual(codes(A_TEXT.replace('|0.9,-1,0.25|', '|x,-1,0.25|'), A), ['E06']);
    assert.deepEqual(codes(A_TEXT.replace('|1|biología', '|7|biología'), A), ['E13']);
    assert.deepEqual(codes(A_TEXT.replace(LF + 'i2|', LF + 'i1|'), A), ['E11']);
  });

  test('E07 aridad de lista por count_key y de tupla', () => {
    assert.deepEqual(codes(A_TEXT.replace('impacto' + BS + ', justicia', 'impacto, justicia'), A), ['E07']);
    assert.deepEqual(codes(A_TEXT.replace('|0.9,-1,0.25|', '|0.9,-1|'), A), ['E07']);
  });

  test('E09 escape inválido y barra final; tolerante informa E09 y descarta el registro', () => {
    const bad = A_TEXT.replace('|Biología|', '|Bio' + BS + 'xlogía|');
    assert.deepEqual(codes(bad, A), ['E09']);
    const doc = parse(bad, A, { strict: false });
    assert.deepEqual(doc.errors.map(e => [e.code, e.line]), [['E09', 2]]);
    assert.equal(doc.records.length, 11);
    assert.equal(doc.records[0].id, 'i2');
    assert.deepEqual(doc.invalidLines(), [2]);
    assert.deepEqual(codes(A_TEXT.replace(',low' + LF, ',low' + BS + LF), A), ['E09']);
  });

  test('E09 en la cabecera se informa sin perder prefijo ni n', () => {
    const bad = A_TEXT.replace('|l=es|', '|l=e' + BS + 'qs|');
    assert.deepEqual(codes(bad, A), ['E09']);
    const doc = parse(bad, A, { strict: false });
    assert.deepEqual(doc.errors.map(e => [e.code, e.line]), [['E09', 1]]);
    assert.equal(doc.header.l, 'e' + BS + 'qs');
    assert.equal(doc.records.length, 12);
    assert.equal(doc.headerErrors().length, 1);
    assert.deepEqual(doc.invalidLines(), []);
    // barra invertida colgante al final de la cabecera: E09 en ambos modos, sin excepción cruda
    const lines = A_TEXT.split(LF);
    const dangling = [lines[0] + BS, ...lines.slice(1)].join(LF);
    assert.deepEqual(codes(dangling, A), ['E09']);
    const doc2 = parse(dangling, A, { strict: false });
    assert.deepEqual(doc2.errors.map(e => [e.code, e.line]), [['E09', 1]]);
    assert.equal(doc2.header.k, 4);
  });

  test('E12 entrada de cabecera sin =', () => {
    assert.deepEqual(codes(A_TEXT.replace('|l=es|', '|les|'), A), ['E12']);
  });

  test('una línea rechazada no reserva su valor único', () => {
    const lines = A_TEXT.trim().split(LF);
    lines[1] = lines[1].replace('|1|biología', '|7|biología'); // i1 con E13
    lines[2] = lines[2].replace(/^i2\|/, 'i1|');               // i1 válido en la línea 3
    const doc = parse(lines.join(LF), A, { strict: false });
    assert.deepEqual(doc.errors.map(e => [e.code, e.line]), [['E13', 2]]);
    assert.equal(doc.records[0].id, 'i1');
    assert.equal(doc.records.length, 11);
    assert.deepEqual(doc.recordLines.slice(0, 2), [3, 4]);
    const dup = A_TEXT.replace(LF + 'i2|', LF + 'i1|');
    assert.deepEqual(parse(dup, A, { strict: false }).errors.map(e => [e.code, e.line]), [['E11', 3]]);
  });

  test('diagnóstico: líneas inválidas, registros faltantes y truncamiento', () => {
    const lines = A_TEXT.trim().split(LF);
    const text = [lines[0], lines[1], lines[2],lines[3].replace('4*', '4'), lines[4].slice(0, 30)].join(LF);
    const doc = parse(text, A, { strict: false });
    const d = doc.diagnostics();
    assert.deepEqual(d.invalid_lines, [4, 5]);
    assert.equal(d.missing_records, 8);
    assert.equal(d.truncated, true);
    assert.deepEqual(d.valid_lines, [2, 3]);
    assert.equal(d.record_lines, 4);
    assert.equal(d.declared_n, 12);
  });

  test('modo tolerante recupera los registros válidos', () => {
    const doc = parse(A_TEXT.replace('cloroplastos*', 'cloroplastos'), A, { strict: false });
    assert.equal(doc.records.length, 11);
    assert.deepEqual(doc.errors.map(e => e.code), ['E08']);
    assert.equal(doc.ok, false);
  });

  test('E01 documento vacío: estricto lanza, tolerante devuelve el error', () => {
    assert.throws(() => parse('  ' + LF + LF, A), (e: unknown) => e instanceof MiniValidationError && e.codes[0] === 'E01');
    const doc = parse('', A, { strict: false });
    assert.deepEqual(doc.errors.map(e => [e.code, e.line]), [['E01', 0]]);
    assert.deepEqual(doc.toCanonical(), { prefix: '', header: {}, items: [] });
  });

  test('CRLF, BOM y líneas en blanco', () => {
    const text = BOM + A_TEXT.split(LF).join(CR + LF + CR + LF);
    assert.equal(parse(text, A).records.length, 12);
  });

  test('elementos entre comillas equivalen al escape', () => {
    const quoted = A_TEXT.replace('impacto' + BS + ', justicia y evidencia*', '"impacto, justicia y evidencia"*')
      .replace('unidad entre mensaje' + BS + ', color y audiencia*', '"unidad entre mensaje, color y audiencia*"');
    assert.ok(canonicalEqual(parse(quoted, A).toCanonical(), parse(A_TEXT, A).toCanonical()));
    assert.deepEqual(codes(A_TEXT.replace('newton*', '"newton*'), A), ['E09']);
    assert.deepEqual(codes(A_TEXT.replace('newton*', '"newton"x*'), A), ['E09']);
  });

  test('detección de MiniError con línea y campo', () => {
    try {
      parse(A_TEXT.replace('|1|biología', '|7|biología'), A);
      assert.fail('debió lanzar');
    } catch (e) {
      assert.ok(e instanceof MiniValidationError);
      const err = e.errors[0];
      assert.equal(err.line, 2);
      assert.equal(err.field, 'difficulty');
      assert.equal(String(err), 'E13 line 2 [difficulty]: 7 > max 5');
    }
  });
});

describe('protocolo de forks', () => {
  const A = REG.get('a');
  const Q = REG.get('q');

  test('q es fork válido de a', () => {
    assert.deepEqual(checkFork(Q, A), []);
    assert.deepEqual(Q.core.map(f => f.name), A.core.map(f => f.name));
  });

  test('reordenar el núcleo o eliminar campos se rechaza con E21', () => {
    const d = contractToJSON(A);
    d.prefix = 'bad';
    d.parent = 'a';
    [d.core[1], d.core[2]] = [d.core[2], d.core[1]];
    const errs = checkFork(d, A);
    assert.ok(errs.length && errs.every(e => e.code === 'E21'));
    const d2 = contractToJSON(A);
    d2.prefix = 'bad2';
    d2.core = d2.core.slice(0, -1);
    assert.ok(checkFork(d2, A).length);
  });

  test('el padre lee documentos del hijo sin la cola; el hijo lee documentos del padre', () => {
    const qtext = lf(fixtures(Q).valid).trim();
    const lines = qtext.split(LF);
    const stripped = ['a' + lines[0].slice(1), ...lines.slice(1).map(l => l.split('|').slice(0, A.arity).join('|'))].join(LF);
    assert.equal(parse(stripped, A).records.length, 12);
    const doc = parse('q' + lf(fixtures(A).valid).slice(1), Q);
    assert.equal(doc.records.length, 12);
    assert.equal(doc.records[0].feedback, null);
  });

  test('la cola de extensiones puede omitirse parcialmente', () => {
    const lines = lf(fixtures(Q).valid).trim().split(LF);
    lines[1] = lines[1].split('|').slice(0, A.arity + 1).join('|');
    const doc = parse(lines.join(LF), Q);
    assert.notEqual(doc.records[0].feedback, null);
    assert.equal(doc.records[0].hint, null);
  });
});

describe('contratos inválidos (E20)', () => {
  const base: ContractJSON = { prefix: 'x', core: [{ name: 'a', type: 'str' }] };
  const bad: [string, ContractJSON][] = [
    ['sin prefijo', { core: [{ name: 'a', type: 'str' }] } as unknown as ContractJSON],
    ['prefijo inválido', { ...base, prefix: '9x' }],
    ['sin núcleo', { ...base, core: [] }],
    ['tipo desconocido', { ...base, core: [{ name: 'a', type: 'date' as 'str' }] }],
    ['enum sin valores', { ...base, core: [{ name: 'a', type: 'enum' }] }],
    ['lista de tuplas', { ...base, core: [{ name: 'a', type: 'list', item: 'tuple' as 'str' }] }],
    ['marcador inválido', { ...base, core: [{ name: 'a', type: 'mlist', marker: 'two' as 'any' }] }],
    ['tupla vacía', { ...base, core: [{ name: 'a', type: 'tuple' }] }],
    ['campos duplicados', { ...base, extensions: [{ name: 'a', type: 'int' }] }],
    ['separador |', { ...base, list_separator: '|' }],
    ['separador largo', { ...base, list_separator: ';;' }],
    ['cabecera mlist', { ...base, header: { keys: { z: { type: 'mlist' as 'list' } } } }],
  ];
  for (const [name, d] of bad) {
    test(name, () => {
      assert.throws(() => normalizeContract(d), (e: unknown) => e instanceof MiniError && e.code === 'E20');
    });
  }

  test('contrato mínimo con separador ; y extensiones', () => {
    const c = normalizeContract({
      prefix: 'mini-x', list_separator: ';', records_key: 'rows',
      core: [{ name: 'id', type: 'str', unique: true }, { name: 'tags', type: 'list' }],
      extensions: [{ name: 'score', type: 'float' }],
    });
    assert.equal(signature(c), 'id:str | tags:list<str> || score:float?');
    const doc = parse('mini-x|n=2' + LF + 'r1|a;b,c' + LF + 'r2||1.5', c);
    assert.deepEqual(doc.toCanonical(), {
      prefix: 'mini-x', header: { n: 2, v: 1 },
      rows: [{ id: 'r1', tags: ['a', 'b,c'], score: null }, { id: 'r2', tags: [], score: 1.5 }],
    });
    assert.equal(dumps(doc.toCanonical(), c), 'mini-x|n=2' + LF + 'r1|a;b,c' + LF + 'r2||1.5');
    assert.equal(normalizeContract(c), c);
  });
});
