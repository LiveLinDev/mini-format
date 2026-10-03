(() => {
  const data = JSON.parse(document.querySelector('#story-data').textContent);
  const labels = {
    es: {generate:'La IA genera 20 tickets en .mini', validate:'El validador detecta un envoltorio Markdown', repair:'Repair quita el envoltorio y detecta el id incorrecto', model_repair:'La IA corrige sólo la línea 4; conserva las otras 19', revalidate:'Se comprueban otra vez los 20 tickets', parse:'El parser entrega JSON a la aplicación'},
    en: {generate:'AI generates 20 tickets in .mini', validate:'Validator detects a Markdown wrapper', repair:'Repair removes the wrapper and detects the wrong id', model_repair:'AI corrects only line 4; the other 19 are preserved', revalidate:'All 20 tickets are checked again', parse:'Parser delivers JSON to the application'}
  };
  let count = 0;
  const lang = () => document.documentElement.lang.startsWith('en') ? 'en' : 'es';
  const readRuns = () => {try{return JSON.parse(localStorage.getItem('mini-story-runs') || '[]')}catch{return []}};
  function savedRuns(){const ul=document.querySelector('#story-runs');ul.replaceChildren(...readRuns().map(r=>{const li=document.createElement('li');li.textContent=new Date(r.date).toLocaleString(lang())+' · 20 tickets · '+r.mode;return li}))}
  function render(){const l=lang();document.querySelector('#story-steps').replaceChildren(...data.history.trace.slice(0,count).map(step=>{const li=document.createElement('li');li.textContent=labels[l][step.stage] || step.stage;if(step.ok===false)li.className='needs-repair';return li}));const done=count===data.history.trace.length;document.querySelector('#story-output').hidden=!done;document.querySelector('#story-status').textContent=done?(l==='es'?'20 tickets válidos. JSON listo para usar.':'20 valid tickets. JSON ready to use.'):(l==='es'?`Paso ${count} de 6. Respuesta guardada; sin llamadas a IA.`:`Step ${count} of 6. Saved response; no AI calls.`);document.querySelector('#story-json').textContent=JSON.stringify(data.history.data,null,2);document.querySelector('#story-history').textContent=JSON.stringify(data.history,null,2);savedRuns()}
  function record(mode){try{const runs=readRuns();runs.unshift({date:new Date().toISOString(),mode});localStorage.setItem('mini-story-runs',JSON.stringify(runs.slice(0,10)))}catch{/* Replay still works without storage. */}}
  document.querySelector('#story-run').onclick=()=>{count=data.history.trace.length;record('replay');render()};
  document.querySelector('#story-next').onclick=()=>{count=count===data.history.trace.length?1:count+1;if(count===data.history.trace.length)record('steps');render()};
  document.querySelector('#story-save').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(data.history,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='mini-support-history.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
  new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});render();
})();
