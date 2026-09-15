/* parser.ts — parser determinista: texto .mini + contrato -> objeto canónico (SPEC §7, §8).
 * La validación es local (cada registro en su línea) y global (conteo y unicidad).
 * El análisis se implementa como un motor incremental por líneas que comparten
 * `parse` y el lector en streaming, de modo que ambos producen resultados idénticos.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import * as codec from './codec.ts';
import type { Tok } from './codec.ts';
import { headerKeyAsField, normalizeContract } from './contract.ts';
import type { Contract, ContractJSON, Field } from './contract.ts';
import {
  E_ARITY, E_COUNT_MISMATCH, E_HEADER_KEY, E_LIST_ARITY, E_MARKER, E_NO_COUNT, E_NO_HEADER,
  E_TYPE, E_UNIQUE, E_UNKNOWN_PREFIX, MiniError, MiniValidationError,
} from './errors.ts';
import { decodeScalar } from './values.ts';

export type Value = null | string | number | boolean | Value[] | { [key: string]: Value };
export type MiniRecord = Record<string, Value>;
export type Header = Record<string, Value>;

export interface CanonicalObject {
  prefix: string;
  header: Header;
  [recordsKey: string]: unknown;
}

export interface ParseOptions {
  /** true (por defecto): lanza MiniValidationError si hay errores. false: devuelve registros válidos + errores. */
  strict?: boolean;
}

/** Documento analizado. */
export class Document {
  readonly prefix: string;
  readonly version: number;
  readonly header: Header;
  readonly records: MiniRecord[];
  readonly errors: MiniError[];
  readonly contract: Contract;
  /** Número de líneas significativas (cabecera + registros). */
  readonly lines: number;

  constructor(init: {
    prefix: string; version: number; header: Header; records: MiniRecord[];
    errors: MiniError[]; contract: Contract; lines: number;
  }) {
    this.prefix = init.prefix;
    this.version = init.version;
    this.header = init.header;
    this.records = init.records;
    this.errors = init.errors;
    this.contract = init.contract;
    this.lines = init.lines;
  }

  get ok(): boolean {
    return this.errors.length === 0;
  }

  /** Objeto canónico `{prefix, header, <records_key>: [...]}` (SPEC §7). */
  toCanonical(): CanonicalObject {
    return {
      prefix: this.prefix,
      header: shallowCopy(this.header),
      [this.contract.records_key]: this.records.map(r => shallowCopy(r)),
    } as CanonicalObject;
  }

  /** Alias de toCanonical() por compatibilidad con js/mini.js. */
  canonical(): CanonicalObject {
    return this.toCanonical();
  }
}

const hasOwn = (o: object, k: string): boolean => Object.prototype.hasOwnProperty.call(o, k);

/** Asigna una propiedad propia incluso si la clave es `__proto__`. */
export function put(o: Record<string, unknown>, k: string, v: unknown): void {
  if (k === '__proto__') Object.defineProperty(o, k, { value: v, enumerable: true, writable: true, configurable: true });
  else o[k] = v;
}

/** Copia superficial que conserva claves como `__proto__`. */
export function shallowCopy<T extends Record<string, unknown>>(o: T): T {
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(o)) put(out, k, o[k]);
  return out as T;
}

// ---------------------------------------------------------------- cabecera
export interface HeaderResult {
  prefix: string;
  header: Header;
  errors: MiniError[];
}

export function parseHeader(line: string, lineno: number, c: Contract, strict: boolean): HeaderResult {
  const errs: MiniError[] = [];
  let fields: Tok[][];
  try {
    fields = codec.splitFields(line, c.list_separator, lineno, strict);
  } catch (e) {
    if (!(e instanceof MiniError)) throw e;
    // escape inválido en la cabecera: se informa y se recupera el resto en modo tolerante
    // (una barra invertida colgante al final se descarta para poder recuperar)
    errs.push(e);
    try {
      fields = codec.splitFields(line, c.list_separator, lineno, false);
    } catch {
      fields = codec.splitFields(line.slice(0, -1), c.list_separator, lineno, false);
    }
  }
  const prefix = fields.length ? codec.textOf(fields[0]) : '';
  const header: Header = {};
  for (const toks of fields.slice(1)) {
    const txt = codec.textOf(toks);
    if (!txt) continue;
    // se divide en el primer '=' no escapado (un '=' dentro del valor es literal)
    const eq = toks.findIndex(t => t[0] === '=' && !t[1]);
    if (eq < 0) {
      errs.push(new MiniError(E_HEADER_KEY, lineno, `header entry '${txt}' is not key=value`));
      continue;
    }
    const key = codec.textOf(codec.stripToks(toks.slice(0, eq)));
    const vt = codec.stripToks(toks.slice(eq + 1));
    const hk = hasOwn(c.headerKeys, key) ? c.headerKeys[key] : undefined;
    try {
      if (!hk) {
        put(header, key, codec.textOf(vt));
      } else if (hk.type === 'list') {
        const hf = headerKeyAsField(hk);
        put(header, key, codec.splitList(vt, c.list_separator, lineno).map(([t]) => decodeScalar(t, hf, lineno, key, true)));
      } else if (hk.type === 'tuple') {
        const parts = codec.splitList(vt, c.list_separator, lineno);
        if (parts.length !== hk.items.length) {
          throw new MiniError(E_LIST_ARITY, lineno, `expected ${hk.items.length} components, got ${parts.length}`, key);
        }
        const o: Record<string, Value> = {};
        hk.items.forEach((cmp, i) => {
          const t = parts[i][0];
          put(o, cmp.name, t === '' ? null : decodeScalar(t, cmp, lineno, `${key}.${cmp.name}`));
        });
        put(header, key, o);
      } else {
        put(header, key, decodeScalar(codec.textOf(vt), headerKeyAsField(hk), lineno, key));
      }
    } catch (e) {
      if (e instanceof MiniError) errs.push(e);
      else throw e;
    }
  }
  for (const k of Object.keys(c.headerKeys)) {
    const hk = c.headerKeys[k];
    if (!hasOwn(header, k)) {
      if (hk.required && k !== 'n') errs.push(new MiniError(E_HEADER_KEY, lineno, `required header key '${k}' missing`));
      else if (hk.default !== null) put(header, k, hk.default);
    }
  }
  if (!hasOwn(header, 'n')) errs.push(new MiniError(E_NO_COUNT, lineno, 'header must declare n=<record count>'));
  return { prefix, header, errors: errs };
}

// ---------------------------------------------------------------- campos
interface MListValue {
  items: Value[];
  selected: number | number[] | null;
}

class MList {
  readonly value: MListValue;
  constructor(value: MListValue) {
    this.value = value;
  }
}

/** Decodifica un campo (lista de tokens) según su definición. */
export function decodeField(toks: readonly Tok[], f: Field, lineno: number, sep: string, header?: Header | null): Value | MList {
  if (f.type === 'str' || f.type === 'int' || f.type === 'float' || f.type === 'bool' || f.type === 'enum') {
    const txt = codec.textOf(toks);
    if (txt === '') {
      if (f.optional) return f.default as Value;
      throw new MiniError(E_TYPE, lineno, 'required value is empty', f.name);
    }
    return decodeScalar(txt, f, lineno);
  }
  if (f.type === 'list' || f.type === 'mlist') {
    const elems = codec.splitList(toks, sep, lineno);
    if (!elems.length && !f.optional && f.min !== null && f.min > 0) {
      throw new MiniError(E_LIST_ARITY, lineno, 'required list is empty', f.name);
    }
    if (f.min !== null && elems.length < f.min) {
      throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements, min ${Math.trunc(f.min)}`, f.name);
    }
    if (f.max !== null && elems.length > f.max) {
      throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements, max ${Math.trunc(f.max)}`, f.name);
    }
    if (f.count_key && header) {
      const k = hasOwn(header, f.count_key) ? header[f.count_key] : undefined;
      if (typeof k === 'number' && Number.isInteger(k) && elems.length !== k) {
        throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements but header ${f.count_key}=${k}`, f.name);
      }
    }
    const items = elems.map(([t]) => decodeScalar(t, f, lineno, f.name, true));
    if (f.type === 'list') {
      if (elems.some(e => e[1])) throw new MiniError(E_MARKER, lineno, 'marker * not allowed in a plain list', f.name);
      return items;
    }
    const marked: number[] = [];
    elems.forEach((e, i) => { if (e[1]) marked.push(i); });
    if (f.marker === 'exactly_one' && marked.length !== 1) {
      throw new MiniError(E_MARKER, lineno, `exactly one element must carry *, found ${marked.length}`, f.name);
    }
    if (f.marker === 'at_least_one' && marked.length < 1) {
      throw new MiniError(E_MARKER, lineno, 'at least one element must carry *', f.name);
    }
    if (f.marker === 'at_most_one' && marked.length > 1) {
      throw new MiniError(E_MARKER, lineno, `at most one element may carry *, found ${marked.length}`, f.name);
    }
    const single = f.marker === 'exactly_one' || f.marker === 'at_most_one';
    return new MList({ items, selected: single ? (marked.length ? marked[0] : null) : marked });
  }
  if (f.type === 'tuple') {
    const parts = codec.splitList(toks, sep, lineno);
    if (!parts.length && f.optional) return null;
    if (parts.length !== f.items.length) {
      throw new MiniError(E_LIST_ARITY, lineno, `tuple expects ${f.items.length} components, got ${parts.length}`, f.name);
    }
    const out: Record<string, Value> = {};
    f.items.forEach((cmp, i) => {
      const [txt, m] = parts[i];
      if (m) throw new MiniError(E_MARKER, lineno, 'marker * not allowed inside a tuple', f.name);
      if (txt === '') {
        if (cmp.optional) {
          put(out, cmp.name, cmp.default);
          return;
        }
        throw new MiniError(E_TYPE, lineno, `tuple component '${cmp.name}' is empty`, f.name);
      }
      put(out, cmp.name, decodeScalar(txt, cmp, lineno, `${f.name}.${cmp.name}`));
    });
    return out;
  }
  throw new MiniError(E_TYPE, lineno, `unsupported field type ${(f as Field).type}`, f.name);
}

function uniqueKey(v: Value): string {
  if (typeof v === 'number') return 'n:' + String(v);
  if (typeof v === 'string') return 's:' + v;
  return 'j:' + JSON.stringify(v);
}

// ---------------------------------------------------------- motor por líneas
/** Resultado de procesar una línea física de registro. */
export interface LineOutcome {
  line: number;
  /** Registro válido, o null si la línea tuvo errores. */
  record: MiniRecord | null;
  errors: MiniError[];
}

/**
 * Motor incremental: recibe líneas físicas (sin LF) en orden y acumula el estado.
 * Uso interno de `parse` y `createReader`; expuesto para integraciones avanzadas.
 */
export class LineEngine {
  readonly contract: Contract;
  readonly strict: boolean;
  prefix: string = '';
  header: Header | null = null;
  readonly records: MiniRecord[] = [];
  readonly errors: MiniError[] = [];
  /** Número de la última línea física recibida. */
  physical: number = 0;
  /** Líneas significativas vistas (cabecera incluida). */
  significant: number = 0;
  private readonly uniques: Map<string, Map<string, number>> = new Map();

  constructor(contract: Contract, strict: boolean) {
    this.contract = contract;
    this.strict = strict;
    for (const f of contract.fields) if (f.unique) this.uniques.set(f.name, new Map());
  }

  /** Procesa una línea física. Devuelve null si es la cabecera o una línea en blanco. */
  feed(raw: string): LineOutcome | null {
    this.physical += 1;
    const lineno = this.physical;
    let line = raw;
    if (lineno === 1 && line.charCodeAt(0) === 0xfeff) line = line.slice(1);
    if (line.endsWith('\r')) line = line.slice(0, -1);
    if (codec.isBlank(line)) return null;
    this.significant += 1;
    if (this.header === null) {
      this.acceptHeader(line, lineno);
      return null;
    }
    return this.acceptRecord(line, lineno);
  }

  private acceptHeader(line: string, lineno: number): void {
    const c = this.contract;
    const res = parseHeader(line, lineno, c, this.strict);
    this.prefix = res.prefix;
    this.header = res.header;
    this.errors.push(...res.errors);
    if (res.prefix !== c.prefix) {
      this.errors.push(new MiniError(E_UNKNOWN_PREFIX, lineno, `header prefix '${res.prefix}' does not match contract '${c.prefix}'`));
    }
  }

  private acceptRecord(line: string, lineno: number): LineOutcome {
    const c = this.contract;
    const sep = c.list_separator;
    let toks: Tok[][];
    try {
      toks = codec.splitFields(line, sep, lineno, this.strict);
    } catch (e) {
      if (!(e instanceof MiniError)) throw e;
      this.errors.push(e);
      return { line: lineno, record: null, errors: [e] };
    }
    const nf = toks.length;
    if (nf < c.arity) {
      const e = new MiniError(E_ARITY, lineno, `record has ${nf} fields, core requires ${c.arity}`);
      this.errors.push(e);
      return { line: lineno, record: null, errors: [e] };
    }
    if (nf > c.fields.length) {
      const e = new MiniError(E_ARITY, lineno, `record has ${nf} fields, contract allows at most ${c.fields.length}`);
      this.errors.push(e);
      return { line: lineno, record: null, errors: [e] };
    }
    const rec: MiniRecord = {};
    const recErrs: MiniError[] = [];
    c.fields.forEach((f, i) => {
      if (i >= nf) {
        if (f.type === 'mlist') {
          put(rec, f.json_items, null);
          put(rec, f.json_selected, null);
        } else {
          put(rec, f.name, f.default);
        }
        return;
      }
      try {
        const v = decodeField(toks[i], f, lineno, sep, this.header);
        if (v instanceof MList) {
          put(rec, f.json_items, v.value.items);
          put(rec, f.json_selected, v.value.selected);
        } else {
          put(rec, f.name, v);
        }
      } catch (e) {
        if (e instanceof MiniError) recErrs.push(e);
        else throw e;
      }
    });
    for (const [name, seen] of this.uniques) {
      const v = hasOwn(rec, name) ? rec[name] : undefined;
      if (v !== null && v !== undefined) {
        const k = uniqueKey(v);
        const first = seen.get(k);
        if (first !== undefined) {
          recErrs.push(new MiniError(E_UNIQUE, lineno, `duplicate value '${String(v)}' (first seen line ${first})`, name));
        } else {
          seen.set(k, lineno);
        }
      }
    }
    if (recErrs.length) {
      this.errors.push(...recErrs);
      return { line: lineno, record: null, errors: recErrs };
    }
    this.records.push(rec);
    return { line: lineno, record: rec, errors: [] };
  }

  /** Líneas de registro significativas vistas hasta ahora. */
  get recordLines(): number {
    return Math.max(0, this.significant - 1);
  }

  /** Cierra el documento: E01 si no hubo cabecera, E04 si el conteo no coincide con n. */
  finish(): Document {
    const c = this.contract;
    if (this.header === null) {
      const errors = [...this.errors, new MiniError(E_NO_HEADER, 0, 'empty document: header missing')];
      return new Document({ prefix: '', version: 1, header: {}, records: [], errors, contract: c, lines: 0 });
    }
    const errors = [...this.errors];
    const n = hasOwn(this.header, 'n') ? this.header.n : undefined;
    const total = this.recordLines;
    if (typeof n === 'number' && Number.isInteger(n) && n !== total) {
      errors.push(new MiniError(E_COUNT_MISMATCH, 0, `header declares n=${n} but document has ${total} record lines`));
    }
    const v = hasOwn(this.header, 'v') ? this.header.v : undefined;
    const version = typeof v === 'number' && v ? Math.trunc(v) : 1;
    return new Document({
      prefix: this.prefix, version, header: this.header, records: [...this.records], errors,
      contract: c, lines: this.significant,
    });
  }
}

/**
 * Analiza `text` contra `contract`.
 * strict=true (por defecto) lanza MiniValidationError con todos los errores;
 * strict=false devuelve un Document con los registros válidos y la lista de errores.
 */
export function parse(text: string, contract: Contract | ContractJSON, opts: ParseOptions = {}): Document {
  const c = normalizeContract(contract);
  const strict = opts.strict !== false;
  const engine = new LineEngine(c, strict);
  for (const raw of String(text).split('\n')) engine.feed(raw);
  const doc = engine.finish();
  if (strict && doc.errors.length) throw new MiniValidationError(doc.errors);
  return doc;
}

/** Devuelve el prefijo de la cabecera sin necesitar el contrato (o null si no hay cabecera). */
export function detectPrefix(text: string): string | null {
  let s = String(text);
  if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
  for (let raw of s.split('\n')) {
    if (raw.endsWith('\r')) raw = raw.slice(0, -1);
    if (codec.isBlank(raw)) continue;
    let t: Tok[][];
    try {
      t = codec.splitFields(raw, ',', 1, false);
    } catch {
      t = codec.splitFields(raw.slice(0, -1), ',', 1, false); // barra invertida colgante
    }
    return t.length ? codec.textOf(t[0]) : null;
  }
  return null;
}
