/* mini.js — JavaScript port of the .mini reference implementation (spec 1.0).
 * Exposes a global `MINI` (browser) / module.exports (node) with:
 *   parse(text, contract, {strict}) -> {prefix, header, records, errors, canonical()}
 *   dumps(obj, contract)            -> string
 *   specBlock(contract, lang, example) -> string
 *   checkFork(child, parent)        -> [errors]
 *   normalizeContract(json)         -> contract object with defaults applied
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MINI = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const FIELD_SEP = '|', MARKER = '*', ESC = '\\';
  const SCALAR = new Set(['str', 'int', 'float', 'bool', 'enum']);

  class MiniError extends Error {
    constructor(code, line, message, field) { super(message); this.code = code; this.line = line; this.field = field || ''; }
    toString() { return `${this.code} ${this.line ? 'line ' + this.line : 'document'}${this.field ? ' [' + this.field + ']' : ''}: ${this.message}`; }
  }

  // ------------------------------------------------------------ contract
  function normalizeContract(d) {
    if (!d || !d.prefix) throw new MiniError('E20', 0, "contract requires 'prefix'");
    const c = {
      prefix: String(d.prefix), version: d.version || 1, name: d.name || '', description: d.description || '',
      parent: d.parent || null, list_separator: d.list_separator || ',', records_key: d.records_key || 'records',
      domain: d.domain || '', headerKeys: {}, core: [], extensions: [],
    };
    if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(c.prefix)) throw new MiniError('E20', 0, `bad prefix '${c.prefix}'`);
    const hdr = d.header || {};
    const required = new Set([...(hdr.required || ['n']), 'n']);
    const keys = Object.assign({}, hdr.keys || {});
    if (!keys.n) keys.n = { type: 'int', desc: 'number of records' };
    if (!keys.v) keys.v = { type: 'int', default: 1, desc: 'contract version' };
    for (const k of Object.keys(keys)) {
      const s = keys[k];
      c.headerKeys[k] = { name: k, type: s.type || 'str', required: required.has(k), item: s.item || 'str',
        items: (s.items || []).map(normField), values: s.values || null, default: s.default === undefined ? null : s.default, desc: s.desc || '' };
    }
    for (const k of required) if (!c.headerKeys[k]) c.headerKeys[k] = { name: k, type: 'str', required: true, item: 'str', items: [], values: null, default: null, desc: '' };
    c.core = (d.core || []).map(normField);
    c.extensions = (d.extensions || []).map(f => Object.assign(normField(f), { optional: true }));
    if (!c.core.length) throw new MiniError('E20', 0, 'contract requires at least one core field');
    const names = [...c.core, ...c.extensions].map(f => f.name);
    if (new Set(names).size !== names.length) throw new MiniError('E20', 0, 'duplicate field names');
    c.fields = [...c.core, ...c.extensions];
    c.arity = c.core.length;
    return c;
  }
  function normField(d) {
    if (!d.name || !d.type) throw new MiniError('E20', 0, 'field requires name and type');
    const f = { name: d.name, type: d.type, optional: !!d.optional, unique: !!d.unique, values: d.values || null,
      item: d.item || 'str', item_values: d.item_values || null, min: d.min === undefined ? null : d.min,
      max: d.max === undefined ? null : d.max, marker: d.marker || 'exactly_one', count_key: d.count_key || null,
      items: (d.items || []).map(normField), desc: d.desc || '', default: d.default === undefined ? null : d.default };
    if (f.type === 'mlist') { const j = d.json || {}; f.json_items = j.items || 'items'; f.json_selected = j.selected || (f.marker === 'exactly_one' ? 'correct' : 'selected'); }
    if (f.type === 'enum' && !f.values) throw new MiniError('E20', 0, `field ${f.name}: enum requires values`);
    if (f.type === 'tuple' && !f.items.length) throw new MiniError('E20', 0, `field ${f.name}: tuple requires items`);
    return f;
  }
  function fieldSignature(f) {
    let body;
    if (f.type === 'enum') body = 'enum{' + f.values.join('|') + '}';
    else if (f.type === 'list' || f.type === 'mlist') {
      const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
      body = `${f.type}<${it}>`;
      if (f.min !== null || f.max !== null) body += `[${f.min === null ? '' : f.min}..${f.max === null ? '' : f.max}]`;
      if (f.type === 'mlist') body += { exactly_one: '*1', at_least_one: '*1+', at_most_one: '*0..1', any: '*' }[f.marker];
    } else if (f.type === 'tuple') body = 'tuple(' + f.items.map(c => `${c.name}:${c.type}`).join(',') + ')';
    else { body = f.type; if (f.min !== null || f.max !== null) body += `[${f.min === null ? '' : f.min}..${f.max === null ? '' : f.max}]`; }
    return `${f.name}:${body}${f.optional ? '?' : ''}`;
  }
  function signature(c) {
    const core = c.core.map(fieldSignature).join(' | '); const ext = c.extensions.map(fieldSignature).join(' | ');
    return core + (ext ? ' || ' + ext : '');
  }

  // --------------------------------------------------------------- codec
  function tokenize(line, sep, lineno, strict) {
    const out = []; let i = 0; const n = line.length;
    while (i < n) {
      const ch = line[i];
      if (ch === ESC) {
        if (i + 1 >= n) throw new MiniError('E09', lineno, 'dangling backslash at end of line');
        const nx = line[i + 1];
        if (nx === 'n') out.push(['\n', true]);
        else if (nx === FIELD_SEP || nx === MARKER || nx === ESC || nx === sep || nx === ',' || nx === '"') out.push([nx, true]);
        else if (strict) throw new MiniError('E09', lineno, `invalid escape sequence '\\${nx}'`);
        else { out.push([ESC, true]); out.push([nx, true]); }
        i += 2;
      } else { out.push([ch, false]); i += 1; }
    }
    return out;
  }
  const splitOn = (toks, d) => { const parts = [[]]; for (const t of toks) { if (t[0] === d && !t[1]) parts.push([]); else parts[parts.length - 1].push(t); } return parts; };
  function stripToks(t) { let a = 0, b = t.length; while (a < b && /\s/.test(t[a][0]) && !t[a][1]) a++; while (b > a && /\s/.test(t[b - 1][0]) && !t[b - 1][1]) b--; return t.slice(a, b); }
  const textOf = t => t.map(x => x[0]).join('');
  const splitFields = (line, sep, lineno, strict) => splitOn(tokenize(line, sep, lineno, strict), FIELD_SEP).map(stripToks);
  function splitList(toks, sep, lineno) {
    if (!toks.length) return [];
    const out = []; let i = 0; const n = toks.length; const ws = k => /\s/.test(toks[k][0]) && !toks[k][1];
    for (;;) {
      while (i < n && ws(i)) i++;
      if (i < n && toks[i][0] === '"' && !toks[i][1]) {
        i++; const buf = []; let closed = false;
        while (i < n) { const [ch, esc] = toks[i]; if (ch === '"' && !esc) { if (i + 1 < n && toks[i + 1][0] === '"' && !toks[i + 1][1]) { buf.push('"'); i += 2; continue; } closed = true; i++; break; } buf.push(ch); i++; }
        if (!closed) throw new MiniError('E09', lineno || 0, 'unbalanced double quote in list element');
        let marked = false;
        if (buf.length && buf[buf.length - 1] === MARKER && !toks[i - 2][1]) { marked = true; buf.pop(); }
        while (i < n && ws(i)) i++;
        if (i < n && toks[i][0] === MARKER && !toks[i][1]) { marked = true; i++; }
        while (i < n && ws(i)) i++;
        if (i < n && !(toks[i][0] === sep && !toks[i][1])) throw new MiniError('E09', lineno || 0, 'text after closing quote in list element');
        out.push([buf.join(''), marked]);
      } else {
        let j = i; while (j < n && !(toks[j][0] === sep && !toks[j][1])) j++;
        let part = stripToks(toks.slice(i, j)); let marked = false;
        if (part.length && part[part.length - 1][0] === MARKER && !part[part.length - 1][1]) { marked = true; part = stripToks(part.slice(0, -1)); }
        out.push([textOf(part), marked]); i = j;
      }
      if (i >= n) break;
      i++; if (i >= n) { out.push(['', false]); break; }
    }
    return out;
  }
  const escapeScalar = v => String(v).split(ESC).join(ESC + ESC).split(FIELD_SEP).join(ESC + FIELD_SEP).replace(/\r\n|\r|\n/g, ESC + 'n');
  function escapeElement(v, sep) { let s = escapeScalar(v).split(sep).join(ESC + sep); if (s.endsWith(MARKER)) s = s.slice(0, -1) + ESC + MARKER; if (s.startsWith('"')) s = ESC + s; return s; }

  // -------------------------------------------------------------- values
  const INT_RE = /^[+-]?\d+$/, FLOAT_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
  function decodeScalar(text, f, lineno, name, asItem) {
    name = name || f.name;
    const t = asItem ? f.item : f.type; const values = asItem ? f.item_values : f.values;
    if (t === 'str') return text;
    if (t === 'int') { if (!INT_RE.test(text)) throw new MiniError('E06', lineno, `expected int, got '${text}'`, name); const v = parseInt(text, 10); range(v, f, lineno, name, asItem); return v; }
    if (t === 'float') { if (!FLOAT_RE.test(text)) throw new MiniError('E06', lineno, `expected number, got '${text}'`, name); const v = parseFloat(text); if (!isFinite(v)) throw new MiniError('E06', lineno, 'non-finite number', name); range(v, f, lineno, name, asItem); return v; }
    if (t === 'bool') { const l = text.trim().toLowerCase(); if (['true', '1', 'yes', 'y', 't'].includes(l)) return true; if (['false', '0', 'no', 'n', 'f'].includes(l)) return false; throw new MiniError('E06', lineno, `expected true/false, got '${text}'`, name); }
    if (t === 'enum') { if (!values || !values.includes(text)) throw new MiniError('E10', lineno, `'${text}' not in {${(values || []).join('|')}}`, name); return text; }
    throw new MiniError('E06', lineno, `unsupported type ${t}`, name);
  }
  function range(v, f, lineno, name, asItem) { if (asItem) return; if (f.min !== null && v < f.min) throw new MiniError('E13', lineno, `${v} < min ${f.min}`, name); if (f.max !== null && v > f.max) throw new MiniError('E13', lineno, `${v} > max ${f.max}`, name); }
  function formatNumber(x) { if (typeof x === 'boolean') return x ? 'true' : 'false'; if (Number.isInteger(x) && Math.abs(x) < 1e15) return String(x); return String(x); }
  function encodeScalar(v, f, asItem) { const t = asItem ? f.item : f.type; if (v === null || v === undefined) return ''; if (t === 'bool') return v ? 'true' : 'false'; if (t === 'int') return String(Math.trunc(Number(v))); if (t === 'float') return formatNumber(Number(v)); return String(v); }

  // -------------------------------------------------------------- parser
  function physicalLines(text) { if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); const out = []; text.split('\n').forEach((raw, i) => { const l = raw.replace(/\r$/, ''); if (l.trim() !== '') out.push([i + 1, l]); }); return out; }
  function parseHeader(line, lineno, c, strict) {
    const errs = []; const fields = splitFields(line, c.list_separator, lineno, strict);
    const prefix = fields.length ? textOf(fields[0]) : ''; const header = {};
    for (const toks of fields.slice(1)) {
      const txt = textOf(toks); if (!txt) continue;
      const eq = toks.findIndex(t => t[0] === '=' && !t[1]);
      if (eq < 0) { errs.push(new MiniError('E12', lineno, `header entry '${txt}' is not key=value`)); continue; }
      const key = textOf(stripToks(toks.slice(0, eq))); const vt = stripToks(toks.slice(eq + 1)); const hk = c.headerKeys[key];
      try {
        if (!hk) header[key] = textOf(vt);
        else if (hk.type === 'list') header[key] = splitList(vt, c.list_separator, lineno).map(([t]) => decodeScalar(t, hk, lineno, key, true));
        else if (hk.type === 'tuple') { const parts = splitList(vt, c.list_separator, lineno); if (parts.length !== hk.items.length) throw new MiniError('E07', lineno, `expected ${hk.items.length} components, got ${parts.length}`, key); const o = {}; hk.items.forEach((cmp, i) => { o[cmp.name] = parts[i][0] === '' ? null : decodeScalar(parts[i][0], cmp, lineno, key + '.' + cmp.name); }); header[key] = o; }
        else header[key] = decodeScalar(textOf(vt), hk, lineno, key);
      } catch (e) { if (e instanceof MiniError) errs.push(e); else throw e; }
    }
    for (const k of Object.keys(c.headerKeys)) { const hk = c.headerKeys[k]; if (!(k in header)) { if (hk.required && k !== 'n') errs.push(new MiniError('E12', lineno, `required header key '${k}' missing`)); else if (hk.default !== null) header[k] = hk.default; } }
    if (!('n' in header)) errs.push(new MiniError('E03', lineno, 'header must declare n=<record count>'));
    return { prefix, header, errs };
  }
  function decodeField(toks, f, lineno, sep, header) {
    if (SCALAR.has(f.type)) { const txt = textOf(toks); if (txt === '') { if (f.optional) return f.default; throw new MiniError('E06', lineno, 'required value is empty', f.name); } return decodeScalar(txt, f, lineno); }
    if (f.type === 'list' || f.type === 'mlist') {
      const elems = splitList(toks, sep, lineno);
      if (f.min !== null && elems.length < f.min) throw new MiniError('E07', lineno, `list has ${elems.length} elements, min ${f.min}`, f.name);
      if (f.max !== null && elems.length > f.max) throw new MiniError('E07', lineno, `list has ${elems.length} elements, max ${f.max}`, f.name);
      if (f.count_key && header && Number.isInteger(header[f.count_key]) && elems.length !== header[f.count_key]) throw new MiniError('E07', lineno, `list has ${elems.length} elements but header ${f.count_key}=${header[f.count_key]}`, f.name);
      const items = elems.map(([t]) => decodeScalar(t, f, lineno, f.name, true));
      if (f.type === 'list') { if (elems.some(e => e[1])) throw new MiniError('E08', lineno, 'marker * not allowed in a plain list', f.name); return items; }
      const marked = elems.map((e, i) => e[1] ? i : -1).filter(i => i >= 0);
      if (f.marker === 'exactly_one' && marked.length !== 1) throw new MiniError('E08', lineno, `exactly one element must carry *, found ${marked.length}`, f.name);
      if (f.marker === 'at_least_one' && marked.length < 1) throw new MiniError('E08', lineno, 'at least one element must carry *', f.name);
      if (f.marker === 'at_most_one' && marked.length > 1) throw new MiniError('E08', lineno, `at most one element may carry *, found ${marked.length}`, f.name);
      return { __mlist: true, items, selected: (f.marker === 'exactly_one' || f.marker === 'at_most_one') ? (marked.length ? marked[0] : null) : marked };
    }
    if (f.type === 'tuple') {
      const parts = splitList(toks, sep, lineno); if (!parts.length && f.optional) return null;
      if (parts.length !== f.items.length) throw new MiniError('E07', lineno, `tuple expects ${f.items.length} components, got ${parts.length}`, f.name);
      const o = {}; f.items.forEach((cmp, i) => { const [txt, m] = parts[i]; if (m) throw new MiniError('E08', lineno, 'marker * not allowed inside a tuple', f.name); if (txt === '') { if (cmp.optional) { o[cmp.name] = cmp.default; return; } throw new MiniError('E06', lineno, `tuple component '${cmp.name}' is empty`, f.name); } o[cmp.name] = decodeScalar(txt, cmp, lineno, f.name + '.' + cmp.name); });
      return o;
    }
    throw new MiniError('E06', lineno, `unsupported field type ${f.type}`, f.name);
  }
  function parse(text, c, opts) {
    const strict = !(opts && opts.strict === false);
    const lines = physicalLines(text); const errors = [];
    if (!lines.length) { const e = [new MiniError('E01', 0, 'empty document: header missing')]; if (strict) { const err = new Error('invalid'); err.errors = e; throw err; } return { prefix: '', header: {}, records: [], errors: e, contract: c }; }
    const [hl, htext] = lines[0]; const { prefix, header, errs } = parseHeader(htext, hl, c, strict); errors.push(...errs);
    if (prefix !== c.prefix) errors.push(new MiniError('E02', hl, `header prefix '${prefix}' does not match contract '${c.prefix}'`));
    const records = []; const uniques = {}; c.fields.forEach(f => { if (f.unique) uniques[f.name] = {}; });
    for (const [lineno, line] of lines.slice(1)) {
      let toks; try { toks = splitFields(line, c.list_separator, lineno, strict); } catch (e) { errors.push(e); continue; }
      const nf = toks.length;
      if (nf < c.arity) { errors.push(new MiniError('E05', lineno, `record has ${nf} fields, core requires ${c.arity}`)); continue; }
      if (nf > c.fields.length) { errors.push(new MiniError('E05', lineno, `record has ${nf} fields, contract allows at most ${c.fields.length}`)); continue; }
      const rec = {}; const recErrs = [];
      c.fields.forEach((f, i) => {
        if (i >= nf) { if (f.type === 'mlist') { rec[f.json_items] = null; rec[f.json_selected] = null; } else rec[f.name] = f.default; return; }
        try { const v = decodeField(toks[i], f, lineno, c.list_separator, header); if (v && v.__mlist) { rec[f.json_items] = v.items; rec[f.json_selected] = v.selected; } else rec[f.name] = v; }
        catch (e) { if (e instanceof MiniError) recErrs.push(e); else throw e; }
      });
      for (const name of Object.keys(uniques)) { const v = rec[name]; if (v !== null && v !== undefined) { if (v in uniques[name]) recErrs.push(new MiniError('E11', lineno, `duplicate value '${v}' (first seen line ${uniques[name][v]})`, name)); else uniques[name][v] = lineno; } }
      if (recErrs.length) { errors.push(...recErrs); continue; }
      records.push(rec);
    }
    const n = header.n; const total = lines.length - 1;
    if (Number.isInteger(n) && n !== total) errors.push(new MiniError('E04', 0, `header declares n=${n} but document has ${total} record lines`));
    const doc = { prefix, version: header.v || 1, header, records, errors, contract: c, lines: lines.length,
      canonical() { const o = { prefix: this.prefix, header: Object.assign({}, this.header) }; o[c.records_key] = this.records.map(r => Object.assign({}, r)); return o; } };
    if (strict && errors.length) { const err = new Error(errors.map(String).join('\n')); err.errors = errors; throw err; }
    return doc;
  }
  function detectPrefix(text) { const l = physicalLines(text); if (!l.length) return null; const t = splitFields(l[0][1], ',', 1, false); return t.length ? textOf(t[0]) : null; }

  // ---------------------------------------------------------- serializer
  function encList(values, f, sep, marked) { const ms = new Set(marked || []); return values.map((v, i) => { let s = escapeElement(encodeScalar(v, f, true), sep); if (ms.has(i)) s += MARKER; return s; }).join(sep); }
  function encodeField(value, f, sep, rec) {
    if (f.type === 'mlist' && rec) { const items = rec[f.json_items]; if (items === null || items === undefined) { if (f.optional) return ''; throw new MiniError('E06', 0, 'required marked list is null', f.name); } value = { items, selected: rec[f.json_selected] }; }
    if (value === null || value === undefined) { if (f.optional) return ''; throw new MiniError('E06', 0, 'required field is null', f.name); }
    if (SCALAR.has(f.type)) { if (f.type === 'enum' && !f.values.includes(String(value))) throw new MiniError('E06', 0, `'${value}' not in enum`, f.name); return escapeScalar(encodeScalar(value, f)); }
    if (f.type === 'list') { if (!Array.isArray(value)) throw new MiniError('E06', 0, 'list expected', f.name); return encList(value, f, sep); }
    if (f.type === 'mlist') {
      const items = value.items || []; const sel = value.selected; let marked = sel === null || sel === undefined ? [] : (Array.isArray(sel) ? sel.slice().sort((a, b) => a - b) : [sel]);
      if (f.marker === 'exactly_one' && marked.length !== 1) throw new MiniError('E08', 0, 'exactly one selected element required', f.name);
      if (f.marker === 'at_least_one' && !marked.length) throw new MiniError('E08', 0, 'at least one selected element required', f.name);
      if (f.marker === 'at_most_one' && marked.length > 1) throw new MiniError('E08', 0, 'at most one selected element allowed', f.name);
      for (const m of marked) if (!(m >= 0 && m < items.length)) throw new MiniError('E08', 0, `selected index ${m} out of range`, f.name);
      return encList(items, f, sep, marked);
    }
    if (f.type === 'tuple') { if (typeof value !== 'object') throw new MiniError('E06', 0, 'tuple expects an object', f.name); return f.items.map(cmp => { const v = value[cmp.name]; if (v === null || v === undefined) { if (cmp.optional) return ''; throw new MiniError('E07', 0, `tuple component '${cmp.name}' missing`, f.name); } return escapeElement(encodeScalar(v, cmp), sep); }).join(sep); }
    throw new MiniError('E06', 0, `unsupported type ${f.type}`, f.name);
  }
  function encodeHeader(header, c, n) {
    const sep = c.list_separator; const parts = [c.prefix]; const hdr = Object.assign({}, header, { n });
    const ordered = ['n', ...Object.keys(c.headerKeys).filter(k => k in hdr && k !== 'n'), ...Object.keys(hdr).filter(k => !(k in c.headerKeys))];
    for (const k of ordered) {
      const v = hdr[k]; if (v === null || v === undefined) continue; const hk = c.headerKeys[k];
      if (k === 'v' && Number(v) === 1 && hk && hk.default === 1) continue;
      let txt;
      if (!hk) txt = escapeScalar(String(v));
      else if (hk.type === 'list') txt = encList(v, hk, sep);
      else if (hk.type === 'tuple') txt = hk.items.map(cmp => (v[cmp.name] === null || v[cmp.name] === undefined) ? '' : escapeElement(encodeScalar(v[cmp.name], cmp), sep)).join(sep);
      else txt = escapeScalar(encodeScalar(v, hk));
      parts.push(`${k}=${txt}`);
    }
    return parts.join(FIELD_SEP);
  }
  function encodeRecord(rec, c) {
    const sep = c.list_separator; const cells = c.core.map(f => encodeField(rec[f.name], f, sep, rec));
    const ext = c.extensions.map(f => encodeField(rec[f.name], f, sep, rec)); while (ext.length && ext[ext.length - 1] === '') ext.pop();
    return [...cells, ...ext].join(FIELD_SEP);
  }
  function dumps(obj, c) { const records = obj[c.records_key] || obj.records || []; const lines = [encodeHeader(obj.header || {}, c, records.length)]; for (const r of records) lines.push(encodeRecord(r, c)); return lines.join('\n'); }

  // ------------------------------------------------------------- forking
  function checkFork(child, parent) {
    const errs = []; const pf = parent.fields, cf = child.fields;
    if (cf.length < pf.length) { errs.push(new MiniError('E21', 0, `fork '${child.prefix}' drops fields of parent '${parent.prefix}'`)); return errs; }
    pf.forEach((p, i) => { const k = cf[i]; if (p.name !== k.name || p.type !== k.type) errs.push(new MiniError('E21', 0, `fork '${child.prefix}' changes inherited field #${i + 1}: parent ${fieldSignature(p)} != child ${fieldSignature(k)}`)); if ((p.type === 'list' || p.type === 'mlist') && p.item !== k.item) errs.push(new MiniError('E21', 0, `fork changes item type of '${p.name}'`)); if (p.type === 'tuple' && p.items.map(x => x.name).join() !== k.items.map(x => x.name).join()) errs.push(new MiniError('E21', 0, `fork changes tuple layout of '${p.name}'`)); });
    if (child.list_separator !== parent.list_separator) errs.push(new MiniError('E21', 0, 'fork changes list_separator of its parent'));
    for (const k of Object.keys(parent.headerKeys)) if (parent.headerKeys[k].required && !(child.headerKeys[k] && child.headerKeys[k].required)) errs.push(new MiniError('E21', 0, `fork drops required header key '${k}'`));
    return errs;
  }

  // ------------------------------------------------------------- prompt
  function fieldDoc(f, sep, lang) {
    const es = lang === 'es'; const opt = f.optional ? (es ? ' (opcional)' : ' (optional)') : '';
    if (f.type === 'enum') return `${f.name}: ${es ? 'uno de' : 'one of'} {${f.values.join('|')}}${opt}`;
    if (f.type === 'list' || f.type === 'mlist') {
      const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
      let rng = ''; if (f.min !== null || f.max !== null) rng = es ? `, entre ${f.min || 0} y ${f.max === null ? '∞' : f.max} elementos` : `, ${f.min || 0} to ${f.max === null ? '∞' : f.max} elements`;
      let base = es ? `${f.name}: lista de ${it} separada por '${sep}'${rng}` : `${f.name}: '${sep}'-separated list of ${it}${rng}`;
      if (f.type === 'mlist') { const rule = { exactly_one: es ? 'exactamente un' : 'exactly one', at_least_one: es ? 'al menos un' : 'at least one', at_most_one: es ? 'como máximo un' : 'at most one', any: es ? 'cero o más' : 'zero or more' }[f.marker]; base += es ? `; ${rule} elemento lleva el sufijo * (seleccionado)` : `; ${rule} element carries the suffix * (selected)`; }
      return base + opt;
    }
    if (f.type === 'tuple') { const comps = f.items.map(c => `${c.name}:${c.type}`).join(sep); return (es ? `${f.name}: tupla fija '${comps}' separada por '${sep}'` : `${f.name}: fixed tuple '${comps}' separated by '${sep}'`) + opt; }
    let rng = ''; if (f.min !== null || f.max !== null) rng = ` [${f.min === null ? '' : f.min}..${f.max === null ? '' : f.max}]`;
    return `${f.name}: ${f.type}${rng}${opt}${f.desc ? ' — ' + f.desc : ''}`;
  }
  function specBlock(c, lang, example) {
    const es = lang === 'es'; const sep = c.list_separator;
    const hk = Object.keys(c.headerKeys).filter(k => k !== 'v');
    const hdrDesc = hk.map(k => `${k}=<${c.headerKeys[k].type}>${c.headerKeys[k].required ? '' : '?'}`).join(', ');
    const core = c.core.map((f, i) => `  ${i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
    const ext = c.extensions.map((f, i) => `  ${c.core.length + i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
    const L = [];
    if (es) {
      L.push(`FORMATO .mini — familia '${c.prefix}' v${c.version}${c.name ? ' (' + c.name + ')' : ''}`); if (c.description) L.push(c.description); L.push('Reglas:');
      L.push(`- Texto plano UTF-8. La PRIMERA línea es la cabecera: '${c.prefix}|${hdrDesc}'. n es obligatorio y debe ser igual al número exacto de líneas de registro.`);
      L.push('- Después de la cabecera, UNA línea por registro; nada más (sin comentarios, sin bloques de código, sin líneas en blanco intermedias).');
      L.push(`- Cada registro tiene los campos en ESTE orden, separados por '|' (el orden es la semántica; no se escriben nombres de campo):`); L.push(core);
      if (ext) { L.push('  Campos de extensión (opcionales, solo al final, pueden omitirse):'); L.push(ext); }
      L.push(`- Si un elemento de lista contiene el separador '${sep}', enciérralo entre comillas dobles al estilo CSV ("impacto${sep} justicia y evidencia"; el marcador * va después de la comilla de cierre) o escapa el separador como '\\${sep}'. Un asterisco final literal se escribe '\\*'.`);
      L.push(`- Escapes válidos en cualquier valor: '\\|' para una barra vertical literal, '\\\\' para una barra invertida, '\\n' para un salto de línea.`);
      L.push('- Valores numéricos sin comillas; booleanos true/false. Los campos escalares no llevan comillas.'); L.push('- Un campo vacío significa nulo (solo permitido en campos opcionales).');
      L.push(`- Registro: ${c.arity} campos núcleo${c.extensions.length ? ' + hasta ' + c.extensions.length + ' de extensión' : ''}.`);
    } else {
      L.push(`.mini FORMAT — family '${c.prefix}' v${c.version}${c.name ? ' (' + c.name + ')' : ''}`); if (c.description) L.push(c.description); L.push('Rules:');
      L.push(`- Plain UTF-8 text. The FIRST line is the header: '${c.prefix}|${hdrDesc}'. n is mandatory and must equal the exact number of record lines.`);
      L.push('- After the header, ONE line per record and nothing else (no comments, no code fences, no blank lines in between).');
      L.push(`- Each record has these fields in THIS order, separated by '|' (position is the semantics; field names are never written):`); L.push(core);
      if (ext) { L.push('  Extension fields (optional, tail only, may be omitted):'); L.push(ext); }
      L.push(`- If a list element contains the separator '${sep}', enclose the element in double quotes CSV-style ("impact${sep} justice and evidence"; the * marker goes after the closing quote) or escape the separator as '\\${sep}'. A literal trailing asterisk is written '\\*'.`);
      L.push(`- Escapes valid in any value: '\\|' for a literal vertical bar, '\\\\' for a backslash, '\\n' for a line break.`);
      L.push('- Numbers unquoted; booleans true/false. Scalar fields are never quoted.'); L.push('- An empty field means null (allowed only for optional fields).');
      L.push(`- Record: ${c.arity} core fields${c.extensions.length ? ' + up to ' + c.extensions.length + ' extension fields' : ''}.`);
    }
    if (example) { L.push(es ? 'Ejemplo válido:' : 'Valid example:'); L.push(example); }
    return L.join('\n');
  }

  return { MiniError, normalizeContract, fieldSignature, signature, parse, dumps, detectPrefix, checkFork, specBlock, escapeScalar, escapeElement, SPEC_VERSION: '1.0' };
});
