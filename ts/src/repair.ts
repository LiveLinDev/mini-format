/* repair.ts — reparación selectiva de documentos .mini generados por un modelo.
 * Equivalente de minifmt.ai.repair (referencia Python): extractDocument, invalidItems,
 * repairRequest y mergeRepair producen las mismas líneas, códigos y textos de solicitud.
 *
 * Convenciones de la respuesta de reparación:
 *  - primera línea significativa: `<prefix>|n=<k>` con k = número de líneas corregidas;
 *  - después, exactamente k líneas, una por línea solicitada y en el mismo orden;
 *  - una línea con solo `-` significa «no era un registro; elimínala»;
 *  - si se solicitó la cabecera, su corrección es una cabecera completa en su posición.
 * La fusión nunca reescribe `n` de la cabecera original: si se perdieron registros, E04 sigue visible.
 * Módulo seguro para navegador (sin APIs de Node).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { splitFields } from './codec.ts';
import { normalizeContract } from './contract.ts';
import type { Contract, ContractJSON } from './contract.ts';
import { E_HEADER_KEY, E_NO_COUNT, E_NO_HEADER, E_UNKNOWN_PREFIX, MiniError, MiniValidationError } from './errors.ts';
import { Document, parse, uniqueKey } from './parser.ts';
import { specBlock } from './prompt.ts';

const HEADER_CODES: ReadonlySet<string> = new Set([E_NO_HEADER, E_UNKNOWN_PREFIX, E_NO_COUNT, E_HEADER_KEY]);
/** Marca de eliminación en una respuesta de reparación. */
export const DROP_MARK = '-';
const FENCE = /^\s*(```|~~~)/;

const PY_WS = '\t\n\v\f\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000';
const PY_WS_EDGES = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, 'g');

/** Blancos que elimina str.strip() de la referencia (ASCII y Unicode habituales). */
function pyStrip(s: string): string {
  return s.replace(PY_WS_EDGES, '');
}

function stripNewlines(s: string): string {
  return s.replace(/^\n+|\n+$/g, '');
}

/** Líneas físicas no vacías como pares [número 1-based, texto sin CR final]. */
export function physicalLines(text: string): [number, string][] {
  let t = text;
  if (t.charCodeAt(0) === 0xfeff) t = t.slice(1);
  const out: [number, string][] = [];
  t.split('\n').forEach((raw, i) => {
    const line = raw.replace(/\r+$/, '');
    if (pyStrip(line) !== '') out.push([i + 1, line]);
  });
  return out;
}

// ------------------------------------------------------------ localización
/**
 * Devuelve el documento .mini contenido en una respuesta del modelo.
 * Quita la prosa inicial y las cercas de código: el documento empieza en la primera línea
 * que comienza por `<prefix>|` (o es el prefijo solo). Si la cabecera estaba dentro de una
 * cerca, se descarta lo que sigue a la cerca de cierre. La prosa final sin cerca se conserva
 * para que se informe como línea inválida. Sin cabecera, devuelve el texto sin cercas.
 */
export function extractDocument(text: string | null | undefined, contract: Contract | ContractJSON): string {
  if (text === null || text === undefined) return '';
  const lines = String(text).split('\r\n').join('\n').split('\n');
  const pref = normalizeContract(contract).prefix;
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    const s = pyStrip(lines[i]).replace(/^﻿+/, '');
    if (s === pref || s.startsWith(pref + '|')) {
      start = i;
      break;
    }
  }
  if (start < 0) return stripNewlines(lines.filter(ln => !FENCE.test(ln)).join('\n'));
  const inFence = lines.slice(0, start).some(ln => FENCE.test(ln));
  let body = lines.slice(start);
  if (inFence) {
    const j = body.findIndex(ln => FENCE.test(ln));
    if (j >= 0) body = body.slice(0, j);
  } else {
    body = body.filter(ln => !FENCE.test(ln));
  }
  return stripNewlines(body.join('\n'));
}

/** Análisis tolerante que nunca lanza: [documento | null, errores]. Sin cabecera, el documento es null. */
export function lenientParse(text: string, contract: Contract | ContractJSON): [Document | null, MiniError[]] {
  try {
    const doc = parse(text, contract, { strict: false });
    if (doc.headerLine === 0 && doc.errors.some(e => e.code === E_NO_HEADER)) return [null, [...doc.errors]];
    return [doc, [...doc.errors]];
  } catch (e) {
    if (e instanceof MiniValidationError) return [null, [...e.errors]];
    if (e instanceof MiniError) return [null, [e]];
    throw e;
  }
}

// ------------------------------------------------------------ solicitud
/** Una línea (o varios fragmentos de un mismo registro) a reparar. */
export interface RepairItem {
  /** Línea física 1-based en el documento extraído (primera línea del ítem). */
  line: number;
  /** Contenido original (los fragmentos de un registro se unen con un salto de línea real). */
  text: string;
  errors: MiniError[];
  isHeader: boolean;
  /** Todas las líneas físicas que cubre el ítem. */
  lines: number[];
}

export interface RepairRequest {
  system: string;
  user: string;
  items: RepairItem[];
  /** Documento extraído al que se refieren los números de línea. */
  document: string;
  prefix: string;
  maxTokensHint: number;
  /** Hay algo que reparar. */
  readonly needed: boolean;
  /** Todas las líneas cubiertas por los ítems, en orden. */
  readonly lines: number[];
}

export interface RepairRequestOptions {
  /** Texto de origen del que se extrajo el documento (permite recuperar valores). */
  context?: string | null;
  /** Antepone el bloque de especificación al mensaje de sistema (estable, cacheable). Por defecto true. */
  includeSpec?: boolean;
  /** Máximo de ítems a incluir. */
  maxItems?: number | null;
}

function codepoints(s: string): number {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

function fieldCount(text: string, c: Contract): number | null {
  try {
    return splitFields(text.split('\n').join(' '), c.list_separator, 0, false).length;
  } catch (e) {
    if (e instanceof MiniError) return null;
    throw e;
  }
}

/** Líneas físicas inválidas de un documento (ya extraído), con sus errores. */
export function invalidItems(document: string, contract: Contract | ContractJSON): RepairItem[] {
  const c = normalizeContract(contract);
  const phys = physicalLines(document);
  if (!phys.length) return [];
  const byLine = new Map<number, MiniError[]>();
  const [, errors] = lenientParse(document, c);
  for (const e of errors) {
    if (e.line > 0) {
      const list = byLine.get(e.line);
      if (list) list.push(e);
      else byLine.set(e.line, [e]);
    }
  }
  const headerLine = phys[0][0];
  const items: RepairItem[] = [];
  let prevIdx = -2;
  phys.forEach(([lineno, text], idx) => {
    const errs = byLine.get(lineno);
    if (!errs) return;
    const item: RepairItem = { line: lineno, text, errors: errs, isHeader: lineno === headerLine, lines: [lineno] };
    // un salto de línea sin escapar dentro de un valor parte un registro en fragmentos cortos
    if (items.length && prevIdx === idx - 1 && !item.isHeader && !items[items.length - 1].isHeader) {
      const last = items[items.length - 1];
      const nLast = fieldCount(last.text, c);
      const nThis = fieldCount(text, c);
      if (nLast !== null && nThis !== null && nLast < c.arity && nThis < c.arity
        && c.arity <= nLast + nThis - 1 && nLast + nThis - 1 <= c.fields.length) {
        last.text = last.text + '\n' + text;
        last.errors.push(...item.errors);
        last.lines.push(lineno);
        prevIdx = idx;
        return;
      }
    }
    items.push(item);
    prevIdx = idx;
  });
  return items;
}

function fmtError(e: MiniError): string {
  const fld = e.field ? ` [${e.field}]` : '';
  return `${e.code}${fld}: ${e.message}`;
}

function makeRequest(init: Omit<RepairRequest, 'needed' | 'lines'>): RepairRequest {
  return Object.defineProperties(init, {
    needed: { get(this: RepairRequest) { return this.items.length > 0; }, enumerable: true },
    lines: { get(this: RepairRequest) { return this.items.flatMap(it => it.lines); }, enumerable: true },
  }) as RepairRequest;
}

/**
 * Construye la solicitud de reparación selectiva de un documento generado.
 * `document` puede ser la respuesta cruda del modelo: pasa antes por extractDocument
 * y los números de línea se refieren a ese resultado.
 */
export function repairRequest(
  document: string, contract: Contract | ContractJSON, lang: string = 'es', opts: RepairRequestOptions = {},
): RepairRequest {
  const c = normalizeContract(contract);
  const docText = extractDocument(document, c);
  let items = invalidItems(docText, c);
  if (opts.maxItems !== undefined && opts.maxItems !== null) items = items.slice(0, Math.max(0, opts.maxItems));
  const phys = physicalLines(docText);
  const headerText = phys.length ? phys[0][1] : `${c.prefix}|n=0`;
  const es = lang === 'es';
  const spec = opts.includeSpec === false ? '' : specBlock(c, lang);
  let sys = es
    ? 'Eres un corrector de documentos .mini. Corriges únicamente las líneas que se te indican, conservando su contenido y respetando el formato.'
    : 'You repair .mini documents. You fix only the lines you are given, keeping their content and following the format.';
  if (spec) sys += '\n\n' + spec;
  const L: string[] = [];
  const k = items.length;
  if (es) {
    L.push(`Un documento .mini de la familia '${c.prefix}' tiene ${k} línea(s) inválida(s). Corrige SOLO esas líneas.`);
    L.push(`Cabecera del documento (contexto): ${headerText}`);
    L.push('Líneas inválidas (número de línea, contenido y errores del validador):');
  } else {
    L.push(`A .mini document of family '${c.prefix}' has ${k} invalid line(s). Fix ONLY those lines.`);
    L.push(`Document header (context): ${headerText}`);
    L.push('Invalid lines (line number, content and validator errors):');
  }
  for (const it of items) {
    const tag = it.isHeader ? (es ? ' cabecera' : ' header') : '';
    if (it.lines.length > 1) {
      L.push(`[L${it.lines[0]}-L${it.lines[it.lines.length - 1]}] ` + (es
        ? '(fragmentos de un mismo registro partido por un salto de línea sin escapar; devuelve UNA sola línea)'
        : '(fragments of one record split by an unescaped line break; return ONE line)'));
      const frags = it.text.split('\n');
      const m = Math.min(frags.length, it.lines.length);
      for (let i = 0; i < m; i++) L.push(`    L${it.lines[i]}: ${frags[i]}`);
    } else {
      L.push(`[L${it.line}${tag}] ${it.text}`);
    }
    for (const e of it.errors) L.push(`    - ${fmtError(e)}`);
  }
  if (opts.context) {
    L.push('');
    L.push(es ? 'Texto de origen (para recuperar valores):' : 'Source text (to recover values):');
    L.push(opts.context);
  }
  L.push('');
  if (es) {
    L.push(`Responde solo con un documento .mini: primera línea '${c.prefix}|n=${k}', seguida de `
      + `exactamente ${k} línea(s), una corrección por cada línea inválida y en el mismo orden. `
      + 'Si una línea corregida es la cabecera, escribe la cabecera completa. Si una línea no es un '
      + `registro (texto explicativo), escribe solo '${DROP_MARK}'. No repitas las líneas válidas ni `
      + 'añadas explicaciones ni bloques de código.');
  } else {
    L.push(`Answer with a .mini document only: first line '${c.prefix}|n=${k}', followed by exactly `
      + `${k} line(s), one correction per invalid line, in the same order. If a corrected line is the `
      + 'header, write the full header. If a line is not a record (explanatory text), write only '
      + `'${DROP_MARK}'. Do not repeat valid lines, add explanations or code fences.`);
  }
  const chars = items.reduce((acc, it) => acc + codepoints(it.text), 0);
  const hint = Math.max(64, Math.trunc(chars / 2.5) + 16 * (k + 1));
  return makeRequest({ system: sys, user: L.join('\n'), items, document: docText, prefix: c.prefix, maxTokensHint: hint });
}

// ------------------------------------------------------------ fusión
export interface MergeResult {
  /** Documento fusionado. */
  text: string;
  /** Análisis tolerante del documento fusionado (null si no tiene cabecera). */
  document: Document | null;
  /** Errores que quedan tras la fusión. */
  errors: MiniError[];
  /** Líneas sustituidas por una corrección válida. */
  replaced: number[];
  /** Líneas eliminadas a petición (`-`) o por duplicar otro registro. */
  dropped: number[];
  /** Líneas solicitadas que siguen inválidas. */
  unresolved: number[];
  /** Problemas de la propia respuesta de reparación. */
  notes: string[];
  /** Documento sin errores. */
  ok: boolean;
}

function answerLines(repairedText: string, c: Contract): [string[], string[]] {
  const notes: string[] = [];
  const body = extractDocument(repairedText || '', c);
  const phys = physicalLines(body);
  if (!phys.length) return [[], ['empty repair answer']];
  const first = pyStrip(phys[0][1]);
  let lines: string[];
  if (first === c.prefix || first.startsWith(c.prefix + '|')) {
    lines = phys.slice(1).map(([, t]) => t);
    const m = /\|\s*n\s*=\s*(\d+)/.exec(first);
    if (m && parseInt(m[1], 10) !== lines.length) {
      notes.push(`repair header declares n=${m[1]} but has ${lines.length} lines`);
    }
  } else {
    notes.push('repair answer has no header; lines taken in order');
    lines = phys.map(([, t]) => t);
  }
  return [lines, notes];
}

const ascending = (a: number, b: number): number => a - b;

/**
 * Inserta las líneas corregidas de una respuesta de reparación en el documento original.
 * Cada corrección se acepta solo si es válida por sí sola bajo el contrato (validada con la
 * cabecera original, o con la corregida si la cabecera formaba parte de la solicitud). Las
 * correcciones rechazadas dejan la línea original, de modo que nunca se pierde información.
 */
export function mergeRepair(
  originalDoc: string, repairedText: string, contract: Contract | ContractJSON, request?: RepairRequest | null,
): MergeResult {
  const c = normalizeContract(contract);
  const docText = request ? request.document : extractDocument(originalDoc, c);
  const items = request ? request.items : invalidItems(docText, c);
  const phys = physicalLines(docText);
  const [answer, notes] = answerLines(repairedText, c);
  if (answer.length !== items.length) notes.push(`expected ${items.length} corrected lines, got ${answer.length}`);
  const content = new Map<number, string>(phys);
  const order = phys.map(([ln]) => ln);
  const headerLine = order.length ? order[0] : null;
  const replaced: number[] = [];
  const dropped: number[] = [];
  const unresolved: number[] = [];
  const pairs: [RepairItem, string][] = items.slice(0, answer.length).map((it, i) => [it, answer[i]]);

  // primero la cabecera, para validar las correcciones de registros contra ella
  for (const [it, next] of pairs) {
    if (!it.isHeader) continue;
    const cand = pyStrip(next);
    if (cand.startsWith(c.prefix + '|') || cand === c.prefix) {
      const [probe, errs] = lenientParse(cand, c);
      if (probe !== null && !errs.some(e => HEADER_CODES.has(e.code))) {
        content.set(it.line, cand);
        replaced.push(it.line);
        continue;
      }
    }
    unresolved.push(it.line);
  }
  const fallbackHeader = `${c.prefix}|n=0`;
  const headerText = headerLine !== null ? (content.get(headerLine) ?? fallbackHeader) : fallbackHeader;
  const invalidLines = new Set(items.flatMap(it => it.lines));
  const seen = new Set<string>();
  for (const ln of order) {
    if (!invalidLines.has(ln) && ln !== headerLine) seen.add(pyStrip(content.get(ln) as string));
  }
  // valores de los campos `unique` que ya pertenecen a los registros que se quedan en el documento:
  // una corrección no puede reclamar uno (convertiría un registro válido en un duplicado E11)
  const uniqueNames = c.fields.filter(f => f.unique).map(f => f.name);
  const claimed = new Map<string, Set<string>>(uniqueNames.map(name => [name, new Set<string>()]));
  if (uniqueNames.length) {
    const kept = order.filter(ln => !invalidLines.has(ln) && ln !== headerLine).map(ln => content.get(ln) as string);
    const [keptDoc] = lenientParse([headerText, ...kept].join('\n'), c);
    for (const rec of keptDoc ? keptDoc.records : []) {
      for (const name of uniqueNames) {
        const v = rec[name];
        if (v !== null && v !== undefined) (claimed.get(name) as Set<string>).add(uniqueKey(v));
      }
    }
  }
  for (const [it, next] of pairs) {
    if (it.isHeader) continue;
    const cand = pyStrip(next);
    if (cand === DROP_MARK) {
      dropped.push(...it.lines);
      for (const ln of it.lines) content.delete(ln);
      continue;
    }
    if (seen.has(cand)) {
      // el mismo registro se devolvió dos veces (o ya existe): se conserva una sola copia
      notes.push(`line ${it.line}: correction duplicates another record; dropped`);
      dropped.push(...it.lines);
      for (const ln of it.lines) content.delete(ln);
      continue;
    }
    const [probe, errs] = lenientParse(headerText + '\n' + cand, c);
    // el documento de prueba tiene la n de la cabecera original: se ignora el conteo
    const lineErrs = errs.filter(e => e.line > 1 || (e.line === 0 && e.code !== 'E04'));
    if (probe !== null && probe.records.length === 1 && !lineErrs.length && !cand.includes('\n')) {
      const probed = probe.records[0];
      const clash = uniqueNames.find(name => {
        const v = probed[name];
        return v !== null && v !== undefined && (claimed.get(name) as Set<string>).has(uniqueKey(v));
      });
      if (clash !== undefined) {
        // SPEC §6: un valor `unique` no puede repetirse; se conserva la línea original en vez de dañar otro registro válido
        notes.push(`line ${it.line}: correction repeats the unique value of field '${clash}' of another record`);
        unresolved.push(...it.lines);
        continue;
      }
      content.set(it.line, cand);
      for (const ln of it.lines.slice(1)) content.delete(ln);
      replaced.push(...it.lines);
      seen.add(cand);
      for (const name of uniqueNames) {
        const v = probed[name];
        if (v !== null && v !== undefined) (claimed.get(name) as Set<string>).add(uniqueKey(v));
      }
    } else {
      unresolved.push(...it.lines);
    }
  }
  for (const it of items.slice(answer.length)) unresolved.push(...it.lines);
  const merged = order.filter(ln => content.has(ln)).map(ln => content.get(ln) as string).join('\n');
  const [doc, errors] = lenientParse(merged, c);
  return {
    text: merged,
    document: doc,
    errors,
    replaced: replaced.sort(ascending),
    dropped: dropped.sort(ascending),
    unresolved: [...new Set(unresolved)].sort(ascending),
    notes,
    ok: doc !== null && errors.length === 0,
  };
}
