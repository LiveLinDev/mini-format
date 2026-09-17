/* codec.ts — capa léxica de .mini: escapes, división de campos y listas,
 * elementos entre comillas (SPEC §3, §4).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { E_ESCAPE, MiniError } from './errors.ts';

export const FIELD_SEP = '|';
export const MARKER = '*';
export const ESCAPE = '\\';
export const QUOTE = '"';

/** Token léxico: [carácter, ¿estaba escapado?]. */
export type Tok = readonly [string, boolean];

/** Elemento de lista ya separado: [texto, ¿lleva marcador *?]. */
export type ListElement = [string, boolean];

// Espacio en blanco con la misma definición que str.isspace() de la referencia.
const WS: ReadonlySet<string> = new Set([
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
].map(cp => String.fromCharCode(cp)));

/** ¿Es `ch` (un único carácter) espacio en blanco no significativo? */
export function isSpace(ch: string): boolean {
  return WS.has(ch);
}

/** ¿La cadena está vacía o contiene solo espacio en blanco? */
export function isBlank(s: string): boolean {
  for (const ch of s) if (!WS.has(ch)) return false;
  return true;
}

/** Recorta espacio en blanco en ambos extremos (definición de isSpace). */
export function trimSpace(s: string): string {
  let a = 0;
  let b = s.length;
  while (a < b && WS.has(s[a])) a++;
  while (b > a && WS.has(s[b - 1])) b--;
  return s.slice(a, b);
}

/** Convierte una línea física en tokens (carácter, escapado), resolviendo escapes. */
export function tokenize(line: string, sep: string, lineno: number, strict: boolean = true): Tok[] {
  const out: Tok[] = [];
  const n = line.length;
  let i = 0;
  while (i < n) {
    const ch = line[i];
    if (ch === ESCAPE) {
      if (i + 1 >= n) throw new MiniError(E_ESCAPE, lineno, 'dangling backslash at end of line');
      const nx = line[i + 1];
      if (nx === 'n') out.push(['\n', true]);
      else if (nx === FIELD_SEP || nx === MARKER || nx === ESCAPE || nx === sep || nx === ',' || nx === QUOTE) out.push([nx, true]);
      else if (strict) throw new MiniError(E_ESCAPE, lineno, `invalid escape sequence '\\${nx}'`);
      else { // tolerante: conserva ambos caracteres literalmente
        out.push([ESCAPE, true]);
        out.push([nx, true]);
      }
      i += 2;
    } else {
      out.push([ch, false]);
      i += 1;
    }
  }
  return out;
}

/** Divide tokens en el delimitador no escapado. */
export function splitOn(toks: readonly Tok[], delim: string): Tok[][] {
  const parts: Tok[][] = [[]];
  for (const t of toks) {
    if (t[0] === delim && !t[1]) parts.push([]);
    else parts[parts.length - 1].push(t);
  }
  return parts;
}

/** Elimina espacio en blanco no escapado al inicio y al final. */
export function stripToks(toks: readonly Tok[]): Tok[] {
  let a = 0;
  let b = toks.length;
  while (a < b && isSpace(toks[a][0]) && !toks[a][1]) a++;
  while (b > a && isSpace(toks[b - 1][0]) && !toks[b - 1][1]) b--;
  return toks.slice(a, b);
}

export function textOf(toks: readonly Tok[]): string {
  let s = '';
  for (const t of toks) s += t[0];
  return s;
}

/** Tokeniza una línea y la divide en campos por `|` no escapado (recortados). */
export function splitFields(line: string, sep: string, lineno: number, strict: boolean = true): Tok[][] {
  return splitOn(tokenize(line, sep, lineno, strict), FIELD_SEP).map(stripToks);
}

/**
 * Divide un campo de tipo lista en pares (texto, marcado).
 * Un campo vacío da una lista vacía. Admite elementos entre comillas estilo CSV
 * con `""` como comilla literal y el marcador tras (o justo antes de) la comilla de cierre.
 */
export function splitList(toks: readonly Tok[], sep: string, lineno: number = 0): ListElement[] {
  if (!toks.length) return [];
  const out: ListElement[] = [];
  const n = toks.length;
  const ws = (k: number): boolean => isSpace(toks[k][0]) && !toks[k][1];
  let i = 0;
  for (;;) {
    while (i < n && ws(i)) i++;
    if (i < n && toks[i][0] === QUOTE && !toks[i][1]) {
      i++;
      const buf: string[] = [];
      let closed = false;
      while (i < n) {
        const [ch, esc] = toks[i];
        if (ch === QUOTE && !esc) {
          if (i + 1 < n && toks[i + 1][0] === QUOTE && !toks[i + 1][1]) {
            buf.push(QUOTE);
            i += 2;
            continue;
          }
          closed = true;
          i++;
          break;
        }
        buf.push(ch);
        i++;
      }
      if (!closed) throw new MiniError(E_ESCAPE, lineno, 'unbalanced double quote in list element');
      let marked = false;
      // un marcador escrito justo antes de la comilla de cierre ("foo*") también se acepta
      if (buf.length && buf[buf.length - 1] === MARKER && !toks[i - 2][1]) {
        marked = true;
        buf.pop();
      }
      while (i < n && ws(i)) i++;
      if (i < n && toks[i][0] === MARKER && !toks[i][1]) {
        marked = true;
        i++;
      }
      while (i < n && ws(i)) i++;
      if (i < n && !(toks[i][0] === sep && !toks[i][1])) {
        throw new MiniError(E_ESCAPE, lineno, 'text after closing quote in list element');
      }
      out.push([buf.join(''), marked]);
    } else {
      let j = i;
      while (j < n && !(toks[j][0] === sep && !toks[j][1])) j++;
      let part = stripToks(toks.slice(i, j));
      let marked = false;
      if (part.length && part[part.length - 1][0] === MARKER && !part[part.length - 1][1]) {
        marked = true;
        part = stripToks(part.slice(0, -1));
      }
      out.push([textOf(part), marked]);
      i = j;
    }
    if (i >= n) break;
    i++; // consume el separador
    if (i >= n) { // separador final -> último elemento vacío
      out.push(['', false]);
      break;
    }
  }
  return out;
}

// ------------------------------------------------------------ codificación
/** Escapa un valor que vive directamente en un campo (no dentro de una lista). */
export function escapeScalar(value: string): string {
  return String(value)
    .split(ESCAPE).join(ESCAPE + ESCAPE)
    .split(FIELD_SEP).join(ESCAPE + FIELD_SEP)
    .replace(/\r\n|\r|\n/g, ESCAPE + 'n');
}

/**
 * Escapa un elemento de lista: como un escalar, más el separador, un `*` final y una `"` inicial.
 * La cadena vacía se escribe `""` (SPEC 1.1 §3.4): un elemento vacío sin comillas no se
 * distingue de una lista vacía cuando es el único elemento.
 */
export function escapeElement(value: string, sep: string): string {
  if (String(value) === '') return QUOTE + QUOTE;
  let s = escapeScalar(value).split(sep).join(ESCAPE + sep);
  if (s.endsWith(MARKER)) s = s.slice(0, -1) + ESCAPE + MARKER;
  if (s.startsWith(QUOTE)) s = ESCAPE + s;
  return s;
}
