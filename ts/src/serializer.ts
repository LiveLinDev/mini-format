/* serializer.ts — objeto canónico + contrato -> texto .mini (SPEC §9).
 * Es estricto a propósito: rechaza valores que no encajan en el contrato para que
 * parse(dumps(obj)) == obj y dumps(parse(t)) == t se cumplan en todo documento válido.
 * SPEC 1.1 §9: el error ante un objeto inválido es un MiniError con el código que el parser
 * da a la misma violación y la línea física que ocuparía la entrada (1 = cabecera,
 * i + 2 = registro i). Todo documento emitido se verifica con un análisis estricto.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import * as codec from './codec.ts';
import { SCALAR_TYPES, headerKeyAsField, normalizeContract } from './contract.ts';
import type { Contract, ContractJSON, Field } from './contract.ts';
import { E_ENUM, E_MARKER, E_TYPE, MiniError, MiniValidationError } from './errors.ts';
import { parse } from './parser.ts';
import { encodeScalar } from './values.ts';

type Obj = Record<string, unknown>;

const hasOwn = (o: object, k: string): boolean => Object.prototype.hasOwnProperty.call(o, k);
const get = (o: Obj, k: string): unknown => (hasOwn(o, k) ? o[k] : undefined);
const isNil = (v: unknown): v is null | undefined => v === null || v === undefined;

function encList(values: readonly unknown[], f: Field, sep: string, marked?: readonly number[]): string {
  const ms = new Set(marked || []);
  return values
    .map((v, i) => {
      let s = codec.escapeElement(encodeScalar(v, f, true), sep);
      if (ms.has(i)) s += codec.MARKER;
      return s;
    })
    .join(sep);
}

/** Codifica un campo. Para `mlist` se leen las claves hermanas desde `rec`. */
export function encodeField(value: unknown, f: Field, sep: string, rec?: Obj): string {
  if (f.type === 'mlist' && rec) {
    const items = get(rec, f.json_items);
    if (isNil(items)) {
      if (f.optional) return '';
      throw new MiniError(E_TYPE, 0, 'required marked list is null', f.name);
    }
    value = { [f.json_items]: items, [f.json_selected]: get(rec, f.json_selected) };
  }
  if (isNil(value)) {
    if (f.optional) return '';
    throw new MiniError(E_TYPE, 0, 'required field is null', f.name);
  }
  if (SCALAR_TYPES.has(f.type)) {
    if (f.type === 'enum' && !(f.values || []).includes(String(value))) {
      throw new MiniError(E_ENUM, 0, `'${String(value)}' not in enum`, f.name);
    }
    return codec.escapeScalar(encodeScalar(value, f));
  }
  if (f.type === 'list') {
    if (!Array.isArray(value)) throw new MiniError(E_TYPE, 0, 'list expected', f.name);
    return encList(value, f, sep);
  }
  if (f.type === 'mlist') {
    let items: unknown;
    let sel: unknown;
    if (Array.isArray(value)) { // atajo [items, selected]
      [items, sel] = value;
    } else if (typeof value === 'object') {
      items = get(value as Obj, f.json_items);
      if (isNil(items)) items = [];
      sel = get(value as Obj, f.json_selected);
    }
    if (!Array.isArray(items)) throw new MiniError(E_TYPE, 0, 'list expected', f.name);
    let marked: number[];
    if (isNil(sel)) marked = [];
    else if (typeof sel === 'number') marked = [sel];
    else if (Array.isArray(sel)) marked = sel.map(Number);
    else throw new MiniError(E_MARKER, 0, `invalid selection '${String(sel)}'`, f.name);
    if (f.marker === 'exactly_one' && marked.length !== 1) {
      throw new MiniError(E_MARKER, 0, 'exactly one selected element required', f.name);
    }
    if (f.marker === 'at_least_one' && !marked.length) {
      throw new MiniError(E_MARKER, 0, 'at least one selected element required', f.name);
    }
    if (f.marker === 'at_most_one' && marked.length > 1) {
      throw new MiniError(E_MARKER, 0, 'at most one selected element allowed', f.name);
    }
    for (const m of marked) {
      if (!(Number.isInteger(m) && m >= 0 && m < items.length)) {
        throw new MiniError(E_MARKER, 0, `selected index ${m} out of range`, f.name);
      }
    }
    return encList(items, f, sep, marked);
  }
  if (f.type === 'tuple') {
    if (typeof value !== 'object' || Array.isArray(value)) throw new MiniError(E_TYPE, 0, 'tuple expects an object', f.name);
    return f.items
      .map(cmp => {
        const v = get(value as Obj, cmp.name);
        if (isNil(v)) {
          if (cmp.optional) return '';
          throw new MiniError(E_TYPE, 0, `tuple component '${cmp.name}' missing`, f.name);
        }
        return codec.escapeElement(encodeScalar(v, cmp), sep);
      })
      .join(sep);
  }
  throw new MiniError(E_TYPE, 0, `unsupported type ${(f as Field).type}`, f.name);
}

/** Codifica la cabecera: `n` primero, luego claves del contrato en su orden, luego claves extra. */
export function encodeHeader(header: Obj, c: Contract, n: number): string {
  const sep = c.list_separator;
  const parts = [c.prefix];
  const hdr: Obj = {};
  for (const k of Object.keys(header)) {
    if (k === '__proto__') Object.defineProperty(hdr, k, { value: header[k], enumerable: true, writable: true, configurable: true });
    else hdr[k] = header[k];
  }
  hdr.n = n;
  const ordered = [
    'n',
    ...Object.keys(c.headerKeys).filter(k => hasOwn(hdr, k) && k !== 'n'),
    ...Object.keys(hdr).filter(k => !hasOwn(c.headerKeys, k)),
  ];
  for (const k of ordered) {
    const v = hdr[k];
    if (isNil(v)) continue;
    const hk = hasOwn(c.headerKeys, k) ? c.headerKeys[k] : undefined;
    if (k === 'v' && Number(v) === 1 && hk && hk.default === 1) continue; // la versión por defecto es implícita
    let txt: string;
    if (!hk) {
      txt = codec.escapeScalar(String(v));
    } else if (hk.type === 'list') {
      if (!Array.isArray(v)) throw new MiniError(E_TYPE, 0, 'list expected', k);
      txt = encList(v, headerKeyAsField(hk), sep);
    } else if (hk.type === 'tuple') {
      if (typeof v !== 'object') throw new MiniError(E_TYPE, 0, 'tuple expects an object', k);
      txt = hk.items
        .map(cmp => {
          const cv = get(v as Obj, cmp.name);
          return isNil(cv) ? '' : codec.escapeElement(encodeScalar(cv, cmp), sep);
        })
        .join(sep);
    } else {
      txt = codec.escapeScalar(encodeScalar(v, headerKeyAsField(hk)));
    }
    parts.push(`${k}=${txt}`);
  }
  return parts.join(codec.FIELD_SEP);
}

/** Codifica un registro; las extensiones nulas del final se omiten. */
export function encodeRecord(rec: Obj, c: Contract): string {
  const sep = c.list_separator;
  const cells = c.core.map(f => encodeField(get(rec, f.name), f, sep, rec));
  const ext = c.extensions.map(f => encodeField(get(rec, f.name), f, sep, rec));
  while (ext.length && ext[ext.length - 1] === '') ext.pop();
  return [...cells, ...ext].join(codec.FIELD_SEP);
}

/** Serializa un objeto canónico `{header, <records_key>: [...]}` a texto .mini (sin LF final). */
export function dumps(obj: Obj, contract: Contract | ContractJSON): string {
  const c = normalizeContract(contract);
  let records = get(obj, c.records_key);
  if (isNil(records)) records = get(obj, 'records');
  if (isNil(records)) records = [];
  if (!Array.isArray(records)) throw new MiniError(E_TYPE, 0, `'${c.records_key}' must be an array`);
  const header = (get(obj, 'header') || {}) as Obj;
  if (typeof header !== 'object' || Array.isArray(header)) throw new MiniError(E_TYPE, 1, 'header must be an object');
  const n = records.length;
  const lines = [atLine(() => encodeHeader(header, c, n), 1)];
  records.forEach((r, i) => {
    if (!r || typeof r !== 'object' || Array.isArray(r)) throw new MiniError(E_TYPE, i + 2, 'record must be an object');
    lines.push(atLine(() => encodeRecord(r as Obj, c), i + 2));
  });
  const text = lines.join('\n');
  try {
    parse(text, c, { strict: true });
  } catch (e) {
    if (e instanceof MiniValidationError) throw e.errors[0];
    throw e;
  }
  return text;
}

/** Ejecuta `encode` y ubica en `lineno` un MiniError sin línea. */
function atLine(encode: () => string, lineno: number): string {
  try {
    return encode();
  } catch (e) {
    if (e instanceof MiniError && !e.line) throw new MiniError(e.code, lineno, e.message, e.field);
    throw e;
  }
}
