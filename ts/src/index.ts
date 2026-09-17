/* index.ts — API pública de @mini-format/core (biblioteca TypeScript de la notación .mini, SPEC 1.1).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { normalizeContract } from './contract.ts';
import type { Contract, ContractJSON } from './contract.ts';
import { parse } from './parser.ts';
import { dumps } from './serializer.ts';
import { scalarEqual } from './values.ts';

export const VERSION = '1.1.0';
export const SPEC_VERSION = '1.1';

export {
  MiniError, MiniValidationError,
  E_NO_HEADER, E_UNKNOWN_PREFIX, E_NO_COUNT, E_COUNT_MISMATCH, E_ARITY, E_TYPE, E_LIST_ARITY,
  E_MARKER, E_ESCAPE, E_ENUM, E_UNIQUE, E_HEADER_KEY, E_RANGE, E_CONTRACT, E_FORK,
} from './errors.ts';
export type { ErrorCode } from './errors.ts';

export {
  normalizeContract, isContract, fieldSignature, signature, checkFork, contractToJSON, headerKeyAsField,
  SCALAR_TYPES, COMPOSITE_TYPES, ALL_TYPES, MARKER_MODES,
} from './contract.ts';
export type {
  Contract, ContractJSON, Field, FieldJSON, HeaderKey, HeaderKeyJSON, FieldType, ScalarType, CompositeType, MarkerMode,
} from './contract.ts';

export { escapeScalar, escapeElement, tokenize, splitFields, splitList, textOf, FIELD_SEP, MARKER, ESCAPE, QUOTE } from './codec.ts';
export type { Tok, ListElement } from './codec.ts';

export { decodeScalar, encodeScalar, formatNumber, scalarEqual } from './values.ts';
export type { Scalar } from './values.ts';

export { parse, detectPrefix, Document, LineEngine } from './parser.ts';
export type { ParseOptions, CanonicalObject, MiniRecord, Header, Value, LineOutcome, DocumentDiagnostics } from './parser.ts';

export { dumps, encodeField, encodeHeader, encodeRecord } from './serializer.ts';

export { specBlock } from './prompt.ts';
export type { Lang } from './prompt.ts';

export { Registry, loadContract, defaultForksDir } from './registry.ts';
export type { RegistryIndexEntry } from './registry.ts';

export { createReader, readRecords } from './stream.ts';
export type { MiniReader, ReaderOptions, ReaderResult, ReaderProgress, StreamRecord, IncompleteRecord } from './stream.ts';

/** Igualdad estructural tolerante a diferencias de representación int/float (SPEC §7). */
export function canonicalEqual(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((x, i) => canonicalEqual(x, b[i]));
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    const sb = new Set(kb);
    return ka.every(k => sb.has(k) && canonicalEqual((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
  }
  return scalarEqual(a, b);
}

/** obj -> .mini -> obj' debe ser igual a obj, y texto -> obj -> texto debe ser estable (SPEC §9). */
export function roundtripOk(obj: Record<string, unknown>, contract: Contract | ContractJSON): boolean {
  const c = normalizeContract(contract);
  const text = dumps(obj, c);
  const back = parse(text, c).toCanonical();
  const records = (obj[c.records_key] ?? obj.records ?? []) as Record<string, unknown>[];
  const header: Record<string, unknown> = Object.assign({}, (obj.header || {}) as Record<string, unknown>);
  header.n = records.length;
  if (!Object.prototype.hasOwnProperty.call(header, 'v')) {
    header.v = c.headerKeys.v ? c.headerKeys.v.default : 1;
  }
  const refRecords = records.map(r => {
    const out = Object.assign({}, r);
    for (const f of c.extensions) {
      if (f.type === 'mlist') {
        if (!(f.json_items in out)) out[f.json_items] = null;
        if (!(f.json_selected in out)) out[f.json_selected] = null;
      } else if (!(f.name in out)) {
        out[f.name] = null;
      }
    }
    return out;
  });
  const ref = { prefix: c.prefix, header, [c.records_key]: refRecords };
  return canonicalEqual(back, ref) && dumps(back, c) === text;
}
