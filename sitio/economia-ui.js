(function () {
  'use strict';
  const sim = document.getElementById('ecoSim');
  if (!sim) return;

  const modelSel = document.getElementById('ecoModel');
  const callsInput = document.getElementById('ecoCalls');
  const modeSel = document.getElementById('ecoMode');
  const cacheSel = document.getElementById('ecoCache');

  const outJson = document.getElementById('ecoJsonUsd');
  const outMini = document.getElementById('ecoMiniUsd');
  const outSaved = document.getElementById('ecoSavedUsd');
  const outNote = document.getElementById('ecoSimNote');

  function fmtUsd(val) {
    return '$' + val.toFixed(2);
  }

  function update() {
    const opt = modelSel.options[modelSel.selectedIndex];
    const inRate = parseFloat(opt.dataset.in || '2.0');
    const outRate = parseFloat(opt.dataset.out || '10.0');
    const cacheRate = parseFloat(opt.dataset.cache || String(inRate * 0.1));
    const calls = Math.max(100, parseInt(callsInput.value || '10000', 10));
    const mode = modeSel.value;
    const cachePct = Math.max(0, Math.min(95, parseFloat(cacheSel.value || '80'))) / 100.0;

    // Verified per-20-ticket workload baseline tokens (o200k_base):
    // JSON compact output = 443 tok; domain/2 = 244 (or domain/1 = 278); compact_rows = 182 tok
    // Input prompt overhead: JSON schema prompt = 520 tok; full .mini = 453; lean = 100; compact_rows = 68
    const baseTaskInput = 620;
    const jsonInTok = baseTaskInput + 520;
    const jsonOutTok = 443;

    let miniPromptTok = 453;
    let miniOutTok = 278;
    if (mode === 'lean') {
      miniPromptTok = 100;
      miniOutTok = 244;
    } else if (mode === 'rows') {
      miniPromptTok = 68;
      miniOutTok = 182;
    }

    const effJsonInRate = inRate * (1.0 - cachePct) + cacheRate * cachePct;
    const effMiniInRate = inRate * (1.0 - cachePct) + cacheRate * cachePct;

    const jsonUsd = (calls / 1e6) * (jsonInTok * effJsonInRate + jsonOutTok * outRate);
    const miniUsd = (calls / 1e6) * ((baseTaskInput + miniPromptTok) * effMiniInRate + miniOutTok * outRate);
    const saved = jsonUsd - miniUsd;
    const pct = jsonUsd > 0 ? (saved / jsonUsd) * 100.0 : 0.0;

    outJson.textContent = fmtUsd(jsonUsd);
    outMini.textContent = fmtUsd(miniUsd);
    outSaved.textContent = fmtUsd(saved) + ' (' + pct.toFixed(1) + '%)';

    const es = document.documentElement.lang === 'es';
    if (outNote) {
      outNote.textContent = es
        ? 'Calculo ilustrativo sobre 20 registros/llamada (' + calls.toLocaleString('es-ES') + ' llamadas/mes, ' + Math.round(cachePct * 100) + '% cache hit).'
        : 'Illustrative monthly estimate at 20 records/call (' + calls.toLocaleString('en-US') + ' calls/mo, ' + Math.round(cachePct * 100) + '% cache hit).';
    }
  }

  [modelSel, callsInput, modeSel, cacheSel].forEach(function (el) {
    el.addEventListener('input', update);
    el.addEventListener('change', update);
  });
  new MutationObserver(update).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  update();
})();
