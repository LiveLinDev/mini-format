/* Economía de .mini frente a JSON (espejo de experiments/economia/calculo.py).
 *
 * Módulo PURO: sin DOM, sin red, sin reloj, sin archivos. Carga igual en el navegador
 * (window.EconomiaCalculo) y en Node (require). Los mismos vectores dorados
 * (evidencia/vectores/economia.json) deben dar EXACTAMENTE las mismas cadenas que la
 * versión de Python.
 *
 * Política numérica: aritmética RACIONAL exacta con BigInt (nunca Number); el redondeo
 * ocurre una sola vez por cifra de salida, ROUND_HALF_UP (empates hacia la mayor
 * magnitud). Los decimales entran como CADENAS ("0.075") o enteros; un Number no entero
 * se rechaza. Sin tarifa verificada, o con un dato de usage ausente, el resultado es
 * null con "estado" y "motivo": jamás un precio o un cero inventado.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.EconomiaCalculo = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const MILLON = 1000000n;
  const DEC_USD = 6, DEC_USD_FINO = 9, DEC_PCT = 4, DEC_RAZON = 6, DEC_LOTES = 4;
  const AVISO_PROYECCION_ES = 'Proyección aritmética según la proporción medida; no es la respuesta real de un modelo con un millón de tokens.';
  const AVISO_PROYECCION_EN = 'Arithmetic projection from the measured ratio; it is not the real response of a model producing one million tokens.';
  const AVISO_PRESUPUESTO_ES = 'El presupuesto es un valor ilustrativo de la interfaz: no autoriza gastar nada ni implica que exista ese dinero.';
  const AVISO_PRESUPUESTO_EN = 'The budget is an illustrative interface value: it does not authorize spending anything nor imply that the money exists.';
  const CATEGORIAS = ['entrada_sin_cache', 'entrada_cache_lectura', 'entrada_cache_escritura', 'salida', 'razonamiento', 'otros'];
  const CATEGORIAS_TOKENS = [
    ['entrada_sin_cache', 'entrada_sin_cache', 'entrada_sin_cache_por_millon'],
    ['entrada_cache_lectura', 'entrada_cache_lectura', 'entrada_cache_lectura_por_millon'],
    ['entrada_cache_escritura', 'entrada_cache_escritura', 'entrada_cache_escritura_por_millon'],
    ['salida', 'salida', 'salida_por_millon'],
  ];
  const POLITICA = {
    aritmetica: 'racional exacta (enteros); sin float',
    redondeo: 'ROUND_HALF_UP (empates hacia la mayor magnitud), una vez por cifra de salida',
    decimales: { usd: DEC_USD, usd_fino: DEC_USD_FINO, porcentaje: DEC_PCT, razon: DEC_RAZON, lotes: DEC_LOTES, tokens: 0 },
    cantidades_contables: 'hacia abajo (floor)',
  };

  // ------------------------------------------------------------ racionales
  function gcd(a, b) { if (a < 0n) a = -a; if (b < 0n) b = -b; while (b) { const t = a % b; a = b; b = t; } return a; }
  function fr(n, d) {
    if (d === undefined) d = 1n;
    if (d === 0n) throw new Error('división por cero');
    if (d < 0n) { n = -n; d = -d; }
    const g = gcd(n, d) || 1n;
    return { n: n / g, d: d / g };
  }
  const F0 = fr(0n);
  const add = (a, b) => fr(a.n * b.d + b.n * a.d, a.d * b.d);
  const sub = (a, b) => fr(a.n * b.d - b.n * a.d, a.d * b.d);
  const mul = (a, b) => fr(a.n * b.n, a.d * b.d);
  const div = (a, b) => fr(a.n * b.d, a.d * b.n);
  const cmp = (a, b) => { const l = a.n * b.d, r = b.n * a.d; return l < r ? -1 : (l > r ? 1 : 0); };
  const esCero = (a) => a.n === 0n;
  const fromInt = (n) => fr(BigInt(n));
  const DEC_RE = /^[+-]?\d+(?:\.\d+)?$/;
  const ENT_RE = /^\d+$/;
  const isObj = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
  const falta = (x) => x === undefined || x === null;
  function dflt(o, k, d) { return (o && Object.prototype.hasOwnProperty.call(o, k) && o[k] !== undefined) ? o[k] : d; }

  function aFraccion(x, campo) {
    campo = campo || 'valor';
    if (typeof x === 'boolean') throw new TypeError(campo + ': no se admite bool; use una cadena decimal');
    if (typeof x === 'bigint') return fr(x);
    if (typeof x === 'number') {
      if (!Number.isSafeInteger(x)) throw new TypeError(campo + ': no se admite float; use una cadena decimal (p. ej. "0.075")');
      return fr(BigInt(x));
    }
    if (isRacional(x)) return x;
    if (typeof x === 'string') {
      const s = x.trim();
      if (!DEC_RE.test(s)) throw new Error(campo + ': cadena decimal inválida ' + JSON.stringify(x));
      const neg = s[0] === '-';
      const limpio = s.replace(/^[+-]/, '');
      const partes = limpio.split('.');
      const frac = partes[1] || '';
      const n = BigInt(partes[0] + frac) * (neg ? -1n : 1n);
      return fr(n, 10n ** BigInt(frac.length));
    }
    throw new TypeError(campo + ': tipo no admitido');
  }
  function isRacional(x) { return isObj(x) && typeof x.n === 'bigint' && typeof x.d === 'bigint'; }
  function noNeg(x, campo) {
    const v = aFraccion(x, campo);
    if (v.n < 0n) throw new Error(campo + ': no puede ser negativo');
    return v;
  }
  function tokens(x, campo) {
    let v;
    if (typeof x === 'boolean') throw new TypeError(campo + ': use un entero');
    if (typeof x === 'bigint') v = x;
    else if (typeof x === 'number') {
      if (!Number.isSafeInteger(x)) throw new TypeError(campo + ': use un entero');
      v = BigInt(x);
    } else if (typeof x === 'string' && ENT_RE.test(x.trim())) v = BigInt(x.trim());
    else throw new Error(campo + ': se esperaba un entero no negativo');
    if (v < 0n) throw new Error(campo + ': no puede ser negativo');
    return v;
  }
  function redondear(x, dec) {
    const n = x.n * (10n ** BigInt(dec));
    const d = x.d;
    const an = n < 0n ? -n : n;
    let q = an / d;
    const r = an % d;
    if (2n * r >= d) q += 1n;
    return n < 0n ? -q : q;
  }
  function fmt(x, dec) {
    const q = redondear(x, dec);
    const neg = q < 0n;
    let s = (neg ? -q : q).toString();
    const signo = neg ? '-' : '';
    if (dec === 0) return signo + s;
    s = s.padStart(dec + 1, '0');
    return signo + s.slice(0, s.length - dec) + '.' + s.slice(s.length - dec);
  }
  function piso(x) { let q = x.n / x.d; if (x.n < 0n && x.n % x.d !== 0n) q -= 1n; return q; }
  function techo(x) { return -piso(fr(-x.n, x.d)); }

  // ---------------------------------------------------------------- tarifas
  function buscarTarifa(tarifas, proveedor, modeloApiId) {
    if (isObj(tarifas)) tarifas = [tarifas];
    const p = String(proveedor || '').trim().toLowerCase();
    for (const t of (tarifas || [])) {
      if (String(t.proveedor || '').trim().toLowerCase() !== p) continue;
      if (t.modelo_api_id === modeloApiId || (Array.isArray(t.alias) && t.alias.indexOf(modeloApiId) >= 0)) return t;
    }
    return null;
  }
  function precio(tarifa, campo) { const v = tarifa[campo]; return falta(v) ? null : noNeg(v, campo); }
  function tarifaUtilizable(tarifa, proveedor, modelo) {
    if (!tarifa) return ['tarifa_no_verificada', 'tarifa no verificada: no hay tarifa para ' + proveedor + '/' + modelo];
    if (tarifa.estado !== 'verificada') return ['tarifa_no_verificada', 'tarifa no verificada: ' + proveedor + '/' + modelo + ' figura como ' + tarifa.estado];
    if (dflt(tarifa, 'moneda', 'USD') !== 'USD') throw new Error('solo se admite moneda USD');
    return null;
  }
  function tarifaDe(entrada, alt) {
    const t = (alt && alt.tarifa) || entrada.tarifa;
    if (!isObj(t)) throw new Error('falta la tarifa');
    return t;
  }

  // ---------------------------------------------------------- razón y ahorro
  function razonYAhorro(tMini, tJson) {
    if (falta(tMini) || falta(tJson)) {
      return { estado: 'no_definido', motivo: 'falta T_MINI o T_JSON', razon: null, ahorro_salida_pct: null, hay_ahorro: null };
    }
    const tm = tokens(tMini, 't_mini');
    const tj = tokens(tJson, 't_json');
    if (tj === 0n) {
      return { estado: 'no_definido', motivo: 'T_JSON = 0: la razón no está definida', razon: null, ahorro_salida_pct: null, hay_ahorro: null };
    }
    const r = fr(tm, tj);
    const ahorro = mul(fromInt(100), sub(fromInt(1), r));
    return { estado: 'calculado', motivo: null, razon: fmt(r, DEC_RAZON), ahorro_salida_pct: fmt(ahorro, DEC_PCT), hay_ahorro: cmp(ahorro, F0) > 0 };
  }
  function razonExacta(entrada) {
    if (!falta(entrada.razon)) return [noNeg(entrada.razon, 'razon'), null];
    const res = razonYAhorro(entrada.t_mini, entrada.t_json);
    if (res.estado !== 'calculado') return [null, res.motivo];
    return [fr(tokens(entrada.t_mini, 't_mini'), tokens(entrada.t_json, 't_json')), null];
  }

  // ------------------------------------------------------ costo por solicitud
  function costoUso(usage, tarifa) {
    if (!isObj(usage)) return [null, ['usage_no_informado', 'usage no informado: el intento no trae usage']];
    const cats = {};
    const pSalida = precio(tarifa, 'salida_por_millon');
    for (const [cat, campo, pcampo] of CATEGORIAS_TOKENS) {
      let tk = usage[campo];
      tk = falta(tk) ? null : tokens(tk, campo);
      const pr = precio(tarifa, pcampo);
      if (pr === null) {
        if (tk === null || tk === 0n) { cats[cat] = F0; continue; }
        return [null, ['tarifa_no_verificada', 'tarifa no verificada: falta el precio de ' + pcampo + ' y el intento usó ' + tk + ' tokens']];
      }
      if (tk === null) return [null, ['usage_no_informado', 'usage no informado: ' + campo]];
      cats[cat] = div(mul(fr(tk), pr), fr(MILLON));
    }
    const incl = falta(usage.razonamiento_incluido_en_salida) ? null : usage.razonamiento_incluido_en_salida;
    let raz = usage.razonamiento;
    raz = falta(raz) ? null : tokens(raz, 'razonamiento');
    if (incl === true) {
      if (raz !== null && !falta(usage.salida) && raz > tokens(usage.salida, 'salida')) {
        throw new Error('razonamiento mayor que salida con razonamiento_incluido_en_salida = true');
      }
      cats.razonamiento = F0;
    } else if (incl === false) {
      if (raz === null) return [null, ['usage_no_informado', 'usage no informado: razonamiento']];
      if (raz === 0n) cats.razonamiento = F0;
      else if (pSalida === null) return [null, ['tarifa_no_verificada', 'tarifa no verificada: falta el precio de salida_por_millon y el intento usó ' + raz + ' tokens de razonamiento']];
      else cats.razonamiento = div(mul(fr(raz), pSalida), fr(MILLON));
    } else {
      if (raz === null || raz === 0n) cats.razonamiento = F0;
      else return [null, ['usage_no_informado', 'usage no informado: razonamiento_incluido_en_salida (hay tokens de razonamiento y no se sabe si ya están en salida)']];
    }
    const otros = usage.otros_usd || {};
    let suma = F0;
    for (const nombre of Object.keys(otros).sort()) suma = add(suma, noNeg(otros[nombre], 'otros_usd.' + nombre));
    cats.otros = suma;
    return [cats, null];
  }
  function fmtCats(cats) {
    if (cats === null) return null;
    const o = {};
    for (const c of CATEGORIAS) o[c] = fmt(cats[c], DEC_USD);
    return o;
  }
  function costoIntento(intento, tarifas) {
    const prov = intento.proveedor || '';
    const mod = intento.modelo || '';
    const t = buscarTarifa(tarifas, prov, mod);
    const bloqueo = tarifaUtilizable(t, prov, mod);
    if (bloqueo) return [null, bloqueo];
    return costoUso(intento.usage, t);
  }
  function sumar(lista) {
    const tot = {};
    for (const c of CATEGORIAS) tot[c] = F0;
    for (const cats of lista) for (const c of CATEGORIAS) tot[c] = add(tot[c], cats[c]);
    return tot;
  }
  function totalCats(cats) { let s = F0; for (const c of CATEGORIAS) s = add(s, cats[c]); return s; }
  function idGrupo(s) {
    if (falta(s.id) || String(s.id) === '') throw new Error('toda solicitud necesita un id');
    return falta(s.grupo) ? String(s.id) : String(s.grupo);
  }
  function solicitudExacta(solicitud, tarifas) {
    const intentosOut = [];
    const ok = [];
    let falla = null;
    for (const it of (solicitud.intentos || [])) {
      const [cats, err] = costoIntento(it, tarifas);
      intentosOut.push({
        fase: falta(it.fase) ? null : it.fase, modelo: falta(it.modelo) ? null : it.modelo, proveedor: falta(it.proveedor) ? null : it.proveedor,
        estado: err === null ? 'calculado' : err[0], motivo: err === null ? null : err[1],
        costo_usd: cats === null ? null : fmt(totalCats(cats), DEC_USD), categorias: fmtCats(cats),
      });
      if (err === null) ok.push(cats); else if (falla === null) falla = err;
    }
    const base = { id: String(solicitud.id), grupo: idGrupo(solicitud), n_intentos: intentosOut.length, intentos: intentosOut };
    if (falla === null) {
      const tot = sumar(ok);
      Object.assign(base, { estado: 'calculado', motivo: null, costo_usd: fmt(totalCats(tot), DEC_USD), categorias: fmtCats(tot), costo_parcial_verificado_usd: null });
    } else {
      Object.assign(base, { estado: falla[0], motivo: falla[1], costo_usd: null, categorias: null,
        costo_parcial_verificado_usd: ok.length ? fmt(totalCats(sumar(ok)), DEC_USD) : null });
    }
    return [base, ok, falla];
  }
  function costoSolicitud(solicitud, tarifas) { return solicitudExacta(solicitud, tarifas)[0]; }

  function valorDeGrupo(solicitudes, grupo, campo) {
    for (const s of solicitudes) {
      if (String(s.id) === grupo) return falta(s[campo]) ? null : tokens(s[campo], campo);
    }
    const vistos = new Set();
    for (const s of solicitudes) if (!falta(s[campo])) vistos.add(tokens(s[campo], campo).toString());
    if (vistos.size > 1) throw new Error('grupo ' + grupo + ': ' + campo + ' inconsistente entre solicitudes; declárelo solo en la solicitud original');
    return vistos.size ? BigInt(Array.from(vistos)[0]) : null;
  }

  function costoPor1000Validos(costoTotalUsd, registrosValidosFinales) {
    if (falta(costoTotalUsd)) {
      return { estado: 'no_definido', motivo: 'el costo total no está calculado', costo_por_1000_validos_usd: null, costo_incurrido_usd: null };
    }
    const costo = noNeg(costoTotalUsd, 'costo_total_usd');
    if (falta(registrosValidosFinales)) {
      return { estado: 'no_definido', motivo: 'registros_validos_finales no informado', costo_por_1000_validos_usd: null, costo_incurrido_usd: fmt(costo, DEC_USD) };
    }
    const v = tokens(registrosValidosFinales, 'registros_validos_finales');
    if (v === 0n) {
      return { estado: 'no_definido', motivo: '0 registros válidos finales: el costo por 1000 válidos no está definido', costo_por_1000_validos_usd: null, costo_incurrido_usd: fmt(costo, DEC_USD) };
    }
    return { estado: 'calculado', motivo: null, costo_por_1000_validos_usd: fmt(div(mul(fromInt(1000), costo), fr(v)), DEC_USD), costo_incurrido_usd: fmt(costo, DEC_USD) };
  }

  function costoTotal(solicitudes, tarifas) {
    const orden = [];
    const porGrupo = {};
    for (const s of solicitudes) {
      const g = idGrupo(s);
      if (!Object.prototype.hasOwnProperty.call(porGrupo, g)) { porGrupo[g] = []; orden.push(g); }
      porGrupo[g].push(s);
    }
    const gruposOut = [];
    const catsOkTotal = [];
    let falla = null;
    let nInt = 0;
    let solTotal = 0n, valTotal = 0n;
    for (const g of orden) {
      const ss = porGrupo[g];
      const catsG = [];
      let fallaG = null;
      let nIntG = 0;
      for (const s of ss) {
        const [res, ok, f] = solicitudExacta(s, tarifas);
        nIntG += res.n_intentos;
        for (const c of ok) catsG.push(c);
        if (f !== null && fallaG === null) fallaG = f;
      }
      nInt += nIntG;
      for (const c of catsG) catsOkTotal.push(c);
      if (fallaG !== null && falla === null) falla = fallaG;
      const pedidos = valorDeGrupo(ss, g, 'registros_solicitados');
      const validos = valorDeGrupo(ss, g, 'registros_validos_finales');
      solTotal = (solTotal === null || pedidos === null) ? null : solTotal + pedidos;
      valTotal = (valTotal === null || validos === null) ? null : valTotal + validos;
      gruposOut.push({
        grupo: g, n_solicitudes: ss.length, n_intentos: nIntG,
        estado: fallaG === null ? 'calculado' : fallaG[0],
        costo_usd: fallaG === null ? fmt(totalCats(sumar(catsG)), DEC_USD) : null,
        registros_solicitados: pedidos === null ? null : pedidos.toString(),
        registros_validos_finales: validos === null ? null : validos.toString(),
      });
    }
    const salida = {
      moneda: 'USD', n_solicitudes: solicitudes.length, n_intentos: nInt, grupos: gruposOut,
      registros_solicitados: solTotal === null ? null : solTotal.toString(),
      registros_validos_finales: valTotal === null ? null : valTotal.toString(),
    };
    const tot = sumar(catsOkTotal);
    let p1000;
    if (falla === null) {
      const total = totalCats(tot);
      Object.assign(salida, { estado: 'calculado', motivo: null, costo_total_usd: fmt(total, DEC_USD), categorias: fmtCats(tot), costo_parcial_verificado_usd: null });
      p1000 = costoPor1000Validos(total, valTotal);
    } else {
      Object.assign(salida, { estado: falla[0], motivo: falla[1], costo_total_usd: null, categorias: null,
        costo_parcial_verificado_usd: catsOkTotal.length ? fmt(totalCats(tot), DEC_USD) : null });
      p1000 = { estado: 'no_definido', motivo: 'el costo total no está calculado (' + falla[1] + ')', costo_por_1000_validos_usd: null, costo_incurrido_usd: null };
    }
    salida.costo_por_1000_validos = p1000;
    return salida;
  }

  // --------------------------------------------------------------- perfiles
  function perfil(p) {
    const fValid = noNeg(dflt(p, 'fraccion_validos', '1'), 'fraccion_validos');
    const frr = noNeg(dflt(p, 'fraccion_reparada', '1'), 'fraccion_reparada');
    if (cmp(fValid, fromInt(1)) > 0 || cmp(frr, fromInt(1)) > 0) throw new Error('fraccion_validos y fraccion_reparada deben estar entre 0 y 1');
    return {
      nombre: falta(p.nombre) ? null : p.nombre,
      I: fr(tokens(dflt(p, 'tokens_instruccion', 0), 'tokens_instruccion')),
      en_cache: Boolean(dflt(p, 'instruccion_en_cache', false)),
      e: noNeg(dflt(p, 'tokens_entrada_por_registro', 0), 'tokens_entrada_por_registro'),
      o: noNeg(dflt(p, 'tokens_salida_por_registro', 0), 'tokens_salida_por_registro'),
      c: noNeg(dflt(p, 'tokens_salida_fijos', 0), 'tokens_salida_fijos'),
      f_valid: fValid,
      R: noNeg(dflt(p, 'reintentos_por_lote', 0), 'reintentos_por_lote'),
      fr: frr,
    };
  }
  function SinPrecio(campo) { this.campo = campo; }

  function costoLoteInterno(p, tarifa, k) {
    const pIn = precio(tarifa, 'entrada_sin_cache_por_millon');
    const pCa = precio(tarifa, 'entrada_cache_lectura_por_millon');
    const pOut = precio(tarifa, 'salida_por_millon');
    const req = (pr, campo, tk) => {
      if (esCero(tk)) return F0;
      if (pr === null) throw new SinPrecio(campo);
      return div(mul(tk, pr), fr(MILLON));
    };
    let entrada, salida, tokSal;
    try {
      const instr = p.en_cache ? req(pCa, 'entrada_cache_lectura_por_millon', p.I) : req(pIn, 'entrada_sin_cache_por_millon', p.I);
      entrada = add(instr, req(pIn, 'entrada_sin_cache_por_millon', mul(k, p.e)));
      tokSal = add(mul(p.o, k), p.c);
      salida = req(pOut, 'salida_por_millon', tokSal);
    } catch (ex) {
      if (ex instanceof SinPrecio) return [null, ['tarifa_no_verificada', 'tarifa no verificada: falta el precio de ' + ex.campo]];
      throw ex;
    }
    const reint = mul(p.R, add(entrada, mul(p.fr, salida)));
    return [{ entrada: entrada, salida: salida, reintentos: reint, total: add(add(entrada, salida), reint), tokens_salida: tokSal, registros_validos: mul(k, p.f_valid) }, null];
  }
  function costoLote(entrada) {
    const tarifa = tarifaDe(entrada);
    const bloqueo = tarifaUtilizable(tarifa, tarifa.proveedor, tarifa.modelo_api_id);
    const k = noNeg(entrada.k, 'k');
    if (esCero(k)) throw new Error('k debe ser mayor que 0');
    if (bloqueo) return { estado: bloqueo[0], motivo: bloqueo[1], costo_lote_usd: null };
    const [c, err] = costoLoteInterno(perfil(entrada.perfil), tarifa, k);
    if (err) return { estado: err[0], motivo: err[1], costo_lote_usd: null };
    return {
      estado: 'calculado', motivo: null, costo_lote_usd: fmt(c.total, DEC_USD),
      entrada_usd: fmt(c.entrada, DEC_USD), salida_usd: fmt(c.salida, DEC_USD), reintentos_usd: fmt(c.reintentos, DEC_USD),
      tokens_salida_por_lote: fmt(c.tokens_salida, DEC_LOTES), registros_validos_por_lote: fmt(c.registros_validos, DEC_LOTES),
    };
  }

  // -------------------------------------------------------------- escenario A
  function escenarioA(entrada) {
    const tarifa = tarifaDe(entrada);
    const bloqueo = tarifaUtilizable(tarifa, tarifa.proveedor, tarifa.modelo_api_id);
    const ref = noNeg(dflt(entrada, 'tokens_json_referencia', 1000000), 'tokens_json_referencia');
    const out = {
      tipo: 'proyeccion', aviso_es: AVISO_PROYECCION_ES, aviso_en: AVISO_PROYECCION_EN,
      tokens_json_referencia: fmt(ref, 0), politica_redondeo: 'ROUND_HALF_UP',
    };
    const [r, motivoR] = razonExacta(entrada);
    out.razon = r === null ? null : fmt(r, DEC_RAZON);
    out.tokens_mini_equivalentes = r === null ? null : fmt(mul(ref, r), 0);
    const so = { estado: null, motivo: null, costo_json_usd: null, costo_mini_usd: null, ahorro_usd: null, ahorro_pct: null, hay_ahorro: null };
    if (r === null) { so.estado = 'no_definido'; so.motivo = motivoR; }
    else if (bloqueo) { so.estado = bloqueo[0]; so.motivo = bloqueo[1]; }
    else {
      const pOut = precio(tarifa, 'salida_por_millon');
      if (pOut === null) { so.estado = 'tarifa_no_verificada'; so.motivo = 'tarifa no verificada: falta el precio de salida_por_millon'; }
      else {
        const cj = div(mul(ref, pOut), fr(MILLON));
        const cm = div(mul(mul(ref, r), pOut), fr(MILLON));
        Object.assign(so, {
          estado: 'calculado', costo_json_usd: fmt(cj, DEC_USD), costo_mini_usd: fmt(cm, DEC_USD), ahorro_usd: fmt(sub(cj, cm), DEC_USD),
          ahorro_pct: esCero(cj) ? null : fmt(div(mul(fromInt(100), sub(cj, cm)), cj), DEC_PCT), hay_ahorro: cmp(cj, cm) > 0,
        });
      }
    }
    out.solo_salida = so;
    const tot = entrada.total;
    if (falta(tot)) out.total = null;
    else {
      const k = noNeg(tot.k, 'total.k');
      if (esCero(k)) throw new Error('total.k debe ser mayor que 0');
      const t = { estado: null, motivo: null, lotes_equivalentes: null, costo_json_usd: null, costo_mini_usd: null, ahorro_usd: null,
        ahorro_pct: null, hay_ahorro: null, razon_salida_implicita: null, k: fmt(k, DEC_LOTES) };
      if (bloqueo) { t.estado = bloqueo[0]; t.motivo = bloqueo[1]; }
      else {
        const [cj, ej] = costoLoteInterno(perfil(tot.perfil_json), tarifa, k);
        const [cm, em] = costoLoteInterno(perfil(tot.perfil_mini), tarifa, k);
        if (ej || em) { const e = ej || em; t.estado = e[0]; t.motivo = e[1]; }
        else if (esCero(cj.tokens_salida)) { t.estado = 'no_definido'; t.motivo = 'el perfil JSON no tiene tokens de salida por lote'; }
        else {
          const nLotes = div(ref, cj.tokens_salida);
          const tj = mul(nLotes, cj.total);
          const tm = mul(nLotes, cm.total);
          Object.assign(t, {
            estado: 'calculado', lotes_equivalentes: fmt(nLotes, DEC_LOTES), costo_json_usd: fmt(tj, DEC_USD), costo_mini_usd: fmt(tm, DEC_USD),
            ahorro_usd: fmt(sub(tj, tm), DEC_USD), ahorro_pct: esCero(tj) ? null : fmt(div(mul(fromInt(100), sub(tj, tm)), tj), DEC_PCT),
            hay_ahorro: cmp(tj, tm) > 0, razon_salida_implicita: fmt(div(cm.tokens_salida, cj.tokens_salida), DEC_RAZON),
          });
        }
      }
      out.total = t;
    }
    out.supuestos = {
      misma_tarifa_ambos_formatos: true,
      total_incluye: 'entrada (instrucción y tarea), salida y reintentos por lote',
      solo_salida_incluye: 'únicamente tokens de salida x precio de salida',
      mismo_trabajo: 'los dos formatos producen los mismos registros (mismos lotes)',
      tarifa_estado: falta(tarifa.estado) ? null : tarifa.estado,
      tarifa_fecha_consulta_utc: falta(tarifa.fecha_consulta_utc) ? null : tarifa.fecha_consulta_utc,
    };
    return out;
  }

  // -------------------------------------------------------------- escenario B
  function escenarioB(entrada) {
    const presupuesto = noNeg(dflt(entrada, 'presupuesto_usd', '1000'), 'presupuesto_usd');
    const kDef = entrada.k;
    const altsOut = [];
    const calculados = [];
    for (const alt of (entrada.alternativas || [])) {
      const fila = { nombre: falta(alt.nombre) ? null : alt.nombre, estado: null, motivo: null, costo_lote_usd: null, tokens_salida_por_lote: null,
        registros_validos_por_lote: null, lotes: null, registros_utiles: null, tokens_salida_capacidad: null, gasto_usd: null, sobrante_usd: null };
      let costo = null, tok = null, rv = null;
      if (!falta(alt.perfil)) {
        const tarifa = tarifaDe(entrada, alt);
        const bloqueo = tarifaUtilizable(tarifa, tarifa.proveedor, tarifa.modelo_api_id);
        const k = noNeg(dflt(alt, 'k', kDef), 'k');
        if (esCero(k)) throw new Error('k debe ser mayor que 0');
        if (bloqueo) { fila.estado = bloqueo[0]; fila.motivo = bloqueo[1]; }
        else {
          const [c, err] = costoLoteInterno(perfil(alt.perfil), tarifa, k);
          if (err) { fila.estado = err[0]; fila.motivo = err[1]; }
          else { costo = c.total; tok = c.tokens_salida; rv = c.registros_validos; }
        }
      } else {
        costo = noNeg(alt.costo_lote_usd, 'costo_lote_usd');
        tok = falta(alt.tokens_salida_por_lote) ? null : noNeg(alt.tokens_salida_por_lote, 'tokens_salida_por_lote');
        rv = falta(alt.registros_validos_por_lote) ? null : noNeg(alt.registros_validos_por_lote, 'registros_validos_por_lote');
      }
      if (costo !== null) {
        fila.costo_lote_usd = fmt(costo, DEC_USD);
        fila.tokens_salida_por_lote = tok === null ? null : fmt(tok, DEC_LOTES);
        fila.registros_validos_por_lote = rv === null ? null : fmt(rv, DEC_LOTES);
        if (esCero(costo)) { fila.estado = 'costo_lote_cero'; fila.motivo = 'el costo por lote es 0: no se puede dividir el presupuesto'; }
        else {
          const lotes = piso(div(presupuesto, costo));
          const gasto = mul(fr(lotes), costo);
          fila.estado = 'calculado'; fila.lotes = lotes.toString(); fila.gasto_usd = fmt(gasto, DEC_USD); fila.sobrante_usd = fmt(sub(presupuesto, gasto), DEC_USD);
          fila.registros_utiles = rv === null ? null : piso(mul(fr(lotes), rv)).toString();
          fila.tokens_salida_capacidad = tok === null ? null : piso(mul(fr(lotes), tok)).toString();
        }
      }
      calculados.push(fila.registros_utiles === null ? null : BigInt(fila.registros_utiles));
      altsOut.push(fila);
    }
    const comparacion = [];
    if (altsOut.length) {
      const refNombre = altsOut[0].nombre;
      const refRu = calculados[0];
      for (let i = 1; i < altsOut.length; i++) {
        const ru = calculados[i];
        const d = (ru === null || refRu === null) ? null : (ru - refRu).toString();
        const pct = (ru === null || refRu === null || refRu === 0n) ? null : fmt(mul(fromInt(100), sub(fr(ru, refRu), fromInt(1))), DEC_PCT);
        comparacion.push({ nombre: altsOut[i].nombre, referencia: refNombre, diferencia_registros_utiles: d, registros_utiles_vs_referencia_pct: pct });
      }
    }
    const cien = mul(presupuesto, fromInt(100));
    return {
      tipo: 'capacidad', presupuesto_usd: cien.d === 1n ? fmt(presupuesto, 2) : fmt(presupuesto, DEC_USD),
      presupuesto_ilustrativo: true, aviso_es: AVISO_PRESUPUESTO_ES, aviso_en: AVISO_PRESUPUESTO_EN,
      alternativas: altsOut, comparacion: comparacion,
      supuestos: { lotes: 'floor(presupuesto / costo exacto por lote)', registros_utiles: 'floor(lotes x registros válidos por lote)', costo_lote: 'entrada (instrucción y tarea) + salida + reintentos' },
    };
  }

  // ------------------------------------------------------ punto de equilibrio
  function recta(p, tarifa) {
    const [c0, e0] = costoLoteInterno(p, tarifa, F0);
    const [c1, e1] = costoLoteInterno(p, tarifa, fromInt(1));
    if (e0 || e1) return [null, e0 || e1];
    return [[c0.total, sub(c1.total, c0.total)], null];
  }
  function soloSalida(p) { return Object.assign({}, p, { I: F0, e: F0, R: F0 }); }

  function equilibrio(pj, pm, tarifa, kRef) {
    const [rj, ej] = recta(pj, tarifa);
    const [rm, em] = recta(pm, tarifa);
    const vacio = { estado: null, motivo: null, k_minimo: null, k_maximo: null, k_equilibrio_exacto: null, delta_fijo_usd: null, delta_por_registro_usd: null,
      delta_en_k_referencia_usd: null, ahorro_en_k_referencia_pct: null, mensaje_es: null, mensaje_en: null };
    if (ej || em) { const e = ej || em; return Object.assign(vacio, { estado: e[0], motivo: e[1] }); }
    const b = sub(rj[0], rm[0]);
    const a = sub(rj[1], rm[1]);
    const d1 = add(a, b);
    let estado, kmin = null, kmax = null;
    if (cmp(a, F0) > 0) {
      if (cmp(d1, F0) > 0) { estado = 'siempre_ahorra'; kmin = 1n; }
      else { estado = 'desde_k'; kmin = piso(div(fr(-b.n, b.d), a)) + 1n; }
    } else if (esCero(a)) {
      if (cmp(b, F0) > 0) { estado = 'siempre_ahorra'; kmin = 1n; } else estado = 'sin_ahorro_neto';
    } else if (cmp(d1, F0) > 0) {
      estado = 'solo_hasta_k'; kmin = 1n; kmax = techo(div(b, fr(-a.n, a.d))) - 1n;
    } else estado = 'sin_ahorro_neto';
    let es, en;
    if (estado === 'siempre_ahorra') { es = 'Hay ahorro neto para cualquier tamaño de lote desde 1 registro.'; en = 'There is a net saving for any batch size from 1 record.'; }
    else if (estado === 'desde_k') { es = 'Hay ahorro neto desde ' + kmin + ' registros por lote; con lotes menores no compensa el costo fijo adicional.'; en = 'There is a net saving from ' + kmin + ' records per batch; smaller batches do not offset the extra fixed cost.'; }
    else if (estado === 'solo_hasta_k') { es = 'Hay ahorro neto solo hasta ' + kmax + ' registros por lote; con lotes mayores .mini cuesta más que JSON.'; en = 'There is a net saving only up to ' + kmax + ' records per batch; with larger batches .mini costs more than JSON.'; }
    else { es = 'No hay ahorro neto para ningún tamaño de lote: con estos supuestos .mini cuesta igual o más que JSON.'; en = 'There is no net saving for any batch size: under these assumptions .mini costs the same or more than JSON.'; }
    const raiz = esCero(a) ? null : div(fr(-b.n, b.d), a);
    const res = Object.assign({}, vacio, {
      estado: estado, k_minimo: kmin === null ? null : kmin.toString(), k_maximo: kmax === null ? null : kmax.toString(),
      k_equilibrio_exacto: (raiz !== null && cmp(raiz, F0) > 0) ? fmt(raiz, DEC_LOTES) : null,
      delta_fijo_usd: fmt(b, DEC_USD_FINO), delta_por_registro_usd: fmt(a, DEC_USD_FINO), mensaje_es: es, mensaje_en: en,
    });
    if (kRef !== null) {
      const delta = add(mul(a, kRef), b);
      const base = add(rj[0], mul(rj[1], kRef));
      res.delta_en_k_referencia_usd = fmt(delta, DEC_USD);
      res.ahorro_en_k_referencia_pct = esCero(base) ? null : fmt(div(mul(fromInt(100), delta), base), DEC_PCT);
    }
    return res;
  }
  function puntoEquilibrio(entrada) {
    const tarifa = tarifaDe(entrada);
    const bloqueo = tarifaUtilizable(tarifa, tarifa.proveedor, tarifa.modelo_api_id);
    const kRef = falta(entrada.k_referencia) ? null : noNeg(entrada.k_referencia, 'k_referencia');
    if (kRef !== null && esCero(kRef)) throw new Error('k_referencia debe ser mayor que 0');
    const pj = perfil(entrada.perfil_json), pm = perfil(entrada.perfil_mini);
    let res;
    if (bloqueo) res = { solo_salida: { estado: bloqueo[0], motivo: bloqueo[1] }, total: { estado: bloqueo[0], motivo: bloqueo[1] } };
    else res = { solo_salida: equilibrio(soloSalida(pj), soloSalida(pm), tarifa, kRef), total: equilibrio(pj, pm, tarifa, kRef) };
    res.supuestos = {
      modelo: 'costo por lote lineal en k: costo(k) = A + B x k',
      ahorro_neto: 'costo_json(k) - costo_mini(k) > 0 (un empate no cuenta como ahorro)',
      k: 'registros por lote, enteros desde 1',
      tarifa_estado: falta(tarifa.estado) ? null : tarifa.estado,
      tarifa_fecha_consulta_utc: falta(tarifa.fecha_consulta_utc) ? null : tarifa.fecha_consulta_utc,
    };
    return res;
  }

  // ----------------------------------------------------------------- despacho
  function ejecutar(operacion, entrada) {
    switch (operacion) {
      case 'redondear': return fmt(aFraccion(entrada.valor), Number(entrada.decimales));
      case 'razon_y_ahorro': return razonYAhorro(entrada.t_mini, entrada.t_json);
      case 'costo_solicitud': return costoSolicitud(entrada.solicitud, entrada.tarifas);
      case 'costo_total': return costoTotal(entrada.solicitudes, entrada.tarifas);
      case 'costo_por_1000_validos': return costoPor1000Validos(entrada.costo_total_usd, entrada.registros_validos_finales);
      case 'costo_lote': return costoLote(entrada);
      case 'escenario_a': return escenarioA(entrada);
      case 'escenario_b': return escenarioB(entrada);
      case 'punto_equilibrio': return puntoEquilibrio(entrada);
      case 'buscar_tarifa': {
        const t = buscarTarifa(entrada.tarifas, entrada.proveedor, entrada.modelo_api_id);
        return { encontrada: t !== null, modelo_api_id: t === null ? null : (falta(t.modelo_api_id) ? null : t.modelo_api_id), estado: t === null ? null : (falta(t.estado) ? null : t.estado) };
      }
      default: throw new Error('operación desconocida: ' + operacion);
    }
  }

  return {
    POLITICA: POLITICA, redondear: (x, d) => fmt(aFraccion(x), d), buscarTarifa: buscarTarifa, razonYAhorro: razonYAhorro,
    costoSolicitud: costoSolicitud, costoTotal: costoTotal, costoPor1000Validos: costoPor1000Validos, costoLote: costoLote,
    escenarioA: escenarioA, escenarioB: escenarioB, puntoEquilibrio: puntoEquilibrio, ejecutar: ejecutar,
  };
});
