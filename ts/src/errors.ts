/* errors.ts — modelo de errores de .mini (SPEC §8).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */

/** Códigos estables de error (SPEC §8). */
export const E_NO_HEADER = 'E01';
export const E_UNKNOWN_PREFIX = 'E02';
export const E_NO_COUNT = 'E03';
export const E_COUNT_MISMATCH = 'E04';
export const E_ARITY = 'E05';
export const E_TYPE = 'E06';
export const E_LIST_ARITY = 'E07';
export const E_MARKER = 'E08';
export const E_ESCAPE = 'E09';
export const E_ENUM = 'E10';
export const E_UNIQUE = 'E11';
export const E_HEADER_KEY = 'E12';
export const E_RANGE = 'E13';
export const E_CONTRACT = 'E20';
export const E_FORK = 'E21';

export type ErrorCode =
  | 'E01' | 'E02' | 'E03' | 'E04' | 'E05' | 'E06' | 'E07' | 'E08' | 'E09'
  | 'E10' | 'E11' | 'E12' | 'E13' | 'E20' | 'E21';

/** Un error de validación: código, línea física 1-based (0 = documento) y campo. */
export class MiniError extends Error {
  readonly code: ErrorCode;
  readonly line: number;
  readonly field: string;

  constructor(code: ErrorCode, line: number, message: string, field?: string) {
    super(message);
    this.name = 'MiniError';
    this.code = code;
    this.line = line;
    this.field = field || '';
  }

  override toString(): string {
    const where = this.line ? `line ${this.line}` : 'document';
    const fld = this.field ? ` [${this.field}]` : '';
    return `${this.code} ${where}${fld}: ${this.message}`;
  }

  toJSON(): { code: ErrorCode; line: number; field: string; message: string } {
    return { code: this.code, line: this.line, field: this.field, message: this.message };
  }
}

/** Lanzado por el análisis estricto cuando se recogió uno o más errores. */
export class MiniValidationError extends Error {
  readonly errors: MiniError[];

  constructor(errors: MiniError[]) {
    super(errors.map(String).join('\n'));
    this.name = 'MiniValidationError';
    this.errors = errors;
  }

  get codes(): ErrorCode[] {
    return this.errors.map(e => e.code);
  }
}
