/* helpers.ts — utilidades compartidas por las pruebas de @mini-format/core.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Registry } from '../src/index.ts';
import type { Contract } from '../src/index.ts';

/** Raíz del repositorio (ts/test -> ../../). */
export const ROOT = fileURLToPath(new URL('../../', import.meta.url));
export const FORKS = path.join(ROOT, 'forks');
export const REG = Registry.load(FORKS);

export const LF = String.fromCharCode(10);
export const CR = String.fromCharCode(13);
export const BS = String.fromCharCode(92);
export const BOM = String.fromCharCode(0xfeff);

export function read(file: string): string {
  return fs.readFileSync(file, 'utf8');
}

/** Normaliza CRLF -> LF (el checkout en Windows puede convertir finales de línea). */
export function lf(text: string): string {
  return text.split(CR + LF).join(LF);
}

export interface ForkFixtures {
  contract: Contract;
  dir: string;
  valid: string;
  canonical: Record<string, unknown>;
  escaping: string | null;
  escapingCanonical: Record<string, unknown> | null;
  bad: { name: string; text: string }[];
}

export function fixtures(c: Contract): ForkFixtures {
  const dir = path.join(REG.paths.get(c.prefix) as string, 'fixtures');
  const escPath = path.join(dir, 'escaping.mini');
  const hasEsc = fs.existsSync(escPath);
  return {
    contract: c,
    dir,
    valid: read(path.join(dir, 'valid.mini')),
    canonical: JSON.parse(read(path.join(dir, 'canonical.json'))),
    escaping: hasEsc ? read(escPath) : null,
    escapingCanonical: hasEsc ? JSON.parse(read(path.join(dir, 'escaping.json'))) : null,
    bad: fs.readdirSync(dir)
      .filter(f => f.startsWith('bad_') && f.endsWith('.mini'))
      .sort()
      .map(name => ({ name, text: read(path.join(dir, name)) })),
  };
}

export const ALL = [...REG].map(fixtures);

/** PRNG determinista (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randInt(r: () => number, lo: number, hi: number): number {
  return lo + Math.floor(r() * (hi - lo + 1));
}

export function pick<T>(r: () => number, xs: readonly T[]): T {
  return xs[Math.floor(r() * xs.length)];
}

/** Parte `text` en fragmentos aleatorios de 1 a 7 caracteres. */
export function chunk(text: string, r: () => number, lo: number = 1, hi: number = 7): string[] {
  const out: string[] = [];
  let i = 0;
  while (i < text.length) {
    const k = randInt(r, lo, hi);
    out.push(text.slice(i, i + k));
    i += k;
  }
  return out;
}

/** Alfabeto con todos los caracteres estructurales y algunos no ASCII. */
export const ALPHABET: string[] = [
  ...'abcXYZ019 -.=;:'.split(''), '|', ',', '*', '"', BS, LF, String.fromCharCode(9),
  String.fromCharCode(0xe1), String.fromCharCode(0xf1), String.fromCharCode(0xbf),
];

/** Mutaciones aleatorias de un documento (borrar, insertar, cortar, duplicar línea). */
export function mutate(text: string, r: () => number): string {
  const inserts = [...ALPHABET, BS + 'n', BS + ',', BS + '|', BS + BS, BS + '*', BS + '"', BS + 'x', '""', ' , ', '*,', CR];
  let s = text;
  const ops = randInt(r, 1, 3);
  for (let k = 0; k < ops; k++) {
    const op = r();
    const i = randInt(r, 0, Math.max(0, s.length - 1));
    if (op < 0.35 && s) s = s.slice(0, i) + s.slice(i + 1);
    else if (op < 0.75) s = s.slice(0, i) + pick(r, inserts) + s.slice(i);
    else if (op < 0.9) s = s.slice(0, i);
    else {
      const lines = s.split(LF);
      const j = randInt(r, 0, lines.length - 1);
      lines.splice(j, 0, lines[j]);
      s = lines.join(LF);
    }
  }
  return s;
}

/** Forma comparable de una lista de errores. */
export function errKeys(errors: readonly { code: string; line: number; field: string; message: string }[]): string[] {
  return errors.map(e => `${e.code}@${e.line}[${e.field}] ${e.message}`);
}
