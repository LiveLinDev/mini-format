/* prompt.ts — bloque de especificación transferible derivado del contrato (SPEC §10).
 * Es el texto que se pega en un prompt de sistema para que un modelo produzca
 * documentos válidos de la familia.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { normalizeContract } from './contract.ts';
import type { Contract, ContractJSON, Field } from './contract.ts';

export type Lang = 'en' | 'es';

function fieldDoc(f: Field, sep: string, lang: string): string {
  const es = lang === 'es';
  const opt = f.optional ? (es ? ' (opcional)' : ' (optional)') : '';
  if (f.type === 'enum') {
    return `${f.name}: ${es ? 'uno de ' : 'one of '}{${(f.values || []).join('|')}}${opt}`;
  }
  if (f.type === 'list' || f.type === 'mlist') {
    const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
    let rng = '';
    if (f.min !== null || f.max !== null) {
      const lo = Math.trunc(f.min || 0);
      const hi = f.max ? String(Math.trunc(f.max)) : '∞';
      rng = es ? `, entre ${lo} y ${hi} elementos` : `, ${lo} to ${hi} elements`;
    }
    let base = es ? `${f.name}: lista de ${it} separada por '${sep}'${rng}` : `${f.name}: '${sep}'-separated list of ${it}${rng}`;
    if (f.type === 'mlist') {
      const rules = {
        exactly_one: es ? 'exactamente un' : 'exactly one',
        at_least_one: es ? 'al menos un' : 'at least one',
        at_most_one: es ? 'como máximo un' : 'at most one',
        any: es ? 'cero o más' : 'zero or more',
      } as const;
      const rule = rules[f.marker];
      base += es ? `; ${rule} elemento lleva el sufijo * (seleccionado)` : `; ${rule} element carries the suffix * (selected)`;
    }
    return base + opt;
  }
  if (f.type === 'tuple') {
    const comps = f.items.map(c => `${c.name}:${c.type}`).join(sep);
    return (es ? `${f.name}: tupla fija '${comps}' separada por '${sep}'` : `${f.name}: fixed tuple '${comps}' separated by '${sep}'`) + opt;
  }
  let rng = '';
  if (f.min !== null || f.max !== null) rng = ` [${f.min === null ? '' : f.min}..${f.max === null ? '' : f.max}]`;
  return `${f.name}: ${f.type}${rng}${formatHint(f.type, es)}${opt}${f.desc ? ' — ' + f.desc : ''}`;
}

/** Forma textual de los tipos cuya regla léxica no es evidente (SPEC 1.1 §6). */
function formatHint(t: string, es: boolean): string {
  if (t === 'date') return es ? ' (AAAA-MM-DD)' : ' (YYYY-MM-DD)';
  if (t === 'decimal') return es ? ' (decimal exacto sin exponente, p. ej. 12.50)' : ' (exact decimal without exponent, e.g. 12.50)';
  return '';
}

/** Bloque de especificación para un prompt de sistema (`lang`: 'en' o 'es'). */
export function specBlock(contract: Contract | ContractJSON, lang: Lang | string = 'en', example?: string): string {
  const c = normalizeContract(contract);
  const es = lang === 'es';
  const sep = c.list_separator;
  const hk = Object.keys(c.headerKeys).filter(k => k !== 'v');
  const hdrDesc = hk.map(k => `${k}=<${c.headerKeys[k].type}>${c.headerKeys[k].required ? '' : '?'}`).join(', ');
  const core = c.core.map((f, i) => `  ${i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
  const ext = c.extensions.map((f, i) => `  ${c.core.length + i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
  const L: string[] = [];
  if (es) {
    L.push(`FORMATO .mini — familia '${c.prefix}' v${c.version}${c.name ? ' (' + c.name + ')' : ''}`);
    if (c.description) L.push(c.description);
    L.push('Reglas:');
    L.push(`- Texto plano UTF-8. La PRIMERA línea es la cabecera: '${c.prefix}|${hdrDesc}'. n es obligatorio y debe ser igual al número exacto de líneas de registro.`);
    L.push('- Después de la cabecera, UNA línea por registro; nada más (sin comentarios, sin bloques de código, sin líneas en blanco intermedias).');
    L.push("- Cada registro tiene los campos en ESTE orden, separados por '|' (el orden es la semántica; no se escriben nombres de campo):");
    L.push(core);
    if (ext) {
      L.push('  Campos de extensión (opcionales, solo al final, pueden omitirse):');
      L.push(ext);
    }
    L.push(`- Si un elemento de lista contiene el separador '${sep}', enciérralo entre comillas dobles al estilo CSV ("impacto${sep} justicia y evidencia"; el marcador * va después de la comilla de cierre) o escapa el separador como '\\${sep}'. Un asterisco final literal se escribe '\\*'.`);
    L.push("- Escapes válidos en cualquier valor: '\\|' para una barra vertical literal, '\\\\' para una barra invertida, '\\n' para un salto de línea.");
    L.push('- Valores numéricos sin comillas; booleanos true/false. Los campos escalares no llevan comillas.');
    L.push('- Un campo vacío significa nulo (solo permitido en campos opcionales).');
    L.push(`- Registro: ${c.arity} campos núcleo${c.extensions.length ? ' + hasta ' + c.extensions.length + ' de extensión' : ''}.`);
  } else {
    L.push(`.mini FORMAT — family '${c.prefix}' v${c.version}${c.name ? ' (' + c.name + ')' : ''}`);
    if (c.description) L.push(c.description);
    L.push('Rules:');
    L.push(`- Plain UTF-8 text. The FIRST line is the header: '${c.prefix}|${hdrDesc}'. n is mandatory and must equal the exact number of record lines.`);
    L.push('- After the header, ONE line per record and nothing else (no comments, no code fences, no blank lines in between).');
    L.push("- Each record has these fields in THIS order, separated by '|' (position is the semantics; field names are never written):");
    L.push(core);
    if (ext) {
      L.push('  Extension fields (optional, tail only, may be omitted):');
      L.push(ext);
    }
    L.push(`- If a list element contains the separator '${sep}', enclose the element in double quotes CSV-style ("impact${sep} justice and evidence"; the * marker goes after the closing quote) or escape the separator as '\\${sep}'. A literal trailing asterisk is written '\\*'.`);
    L.push("- Escapes valid in any value: '\\|' for a literal vertical bar, '\\\\' for a backslash, '\\n' for a line break.");
    L.push('- Numbers unquoted; booleans true/false. Scalar fields are never quoted.');
    L.push('- An empty field means null (allowed only for optional fields).');
    L.push(`- Record: ${c.arity} core fields${c.extensions.length ? ' + up to ' + c.extensions.length + ' extension fields' : ''}.`);
  }
  if (example) {
    L.push(es ? 'Ejemplo válido:' : 'Valid example:');
    L.push(example);
  }
  return L.join('\n');
}
