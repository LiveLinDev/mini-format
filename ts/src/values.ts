/* values.ts — decodificación/codificación tipada de escalares (SPEC §6).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import type { Field, ScalarType } from './contract.ts';
import { E_ENUM, E_RANGE, E_TYPE, MiniError } from './errors.ts';

export type Scalar = string | number | boolean;

// SPEC 1.1 §6: solo dígitos ASCII, sin '+', y los flotantes llevan dígitos a ambos lados
// del punto ('.5' y '1.' son E06). Se admiten ceros a la izquierda.
const INT_RE = /^-?[0-9]+$/;
const FLOAT_RE = /^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$/;
const DECIMAL_RE = /^(-?)([0-9]+)(?:\.([0-9]+))?$/;
const DATE_RE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;
const RANGED_TYPES: ReadonlySet<string> = new Set(['int', 'float', 'decimal', 'date']);

/** `AAAA-MM-DD` que nombra un día existente del calendario gregoriano proléptico (0001–9999). */
export function validDate(text: string): boolean {
  const m = DATE_RE.exec(text);
  if (!m) return false;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (y < 1 || mo < 1 || mo > 12 || d < 1) return false;
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1];
  return d <= days;
}

/**
 * Texto canónico de un decimal exacto, o null si `text` no lo es: sin ceros a la
 * izquierda en la parte entera, sin signo en el cero y conservando la escala
 * (`-007.50` -> `-7.50`, `-0.0` -> `0.0`).
 */
export function normalizeDecimal(text: string): string | null {
  const m = DECIMAL_RE.exec(text);
  if (!m) return null;
  let sign = m[1];
  const whole = m[2].replace(/^0+/, '') || '0';
  const frac = m[3];
  if (whole === '0' && (frac === undefined || /^0+$/.test(frac))) sign = '';
  return sign + whole + (frac === undefined ? '' : '.' + frac);
}

/** Texto canónico de un límite `min`/`max` decimal del contrato (string decimal o entero seguro), o null. */
export function decimalBound(value: unknown): string | null {
  if (typeof value === 'number') return Number.isSafeInteger(value) ? String(value === 0 ? 0 : value) : null;
  if (typeof value === 'string') return normalizeDecimal(value);
  return null;
}

/** Compara dos decimales canónicos exactamente: -1, 0 o 1. */
export function compareDecimal(a: string, b: string): number {
  const na = a.startsWith('-');
  const nb = b.startsWith('-');
  if (na !== nb) return na ? -1 : 1;
  const [ia, fa = ''] = (na ? a.slice(1) : a).split('.');
  const [ib, fb = ''] = (nb ? b.slice(1) : b).split('.');
  let cmp = 0;
  if (ia.length !== ib.length) cmp = ia.length < ib.length ? -1 : 1;
  else if (ia !== ib) cmp = ia < ib ? -1 : 1;
  else {
    const len = Math.max(fa.length, fb.length);
    const pa = fa.padEnd(len, '0');
    const pb = fb.padEnd(len, '0');
    if (pa !== pb) cmp = pa < pb ? -1 : 1;
  }
  return na ? -cmp : cmp;
}

function checkRange(v: number | string, f: Field, lineno: number, name: string): void {
  if (!RANGED_TYPES.has(f.type)) return;
  if (f.type === 'decimal') {
    const lo = f.min === null ? null : decimalBound(f.min);
    const hi = f.max === null ? null : decimalBound(f.max);
    if (lo !== null && compareDecimal(v as string, lo) < 0) throw new MiniError(E_RANGE, lineno, `${v} < min ${f.min}`, name);
    if (hi !== null && compareDecimal(v as string, hi) > 0) throw new MiniError(E_RANGE, lineno, `${v} > max ${f.max}`, name);
    return;
  }
  // int/float se comparan numéricamente; las fechas AAAA-MM-DD como cadenas
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
    if (text === 'true' || text === '1') return true;
    if (text === 'false' || text === '0') return false;
    throw new MiniError(E_TYPE, lineno, `expected true/false/1/0, got '${text}'`, name);
  }
  if (t === 'enum') {
    if (!values || !values.includes(text)) {
      throw new MiniError(E_ENUM, lineno, `'${text}' not in {${(values || []).join('|')}}`, name);
    }
    return text;
  }
  if (t === 'date') {
    if (!validDate(text)) throw new MiniError(E_TYPE, lineno, `expected date YYYY-MM-DD, got '${text}'`, name);
    if (!asItem) checkRange(text, f, lineno, name);
    return text;
  }
  if (t === 'decimal') {
    const norm = normalizeDecimal(text);
    if (norm === null) throw new MiniError(E_TYPE, lineno, `expected decimal, got '${text}'`, name);
    if (!asItem) checkRange(norm, f, lineno, name);
    return norm;
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

/**
 * Forma textual canónica de un valor tipado (antes de escapar). Un valor que no
 * puede representar el tipo declarado lanza E06, el código que el parser da a la
 * misma violación (SPEC 1.1 §9).
 */
export function encodeScalar(value: unknown, f: Field, asItem: boolean = false): string {
  const t = asItem ? f.item : f.type;
  if (value === null || value === undefined) return '';
  if (t === 'bool') return value ? 'true' : 'false';
  if (t === 'int') {
    if (typeof value === 'string' && !INT_RE.test(value.trim())) {
      throw new MiniError(E_TYPE, 0, `expected int, got '${value}'`, f.name);
    }
    const v = numberFromJson(value, f, f.name);
    if (!Number.isInteger(v)) throw new MiniError(E_TYPE, 0, `expected int, got '${String(value)}'`, f.name);
    return integerText(v);
  }
  if (t === 'float') return formatNumber(numberFromJson(value, f, f.name));
  if (t === 'decimal') {
    if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value === 0 ? 0 : value);
    if (typeof value !== 'string') {
      throw new MiniError(E_TYPE, 0, `decimal values are strings, got '${String(value)}'`, f.name);
    }
  }
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
