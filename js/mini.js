/* mini.js — motor JavaScript de .mini para el navegador (playground) y CommonJS.
 * ARCHIVO GENERADO por tools/build_js.mjs desde ts/src (@mini-format/core 1.1.0, SPEC 1.1).
 * No se edita a mano: se modifica ts/src y se ejecuta `node --no-warnings tools/build_js.mjs`.
 * tests/test_js_port.mjs comprueba que está al día y ejecuta toda la suite de conformidad contra él.
 * Expone el global `MINI` (navegador) o `module.exports` (Node) con la API de la biblioteca:
 *   parse(text, contract, {strict}) -> Document {prefix, header, records, errors, canonical()}
 *   dumps(obj, contract), specBlock(contract, lang, example), checkFork(child, parent),
 *   normalizeContract(json), signature(contract), createReader(contract, options), ...
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MINI = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const __m = {};

  // ---------------------------------------------------------------- errors.ts
  __m["errors"] = (function () {
    /** Códigos estables de error (SPEC §8). */
    const E_NO_HEADER = 'E01';
    const E_UNKNOWN_PREFIX = 'E02';
    const E_NO_COUNT = 'E03';
    const E_COUNT_MISMATCH = 'E04';
    const E_ARITY = 'E05';
    const E_TYPE = 'E06';
    const E_LIST_ARITY = 'E07';
    const E_MARKER = 'E08';
    const E_ESCAPE = 'E09';
    const E_ENUM = 'E10';
    const E_UNIQUE = 'E11';
    const E_HEADER_KEY = 'E12';
    const E_RANGE = 'E13';
    const E_CONTRACT = 'E20';
    const E_FORK = 'E21';

                           
                                                                             
                                                      

    /** Un error de validación: código, línea física 1-based (0 = documento) y campo. */
    class MiniError extends Error {
               code           ;
               line        ;
               field        ;

      constructor(code           , line        , message        , field         ) {
        super(message);
        this.name = 'MiniError';
        this.code = code;
        this.line = line;
        this.field = field || '';
      }

               toString()         {
        const where = this.line ? `line ${this.line}` : 'document';
        const fld = this.field ? ` [${this.field}]` : '';
        return `${this.code} ${where}${fld}: ${this.message}`;
      }

      toJSON()                                                                    {
        return { code: this.code, line: this.line, field: this.field, message: this.message };
      }
    }

    /** Lanzado por el análisis estricto cuando se recogió uno o más errores. */
    class MiniValidationError extends Error {
               errors             ;

      constructor(errors             ) {
        super(errors.map(String).join('\n'));
        this.name = 'MiniValidationError';
        this.errors = errors;
      }

      get codes()              {
        return this.errors.map(e => e.code);
      }
    }
    return { E_NO_HEADER, E_UNKNOWN_PREFIX, E_NO_COUNT, E_COUNT_MISMATCH, E_ARITY, E_TYPE, E_LIST_ARITY, E_MARKER, E_ESCAPE, E_ENUM, E_UNIQUE, E_HEADER_KEY, E_RANGE, E_CONTRACT, E_FORK, MiniError, MiniValidationError };
  })();

  // ---------------------------------------------------------------- values.ts
  __m["values"] = (function () {
    const { E_ENUM, E_RANGE, E_TYPE, MiniError } = __m["errors"];

                                                   

    // SPEC 1.1 §6: solo dígitos ASCII, sin '+', y los flotantes llevan dígitos a ambos lados
    // del punto ('.5' y '1.' son E06). Se admiten ceros a la izquierda.
    const INT_RE = /^-?[0-9]+$/;
    const FLOAT_RE = /^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$/;
    const DECIMAL_RE = /^(-?)([0-9]+)(?:\.([0-9]+))?$/;
    const DATE_RE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;
    const RANGED_TYPES                      = new Set(['int', 'float', 'decimal', 'date']);

    /** `AAAA-MM-DD` que nombra un día existente del calendario gregoriano proléptico (0001–9999). */
    function validDate(text        )          {
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
    function normalizeDecimal(text        )                {
      const m = DECIMAL_RE.exec(text);
      if (!m) return null;
      let sign = m[1];
      const whole = m[2].replace(/^0+/, '') || '0';
      const frac = m[3];
      if (whole === '0' && (frac === undefined || /^0+$/.test(frac))) sign = '';
      return sign + whole + (frac === undefined ? '' : '.' + frac);
    }

    /** Texto canónico de un límite `min`/`max` decimal del contrato (string decimal o entero seguro), o null. */
    function decimalBound(value         )                {
      if (typeof value === 'number') return Number.isSafeInteger(value) ? String(value === 0 ? 0 : value) : null;
      if (typeof value === 'string') return normalizeDecimal(value);
      return null;
    }

    /** Compara dos decimales canónicos exactamente: -1, 0 o 1. */
    function compareDecimal(a        , b        )         {
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

    function checkRange(v                 , f       , lineno        , name        )       {
      if (!RANGED_TYPES.has(f.type)) return;
      if (f.type === 'decimal') {
        const lo = f.min === null ? null : decimalBound(f.min);
        const hi = f.max === null ? null : decimalBound(f.max);
        if (lo !== null && compareDecimal(v          , lo) < 0) throw new MiniError(E_RANGE, lineno, `${v} < min ${f.min}`, name);
        if (hi !== null && compareDecimal(v          , hi) > 0) throw new MiniError(E_RANGE, lineno, `${v} > max ${f.max}`, name);
        return;
      }
      // int/float se comparan numéricamente; las fechas AAAA-MM-DD como cadenas
      if (f.min !== null && (v          ) < (f.min          )) throw new MiniError(E_RANGE, lineno, `${v} < min ${f.min}`, name);
      if (f.max !== null && (v          ) > (f.max          )) throw new MiniError(E_RANGE, lineno, `${v} > max ${f.max}`, name);
    }

    /**
     * Convierte el texto (ya sin escapes) de un escalar a su valor tipado.
     * Con `asItem` se usa el tipo de elemento de una lista (`item`/`item_values`)
     * y no se aplica el rango min/max (que en listas es aridad).
     */
    function decodeScalar(text        , f       , lineno        , fname         , asItem          = false)         {
      const name = fname || f.name;
      const t = (asItem ? f.item : f.type)              ;
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
    function integerText(x        )         {
      if (Math.abs(x) < 1e21) return String(x === 0 ? 0 : x);
      return BigInt(x).toString();
    }

    /** Representación tipo repr() de la referencia: la más corta, con exponente si exp < -4 o ≥ 16. */
    function reprFloat(x        )         {
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
      let s        ;
      if (exp < 0) s = '0.' + '0'.repeat(-exp - 1) + digits;
      else if (digits.length <= exp + 1) s = digits + '0'.repeat(exp + 1 - digits.length) + '.0';
      else s = digits.slice(0, exp + 1) + '.' + digits.slice(exp + 1);
      return (neg ? '-' : '') + s;
    }

    /** Texto numérico canónico: los flotantes enteros pierden el `.0`; se evita el exponente cuando es exacto. */
    function formatNumber(x                  )         {
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

    function numberFromJson(value         , f       , name        )         {
      const v = typeof value === 'number' ? value : typeof value === 'boolean' ? Number(value) : Number(String(value).trim());
      if (!Number.isFinite(v)) throw new MiniError(E_TYPE, 0, `expected number, got '${String(value)}'`, name);
      return v;
    }

    /**
     * Forma textual canónica de un valor tipado (antes de escapar). Un valor que no
     * puede representar el tipo declarado lanza E06, el código que el parser da a la
     * misma violación (SPEC 1.1 §9).
     */
    function encodeScalar(value         , f       , asItem          = false)         {
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
    function scalarEqual(a         , b         )          {
      if (typeof a === 'number' && typeof b === 'number') {
        if (a === b) return true;
        const diff = Math.abs(a - b);
        return diff <= Math.max(1e-12 * Math.max(Math.abs(a), Math.abs(b)), 1e-12);
      }
      return a === b;
    }
    return { validDate, normalizeDecimal, decimalBound, compareDecimal, decodeScalar, formatNumber, encodeScalar, scalarEqual };
  })();

  // ---------------------------------------------------------------- codec.ts
  __m["codec"] = (function () {
    const { E_ESCAPE, MiniError } = __m["errors"];

    const FIELD_SEP = '|';
    const MARKER = '*';
    const ESCAPE = '\\';
    const QUOTE = '"';

    /** Token léxico: [carácter, ¿estaba escapado?]. */
                                                 

    /** Elemento de lista ya separado: [texto, ¿lleva marcador *?]. */
                                                

    // Espacio en blanco con la misma definición que str.isspace() de la referencia.
    const WS                      = new Set([
      0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
      0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
      0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
    ].map(cp => String.fromCharCode(cp)));

    /** ¿Es `ch` (un único carácter) espacio en blanco no significativo? */
    function isSpace(ch        )          {
      return WS.has(ch);
    }

    /** ¿La cadena está vacía o contiene solo espacio en blanco? */
    function isBlank(s        )          {
      for (const ch of s) if (!WS.has(ch)) return false;
      return true;
    }

    /** Recorta espacio en blanco en ambos extremos (definición de isSpace). */
    function trimSpace(s        )         {
      let a = 0;
      let b = s.length;
      while (a < b && WS.has(s[a])) a++;
      while (b > a && WS.has(s[b - 1])) b--;
      return s.slice(a, b);
    }

    /** Convierte una línea física en tokens (carácter, escapado), resolviendo escapes. */
    function tokenize(line        , sep        , lineno        , strict          = true)        {
      const out        = [];
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
    function splitOn(toks                , delim        )          {
      const parts          = [[]];
      for (const t of toks) {
        if (t[0] === delim && !t[1]) parts.push([]);
        else parts[parts.length - 1].push(t);
      }
      return parts;
    }

    /** Elimina espacio en blanco no escapado al inicio y al final. */
    function stripToks(toks                )        {
      let a = 0;
      let b = toks.length;
      while (a < b && isSpace(toks[a][0]) && !toks[a][1]) a++;
      while (b > a && isSpace(toks[b - 1][0]) && !toks[b - 1][1]) b--;
      return toks.slice(a, b);
    }

    function textOf(toks                )         {
      let s = '';
      for (const t of toks) s += t[0];
      return s;
    }

    /** Tokeniza una línea y la divide en campos por `|` no escapado (recortados). */
    function splitFields(line        , sep        , lineno        , strict          = true)          {
      return splitOn(tokenize(line, sep, lineno, strict), FIELD_SEP).map(stripToks);
    }

    /**
     * Divide un campo de tipo lista en pares (texto, marcado).
     * Un campo vacío da una lista vacía. Admite elementos entre comillas estilo CSV
     * con `""` como comilla literal y el marcador tras (o justo antes de) la comilla de cierre.
     */
    function splitList(toks                , sep        , lineno         = 0)                {
      if (!toks.length) return [];
      const out                = [];
      const n = toks.length;
      const ws = (k        )          => isSpace(toks[k][0]) && !toks[k][1];
      let i = 0;
      for (;;) {
        while (i < n && ws(i)) i++;
        if (i < n && toks[i][0] === QUOTE && !toks[i][1]) {
          i++;
          const buf           = [];
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
    function escapeScalar(value        )         {
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
    function escapeElement(value        , sep        )         {
      if (String(value) === '') return QUOTE + QUOTE;
      let s = escapeScalar(value).split(sep).join(ESCAPE + sep);
      if (s.endsWith(MARKER)) s = s.slice(0, -1) + ESCAPE + MARKER;
      if (s.startsWith(QUOTE)) s = ESCAPE + s;
      return s;
    }
    return { FIELD_SEP, MARKER, ESCAPE, QUOTE, isSpace, isBlank, trimSpace, tokenize, splitOn, stripToks, textOf, splitFields, splitList, escapeScalar, escapeElement };
  })();

  // ---------------------------------------------------------------- contract.ts
  __m["contract"] = (function () {
    const { E_CONTRACT, E_FORK, MiniError } = __m["errors"];
    const { decimalBound, validDate } = __m["values"];

    // ------------------------------------------------------------------ tipos
                                                                                            
                                                           
                                                       
                                                                                    

    const SCALAR_TYPES                      = new Set(['str', 'int', 'float', 'bool', 'enum', 'date', 'decimal']);
    const COMPOSITE_TYPES                      = new Set(['list', 'mlist', 'tuple']);
    const ALL_TYPES                      = new Set([...SCALAR_TYPES, ...COMPOSITE_TYPES]);
    const MARKER_MODES                      = new Set(['exactly_one', 'at_least_one', 'at_most_one', 'any']);

    /** Campo tal como aparece en contract.json. */
                                
                   
                      
                         
                       
                        
                        
                             
                                                                                                              
                            
                            
                          
                         
                          
                                                   
                    
                        
     

    /** Clave de cabecera tal como aparece en contract.json. */
                                    
                                         
                        
                          
                        
                        
                    
     

    /** Contrato tal como aparece en forks/<prefix>/contract.json. */
                                   
                     
                       
                    
                           
                             
                              
                           
                      
                      
                       
                      
                                                                             
                        
                               
     

    /** Campo normalizado (valores por defecto aplicados). */
                            
                   
                      
                        
                      
                              
                       
                                   
                                                                                                     
                                  
                                  
                         
                               
                     
                         
                            
                   
                       
     

    /** Clave de cabecera normalizada. */
                                
                   
                                        
                        
                       
                     
                              
                       
                   
     

    /** Contrato normalizado, listo para parse/dumps/specBlock. */
                               
                     
                      
                   
                          
                            
                             
                          
                     
                     
                      
                     
                                            
                    
                          
                                         
                      
                                     
                    
     

    const NORMALIZED = Symbol.for('mini-format.contract');

    // ----------------------------------------------------------- normalización
    function hasOwn(o        , k        )          {
      return Object.prototype.hasOwnProperty.call(o, k);
    }

    function normField(d           , path         = '')        {
      const raw = (d || {})                                      ;
      const where = path ? `${path}.${raw.name ?? '?'}` : String(raw.name ?? '?');
      if (!hasOwn(raw, 'name') || !hasOwn(raw, 'type')) {
        throw new MiniError(E_CONTRACT, 0, `field ${where}: 'name' and 'type' are required`);
      }
      const t = d.type;
      if (!ALL_TYPES.has(t)) throw new MiniError(E_CONTRACT, 0, `field ${where}: unknown type '${t}'`);
      const f        = {
        name: d.name,
        type: t,
        optional: !!d.optional,
        unique: !!d.unique,
        values: hasOwn(raw, 'values') && d.values ? [...d.values] : null,
        item: d.item || 'str',
        item_values: hasOwn(raw, 'item_values') && d.item_values ? [...d.item_values] : null,
        min: d.min === undefined || d.min === null ? null : d.min,
        max: d.max === undefined || d.max === null ? null : d.max,
        marker: d.marker || 'exactly_one',
        count_key: d.count_key || null,
        items: [],
        json_items: 'items',
        json_selected: 'selected',
        desc: d.desc || '',
        default: d.default === undefined ? null : d.default,
      };
      if (t === 'enum' && !(f.values && f.values.length)) {
        throw new MiniError(E_CONTRACT, 0, `field ${where}: enum requires 'values'`);
      }
      if (t === 'date' || t === 'decimal') {
        // SPEC 1.1 §6: límites de date como AAAA-MM-DD; de decimal, cadena decimal o entero
        for (const bound of [f.min, f.max]) {
          if (bound === null) continue;
          const ok = t === 'date' ? typeof bound === 'string' && validDate(bound) : decimalBound(bound) !== null;
          if (!ok) throw new MiniError(E_CONTRACT, 0, `field ${where}: invalid bound '${String(bound)}' for type ${t}`);
        }
      }
      if (t === 'list' || t === 'mlist') {
        if (!SCALAR_TYPES.has(f.item)) throw new MiniError(E_CONTRACT, 0, `field ${where}: list item type must be scalar`);
        if (f.item === 'enum' && !(f.item_values && f.item_values.length)) {
          throw new MiniError(E_CONTRACT, 0, `field ${where}: enum items require 'item_values'`);
        }
      }
      if (t === 'mlist') {
        if (!MARKER_MODES.has(f.marker)) throw new MiniError(E_CONTRACT, 0, `field ${where}: bad marker mode '${f.marker}'`);
        const j = d.json || {};
        f.json_items = j.items || 'items';
        f.json_selected = j.selected || (f.marker === 'exactly_one' ? 'correct' : 'selected');
      }
      if (t === 'tuple') {
        const comps = d.items || [];
        if (!comps.length) throw new MiniError(E_CONTRACT, 0, `field ${where}: tuple requires 'items'`);
        f.items = comps.map(c => normField(c, where));
        for (const c of f.items) {
          if (!SCALAR_TYPES.has(c.type)) throw new MiniError(E_CONTRACT, 0, `field ${where}: tuple components must be scalar`);
        }
      }
      return f;
    }

    function normHeaderKey(name        , d               , required         )            {
      const t = (d.type || 'str')             ;
      if (!ALL_TYPES.has(t) || t === 'mlist') {
        throw new MiniError(E_CONTRACT, 0, `header key ${name}: unsupported type '${t}'`);
      }
      const hk            = {
        name,
        type: t                     ,
        required,
        item: d.item || 'str',
        items: [],
        values: d.values || null,
        default: d.default === undefined ? null : d.default,
        desc: d.desc || '',
      };
      if (t === 'tuple') hk.items = (d.items || []).map(c => normField(c, `header.${name}`));
      return hk;
    }

    /** Vista de una clave de cabecera como campo (equivale a HeaderKey.as_field de la referencia). */
    function headerKeyAsField(hk           )        {
      return {
        name: hk.name, type: hk.type, optional: !hk.required, unique: false, values: hk.values,
        item: hk.item, item_values: null, min: null, max: null, marker: 'exactly_one', count_key: null,
        items: hk.items, json_items: 'items', json_selected: 'selected', desc: hk.desc, default: hk.default,
      };
    }

    /** Indica si el objeto ya es un contrato normalizado por esta biblioteca. */
    function isContract(c         )                {
      return !!c && typeof c === 'object' && (c                           )[NORMALIZED] === true;
    }

    /**
     * Normaliza un contract.json aplicando valores por defecto y validándolo.
     * Lanza MiniError E20 si el contrato es inválido. Idempotente.
     */
    function normalizeContract(d                         )           {
      if (isContract(d)) return d;
      if (!d || typeof d !== 'object' || !hasOwn(d, 'prefix')) {
        throw new MiniError(E_CONTRACT, 0, "contract requires 'prefix'");
      }
      const prefix = String(d.prefix);
      if (!/^[A-Za-z][A-Za-z0-9_-]*$/.test(prefix)) {
        throw new MiniError(E_CONTRACT, 0, `prefix '${prefix}' must match [A-Za-z][A-Za-z0-9_-]*`);
      }
      const version = d.version === undefined || d.version === null ? 1 : Math.trunc(Number(d.version));
      if (!Number.isFinite(version)) throw new MiniError(E_CONTRACT, 0, `bad version '${d.version}'`);
      const sep = d.list_separator === undefined || d.list_separator === null ? ',' : String(d.list_separator);
      if ([...sep].length !== 1 || '|\\*\n'.includes(sep)) {
        throw new MiniError(E_CONTRACT, 0, 'list_separator must be a single character other than | \\ * or newline');
      }
      const hdr = d.header || {};
      const required = new Set        ([...(hdr.required || ['n']), 'n']);
      const keys                                = Object.assign({}, hdr.keys || {});
      if (!hasOwn(keys, 'n')) keys.n = { type: 'int', desc: 'number of records' };
      if (!hasOwn(keys, 'v')) keys.v = { type: 'int', default: 1, desc: 'contract version' };
      const headerKeys                            = {};
      for (const k of Object.keys(keys)) headerKeys[k] = normHeaderKey(k, keys[k] || {}, required.has(k));
      for (const k of required) {
        if (!hasOwn(headerKeys, k)) {
          headerKeys[k] = { name: k, type: 'str', required: true, item: 'str', items: [], values: null, default: null, desc: '' };
        }
      }
      const core = (d.core || []).map(f => normField(f));
      const extensions = (d.extensions || []).map(f => normField(f));
      if (!core.length) throw new MiniError(E_CONTRACT, 0, 'contract requires at least one core field');
      const names = [...core, ...extensions].map(f => f.name);
      if (new Set(names).size !== names.length) throw new MiniError(E_CONTRACT, 0, 'duplicate field names in contract');
      for (const f of extensions) f.optional = true; // las extensiones son opcionales por definición
      const c           = {
        prefix,
        version,
        name: d.name || '',
        description: d.description || '',
        parent: d.parent || null,
        list_separator: sep,
        records_key: d.records_key || 'records',
        domain: d.domain || '',
        author: d.author || '',
        license: d.license || 'MIT',
        source: d.source || '',
        headerKeys,
        core,
        extensions,
        fields: [...core, ...extensions],
        arity: core.length,
      };
      Object.defineProperty(c, NORMALIZED, { value: true, enumerable: false });
      return c;
    }

    // -------------------------------------------------------------- firmas
    function numText(x                        )         {
      return x === null ? '' : String(x);
    }

    /** Firma corta de un campo, p. ej. `options:mlist<str>[2..6]*1`. */
    function fieldSignature(f       )         {
      let body        ;
      if (f.type === 'enum') {
        body = 'enum{' + (f.values || []).join('|') + '}';
      } else if (f.type === 'list' || f.type === 'mlist') {
        const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
        body = `${f.type}<${it}>`;
        if (f.min !== null || f.max !== null) {
          body += `[${f.min === null ? '' : Math.trunc(Number(f.min))}..${f.max === null ? '' : Math.trunc(Number(f.max))}]`;
        }
        if (f.type === 'mlist') {
          body += ({ exactly_one: '*1', at_least_one: '*1+', at_most_one: '*0..1', any: '*' }         )[f.marker];
        }
      } else if (f.type === 'tuple') {
        body = 'tuple(' + f.items.map(c => `${c.name}:${c.type}`).join(',') + ')';
      } else {
        body = f.type;
        if (f.min !== null || f.max !== null) body += `[${numText(f.min)}..${numText(f.max)}]`;
      }
      return `${f.name}:${body}${f.optional ? '?' : ''}`;
    }

    /** Firma compacta del registro: núcleo `|` separado, extensiones tras `||`. */
    function signature(c          )         {
      const core = c.core.map(fieldSignature).join(' | ');
      const ext = c.extensions.map(fieldSignature).join(' | ');
      return core + (ext ? ' || ' + ext : '');
    }

    // -------------------------------------------------------------- forks
    /** Verifica los invariantes I2–I4 de un fork frente a su padre (SPEC §10). */
    function checkFork(childIn                         , parentIn                         )              {
      const child = normalizeContract(childIn);
      const parent = normalizeContract(parentIn);
      const errs              = [];
      const pf = parent.fields;
      const cf = child.fields;
      if (cf.length < pf.length) {
        errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' drops fields of parent '${parent.prefix}'`));
        return errs;
      }
      pf.forEach((p, i) => {
        const k = cf[i];
        if (p.name !== k.name || p.type !== k.type) {
          errs.push(new MiniError(E_FORK, 0,
            `fork '${child.prefix}' changes inherited field #${i + 1}: parent ${fieldSignature(p)} != child ${fieldSignature(k)}`));
        }
        if ((p.type === 'list' || p.type === 'mlist') && p.item !== k.item) {
          errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' changes item type of '${p.name}'`));
        }
        if (p.type === 'tuple' && JSON.stringify(p.items.map(x => x.name)) !== JSON.stringify(k.items.map(x => x.name))) {
          errs.push(new MiniError(E_FORK, 0, `fork '${child.prefix}' changes tuple layout of '${p.name}'`));
        }
      });
      if (child.list_separator !== parent.list_separator) {
        errs.push(new MiniError(E_FORK, 0, 'fork changes list_separator of its parent'));
      }
      for (const k of Object.keys(parent.headerKeys)) {
        if (parent.headerKeys[k].required && !(hasOwn(child.headerKeys, k) && child.headerKeys[k].required)) {
          errs.push(new MiniError(E_FORK, 0, `fork drops required header key '${k}'`));
        }
      }
      return errs;
    }

    /** Serializa un contrato normalizado de vuelta a su forma JSON (equivale a Contract.to_dict). */
    function contractToJSON(c          )               {
      const fieldToJSON = (f       )            => {
        const d            = { name: f.name, type: f.type };
        if (f.optional) d.optional = true;
        if (f.unique) d.unique = true;
        if (f.values !== null) d.values = [...f.values];
        if (f.type === 'list' || f.type === 'mlist') {
          d.item = f.item;
          if (f.item_values !== null) d.item_values = [...f.item_values];
          if (f.count_key) d.count_key = f.count_key;
        }
        if (f.min !== null) d.min = f.min;
        if (f.max !== null) d.max = f.max;
        if (f.type === 'mlist') {
          d.marker = f.marker;
          d.json = { items: f.json_items, selected: f.json_selected };
        }
        if (f.type === 'tuple') d.items = f.items.map(fieldToJSON);
        if (f.desc) d.desc = f.desc;
        if (f.default !== null) d.default = f.default;
        return d;
      };
      const keys                                = {};
      for (const [k, v] of Object.entries(c.headerKeys)) {
        const o                = { type: v.type };
        if (v.type === 'list') o.item = v.item;
        if (v.type === 'tuple') o.items = v.items.map(fieldToJSON);
        if (v.values !== null) o.values = v.values;
        if (v.default !== null) o.default = v.default;
        if (v.desc) o.desc = v.desc;
        keys[k] = o;
      }
      return {
        prefix: c.prefix, version: c.version, name: c.name, description: c.description, parent: c.parent,
        domain: c.domain, list_separator: c.list_separator, records_key: c.records_key,
        header: { required: Object.keys(c.headerKeys).filter(k => c.headerKeys[k].required), keys },
        core: c.core.map(fieldToJSON), extensions: c.extensions.map(fieldToJSON),
        author: c.author, license: c.license, source: c.source,
      };
    }
    return { SCALAR_TYPES, COMPOSITE_TYPES, ALL_TYPES, MARKER_MODES, headerKeyAsField, isContract, normalizeContract, fieldSignature, signature, checkFork, contractToJSON };
  })();

  // ---------------------------------------------------------------- parser.ts
  __m["parser"] = (function () {
    const codec = __m["codec"];
    const { SCALAR_TYPES, headerKeyAsField, normalizeContract } = __m["contract"];
    const { E_ARITY, E_COUNT_MISMATCH, E_HEADER_KEY, E_LIST_ARITY, E_MARKER, E_NO_COUNT, E_NO_HEADER, E_TYPE, E_UNIQUE, E_UNKNOWN_PREFIX, MiniError, MiniValidationError } = __m["errors"];
    const { decodeScalar } = __m["values"];

                                                                                              
                                                   
                                               

                                      
                     
                     
                                    
     

    /** Informe de diagnóstico de un documento (mismas claves que Document.diagnostics() de la referencia). */
                                          
                  
                     
                        
                           
                            
                            
                              
                              
                         
                                                                               
     

                                   
                                                                                                                       
                       
     

    /** Documento analizado. */
    class Document {
               prefix        ;
               version        ;
               header        ;
               records              ;
               errors             ;
               contract          ;
      /** Número de líneas significativas (cabecera + registros). */
               lines        ;
      /** Línea física de la cabecera (0 si no hubo cabecera). */
               headerLine        ;
      /** Línea física de cada registro aceptado, en orden. */
               recordLines          ;
      /** Líneas significativas tras la cabecera (válidas o no). */
               recordLineCount        ;
      /** Línea física de la última línea significativa. */
               lastLine        ;

      constructor(init   
                                                                               
                                                               
                                                                                                 
       ) {
        this.prefix = init.prefix;
        this.version = init.version;
        this.header = init.header;
        this.records = init.records;
        this.errors = init.errors;
        this.contract = init.contract;
        this.lines = init.lines;
        this.headerLine = init.headerLine ?? 0;
        this.recordLines = init.recordLines ?? [];
        this.recordLineCount = init.recordLineCount ?? 0;
        this.lastLine = init.lastLine ?? 0;
      }

      get ok()          {
        return this.errors.length === 0;
      }

      // ------------------------------------------------------------ diagnóstico
      /** Líneas físicas (ascendentes, sin la cabecera) de los registros rechazados: las que hay que regenerar. */
      invalidLines()           {
        const set = new Set        ();
        for (const e of this.errors) if (e.line > this.headerLine) set.add(e.line);
        return [...set].sort((a, b) => a - b);
      }

      /** Errores de la propia línea de cabecera. */
      headerErrors()              {
        return this.errors.filter(e => this.headerLine > 0 && e.line === this.headerLine);
      }

      /** Errores de documento (línea 0: E01, E04). */
      documentErrors()              {
        return this.errors.filter(e => e.line === 0);
      }

      /** Registros declarados por `n` que faltan en el texto (0 si `n` falta o no se supera). */
      get missingRecords()         {
        const n = Object.prototype.hasOwnProperty.call(this.header, 'n') ? this.header.n : undefined;
        return typeof n === 'number' && Number.isInteger(n) && n > this.recordLineCount ? n - this.recordLineCount : 0;
      }

      /** Parece cortado: faltan líneas según `n`, o la última línea tiene menos campos que el núcleo o una barra colgante. */
      get truncated()          {
        if (this.missingRecords) return true;
        if (!this.recordLineCount) return false;
        return this.errors.some(e => e.line === this.lastLine
          && ((e.code === 'E05' && e.message.includes('core requires')) || (e.code === 'E09' && e.message.includes('dangling'))));
      }

      /** Informe serializable para recuperación parcial y regeneración. */
      diagnostics()                      {
        const n = Object.prototype.hasOwnProperty.call(this.header, 'n') ? this.header.n : null;
        return {
          ok: this.ok,
          prefix: this.prefix,
          declared_n: n === undefined ? null : n,
          record_lines: this.recordLineCount,
          valid_records: this.records.length,
          valid_lines: [...this.recordLines],
          invalid_lines: this.invalidLines(),
          missing_records: this.missingRecords,
          truncated: this.truncated,
          errors: this.errors.map(e => e.toJSON()),
        };
      }

      /** Objeto canónico `{prefix, header, <records_key>: [...]}` (SPEC §7). */
      toCanonical()                  {
        return {
          prefix: this.prefix,
          header: shallowCopy(this.header),
          [this.contract.records_key]: this.records.map(r => shallowCopy(r)),
        }                   ;
      }

      /** Alias de toCanonical() por compatibilidad con js/mini.js. */
      canonical()                  {
        return this.toCanonical();
      }
    }

    const hasOwn = (o        , k        )          => Object.prototype.hasOwnProperty.call(o, k);

    /** Asigna una propiedad propia incluso si la clave es `__proto__`. */
    function put(o                         , k        , v         )       {
      if (k === '__proto__') Object.defineProperty(o, k, { value: v, enumerable: true, writable: true, configurable: true });
      else o[k] = v;
    }

    /** Copia superficial que conserva claves como `__proto__`. */
    function shallowCopy                                   (o   )    {
      const out                          = {};
      for (const k of Object.keys(o)) put(out, k, o[k]);
      return out     ;
    }

    // ---------------------------------------------------------------- cabecera
                                   
                     
                     
                          
     

    function parseHeader(line        , lineno        , c          , strict         )               {
      const errs              = [];
      let fields         ;
      // Los escapes se validan siempre (también en modo tolerante): un escape inválido en la
      // cabecera es E09 dentro de la validación y el resto se recupera con una lectura tolerante.
      void strict;
      try {
        fields = codec.splitFields(line, c.list_separator, lineno, true);
      } catch (e) {
        if (!(e instanceof MiniError)) throw e;
        errs.push(e);
        let trailing = 0;
        while (trailing < line.length && line[line.length - 1 - trailing] === codec.ESCAPE) trailing++;
        const safe = trailing % 2 ? line.slice(0, -1) : line; // descarta una barra invertida colgante
        fields = codec.splitFields(safe, c.list_separator, lineno, false);
      }
      const prefix = fields.length ? codec.textOf(fields[0]) : '';
      const header         = {};
      const seen = new Set        (); // claves presentes aunque su valor sea inválido
      for (const toks of fields.slice(1)) {
        const txt = codec.textOf(toks);
        if (!txt) continue;
        // se divide en el primer '=' no escapado (un '=' dentro del valor es literal)
        const eq = toks.findIndex(t => t[0] === '=' && !t[1]);
        if (eq < 0) {
          errs.push(new MiniError(E_HEADER_KEY, lineno, `header entry '${txt}' is not key=value`));
          continue;
        }
        const key = codec.textOf(codec.stripToks(toks.slice(0, eq)));
        const vt = codec.stripToks(toks.slice(eq + 1));
        if (seen.has(key)) {
          // SPEC 1.1 §5: una clave repetida es E12; se conserva la primera aparición
          errs.push(new MiniError(E_HEADER_KEY, lineno, `duplicate header key '${key}'`));
          continue;
        }
        seen.add(key);
        const hk = hasOwn(c.headerKeys, key) ? c.headerKeys[key] : undefined;
        try {
          if (!hk) {
            put(header, key, codec.textOf(vt));
          } else if (hk.type === 'list') {
            const hf = headerKeyAsField(hk);
            put(header, key, codec.splitList(vt, c.list_separator, lineno).map(([t]) => decodeScalar(t, hf, lineno, key, true)));
          } else if (hk.type === 'tuple') {
            const parts = codec.splitList(vt, c.list_separator, lineno);
            if (parts.length !== hk.items.length) {
              throw new MiniError(E_LIST_ARITY, lineno, `expected ${hk.items.length} components, got ${parts.length}`, key);
            }
            const o                        = {};
            hk.items.forEach((cmp, i) => {
              const t = parts[i][0];
              put(o, cmp.name, t === '' ? null : decodeScalar(t, cmp, lineno, `${key}.${cmp.name}`));
            });
            put(header, key, o);
          } else {
            put(header, key, decodeScalar(codec.textOf(vt), headerKeyAsField(hk), lineno, key));
          }
        } catch (e) {
          if (e instanceof MiniError) errs.push(e);
          else throw e;
        }
      }
      for (const k of Object.keys(c.headerKeys)) {
        const hk = c.headerKeys[k];
        if (!seen.has(k)) {
          if (hk.required && k !== 'n') errs.push(new MiniError(E_HEADER_KEY, lineno, `required header key '${k}' missing`));
          else if (hk.default !== null) put(header, k, hk.default);
        }
      }
      // E03 significa que falta n; un n presente con tipo inválido ya se reportó con el código
      // de esa violación (SPEC 1.1 §5).
      if (!seen.has('n')) errs.push(new MiniError(E_NO_COUNT, lineno, 'header must declare n=<record count>'));
      return { prefix, header, errors: errs };
    }

    // ---------------------------------------------------------------- campos
                          
                     
                                         
     

    class MList {
               value            ;
      constructor(value            ) {
        this.value = value;
      }
    }

    /** Decodifica un campo (lista de tokens) según su definición. */
    function decodeField(toks                , f       , lineno        , sep        , header                )                {
      if (SCALAR_TYPES.has(f.type)) {
        const txt = codec.textOf(toks);
        if (txt === '') {
          if (f.optional) return f.default         ;
          throw new MiniError(E_TYPE, lineno, 'required value is empty', f.name);
        }
        return decodeScalar(txt, f, lineno);
      }
      if (f.type === 'list' || f.type === 'mlist') {
        if (!toks.length && f.optional) {
          // SPEC 1.1 §6: un campo vacío es null en todo campo opcional
          return f.type === 'mlist' ? new MList({ items: f.default           , selected: null }) : f.default         ;
        }
        const elems = codec.splitList(toks, sep, lineno);
        const lo = f.min === null ? null : Number(f.min);
        const hi = f.max === null ? null : Number(f.max);
        if (!elems.length && !f.optional && lo !== null && lo > 0) {
          throw new MiniError(E_LIST_ARITY, lineno, 'required list is empty', f.name);
        }
        if (lo !== null && elems.length < lo) {
          throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements, min ${Math.trunc(lo)}`, f.name);
        }
        if (hi !== null && elems.length > hi) {
          throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements, max ${Math.trunc(hi)}`, f.name);
        }
        if (f.count_key && header) {
          const k = hasOwn(header, f.count_key) ? header[f.count_key] : undefined;
          if (typeof k === 'number' && Number.isInteger(k) && elems.length !== k) {
            throw new MiniError(E_LIST_ARITY, lineno, `list has ${elems.length} elements but header ${f.count_key}=${k}`, f.name);
          }
        }
        const items = elems.map(([t]) => decodeScalar(t, f, lineno, f.name, true));
        if (f.type === 'list') {
          if (elems.some(e => e[1])) throw new MiniError(E_MARKER, lineno, 'marker * not allowed in a plain list', f.name);
          return items;
        }
        const marked           = [];
        elems.forEach((e, i) => { if (e[1]) marked.push(i); });
        if (f.marker === 'exactly_one' && marked.length !== 1) {
          throw new MiniError(E_MARKER, lineno, `exactly one element must carry *, found ${marked.length}`, f.name);
        }
        if (f.marker === 'at_least_one' && marked.length < 1) {
          throw new MiniError(E_MARKER, lineno, 'at least one element must carry *', f.name);
        }
        if (f.marker === 'at_most_one' && marked.length > 1) {
          throw new MiniError(E_MARKER, lineno, `at most one element may carry *, found ${marked.length}`, f.name);
        }
        const single = f.marker === 'exactly_one' || f.marker === 'at_most_one';
        return new MList({ items, selected: single ? (marked.length ? marked[0] : null) : marked });
      }
      if (f.type === 'tuple') {
        const parts = codec.splitList(toks, sep, lineno);
        if (!parts.length && f.optional) return null;
        if (parts.length !== f.items.length) {
          throw new MiniError(E_LIST_ARITY, lineno, `tuple expects ${f.items.length} components, got ${parts.length}`, f.name);
        }
        const out                        = {};
        f.items.forEach((cmp, i) => {
          const [txt, m] = parts[i];
          if (m) throw new MiniError(E_MARKER, lineno, 'marker * not allowed inside a tuple', f.name);
          if (txt === '') {
            if (cmp.optional) {
              put(out, cmp.name, cmp.default);
              return;
            }
            throw new MiniError(E_TYPE, lineno, `tuple component '${cmp.name}' is empty`, f.name);
          }
          put(out, cmp.name, decodeScalar(txt, cmp, lineno, `${f.name}.${cmp.name}`));
        });
        return out;
      }
      throw new MiniError(E_TYPE, lineno, `unsupported field type ${(f         ).type}`, f.name);
    }

    function sortedJson(v       )         {
      if (Array.isArray(v)) return '[' + v.map(sortedJson).join(',') + ']';
      if (v && typeof v === 'object') {
        return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + sortedJson(v[k])).join(',') + '}';
      }
      return JSON.stringify(v);
    }

    /** Clave de unicidad: listas y objetos se comparan por contenido. */
    function uniqueKey(v       )         {
      if (typeof v === 'number') return 'n:' + String(v);
      if (typeof v === 'string') return 's:' + v;
      return 'j:' + sortedJson(v);
    }

    // ---------------------------------------------------------- motor por líneas
    /** Resultado de procesar una línea física de registro. */
                                  
                   
                                                              
                                
                          
     

    /**
     * Motor incremental: recibe líneas físicas (sin LF) en orden y acumula el estado.
     * Uso interno de `parse` y `createReader`; expuesto para integraciones avanzadas.
     */
    class LineEngine {
               contract          ;
               strict         ;
      prefix         = '';
      header                = null;
               records               = [];
               errors              = [];
      /** Número de la última línea física recibida. */
      physical         = 0;
      /** Líneas significativas vistas (cabecera incluida). */
      significant         = 0;
      /** Línea física de la cabecera (0 si aún no hay cabecera). */
      headerLine         = 0;
      /** Línea física de la última línea significativa. */
      lastLine         = 0;
      /** Línea física de cada registro aceptado. */
               acceptedLines           = [];
                       uniques                                   = new Map();

      constructor(contract          , strict         ) {
        this.contract = contract;
        this.strict = strict;
        for (const f of contract.fields) if (f.unique) this.uniques.set(f.name, new Map());
      }

      /** Procesa una línea física. Devuelve null si es la cabecera o una línea en blanco. */
      feed(raw        )                     {
        this.physical += 1;
        const lineno = this.physical;
        let line = raw;
        if (lineno === 1 && line.charCodeAt(0) === 0xfeff) line = line.slice(1);
        if (line.endsWith('\r')) line = line.slice(0, -1);
        if (codec.isBlank(line)) return null;
        this.significant += 1;
        this.lastLine = lineno;
        if (this.header === null) {
          this.headerLine = lineno;
          this.acceptHeader(line, lineno);
          return null;
        }
        return this.acceptRecord(line, lineno);
      }

              acceptHeader(line        , lineno        )       {
        const c = this.contract;
        const res = parseHeader(line, lineno, c, this.strict);
        this.prefix = res.prefix;
        this.header = res.header;
        this.errors.push(...res.errors);
        if (res.prefix !== c.prefix) {
          this.errors.push(new MiniError(E_UNKNOWN_PREFIX, lineno, `header prefix '${res.prefix}' does not match contract '${c.prefix}'`));
        }
      }

              acceptRecord(line        , lineno        )              {
        const c = this.contract;
        const sep = c.list_separator;
        let toks         ;
        try {
          // Los escapes se validan siempre: el modo tolerante devuelve los registros que el
          // estricto aceptaría, más la lista de errores (SPEC §8).
          toks = codec.splitFields(line, sep, lineno, true);
        } catch (e) {
          if (!(e instanceof MiniError)) throw e;
          this.errors.push(e);
          return { line: lineno, record: null, errors: [e] };
        }
        let nf = toks.length;
        if (nf < c.arity) {
          const e = new MiniError(E_ARITY, lineno, `record has ${nf} fields, core requires ${c.arity}`);
          this.errors.push(e);
          return { line: lineno, record: null, errors: [e] };
        }
        if (nf > c.fields.length) {
          const documentVersion = Number(this.header .v ?? 1);
          if (documentVersion > c.version) {
            // splitFields already validated every escape in the unknown tail.
            toks = toks.slice(0, c.fields.length);
            nf = toks.length;
          } else {
            const e = new MiniError(E_ARITY, lineno, `record has ${nf} fields, contract allows at most ${c.fields.length}`);
            this.errors.push(e);
            return { line: lineno, record: null, errors: [e] };
          }
        }
        const rec             = {};
        const recErrs              = [];
        c.fields.forEach((f, i) => {
          if (i >= nf) {
            if (f.type === 'mlist') {
              put(rec, f.json_items, null);
              put(rec, f.json_selected, null);
            } else {
              put(rec, f.name, f.default);
            }
            return;
          }
          try {
            const v = decodeField(toks[i], f, lineno, sep, this.header);
            if (v instanceof MList) {
              put(rec, f.json_items, v.value.items);
              put(rec, f.json_selected, v.value.selected);
            } else {
              put(rec, f.name, v);
            }
          } catch (e) {
            if (e instanceof MiniError) recErrs.push(e);
            else throw e;
          }
        });
        for (const [name, seen] of this.uniques) {
          const v = hasOwn(rec, name) ? rec[name] : undefined;
          if (v !== null && v !== undefined) {
            const first = seen.get(uniqueKey(v));
            if (first !== undefined) {
              recErrs.push(new MiniError(E_UNIQUE, lineno, `duplicate value '${String(v)}' (first seen line ${first})`, name));
            }
          }
        }
        if (recErrs.length) {
          this.errors.push(...recErrs);
          return { line: lineno, record: null, errors: recErrs };
        }
        // solo los registros aceptados reservan valores únicos: una línea rechazada nunca
        // provoca que un registro válido posterior con el mismo valor se descarte
        for (const [name, seen] of this.uniques) {
          const v = hasOwn(rec, name) ? rec[name] : undefined;
          if (v !== null && v !== undefined) seen.set(uniqueKey(v), lineno);
        }
        this.records.push(rec);
        this.acceptedLines.push(lineno);
        return { line: lineno, record: rec, errors: [] };
      }

      /** Líneas de registro significativas vistas hasta ahora (válidas o no). */
      get recordLineCount()         {
        return Math.max(0, this.significant - 1);
      }

      /** Cierra el documento: E01 si no hubo cabecera, E04 si el conteo no coincide con n. */
      finish()           {
        const c = this.contract;
        if (this.header === null) {
          const errors = [...this.errors, new MiniError(E_NO_HEADER, 0, 'empty document: header missing')];
          return new Document({ prefix: '', version: 1, header: {}, records: [], errors, contract: c, lines: 0 });
        }
        const errors = [...this.errors];
        const n = hasOwn(this.header, 'n') ? this.header.n : undefined;
        const total = this.recordLineCount;
        if (typeof n === 'number' && Number.isInteger(n) && n !== total) {
          errors.push(new MiniError(E_COUNT_MISMATCH, 0, `header declares n=${n} but document has ${total} record lines`));
        }
        const v = hasOwn(this.header, 'v') ? this.header.v : undefined;
        const version = typeof v === 'number' && v ? Math.trunc(v) : 1;
        return new Document({
          prefix: this.prefix, version, header: this.header, records: [...this.records], errors,
          contract: c, lines: this.significant, headerLine: this.headerLine, recordLines: [...this.acceptedLines],
          recordLineCount: total, lastLine: this.lastLine,
        });
      }
    }

    /**
     * Analiza `text` contra `contract`.
     * strict=true (por defecto) lanza MiniValidationError con todos los errores;
     * strict=false devuelve un Document con los registros válidos y la lista de errores.
     */
    function parse(text        , contract                         , opts               = {})           {
      const c = normalizeContract(contract);
      const strict = opts.strict !== false;
      const engine = new LineEngine(c, strict);
      for (const raw of String(text).split('\n')) engine.feed(raw);
      const doc = engine.finish();
      if (strict && doc.errors.length) throw new MiniValidationError(doc.errors);
      return doc;
    }

    /** Devuelve el prefijo de la cabecera sin necesitar el contrato (o null si no hay cabecera). */
    function detectPrefix(text        )                {
      let s = String(text);
      if (s.charCodeAt(0) === 0xfeff) s = s.slice(1);
      for (let raw of s.split('\n')) {
        if (raw.endsWith('\r')) raw = raw.slice(0, -1);
        if (codec.isBlank(raw)) continue;
        let t         ;
        try {
          t = codec.splitFields(raw, ',', 1, false);
        } catch {
          t = codec.splitFields(raw.slice(0, -1), ',', 1, false); // barra invertida colgante
        }
        return t.length ? codec.textOf(t[0]) : null;
      }
      return null;
    }
    return { Document, put, shallowCopy, parseHeader, decodeField, LineEngine, parse, detectPrefix };
  })();

  // ---------------------------------------------------------------- serializer.ts
  __m["serializer"] = (function () {
    const codec = __m["codec"];
    const { SCALAR_TYPES, headerKeyAsField, normalizeContract } = __m["contract"];
    const { E_ENUM, E_MARKER, E_TYPE, MiniError, MiniValidationError } = __m["errors"];
    const { parse } = __m["parser"];
    const { encodeScalar } = __m["values"];

                                       

    const hasOwn = (o        , k        )          => Object.prototype.hasOwnProperty.call(o, k);
    const get = (o     , k        )          => (hasOwn(o, k) ? o[k] : undefined);
    const isNil = (v         )                        => v === null || v === undefined;

    function encList(values                    , f       , sep        , marked                    )         {
      const ms = new Set(marked || []);
      return values
        .map((v, i) => {
          let s = codec.escapeElement(encodeScalar(v, f, true), sep);
          if (ms.has(i)) s += codec.MARKER;
          return s;
        })
        .join(sep);
    }

    /** Codifica un campo. Para `mlist` se leen las claves hermanas desde `rec`. */
    function encodeField(value         , f       , sep        , rec      )         {
      if (f.type === 'mlist' && rec) {
        const items = get(rec, f.json_items);
        if (isNil(items)) {
          if (f.optional) return '';
          throw new MiniError(E_TYPE, 0, 'required marked list is null', f.name);
        }
        value = { [f.json_items]: items, [f.json_selected]: get(rec, f.json_selected) };
      }
      if (isNil(value)) {
        if (f.optional) return '';
        throw new MiniError(E_TYPE, 0, 'required field is null', f.name);
      }
      if (SCALAR_TYPES.has(f.type)) {
        if (f.type === 'enum' && !(f.values || []).includes(String(value))) {
          throw new MiniError(E_ENUM, 0, `'${String(value)}' not in enum`, f.name);
        }
        return codec.escapeScalar(encodeScalar(value, f));
      }
      if (f.type === 'list') {
        if (!Array.isArray(value)) throw new MiniError(E_TYPE, 0, 'list expected', f.name);
        return encList(value, f, sep);
      }
      if (f.type === 'mlist') {
        let items         ;
        let sel         ;
        if (Array.isArray(value)) { // atajo [items, selected]
          [items, sel] = value;
        } else if (typeof value === 'object') {
          items = get(value       , f.json_items);
          if (isNil(items)) items = [];
          sel = get(value       , f.json_selected);
        }
        if (!Array.isArray(items)) throw new MiniError(E_TYPE, 0, 'list expected', f.name);
        let marked          ;
        if (isNil(sel)) marked = [];
        else if (typeof sel === 'number') marked = [sel];
        else if (Array.isArray(sel)) marked = sel.map(Number);
        else throw new MiniError(E_MARKER, 0, `invalid selection '${String(sel)}'`, f.name);
        if (f.marker === 'exactly_one' && marked.length !== 1) {
          throw new MiniError(E_MARKER, 0, 'exactly one selected element required', f.name);
        }
        if (f.marker === 'at_least_one' && !marked.length) {
          throw new MiniError(E_MARKER, 0, 'at least one selected element required', f.name);
        }
        if (f.marker === 'at_most_one' && marked.length > 1) {
          throw new MiniError(E_MARKER, 0, 'at most one selected element allowed', f.name);
        }
        for (const m of marked) {
          if (!(Number.isInteger(m) && m >= 0 && m < items.length)) {
            throw new MiniError(E_MARKER, 0, `selected index ${m} out of range`, f.name);
          }
        }
        return encList(items, f, sep, marked);
      }
      if (f.type === 'tuple') {
        if (typeof value !== 'object' || Array.isArray(value)) throw new MiniError(E_TYPE, 0, 'tuple expects an object', f.name);
        return f.items
          .map(cmp => {
            const v = get(value       , cmp.name);
            if (isNil(v)) {
              if (cmp.optional) return '';
              throw new MiniError(E_TYPE, 0, `tuple component '${cmp.name}' missing`, f.name);
            }
            return codec.escapeElement(encodeScalar(v, cmp), sep);
          })
          .join(sep);
      }
      throw new MiniError(E_TYPE, 0, `unsupported type ${(f         ).type}`, f.name);
    }

    /** Codifica la cabecera: `n` primero, luego claves del contrato en su orden, luego claves extra. */
    function encodeHeader(header     , c          , n        )         {
      const sep = c.list_separator;
      const parts = [c.prefix];
      const hdr      = {};
      for (const k of Object.keys(header)) {
        if (k === '__proto__') Object.defineProperty(hdr, k, { value: header[k], enumerable: true, writable: true, configurable: true });
        else hdr[k] = header[k];
      }
      hdr.n = n;
      const ordered = [
        'n',
        ...Object.keys(c.headerKeys).filter(k => hasOwn(hdr, k) && k !== 'n'),
        ...Object.keys(hdr).filter(k => !hasOwn(c.headerKeys, k)),
      ];
      for (const k of ordered) {
        const v = hdr[k];
        if (isNil(v)) continue;
        const hk = hasOwn(c.headerKeys, k) ? c.headerKeys[k] : undefined;
        if (k === 'v' && Number(v) === 1 && hk && hk.default === 1) continue; // la versión por defecto es implícita
        let txt        ;
        if (!hk) {
          txt = codec.escapeScalar(String(v));
        } else if (hk.type === 'list') {
          if (!Array.isArray(v)) throw new MiniError(E_TYPE, 0, 'list expected', k);
          txt = encList(v, headerKeyAsField(hk), sep);
        } else if (hk.type === 'tuple') {
          if (typeof v !== 'object') throw new MiniError(E_TYPE, 0, 'tuple expects an object', k);
          txt = hk.items
            .map(cmp => {
              const cv = get(v       , cmp.name);
              return isNil(cv) ? '' : codec.escapeElement(encodeScalar(cv, cmp), sep);
            })
            .join(sep);
        } else {
          txt = codec.escapeScalar(encodeScalar(v, headerKeyAsField(hk)));
        }
        parts.push(`${k}=${txt}`);
      }
      return parts.join(codec.FIELD_SEP);
    }

    /** Codifica un registro; las extensiones nulas del final se omiten. */
    function encodeRecord(rec     , c          )         {
      const sep = c.list_separator;
      const cells = c.core.map(f => encodeField(get(rec, f.name), f, sep, rec));
      const ext = c.extensions.map(f => encodeField(get(rec, f.name), f, sep, rec));
      while (ext.length && ext[ext.length - 1] === '') ext.pop();
      return [...cells, ...ext].join(codec.FIELD_SEP);
    }

    /** Serializa un objeto canónico `{header, <records_key>: [...]}` a texto .mini (sin LF final). */
    function dumps(obj     , contract                         )         {
      const c = normalizeContract(contract);
      let records = get(obj, c.records_key);
      if (isNil(records)) records = get(obj, 'records');
      if (isNil(records)) records = [];
      if (!Array.isArray(records)) throw new MiniError(E_TYPE, 0, `'${c.records_key}' must be an array`);
      const header = (get(obj, 'header') || {})       ;
      if (typeof header !== 'object' || Array.isArray(header)) throw new MiniError(E_TYPE, 1, 'header must be an object');
      const n = records.length;
      const lines = [atLine(() => encodeHeader(header, c, n), 1)];
      records.forEach((r, i) => {
        if (!r || typeof r !== 'object' || Array.isArray(r)) throw new MiniError(E_TYPE, i + 2, 'record must be an object');
        lines.push(atLine(() => encodeRecord(r       , c), i + 2));
      });
      const text = lines.join('\n');
      try {
        parse(text, c, { strict: true });
      } catch (e) {
        if (e instanceof MiniValidationError) throw e.errors[0];
        throw e;
      }
      return text;
    }

    /** Ejecuta `encode` y ubica en `lineno` un MiniError sin línea. */
    function atLine(encode              , lineno        )         {
      try {
        return encode();
      } catch (e) {
        if (e instanceof MiniError && !e.line) throw new MiniError(e.code, lineno, e.message, e.field);
        throw e;
      }
    }
    return { encodeField, encodeHeader, encodeRecord, dumps };
  })();

  // ---------------------------------------------------------------- prompt.ts
  __m["prompt"] = (function () {
    const { normalizeContract } = __m["contract"];
                                                                       

                                   

    function fieldDoc(f       , sep        , lang        )         {
      const es = lang === 'es';
      const opt = f.optional ? (es ? ' (opcional)' : ' (optional)') : '';
      if (f.type === 'enum') {
        return `${f.name}: ${es ? 'uno de ' : 'one of '}{${(f.values || []).join('|')}}${opt}`;
      }
      if (f.type === 'list' || f.type === 'mlist') {
        const it = f.item !== 'enum' ? f.item : '{' + (f.item_values || []).join('|') + '}';
        let rng = '';
        if (f.min !== null || f.max !== null) {
          const lo = Math.trunc(Number(f.min || 0));
          const hi = f.max ? String(Math.trunc(Number(f.max))) : '∞';
          rng = es ? `, entre ${lo} y ${hi} elementos` : `, ${lo} to ${hi} elements`;
        }
        let base = es ? `${f.name}: lista de ${it} separada por '${sep}'${rng}` : `${f.name}: '${sep}'-separated list of ${it}${rng}`;
        if (f.type === 'mlist') {
          const rules = {
            exactly_one: es ? 'exactamente un' : 'exactly one',
            at_least_one: es ? 'al menos un' : 'at least one',
            at_most_one: es ? 'como máximo un' : 'at most one',
            any: es ? 'cero o más' : 'zero or more',
          }         ;
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
    function formatHint(t        , es         )         {
      if (t === 'date') return es ? ' (AAAA-MM-DD)' : ' (YYYY-MM-DD)';
      if (t === 'decimal') return es ? ' (decimal exacto sin exponente, p. ej. 12.50)' : ' (exact decimal without exponent, e.g. 12.50)';
      return '';
    }

    /** Bloque de especificación para un prompt de sistema (`lang`: 'en' o 'es'). */
    function specBlock(contract                         , lang                = 'en', example         )         {
      const c = normalizeContract(contract);
      const es = lang === 'es';
      const sep = c.list_separator;
      const hk = Object.keys(c.headerKeys).filter(k => k !== 'v');
      const hdrDesc = hk.map(k => `${k}=<${c.headerKeys[k].type}>${c.headerKeys[k].required ? '' : '?'}`).join(', ');
      const core = c.core.map((f, i) => `  ${i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
      const ext = c.extensions.map((f, i) => `  ${c.core.length + i + 1}. ${fieldDoc(f, sep, lang)}`).join('\n');
      const L           = [];
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
    return { specBlock };
  })();

  // ---------------------------------------------------------------- stream.ts
  __m["stream"] = (function () {
    const { isBlank } = __m["codec"];
    const { normalizeContract } = __m["contract"];
    const { MiniError, MiniValidationError } = __m["errors"];
    const { Document, LineEngine } = __m["parser"];
                                                          

    /** Registro emitido en cuanto su línea se cierra con LF. */
                                   
                         
                                  
                   
                                                                         
                    
     

    /** Última línea recibida sin LF final que no pudo validarse (típico de una salida truncada). */
                                       
                   
                   
                                                                                               
                         
                                                        
                        
                          
     

                                    
                                                                                                    
                       
                                                                                  
                                             
                                         
     

                                   
                         
                            
                          
                                                                                  
                              
                                                                        
                       
                               
                    
                                         
                      
                                         
                     
                                                                        
                          
                                          
                                                                                      
                         
                                        
                        
     

                                     
                              
                       
                    
                     
     

                                 
                                                                                                                               
                                                       
                                                                                                   
                                                     
                                  
                              
                                     
                                              
                                            
                                                    
                               
                                        
                              
     

    function countFieldsApprox(line        )         {
      let n = 1;
      for (let i = 0; i < line.length; i++) {
        if (line[i] === '\\') i++;
        else if (line[i] === '|') n++;
      }
      return n;
    }

    function declaredCount(header               )                {
      if (!header || !Object.prototype.hasOwnProperty.call(header, 'n')) return null;
      const n = header.n;
      return typeof n === 'number' && Number.isInteger(n) ? n : null;
    }

    /** Crea un lector incremental para `contract`. */
    function createReader(contract                         , opts                = {})             {
      const c = normalizeContract(contract);
      const strict = opts.strict === true;
      const engine = new LineEngine(c, strict);
      let buffer = '';
      let scanFrom = 0;
      let ended = false;
      let decoder                     = null;
      let reportedErrors = 0;

      const flushErrors = ()       => {
        if (opts.onError) for (; reportedErrors < engine.errors.length; reportedErrors++) opts.onError(engine.errors[reportedErrors]);
        else reportedErrors = engine.errors.length;
      };

      const feedLine = (raw        , out                )       => {
        const hadHeader = engine.header !== null;
        const outcome = engine.feed(raw);
        if (!hadHeader && engine.header !== null && opts.onHeader) {
          opts.onHeader({ prefix: engine.prefix, header: engine.header, line: engine.physical });
        }
        if (outcome && outcome.record) {
          const rec               = { record: outcome.record, line: outcome.line, index: engine.records.length - 1 };
          out.push(rec);
          if (opts.onRecord) opts.onRecord(rec);
        }
        flushErrors();
      };

      const toText = (chunk                     )         => {
        if (typeof chunk === 'string') return chunk;
        if (!decoder) decoder = new TextDecoder('utf-8');
        return decoder.decode(chunk, { stream: true });
      };

      const reader             = {
        push(chunk                     )                 {
          if (ended) throw new Error('mini reader already ended');
          const out                 = [];
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

        end(chunk                      )               {
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
          let incomplete                          = null;
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
          const received = engine.recordLineCount;
          const missing = expected === null ? 0 : Math.max(0, expected - received);
          const excess = expected === null ? 0 : Math.max(0, received - expected);
          const result               = {
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
            received: engine.recordLineCount,
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
    async function* readRecords(
      chunks                                                                    ,
      contract                         ,
      opts                = {},
    )                                                   {
      const reader = createReader(contract, opts);
      for await (const chunk of chunks                                      ) {
        for (const rec of reader.push(chunk)) yield rec;
      }
      return reader.end();
    }
    return { createReader, readRecords };
  })();

  return Object.freeze({
    E_NO_HEADER: __m["errors"].E_NO_HEADER,
    E_UNKNOWN_PREFIX: __m["errors"].E_UNKNOWN_PREFIX,
    E_NO_COUNT: __m["errors"].E_NO_COUNT,
    E_COUNT_MISMATCH: __m["errors"].E_COUNT_MISMATCH,
    E_ARITY: __m["errors"].E_ARITY,
    E_TYPE: __m["errors"].E_TYPE,
    E_LIST_ARITY: __m["errors"].E_LIST_ARITY,
    E_MARKER: __m["errors"].E_MARKER,
    E_ESCAPE: __m["errors"].E_ESCAPE,
    E_ENUM: __m["errors"].E_ENUM,
    E_UNIQUE: __m["errors"].E_UNIQUE,
    E_HEADER_KEY: __m["errors"].E_HEADER_KEY,
    E_RANGE: __m["errors"].E_RANGE,
    E_CONTRACT: __m["errors"].E_CONTRACT,
    E_FORK: __m["errors"].E_FORK,
    MiniError: __m["errors"].MiniError,
    MiniValidationError: __m["errors"].MiniValidationError,
    validDate: __m["values"].validDate,
    normalizeDecimal: __m["values"].normalizeDecimal,
    decimalBound: __m["values"].decimalBound,
    compareDecimal: __m["values"].compareDecimal,
    decodeScalar: __m["values"].decodeScalar,
    formatNumber: __m["values"].formatNumber,
    encodeScalar: __m["values"].encodeScalar,
    scalarEqual: __m["values"].scalarEqual,
    FIELD_SEP: __m["codec"].FIELD_SEP,
    MARKER: __m["codec"].MARKER,
    ESCAPE: __m["codec"].ESCAPE,
    QUOTE: __m["codec"].QUOTE,
    isSpace: __m["codec"].isSpace,
    isBlank: __m["codec"].isBlank,
    trimSpace: __m["codec"].trimSpace,
    tokenize: __m["codec"].tokenize,
    splitOn: __m["codec"].splitOn,
    stripToks: __m["codec"].stripToks,
    textOf: __m["codec"].textOf,
    splitFields: __m["codec"].splitFields,
    splitList: __m["codec"].splitList,
    escapeScalar: __m["codec"].escapeScalar,
    escapeElement: __m["codec"].escapeElement,
    SCALAR_TYPES: __m["contract"].SCALAR_TYPES,
    COMPOSITE_TYPES: __m["contract"].COMPOSITE_TYPES,
    ALL_TYPES: __m["contract"].ALL_TYPES,
    MARKER_MODES: __m["contract"].MARKER_MODES,
    headerKeyAsField: __m["contract"].headerKeyAsField,
    isContract: __m["contract"].isContract,
    normalizeContract: __m["contract"].normalizeContract,
    fieldSignature: __m["contract"].fieldSignature,
    signature: __m["contract"].signature,
    checkFork: __m["contract"].checkFork,
    contractToJSON: __m["contract"].contractToJSON,
    Document: __m["parser"].Document,
    put: __m["parser"].put,
    shallowCopy: __m["parser"].shallowCopy,
    parseHeader: __m["parser"].parseHeader,
    decodeField: __m["parser"].decodeField,
    LineEngine: __m["parser"].LineEngine,
    parse: __m["parser"].parse,
    detectPrefix: __m["parser"].detectPrefix,
    encodeField: __m["serializer"].encodeField,
    encodeHeader: __m["serializer"].encodeHeader,
    encodeRecord: __m["serializer"].encodeRecord,
    dumps: __m["serializer"].dumps,
    specBlock: __m["prompt"].specBlock,
    createReader: __m["stream"].createReader,
    readRecords: __m["stream"].readRecords,
    VERSION: "1.1.0",
    SPEC_VERSION: "1.1",
  });
});
