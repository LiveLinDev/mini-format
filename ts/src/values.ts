/* values.ts — decodificación/codificación tipada de escalares (SPEC §6).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import type { Field, ScalarType } from './contract.ts';
import { trimSpace } from './codec.ts';
import { E_ENUM, E_RANGE, E_TYPE, MiniError } from './errors.ts';

export type Scalar = string | number | boolean;

const INT_RE = /^[+-]?[0-9]+$/;
const FLOAT_RE = /^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$/;
const TRUE = new Set(['true', '1', 'yes', 'y', 't']);
const FALSE = new Set(['false', '0', 'no', 'n', 'f']);

function checkRange(v: number, f: Field, lineno: number, name: string): void {
  if (f.min !== null && v < f.min) throw new MiniError(E_RANGE, lineno, `${v} < min ${f.min}`, name);
  if (f.max !== null && v > f.max) throw new MiniError(E_RANGE, lineno, `${v} > max ${f.max}`, name);
}

/**
 * Convierte el texto (ya sin escapes) de un escalar a su valor tipado.
 * Con `asItem` se usa el tipo de elemento de una lista (`item`/`item_values`)
 * y no se aplica el rango min/max (que en listas es aridad).
 */
export function decodeScalar(text: string, f: Field, lineno: number, fname?: string, asItem: boolean = false): Scalar {
  const name = fname || f.name;
  const t = (asItem ? f.item : f.type) as ScalarType;
  const values = asItem ? f.item_values : f.values;
  if (t === 'str') return text;
  if (t === 'int') {
    if (!INT_RE.test(text)) throw new MiniError(E_TYPE, lineno, `expected int, got '${text}'`, name);
    let v = parseInt(text, 10);
    if (v === 0) v = 0; // normaliza -0
    if (!asItem) checkRange(v, f, lineno, name);
    return v;
  }
  if (t === 'float') {
    if (!FLOAT_RE.test(text)) throw new MiniError(E_TYPE, lineno, `expected number, got '${text}'`, name);
    const v = parseFloat(text);
    if (!Number.isFinite(v)) throw new MiniError(E_TYPE, lineno, 'non-finite number', name);
    if (!asItem) checkRange(v, f, lineno, name);
    return v;
  }
  if (t === 'bool') {
    const low = trimSpace(text).toLowerCase();
    if (TRUE.has(low)) return true;
    if (FALSE.has(low)) return false;
    throw new MiniError(E_TYPE, lineno, `expected true/false, got '${text}'`, name);
  }
  if (t === 'enum') {
    if (!values || !values.includes(text)) {
      throw new MiniError(E_ENUM, lineno, `'${text}' not in {${(values || []).join('|')}}`, name);
    }
    return text;
  }
  throw new MiniError(E_TYPE, lineno, `unsupported scalar type ${t}`, name);
}

/** Representación exacta de un entero grande (|x| ≥ 1e21) sin notación exponencial. */
function integerText(x: number): string {
  if (Math.abs(x) < 1e21) return String(x === 0 ? 0 : x);
  return BigInt(x).toString();
}

/** Representación tipo repr() de la referencia: la más corta, con exponente si exp < -4 o ≥ 16. */
function reprFloat(x: number): string {
  if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
  const [mant, expText] = x.toExponential().split('e');
  const exp = parseInt(expText, 10);
  const neg = mant.startsWith('-');
  const digits = mant.replace('-', '').replace('.', '');
  if (exp < -4 || exp >= 16) {
    const m = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    const e = Math.abs(exp) < 10 ? `0${Math.abs(exp)}` : String(Math.abs(exp));
    return `${neg ? '-' : ''}${m}e${exp < 0 ? '-' : '+'}${e}`;
  }
  let s: string;
  if (exp < 0) s = '0.' + '0'.repeat(-exp - 1) + digits;
  else if (digits.length <= exp + 1) s = digits + '0'.repeat(exp + 1 - digits.length) + '.0';
  else s = digits.slice(0, exp + 1) + '.' + digits.slice(exp + 1);
  return (neg ? '-' : '') + s;
}

/** Texto numérico canónico: los flotantes enteros pierden el `.0`; se evita el exponente cuando es exacto. */
export function formatNumber(x: number | boolean): string {
  if (typeof x === 'boolean') return x ? 'true' : 'false';
  if (Number.isInteger(x) && Math.abs(x) < 1e15) return String(x === 0 ? 0 : x);
  let s = reprFloat(x);
  if (s.includes('e') || s.includes('E')) {
    // expande exponentes para legibilidad/estabilidad de tokens
    let s2 = Math.abs(x) >= 1e21 ? integerText(x) : x.toFixed(15);
    if (s2.includes('.')) s2 = s2.replace(/0+$/, '').replace(/\.$/, '');
    if (parseFloat(s2) === x) return s2;
  }
  return s;
}

function numberFromJson(value: unknown, f: Field, name: string): number {
  const v = typeof value === 'number' ? value : typeof value === 'boolean' ? Number(value) : Number(String(value).trim());
  if (!Number.isFinite(v)) throw new MiniError(E_TYPE, 0, `expected number, got '${String(value)}'`, name);
  return v;
}

/** Forma textual canónica de un valor tipado (antes de escapar). */
export function encodeScalar(value: unknown, f: Field, asItem: boolean = false): string {
  const t = asItem ? f.item : f.type;
  if (value === null || value === undefined) return '';
  if (t === 'bool') return value ? 'true' : 'false';
  if (t === 'int') return integerText(Math.trunc(numberFromJson(value, f, f.name)));
  if (t === 'float') return formatNumber(numberFromJson(value, f, f.name));
  return String(value);
}

/** Igualdad de escalares tolerante a la representación int/float. */
export function scalarEqual(a: unknown, b: unknown): boolean {
  if (typeof a === 'number' && typeof b === 'number') {
    if (a === b) return true;
    const diff = Math.abs(a - b);
    return diff <= Math.max(1e-12 * Math.max(Math.abs(a), Math.abs(b)), 1e-12);
  }
  return a === b;
}
