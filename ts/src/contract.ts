/* contract.ts — modelo de contrato de una familia .mini (SPEC §5, §6, §10).
 * El parser y el serializador interpretan el contrato: una familia nueva no
 * requiere código, solo un contract.json.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { E_CONTRACT, E_FORK, MiniError } from './errors.ts';
import { decimalBound, validDate } from './values.ts';

// ------------------------------------------------------------------ tipos
export type ScalarType = 'str' | 'int' | 'float' | 'bool' | 'enum' | 'date' | 'decimal';
export type CompositeType = 'list' | 'mlist' | 'tuple';
export type FieldType = ScalarType | CompositeType;
export type MarkerMode = 'exactly_one' | 'at_least_one' | 'at_most_one' | 'any';

export const SCALAR_TYPES: ReadonlySet<string> = new Set(['str', 'int', 'float', 'bool', 'enum', 'date', 'decimal']);
export const COMPOSITE_TYPES: ReadonlySet<string> = new Set(['list', 'mlist', 'tuple']);
export const ALL_TYPES: ReadonlySet<string> = new Set([...SCALAR_TYPES, ...COMPOSITE_TYPES]);
export const MARKER_MODES: ReadonlySet<string> = new Set(['exactly_one', 'at_least_one', 'at_most_one', 'any']);

/** Campo tal como aparece en contract.json. */
export interface FieldJSON {
  name: string;
  type: FieldType;
  optional?: boolean;
  unique?: boolean;
  values?: string[];
  item?: ScalarType;
  item_values?: string[];
  /** Rango numérico o aridad; para `date`, cadena AAAA-MM-DD; para `decimal`, cadena decimal o entero. */
  min?: number | string;
  max?: number | string;
  marker?: MarkerMode;
  count_key?: string;
  items?: FieldJSON[];
  json?: { items?: string; selected?: string };
  desc?: string;
  default?: unknown;
}

/** Clave de cabecera tal como aparece en contract.json. */
export interface HeaderKeyJSON {
  type?: Exclude<FieldType, 'mlist'>;
  item?: ScalarType;
  items?: FieldJSON[];
  values?: string[];
  default?: unknown;
  desc?: string;
}

/** Contrato tal como aparece en forks/<prefix>/contract.json. */
export interface ContractJSON {
  prefix: string;
  version?: number;
  name?: string;
  description?: string;
  parent?: string | null;
  list_separator?: string;
  records_key?: string;
  domain?: string;
  author?: string;
  license?: string;
  source?: string;
  header?: { required?: string[]; keys?: Record<string, HeaderKeyJSON> };
  core: FieldJSON[];
  extensions?: FieldJSON[];
}

/** Campo normalizado (valores por defecto aplicados). */
export interface Field {
  name: string;
  type: FieldType;
  optional: boolean;
  unique: boolean;
  values: string[] | null;
  item: ScalarType;
  item_values: string[] | null;
  /** Rango numérico o aridad; cadena en los límites de `date` y (opcionalmente) de `decimal`. */
  min: number | string | null;
  max: number | string | null;
  marker: MarkerMode;
  count_key: string | null;
  items: Field[];
  json_items: string;
  json_selected: string;
  desc: string;
  default: unknown;
}

/** Clave de cabecera normalizada. */
export interface HeaderKey {
  name: string;
  type: Exclude<FieldType, 'mlist'>;
  required: boolean;
  item: ScalarType;
  items: Field[];
  values: string[] | null;
  default: unknown;
  desc: string;
}

/** Contrato normalizado, listo para parse/dumps/specBlock. */
export interface Contract {
  prefix: string;
  version: number;
  name: string;
  description: string;
  parent: string | null;
  list_separator: string;
  records_key: string;
  domain: string;
  author: string;
  license: string;
  source: string;
  headerKeys: Record<string, HeaderKey>;
  core: Field[];
  extensions: Field[];
  /** core + extensions, en orden. */
  fields: Field[];
  /** Número de campos núcleo. */
  arity: number;
}

const NORMALIZED = Symbol.for('mini-format.contract');

// ----------------------------------------------------------- normalización
function hasOwn(o: object, k: string): boolean {
  return Object.prototype.hasOwnProperty.call(o, k);
}

function normField(d: FieldJSON, path: string = ''): Field {
  const raw = (d || {}) as unknown as Record<string, unknown>;
  const where = path ? `${path}.${raw.name ?? '?'}` : String(raw.name ?? '?');
  if (!hasOwn(raw, 'name') || !hasOwn(raw, 'type')) {
    throw new MiniError(E_CONTRACT, 0, `field ${where}: 'name' and 'type' are required`);
  }
  const t = d.type;
  if (!ALL_TYPES.has(t)) throw new MiniError(E_CONTRACT, 0, `field ${where}: unknown type '${t}'`);
  const f: Field = {
    name: d.name,
    type: t,
    optional: !!d.optional,
    unique: !!d.unique,
    values: hasOwn(raw, 'values') && d.values ? [...d.values] : null,
    item: d.item || 'str',
    item_values: hasOwn(raw, 'item_values') && d.item_values ? [...d.item_values] : null,
    min: d.min === undefined || d.min === null ? null : d.min,
    max: d.max === undefined || d.max === null ? null : d.max,
    marker: d.marker || 'exactly_one',
    count_key: d.count_key || null,
    items: [],
    json_items: 'items',
    json_selected: 'selected',
    desc: d.desc || '',
    default: d.default === undefined ? null : d.default,
  };
  if (t === 'enum' && !(f.values && f.values.length)) {
    throw new MiniError(E_CONTRACT, 0, `field ${where}: enum requires 'values'`);
  }
  if (t === 'date' || t === 'decimal') {
    // SPEC 1.1 §6: límites de date como AAAA-MM-DD; de decimal, cadena decimal o entero
    for (const bound of [f.min, f.max]) {
      if (bound === null) continue;
      const ok = t === 'date' ? typeof bound === 'string' && validDate(bound) : decimalBound(bound) !== null;
      if (!ok) throw new MiniError(E_CONTRACT, 0, `field ${where}: invalid bound '${String(bound)}' for type ${t}`);
    }
  }
  if (t === 'list' || t === 'mlist') {
    if (!SCALAR_TYPES.has(f.item)) throw new MiniError(E_CONTRACT, 0, `field ${where}: list item type must be scalar`);
    if (f.item === 'enum' && !(f.item_values && f.item_values.length)) {
      throw new MiniError(E_CONTRACT, 0, `field ${where}: enum items require 'item_values'`);
    }
  }
  if (t === 'mlist') {
    if (!MARKER_MODES.has(f.marker)) throw new MiniError(E_CONTRACT, 0, `field ${where}: bad marker mode '${f.marker}'`);
    const j = d.json || {};
    f.json_items = j.items || 'items';
    f.json_selected = j.selected || (f.marker === 'exactly_one' ? 'correct' : 'selected');
  }
  if (t === 'tuple') {
    const comps = d.items || [];
    if (!comps.length) throw new MiniError(E_CONTRACT, 0, `field ${where}: tuple requires 'items'`);
    f.items = comps.map(c => normField(c, where));
    for (const c of f.items) {
      if (!SCALAR_TYPES.has(c.type)) throw new MiniError(E_CONTRACT, 0, `field ${where}: tuple components must be scalar`);
    }
  }
  return f;
}

function normHeaderKey(name: string, d: HeaderKeyJSON, required: boolean): HeaderKey {
  const t = (d.type || 'str') as FieldType;
  if (!ALL_TYPES.has(t) || t === 'mlist') {
    throw new MiniError(E_CONTRACT, 0, `header key ${name}: unsupported type '${t}'`);
  }
  const hk: HeaderKey = {
    name,
    type: t as HeaderKey['type'],
    required,
    item: d.item || 'str',
    items: [],
    values: d.values || null,
    default: d.default === undefined ? null : d.default,
    desc: d.desc || '',
  };
  if (t === 'tuple') hk.items = (d.items || []).map(c => normField(c, `header.${name}`));
  return hk;
}

/** Vista de una clave de cabecera como campo (equivale a HeaderKey.as_field de la referencia). */
export function headerKeyAsField(hk: HeaderKey): Field {
  return {
    name: hk.name, type: hk.type, optional: !hk.required, unique: false, values: hk.values,
    item: hk.item, item_values: null, min: null, max: null, marker: 'exactly_one', count_key: null,
    items: hk.items, json_items: 'items', json_selected: 'selected', desc: hk.desc, default: hk.default,
  };
}

/** Indica si el objeto ya es un contrato normalizado por esta biblioteca. */
export function isContract(c: unknown): c is Contract {
  return !!c && typeof c === 'object' && (c as Record<symbol, unknown>)[NORMALIZED] === true;
}

/**
 * Normaliza un contract.json aplicando valores por defecto y validándolo.
 * Lanza MiniError E20 si el contrato es inválido. Idempotente.
 */
export function normalizeContract(d: ContractJSON | Contract): Contract {
  if (isContract(d)) return d;
  if (!d || typeof d !== 'object' || !hasOwn(d, 'prefix')) {
    throw new MiniError(E_CONTRACT, 0, "contract requires 'prefix'");
  }
  const prefix = String(d.prefix);
  if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(prefix)) {
    throw new MiniError(E_CONTRACT, 0, `prefix '${prefix}' must match [A-Za-z][A-Za-z0-9_-]*`);
  }
  const version = d.version === undefined || d.version === null ? 1 : Math.trunc(Number(d.version));
  if (!Number.isFinite(version)) throw new MiniError(E_CONTRACT, 0, `bad version '${d.version}'`);
  const sep = d.list_separator === undefined || d.list_separator === null ? ',' : String(d.list_separator);
  if ([...sep].length !== 1 || '|\\*\n'.includes(sep)) {
    throw new MiniError(E_CONTRACT, 0, 'list_separator must be a single character other than | \\ * or newline');
  }
  const hdr = d.header || {};
  const required = new Set<string>([...(hdr.required || ['n']), 'n']);
  const keys: Record<string, HeaderKeyJSON> = Object.assign({}, hdr.keys || {});
  if (!hasOwn(keys, 'n')) keys.n = { type: 'int', desc: 'number of records' };
  if (!hasOwn(keys, 'v')) keys.v = { type: 'int', default: 1, desc: 'contract version' };
  const headerKeys: Record<string, HeaderKey> = {};
  for (const k of Object.keys(keys)) headerKeys[k] = normHeaderKey(k, keys[k] || {}, required.has(k));
  for (const k of required) {
    if (!hasOwn(headerKeys, k)) {
      headerKeys[k] = { name: k, type: 'str', required: true, item: 'str', items: [], values: null, default: null, desc: '' };
    }
  }
  const core = (d.core || []).map(f => normField(f));
  const extensions = (d.extensions || []).map(f => normField(f));
  if (!core.length) throw new MiniError(E_CONTRACT, 0, 'contract requires at least one core field');
  const names = [...core, ...extensions].map(f => f.name);
  if (new Set(names).size !== names.length) throw new MiniError(E_CONTRACT, 0, 'duplicate field names in contract');
  for (const f of extensions) f.optional = true; // las extensiones son opcionales por definición
  const c: Contract = {
    prefix,
    version,
    name: d.name || '',
    description: d.description || '',
    parent: d.parent || null,
    list_separator: sep,
    records_key: d.records_key || 'records',
    domain: d.domain || '',
    author: d.author || '',
    license: d.license || 'MIT',
    source: d.source || '',
    headerKeys,
    core,
    extensions,
    fields: [...core, ...extensions],
    arity: core.length,
  };
  Object.defineProperty(c, NORMALIZED, { value: true, enumerable: false });
  return c;
}

// -------------------------------------------------------------- firmas
function numText(x: number | string | null): string {
  return x === null ? '' : String(x);
}

/** Firma corta de un campo, p. ej. `options:mlist<str>[2..6]*1`. */
export function fieldSignature(f: Field): string {
  let body: string;
  if (f.type === 'enum') {
    body = 'enum{' + (f.values || []).join('|') + '}';
  } else if (f.type === 'list' || f.type === 'mlist') {
    const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
    body = `${f.type}<${it}>`;
    if (f.min !== null || f.max !== null) {
      body += `[${f.min === null ? '' : Math.trunc(Number(f.min))}..${f.max === null ? '' : Math.trunc(Number(f.max))}]`;
    }
    if (f.type === 'mlist') {
      body += ({ exactly_one: '*1', at_least_one: '*1+', at_most_one: '*0..1', any: '*' } as const)[f.marker];
    }
  } else if (f.type === 'tuple') {
    body = 'tuple(' + f.items.map(c => `${c.name}:${c.type}`).join(',') + ')';
  } else {
    body = f.type;
    if (f.min !== null || f.max !== null) body += `[${numText(f.min)}..${numText(f.max)}]`;
  }
  return `${f.name}:${body}${f.optional ? '?' : ''}`;
}

/** Firma compacta del registro: núcleo `|` separado, extensiones tras `||`. */
export function signature(c: Contract): string {
  const core = c.core.map(fieldSignature).join(' | ');
  const ext = c.extensions.map(fieldSignature).join(' | ');
  return core + (ext ? ' || ' + ext : '');
}

// -------------------------------------------------------------- forks
/** Verifica los invariantes I2–I4 de un fork frente a su padre (SPEC §10). */
export function checkFork(childIn: Contract | ContractJSON, parentIn: Contract | ContractJSON): MiniError[] {
  const child = normalizeContract(childIn);
  const parent = normalizeContract(parentIn);
  const errs: MiniError[] = [];
  const pf = parent.fields;
  const cf = child.fields;
  if (cf.length < pf.length) {
    errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' drops fields of parent '${parent.prefix}'`));
    return errs;
  }
  pf.forEach((p, i) => {
    const k = cf[i];
    if (p.name !== k.name || p.type !== k.type) {
      errs.push(new MiniError(E_FORK, 0,
        `fork '${child.prefix}' changes inherited field #${i + 1}: parent ${fieldSignature(p)} != child ${fieldSignature(k)}`));
    }
    if ((p.type === 'list' || p.type === 'mlist') && p.item !== k.item) {
      errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' changes item type of '${p.name}'`));
    }
    if (p.type === 'tuple' && JSON.stringify(p.items.map(x => x.name)) !== JSON.stringify(k.items.map(x => x.name))) {
      errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' changes tuple layout of '${p.name}'`));
    }
  });
  if (child.list_separator !== parent.list_separator) {
    errs.push(new MiniError(E_FORK, 0, 'fork changes list_separator of its parent'));
  }
  for (const k of Object.keys(parent.headerKeys)) {
    if (parent.headerKeys[k].required && !(hasOwn(child.headerKeys, k) && child.headerKeys[k].required)) {
      errs.push(new MiniError(E_FORK, 0, `fork drops required header key '${k}'`));
    }
  }
  return errs;
}

/** Serializa un contrato normalizado de vuelta a su forma JSON (equivale a Contract.to_dict). */
export function contractToJSON(c: Contract): ContractJSON {
  const fieldToJSON = (f: Field): FieldJSON => {
    const d: FieldJSON = { name: f.name, type: f.type };
    if (f.optional) d.optional = true;
    if (f.unique) d.unique = true;
    if (f.values !== null) d.values = [...f.values];
    if (f.type === 'list' || f.type === 'mlist') {
      d.item = f.item;
      if (f.item_values !== null) d.item_values = [...f.item_values];
      if (f.count_key) d.count_key = f.count_key;
    }
    if (f.min !== null) d.min = f.min;
    if (f.max !== null) d.max = f.max;
    if (f.type === 'mlist') {
      d.marker = f.marker;
      d.json = { items: f.json_items, selected: f.json_selected };
    }
    if (f.type === 'tuple') d.items = f.items.map(fieldToJSON);
    if (f.desc) d.desc = f.desc;
    if (f.default !== null) d.default = f.default;
    return d;
  };
  const keys: Record<string, HeaderKeyJSON> = {};
  for (const [k, v] of Object.entries(c.headerKeys)) {
    const o: HeaderKeyJSON = { type: v.type };
    if (v.type === 'list') o.item = v.item;
    if (v.type === 'tuple') o.items = v.items.map(fieldToJSON);
    if (v.values !== null) o.values = v.values;
    if (v.default !== null) o.default = v.default;
    if (v.desc) o.desc = v.desc;
    keys[k] = o;
  }
  return {
    prefix: c.prefix, version: c.version, name: c.name, description: c.description, parent: c.parent,
    domain: c.domain, list_separator: c.list_separator, records_key: c.records_key,
    header: { required: Object.keys(c.headerKeys).filter(k => c.headerKeys[k].required), keys },
    core: c.core.map(fieldToJSON), extensions: c.extensions.map(fieldToJSON),
    author: c.author, license: c.license, source: c.source,
  };
}
