// Evaluación de una respuesta con cada enfoque, comparada contra los datos esperados.
// Estados por registro: ok | silencioso (aceptado con datos incorrectos) | perdido (sin aviso) | regenerar (detectado)
(function (root) {
  const CAMPOS = ['id', 'canal', 'categoria', 'prioridad', 'monto', 'resumen'];
  const igual = (a, b) => CAMPOS.every(k => (a[k] ?? null) === (b[k] ?? null));

  // Lo que escribe un equipo con un prompt propio: "responde una línea por reclamo separada por |"
  function parseCasero(texto) {
    return texto.trim().split('\n').filter(l => l.trim()).map(l => {
      const [id, canal, categoria, prioridad, monto, resumen] = l.split('|');
      return { id, canal, categoria, prioridad: parseInt(prioridad, 10), monto: monto ? parseFloat(monto) : null, resumen };
    });
  }

  function evaluar(enfoque, texto, D, MINI, C) {
    const verdad = D.verdad;
    let aceptados = [], errores = [], falloTotal = null;
    if (enfoque === 'casero') {
      aceptados = parseCasero(texto);
    } else if (enfoque === 'json') {
      try { aceptados = (JSON.parse(texto).reclamos || []); }
      catch (e) { falloTotal = 'JSON.parse: ' + e.message; }
    } else {
      const doc = MINI.parse(texto, C, { strict: false });
      aceptados = doc.records;
      errores = doc.errors.map(e => ({ codigo: e.code, linea: e.line, campo: e.field, mensaje: e.message }));
    }
    const porId = {};
    aceptados.forEach(r => { if (r && r.id !== undefined && !(r.id in porId)) porId[r.id] = r; });
    const estados = verdad.map(v => {
      if (falloTotal) return 'regenerar';
      const r = porId[v.id];
      if (r) return igual(r, v) ? 'ok' : 'silencioso';
      return errores.length ? 'regenerar' : 'perdido';
    });
    const tabla = enfoque === 'mini' ? D.tokens_registro_mini : D.tokens_registro_json;
    const regenerarTokens = falloTotal
      ? D.tokens.o200k_base.json
      : verdad.reduce((s, v, i) => s + (estados[i] === 'regenerar' ? tabla[v.id] : 0), 0);
    const cuenta = k => estados.filter(e => e === k).length;
    return { estados, errores, falloTotal, regenerarTokens,
      resumen: { ok: cuenta('ok'), silencioso: cuenta('silencioso'), perdido: cuenta('perdido'), regenerar: cuenta('regenerar') } };
  }

  const api = { evaluar, parseCasero };
  if (typeof module === 'object' && module.exports) module.exports = api; else root.LOGICA = api;
})(typeof self !== 'undefined' ? self : this);
