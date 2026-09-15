/* stream.ts — lectura incremental de documentos .mini (p. ej. respuestas de un modelo token a token).
 * Aditivo respecto de la SPEC: usa el mismo motor por líneas que `parse`, de modo que al
 * terminar el documento resultante es idéntico al de parse(textoCompleto).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { isBlank } from './codec.ts';
import { normalizeContract } from './contract.ts';
import type { Contract, ContractJSON } from './contract.ts';
import { MiniError, MiniValidationError } from './errors.ts';
import { Document, LineEngine } from './parser.ts';
import type { Header, MiniRecord } from './parser.ts';

/** Registro emitido en cuanto su línea se cierra con LF. */
export interface StreamRecord {
  record: MiniRecord;
  /** Línea física 1-based. */
  line: number;
  /** Posición del registro entre los registros válidos (0-based). */
  index: number;
}

/** Última línea recibida sin LF final que no pudo validarse (típico de una salida truncada). */
export interface IncompleteRecord {
  line: number;
  text: string;
  /** Campos separados por `|` presentes en la línea (aproximado, sin resolver escapes). */
  fieldsSeen: number;
  /** true si la línea incompleta es la cabecera. */
  isHeader: boolean;
  errors: MiniError[];
}

export interface ReaderOptions {
  /** false (por defecto): tolerante. true: escapes estrictos y `end()` lanza MiniValidationError si hay errores. */
  strict?: boolean;
  onHeader?: (info: { prefix: string; header: Header; line: number }) => void;
  onRecord?: (rec: StreamRecord) => void;
  onError?: (err: MiniError) => void;
}

export interface ReaderResult {
  document: Document;
  records: MiniRecord[];
  errors: MiniError[];
  /** Valor de `n` declarado en la cabecera (null si falta o no es entero). */
  expected: number | null;
  /** Líneas de registro significativas recibidas (válidas o no). */
  received: number;
  /** Registros válidos. */
  valid: number;
  /** max(0, expected - received). */
  missing: number;
  /** max(0, received - expected). */
  excess: number;
  /** true si el flujo terminó en LF (o sin contenido pendiente). */
  terminated: boolean;
  incomplete: IncompleteRecord | null;
  /** Hay indicios de truncamiento: registro incompleto o menos líneas que `n`. */
  truncated: boolean;
  /** Sin errores de ningún tipo. */
  complete: boolean;
}

export interface ReaderProgress {
  expected: number | null;
  received: number;
  valid: number;
  errors: number;
}

export interface MiniReader {
  /** Añade un fragmento (texto, o bytes UTF-8; no mezclar ambos en un mismo flujo). Devuelve los registros completados. */
  push(chunk: string | Uint8Array): StreamRecord[];
  /** Cierra el flujo (opcionalmente con un último fragmento) y devuelve el resultado final. */
  end(chunk?: string | Uint8Array): ReaderResult;
  readonly contract: Contract;
  readonly prefix: string;
  readonly header: Header | null;
  readonly records: readonly MiniRecord[];
  readonly errors: readonly MiniError[];
  /** Texto de la línea en curso, aún sin LF. */
  readonly pending: string;
  readonly progress: ReaderProgress;
  readonly ended: boolean;
}

function countFieldsApprox(line: string): number {
  let n = 1;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === '\\') i++;
    else if (line[i] === '|') n++;
  }
  return n;
}

function declaredCount(header: Header | null): number | null {
  if (!header || !Object.prototype.hasOwnProperty.call(header, 'n')) return null;
  const n = header.n;
  return typeof n === 'number' && Number.isInteger(n) ? n : null;
}

/** Crea un lector incremental para `contract`. */
export function createReader(contract: Contract | ContractJSON, opts: ReaderOptions = {}): MiniReader {
  const c = normalizeContract(contract);
  const strict = opts.strict === true;
  const engine = new LineEngine(c, strict);
  let buffer = '';
  let scanFrom = 0;
  let ended = false;
  let decoder: TextDecoder | null = null;
  let reportedErrors = 0;

  const flushErrors = (): void => {
    if (opts.onError) for (; reportedErrors < engine.errors.length; reportedErrors++) opts.onError(engine.errors[reportedErrors]);
    else reportedErrors = engine.errors.length;
  };

  const feedLine = (raw: string, out: StreamRecord[]): void => {
    const hadHeader = engine.header !== null;
    const outcome = engine.feed(raw);
    if (!hadHeader && engine.header !== null && opts.onHeader) {
      opts.onHeader({ prefix: engine.prefix, header: engine.header, line: engine.physical });
    }
    if (outcome && outcome.record) {
      const rec: StreamRecord = { record: outcome.record, line: outcome.line, index: engine.records.length - 1 };
      out.push(rec);
      if (opts.onRecord) opts.onRecord(rec);
    }
    flushErrors();
  };

  const toText = (chunk: string | Uint8Array): string => {
    if (typeof chunk === 'string') return chunk;
    if (!decoder) decoder = new TextDecoder('utf-8');
    return decoder.decode(chunk, { stream: true });
  };

  const reader: MiniReader = {
    push(chunk: string | Uint8Array): StreamRecord[] {
      if (ended) throw new Error('mini reader already ended');
      const out: StreamRecord[] = [];
      const text = toText(chunk);
      if (!text) return out;
      buffer += text;
      let idx = buffer.indexOf('\n', scanFrom);
      let start = 0;
      while (idx >= 0) {
        feedLine(buffer.slice(start, idx), out);
        start = idx + 1;
        idx = buffer.indexOf('\n', start);
      }
      if (start > 0) buffer = buffer.slice(start);
      scanFrom = buffer.length;
      return out;
    },

    end(chunk?: string | Uint8Array): ReaderResult {
      if (ended) throw new Error('mini reader already ended');
      if (chunk !== undefined) reader.push(chunk);
      if (decoder) {
        const tail = decoder.decode();
        if (tail) reader.push(tail);
      }
      ended = true;
      const rest = buffer;
      buffer = '';
      const terminated = isBlank(rest);
      const errsBefore = engine.errors.length;
      const hadHeader = engine.header !== null;
      const lineNo = engine.physical + 1;
      feedLine(rest, []);
      let incomplete: IncompleteRecord | null = null;
      if (!terminated) {
        const lineErrors = engine.errors.slice(errsBefore).filter(e => e.line === lineNo);
        if (lineErrors.length) {
          incomplete = {
            line: lineNo, text: rest, fieldsSeen: countFieldsApprox(rest), isHeader: !hadHeader, errors: lineErrors,
          };
        }
      }
      const document = engine.finish();
      for (let i = engine.errors.length; i < document.errors.length; i++) if (opts.onError) opts.onError(document.errors[i]);
      const expected = declaredCount(engine.header);
      const received = engine.recordLines;
      const missing = expected === null ? 0 : Math.max(0, expected - received);
      const excess = expected === null ? 0 : Math.max(0, received - expected);
      const result: ReaderResult = {
        document,
        records: document.records,
        errors: document.errors,
        expected,
        received,
        valid: document.records.length,
        missing,
        excess,
        terminated,
        incomplete,
        truncated: incomplete !== null || missing > 0,
        complete: document.errors.length === 0,
      };
      if (strict && document.errors.length) {
        throw Object.assign(new MiniValidationError(document.errors), { result });
      }
      return result;
    },

    get contract() { return c; },
    get prefix() { return engine.prefix; },
    get header() { return engine.header; },
    get records() { return engine.records; },
    get errors() { return engine.errors; },
    get pending() { return buffer; },
    get ended() { return ended; },
    get progress() {
      return {
        expected: declaredCount(engine.header),
        received: engine.recordLines,
        valid: engine.records.length,
        errors: engine.errors.length,
      };
    },
  };
  return reader;
}

/**
 * Consume un iterable (síncrono o asíncrono) de fragmentos y produce los registros
 * a medida que se completan. Devuelve el ReaderResult final como valor de retorno del generador.
 */
export async function* readRecords(
  chunks: AsyncIterable<string | Uint8Array> | Iterable<string | Uint8Array>,
  contract: Contract | ContractJSON,
  opts: ReaderOptions = {},
): AsyncGenerator<StreamRecord, ReaderResult, void> {
  const reader = createReader(contract, opts);
  for await (const chunk of chunks as AsyncIterable<string | Uint8Array>) {
    for (const rec of reader.push(chunk)) yield rec;
  }
  return reader.end();
}
