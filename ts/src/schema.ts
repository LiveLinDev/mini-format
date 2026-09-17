/* schema.ts — contratos .mini a partir de JSON Schema y de esquemas Zod (v4).
 * Solo se admiten registros planos (SPEC §12): un objeto cuyas propiedades son escalares
 * (string, integer, number, boolean, enum) o listas de escalares, opcionales o anulables.
 * Todo lo que .mini no puede representar o validar (objetos anidados, listas de objetos,
 * uniones, patrones, formatos, longitudes...) produce un MiniError E20 explícito.
 * Sin dependencias de ejecución: Zod se usa solo a través del esquema que recibe fromZod.
 * Módulo seguro para navegador.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { normalizeContract } from './contract.ts';
import type { ContractJSON, FieldJSON, HeaderKeyJSON, ScalarType } from './contract.ts';
import { E_CONTRACT, MiniError } from './errors.ts';

/** Subconjunto de JSON Schema que se inspecciona. */
export type JsonSchema = { [keyword: string]: unknown };

export interface FromSchemaOptions {
  /** Prefijo de la familia (obligatorio). */
  prefix: string;
  version?: number;
  name?: string;
  description?: string;
  domain?: string;
  records_key?: string;
  list_separator?: string;
  /** Campos con valores únicos (E11). */
  unique?: string[];
  /** Claves de cabecera adicionales (además de n y v). */
  header?: { required?: string[]; keys?: Record<string, HeaderKeyJSON> };
  /**
   * 'error' (por defecto): una restricción que .mini no valida (pattern, format, minLength...)
   * hace fallar la conversión. 'ignore': se descarta y se informa en `warnings`.
   * Las estructuras no representables (anidamiento, uniones) siempre fallan.
   */
  unsupported?: 'error' | 'ignore';
  /** Recibe los avisos de restricciones descartadas con unsupported='ignore'. */
  warnings?: string[];
}

/** Palabras clave sin efecto sobre la validación. */
const ANNOTATIONS = new Set([
  '$schema', '$id', '$comment', 'title', 'description', 'examples', 'default', 'deprecated', 'readOnly', 'writeOnly',
]);
const SAFE_MIN = -9007199254740991;
const SAFE_MAX = 9007199254740991;

function fail(path: string, message: string): never {
  throw new MiniError(E_CONTRACT, 0, `${path}: ${message}`, path);
}

function isObj(v: unknown): v is JsonSchema {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function types(s: JsonSchema): string[] {
  if (Array.isArray(s.type)) return s.type.map(String);
  if (typeof s.type === 'string') return [s.type];
  return [];
}

interface Ctx {
  opts: FromSchemaOptions;
  warnings: string[];
}

/** Restricción que .mini no valida: error o aviso según la opción. */
function unsupported(ctx: Ctx, path: string, keyword: string): void {
  const msg = `${path}: keyword '${keyword}' cannot be validated by .mini`;
  if (ctx.opts.unsupported === 'ignore') ctx.warnings.push(msg);
  else throw new MiniError(E_CONTRACT, 0, msg + " (use unsupported: 'ignore' to drop it)", path);
}

/** Separa la variante nula: {type:[X,'null']}, anyOf/oneOf [X, {type:'null'}], enum con null. */
function splitNullable(s: JsonSchema, path: string): { schema: JsonSchema; nullable: boolean } {
  for (const key of ['anyOf', 'oneOf'] as const) {
    if (!Array.isArray(s[key])) continue;
    const variants = (s[key] as unknown[]).filter(isObj);
    const nonNull = variants.filter(v => !(types(v).length === 1 && types(v)[0] === 'null'));
    if (nonNull.length !== 1 || variants.length !== (s[key] as unknown[]).length) {
      fail(path, `${key} with several non-null variants is not representable (SPEC §12)`);
    }
    const rest: JsonSchema = { ...s };
    delete rest[key];
    return { schema: { ...nonNull[0], ...rest }, nullable: variants.length > nonNull.length };
  }
  const t = types(s);
  let schema = s;
  let nullable = false;
  if (t.includes('null')) {
    nullable = true;
    const others = t.filter(x => x !== 'null');
    if (others.length > 1) fail(path, `union type [${t.join(', ')}] is not representable (SPEC §12)`);
    schema = { ...s, type: others[0] };
  } else if (t.length > 1) {
    fail(path, `union type [${t.join(', ')}] is not representable (SPEC §12)`);
  }
  if (Array.isArray(schema.enum) && schema.enum.includes(null)) {
    nullable = true;
    schema = { ...schema, enum: schema.enum.filter(v => v !== null) };
  }
  return { schema, nullable };
}

function checkKeywords(ctx: Ctx, s: JsonSchema, path: string, allowed: string[]): void {
  for (const k of Object.keys(s)) {
    if (ANNOTATIONS.has(k) || allowed.includes(k)) continue;
    if (k === 'properties' || k === 'items' || k === '$ref' || k === 'allOf' || k === 'not' || k === 'if'
      || k === 'patternProperties' || k === 'prefixItems') {
      fail(path, `keyword '${k}' is not representable in a flat .mini record (SPEC §12)`);
    }
    unsupported(ctx, path, k);
  }
}

interface Scalar {
  type: ScalarType;
  values?: string[];
  min?: number | string;
  max?: number | string;
}

/** Límites de date/decimal: formatMinimum/formatMaximum o anotación x-mini (texto). */
function textBounds(ctx: Ctx, s: JsonSchema, path: string, asItem: boolean, out: Scalar): void {
  const ann = isObj(s['x-mini']) ? (s['x-mini'] as JsonSchema) : {};
  const lo = ann.min ?? s.formatMinimum;
  const hi = ann.max ?? s.formatMaximum;
  for (const [key, v] of [['min', lo], ['max', hi]] as const) {
    if (v === undefined) continue;
    if (typeof v !== 'string' && typeof v !== 'number') fail(path, `invalid ${key} bound`);
    if (asItem) unsupported(ctx, path, key === 'min' ? 'formatMinimum' : 'formatMaximum');
    else out[key] = v as string | number;
  }
}

/** Escalar JSON Schema -> tipo .mini. `asItem`: elemento de lista (sin rango). */
function scalar(ctx: Ctx, s: JsonSchema, path: string, asItem: boolean): Scalar {
  if (Array.isArray(s.enum) || s.const !== undefined) {
    const values = Array.isArray(s.enum) ? s.enum : [s.const];
    if (!values.length || !values.every(v => typeof v === 'string')) {
      fail(path, 'only string enums are representable');
    }
    checkKeywords(ctx, s, path, ['type', 'enum', 'const']);
    return { type: 'enum', values: [...new Set(values as string[])] };
  }
  const t = types(s);
  if (!t.length) fail(path, 'schema without a type is not representable (e.g. z.any(), z.date(), custom types)');
  switch (t[0]) {
    case 'string': {
      const ann = isObj(s['x-mini']) ? (s['x-mini'] as JsonSchema) : {};
      if (s.format === 'date' || ann.type === 'date') {
        const out: Scalar = { type: 'date' };
        textBounds(ctx, s, path, asItem, out);
        checkKeywords(ctx, s, path, ['type', 'format', 'pattern', 'formatMinimum', 'formatMaximum', 'x-mini']);
        return out;
      }
      if (s.format === 'decimal' || ann.type === 'decimal') {
        const out: Scalar = { type: 'decimal' };
        textBounds(ctx, s, path, asItem, out);
        checkKeywords(ctx, s, path, ['type', 'format', 'pattern', 'x-mini']);
        return out;
      }
      checkKeywords(ctx, s, path, ['type']);
      return { type: 'str' };
    }
    case 'boolean':
      checkKeywords(ctx, s, path, ['type']);
      return { type: 'bool' };
    case 'integer':
    case 'number': {
      const isInt = t[0] === 'integer';
      const out: Scalar = { type: isInt ? 'int' : 'float' };
      let min = typeof s.minimum === 'number' ? s.minimum : undefined;
      let max = typeof s.maximum === 'number' ? s.maximum : undefined;
      if (typeof s.exclusiveMinimum === 'number') {
        if (isInt) min = Math.max(min ?? -Infinity, Math.floor(s.exclusiveMinimum) + 1);
        else unsupported(ctx, path, 'exclusiveMinimum');
      }
      if (typeof s.exclusiveMaximum === 'number') {
        if (isInt) max = Math.min(max ?? Infinity, Math.ceil(s.exclusiveMaximum) - 1);
        else unsupported(ctx, path, 'exclusiveMaximum');
      }
      if (isInt && min === SAFE_MIN) min = undefined;
      if (isInt && max === SAFE_MAX) max = undefined;
      checkKeywords(ctx, s, path, ['type', 'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum']);
      if (asItem) {
        if (min !== undefined) unsupported(ctx, path, 'minimum');
        if (max !== undefined) unsupported(ctx, path, 'maximum');
      } else {
        if (min !== undefined) out.min = min;
        if (max !== undefined) out.max = max;
      }
      return out;
    }
    case 'object':
      return fail(path, 'nested object is not representable; use a second family or flatten it (SPEC §12)');
    case 'array':
      return fail(path, 'nested array is not representable (SPEC §12)');
    default:
      return fail(path, `type '${t[0]}' is not representable`);
  }
}

function field(ctx: Ctx, name: string, raw: unknown, required: boolean): FieldJSON {
  const path = name;
  if (!isObj(raw)) fail(path, 'boolean or empty schemas are not representable');
  const { schema: s, nullable } = splitNullable(raw, path);
  const f: FieldJSON = { name, type: 'str' };
  const t = types(s);
  if (t[0] === 'array') {
    const itemsRaw = s.items;
    if (!isObj(itemsRaw)) fail(path, 'arrays require a single item schema');
    const { schema: item, nullable: itemNull } = splitNullable(itemsRaw, `${path}[]`);
    if (itemNull) fail(`${path}[]`, 'null list elements are not representable');
    const sc = scalar(ctx, item, `${path}[]`, true);
    checkKeywords(ctx, s, path, ['type', 'items', 'minItems', 'maxItems']);
    f.type = 'list';
    f.item = sc.type;
    if (sc.values) f.item_values = sc.values;
    if (typeof s.minItems === 'number') f.min = s.minItems;
    if (typeof s.maxItems === 'number') f.max = s.maxItems;
  } else {
    const sc = scalar(ctx, s, path, false);
    f.type = sc.type;
    if (sc.values) f.values = sc.values;
    if (sc.min !== undefined) f.min = sc.min;
    if (sc.max !== undefined) f.max = sc.max;
  }
  const hasDefault = Object.prototype.hasOwnProperty.call(raw, 'default') || Object.prototype.hasOwnProperty.call(s, 'default');
  if (!required || nullable || hasDefault) f.optional = true;
  if (hasDefault) f.default = (Object.prototype.hasOwnProperty.call(raw, 'default') ? raw : s).default;
  const desc = typeof raw.description === 'string' ? raw.description : typeof s.description === 'string' ? s.description : '';
  if (desc) f.desc = desc;
  if (ctx.opts.unique && ctx.opts.unique.includes(name)) f.unique = true;
  return f;
}

/**
 * Convierte un JSON Schema de registro plano en un contrato .mini (ContractJSON).
 * Acepta el esquema de un registro (`type: object`) o de una lista de registros
 * (`type: array` con `items` objeto). El orden de los campos es el de `properties`.
 * Lanza MiniError E20 ante estructuras o restricciones no representables.
 */
export function fromJsonSchema(schema: JsonSchema, opts: FromSchemaOptions): ContractJSON {
  if (!opts || typeof opts.prefix !== 'string') throw new MiniError(E_CONTRACT, 0, "fromJsonSchema requires options.prefix");
  const ctx: Ctx = { opts, warnings: opts.warnings ?? [] };
  let root: unknown = schema;
  if (isObj(root) && types(root)[0] === 'array' && isObj(root.items)) root = root.items;
  if (!isObj(root) || types(root)[0] !== 'object' || !isObj(root.properties)) {
    throw new MiniError(E_CONTRACT, 0, 'root schema must be an object with properties (or an array of such objects)');
  }
  const props = root.properties;
  const required = new Set(Array.isArray(root.required) ? root.required.map(String) : []);
  const extra = root.additionalProperties;
  if (extra !== undefined && extra !== false) unsupported(ctx, '<root>', 'additionalProperties');
  for (const k of Object.keys(root)) {
    if (!ANNOTATIONS.has(k) && !['type', 'properties', 'required', 'additionalProperties'].includes(k)) {
      unsupported(ctx, '<root>', k);
    }
  }
  const names = Object.keys(props);
  if (!names.length) throw new MiniError(E_CONTRACT, 0, 'record schema has no properties');
  const core = names.map(n => field(ctx, n, props[n], required.has(n)));
  for (const u of opts.unique ?? []) {
    if (!names.includes(u)) throw new MiniError(E_CONTRACT, 0, `unique field '${u}' is not a property`);
  }
  const out: ContractJSON = {
    prefix: opts.prefix,
    version: opts.version ?? 1,
    name: opts.name ?? (typeof root.title === 'string' ? root.title : ''),
    description: opts.description ?? (typeof root.description === 'string' ? root.description : ''),
    parent: null,
    list_separator: opts.list_separator ?? ',',
    records_key: opts.records_key ?? 'records',
    domain: opts.domain ?? '',
    header: opts.header ?? { required: ['n'], keys: {} },
    core,
    extensions: [],
  };
  normalizeContract(out); // valida el resultado (E20)
  return out;
}

/** Esquema Zod v4 (tipado estructural: no se importa zod). */
export interface ZodLike {
  toJSONSchema?: (params?: Record<string, unknown>) => unknown;
}

export interface FromZodOptions extends FromSchemaOptions {
  /**
   * Conversor a JSON Schema. Por defecto se usa el método `schema.toJSONSchema` de Zod v4;
   * pase `z.toJSONSchema` (o zod-to-json-schema para Zod 3) si el esquema no lo tiene.
   */
  toJSONSchema?: (schema: never, params?: Record<string, unknown>) => unknown;
}

/**
 * Convierte un esquema Zod de objeto plano en un contrato .mini.
 * Usa la vista de entrada (io: 'input') porque el contrato valida lo que produce el modelo.
 */
export function fromZod(schema: ZodLike, opts: FromZodOptions): ContractJSON {
  const params = { io: 'input', unrepresentable: 'any', target: 'draft-2020-12' };
  let json: unknown;
  if (opts && typeof opts.toJSONSchema === 'function') json = opts.toJSONSchema(schema as never, params);
  else if (schema && typeof schema.toJSONSchema === 'function') json = schema.toJSONSchema(params);
  else {
    throw new MiniError(E_CONTRACT, 0, 'schema has no toJSONSchema(); pass options.toJSONSchema (e.g. z.toJSONSchema)');
  }
  if (!isObj(json)) throw new MiniError(E_CONTRACT, 0, 'toJSONSchema did not return an object');
  return fromJsonSchema(json, opts);
}
