/* registry.ts — registro de familias: contratos desde objetos o desde forks/<prefix>/contract.json.
 * Verifica mecánicamente los invariantes de fork (prefijos únicos, carpeta = prefijo, I2–I4).
 * La carga desde disco usa node:fs mediante process.getBuiltinModule, de modo que el
 * módulo sigue siendo importable en navegadores (solo `Registry.load` requiere Node).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { checkFork, normalizeContract, signature } from './contract.ts';
import type { Contract, ContractJSON } from './contract.ts';
import { E_FORK, MiniError } from './errors.ts';

/** Entrada del índice del registro (forks/registry.json). */
export interface RegistryIndexEntry {
  prefix: string;
  version: number;
  name: string;
  parent: string | null;
  domain: string;
  arity: number;
  extensions: number;
  signature: string;
}

interface NodeFs {
  readdirSync(p: string, o: { withFileTypes: true }): { name: string; isDirectory(): boolean }[];
  readFileSync(p: string, enc: 'utf8'): string;
  existsSync(p: string): boolean;
}
interface NodePath {
  join(...parts: string[]): string;
  resolve(...parts: string[]): string;
}
interface NodeUrl {
  fileURLToPath(u: string | URL): string;
}

function nodeModule<T>(name: string): T {
  const proc = (globalThis as { process?: { getBuiltinModule?: (n: string) => unknown } }).process;
  const mod = proc && typeof proc.getBuiltinModule === 'function' ? proc.getBuiltinModule(name) : undefined;
  if (!mod) throw new Error(`${name} is not available: loading contracts from disk requires Node.js >= 22.3`);
  return mod as T;
}

/** Carpeta de ejemplos del checkout; no se incluye en el paquete publicado. */
export function defaultForksDir(): string {
  const url = nodeModule<NodeUrl>('node:url');
  const fs = nodeModule<NodeFs>('node:fs');
  const packaged = url.fileURLToPath(new URL('../forks/', import.meta.url));
  if (fs.existsSync(packaged)) return packaged;
  return url.fileURLToPath(new URL('../../forks/', import.meta.url));
}

function stripBom(s: string): string {
  return s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

/** Lee y normaliza un contract.json desde disco. */
export function loadContract(file: string): Contract {
  const fs = nodeModule<NodeFs>('node:fs');
  const text = stripBom(fs.readFileSync(file, 'utf8'));
  return normalizeContract(JSON.parse(text) as ContractJSON);
}

export class Registry {
  readonly contracts: Map<string, Contract> = new Map();
  /** Carpeta de origen de cada contrato cargado desde disco. */
  readonly paths: Map<string, string> = new Map();

  constructor(contracts?: Iterable<Contract | ContractJSON>) {
    if (contracts) for (const c of contracts) this.add(c);
  }

  /** Crea un registro a partir de objetos contrato (JSON o normalizados). */
  static from(contracts: Iterable<Contract | ContractJSON>): Registry {
    return new Registry(contracts);
  }

  /** Descubre `<dir>/*\/contract.json` (orden alfabético de carpeta). */
  static load(forksDir?: string): Registry {
    const fs = nodeModule<NodeFs>('node:fs');
    const path = nodeModule<NodePath>('node:path');
    const dir = path.resolve(forksDir || defaultForksDir());
    const reg = new Registry();
    if (!forksDir && !fs.existsSync(dir)) return reg;
    const entries = fs.readdirSync(dir, { withFileTypes: true })
      .filter(e => e.isDirectory())
      .map(e => e.name)
      .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    for (const name of entries) {
      const cpath = path.join(dir, name, 'contract.json');
      if (!fs.existsSync(cpath)) continue;
      const c = loadContract(cpath);
      if (reg.contracts.has(c.prefix)) {
        throw new MiniError(E_FORK, 0, `prefix '${c.prefix}' is registered twice (${cpath})`);
      }
      if (name !== c.prefix) {
        throw new MiniError(E_FORK, 0, `folder '${name}' must be named after prefix '${c.prefix}'`);
      }
      reg.contracts.set(c.prefix, c);
      reg.paths.set(c.prefix, path.join(dir, name));
    }
    return reg;
  }

  add(contract: Contract | ContractJSON): Contract {
    const c = normalizeContract(contract);
    if (this.contracts.has(c.prefix)) throw new MiniError(E_FORK, 0, `prefix '${c.prefix}' already registered`);
    this.contracts.set(c.prefix, c);
    return c;
  }

  get(prefix: string): Contract {
    const c = this.contracts.get(prefix);
    if (!c) throw new MiniError(E_FORK, 0, `unknown prefix '${prefix}'`);
    return c;
  }

  has(prefix: string): boolean {
    return this.contracts.has(prefix);
  }

  get size(): number {
    return this.contracts.size;
  }

  [Symbol.iterator](): IterableIterator<Contract> {
    return this.contracts.values();
  }

  /** Verifica cada fork contra su padre; devuelve la lista de violaciones. */
  check(): MiniError[] {
    const errs: MiniError[] = [];
    for (const c of this.contracts.values()) {
      if (!c.parent) continue;
      const parent = this.contracts.get(c.parent);
      if (!parent) {
        errs.push(new MiniError(E_FORK, 0, `fork '${c.prefix}' declares unknown parent '${c.parent}'`));
        continue;
      }
      errs.push(...checkFork(c, parent));
    }
    return errs;
  }

  /** Cadena de ancestros: [prefix, padre, abuelo, ...]. */
  lineage(prefix: string): string[] {
    const out = [prefix];
    let c = this.get(prefix);
    const seen = new Set([prefix]);
    while (c.parent) {
      if (seen.has(c.parent)) throw new MiniError(E_FORK, 0, `cyclic lineage at '${c.parent}'`);
      seen.add(c.parent);
      out.push(c.parent);
      c = this.get(c.parent);
    }
    return out;
  }

  toIndex(): RegistryIndexEntry[] {
    return [...this.contracts.values()].map(c => ({
      prefix: c.prefix, version: c.version, name: c.name, parent: c.parent, domain: c.domain,
      arity: c.arity, extensions: c.extensions.length, signature: signature(c),
    }));
  }
}
