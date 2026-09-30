/* mini-format — comportamiento de la portada. Sin dependencias; todo es progresivo. */
(function () {
  "use strict";
  var sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* copiar al portapapeles */
  document.querySelectorAll(".cmd .copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.parentElement.querySelector("code");
      if (!code) return;
      navigator.clipboard.writeText(code.textContent.trim()).then(function () {
        btn.dataset.done = "1";
        setTimeout(function () { delete btn.dataset.done; }, 1600);
      }).catch(function () {});
    });
  });

  /* selector de plataforma */
  var seg = document.querySelector(".seg");
  if (seg) seg.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-os]"); if (!b) return;
    seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
    document.querySelectorAll("[data-install]").forEach(function (el) { el.hidden = el.dataset.install !== b.dataset.os; });
  });

  /* pestañas (píldoras y segmentos comparten la misma lógica) */
  document.querySelectorAll('[role="tablist"]').forEach(function (list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function activar(tab) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.dataset.panel); if (panel) panel.hidden = !on;
      });
    }
    tabs.forEach(function (t) { t.tabIndex = t.getAttribute("aria-selected") === "true" ? 0 : -1; });
    list.addEventListener("click", function (e) { var t = e.target.closest('[role="tab"]'); if (t) activar(t); });
    list.addEventListener("keydown", function (e) {
      var i = tabs.indexOf(document.activeElement); if (i < 0) return;
      var j = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i + tabs.length - 1) % tabs.length : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
      if (j === null) return; e.preventDefault(); tabs[j].focus(); activar(tabs[j]);
    });
  });

  /* volver a animar las barras de un panel */
  document.querySelectorAll("[data-replay]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var panel = btn.closest(".js-chart"); if (!panel || sinMovimiento) return;
      panel.classList.remove("reveal"); void panel.offsetWidth; panel.classList.add("reveal");
    });
  });

  /* ------------------------------------------------------------------
     Terminal narrativo. La salida está escrita: no ejecuta nada, y así se
     declara en la nota bajo el terminal. Los comandos y la API son reales.
     Tokens: k palabra clave · s cadena · n número · c comentario · p signo ·
     f función · e error · u enlace · E código de error.
     ------------------------------------------------------------------ */
  var PASOS = [
    { titulo: "~/proyecto — tu contrato", lineas: [
      ['p','$ '], ['','mini from-schema eventos.schema.json -p log --out contrato.json\n'],
      ['s','contrato.json creado para tus eventos\n'],
      ['c','# campos, tipos y reglas salen de tu esquema JSON\n'],
      ['c','# con muestras JSON puedes usar mini build\n\n'],
      ['p','$ '], ['cursor','']
    ]},
    { titulo: "~/proyecto — mini prompt", lineas: [
      ['p','$ '], ['','mini prompt --contract contrato.json --lang es\n\n'],
      ['','Responde en formato '], ['k','.mini'], ['', ', familia '], ['s','log'], ['','.\n'],
      ['','Primera línea: '], ['s','log|n=<número de registros>'], ['','\n'],
      ['','Luego un registro por línea, campos separados por '], ['s','|'], ['',':\n'],
      ['n','  ts'], ['c','     str   marca de tiempo ISO-8601 UTC\n'],
      ['n','  level'], ['c','  enum  DEBUG | INFO | WARN | ERROR | CRITICAL\n'],
      ['n','  service'], ['c','str\n'],
      ['n','  code'], ['c','   str   …\n'],
      ['','Sin texto fuera de los registros.\n\n'],
      ['c','# derivado del contrato: cambia el contrato, cambia el prompt\n']
    ]},
    { titulo: "~/proyecto — python", lineas: [
      ['k','from '], ['','minifmt '], ['k','import '], ['','Contract, parse, spec_block\n\n'],
      ['','c '], ['p','= '], ['','Contract'], ['p','.'], ['f','load'], ['p','('], ['s','"contrato.json"'], ['p',')\n'],
      ['','r '], ['p','= '], ['','cliente'], ['p','.'], ['f','completar'], ['p','('], ['','sistema'], ['p','='], ['f','spec_block'], ['p','('], ['','c'], ['p',', '], ['','lang'], ['p','='], ['s','"es"'], ['p','), '], ['','usuario'], ['p','='], ['','fuente'], ['p',')\n'],
      ['','doc '], ['p','= '], ['f','parse'], ['p','('], ['','r'], ['p',', '], ['','c'], ['p',', '], ['','strict'], ['p','='], ['k','False'], ['p',')\n\n'],
      ['c','# strict=False: acumula errores en doc.errors en vez de lanzar\n'],
      ['c','# cualquier proveedor; mini-format no se interpone en la llamada\n']
    ]},
    { titulo: "~/proyecto — mini diagnose", lineas: [
      ['p','$ '], ['','mini diagnose respuesta.mini --contract contrato.json\n'],
      ['','log|n=3|env=prod\n'],
      ['','2026-09-15T10:00:00Z|INFO|api|OK|arranque|…      '], ['s','✓\n'],
      ['e','2026-09-15T10:01:00Z|ALTO|api|E_DB|timeout|…\n'],
      ['','2026-09-15T10:02:00Z|WARN|api|LAT|p95 alto|…     '], ['s','✓\n\n'],
      ['E','E10'], ['',' line 3 [level]: '], ['','valor fuera de la enumeración\n'],
      ['E','E04'], ['',' document: '], ['','n=3 declarado, 2 registros válidos\n\n'],
      ['c','# código estable + línea + campo: iguales en Python y TypeScript\n'],
      ['p','$ '], ['','echo $?  '], ['n','1\n']
    ]},
    { titulo: "~/proyecto — modo tolerante", lineas: [
      ['','doc'], ['p','.'], ['','records        '], ['c','# 2 registros válidos, ya tipados\n'],
      ['','doc'], ['p','.'], ['','errors         '], ['c','# [E10 line 3 [level], E04 document]\n\n'],
      ['c','// en TypeScript, además:\n'],
      ['','lenient'], ['p','.'], ['f','invalidLines'], ['p','()  '], ['c','// [3]  ← solo esta se reenvía\n'],
      ['','lenient'], ['p','.'], ['','missingRecords  '], ['c','// 1\n\n'],
      ['c','# se conserva lo válido; se regenera solo la línea rechazada\n']
    ]},
    { titulo: "~/proyecto — registros tipados", lineas: [
      ['k','for '], ['','rec '], ['k','in '], ['','doc'], ['p','.'], ['','records'], ['p',':\n'],
      ['','    rec'], ['p','['], ['s','"level"'], ['p',']   '], ['c','# "INFO"  (enum validado)\n'],
      ['','    rec'], ['p','['], ['s','"service"'], ['p','] '], ['c','# "api"\n\n'],
      ['','doc'], ['p','.'], ['f','to_canonical'], ['p','()\n'],
      ['p','{'], ['s','"prefix"'], ['p',': '], ['s','"log"'], ['p',', '], ['s','"header"'], ['p',': {'], ['s','"n"'], ['p',': '], ['n','3'], ['p',', …}, '], ['s','"events"'], ['p',': [ … ]}\n\n'],
      ['c','# desde aquí es código normal: no hay cadenas que parsear\n']
    ]}
  ];

  var salida = document.getElementById("term-out"), titulo = document.getElementById("term-title"),
      pos = document.getElementById("term-pos"), lista = document.getElementById("steps"), walk = document.getElementById("walk");
  if (salida && lista) {
    var actual = 0, escribiendo = null, avance = null, INTERVALO = 7000;
    var mapa = { E: "cod", u: "u" };

    function pintar(i, animado) {
      clearTimeout(escribiendo); clearTimeout(avance);
      actual = i;
      var paso = PASOS[i];
      titulo.textContent = paso.titulo;
      pos.textContent = String(i + 1).padStart(2, "0") + " / " + String(PASOS.length).padStart(2, "0");
      lista.querySelectorAll("li").forEach(function (li, k) {
        li.classList.toggle("active", k === i);
        var pr = li.querySelector(".progress");           // reinicia la barra de progreso
        if (pr) { var n = pr.cloneNode(false); pr.parentNode.replaceChild(n, pr); }
      });
      salida.textContent = "";
      var trozos = paso.lineas.map(function (t) {
        var s = document.createElement("span");
        if (t[0] === "cursor") { s.className = "cursor"; return { span: s, texto: "" }; }
        if (t[0]) s.className = mapa[t[0]] || t[0];
        return { span: s, texto: t[1] };
      });
      var k = 0;
      function fin() { if (!sinMovimiento && !walk.classList.contains("paused")) avance = setTimeout(function () { pintar((actual + 1) % PASOS.length, true); }, INTERVALO); }
      if (!animado || sinMovimiento) { trozos.forEach(function (t) { t.span.textContent = t.texto; salida.appendChild(t.span); }); fin(); return; }
      (function siguiente() {
        if (k >= trozos.length) { fin(); return; }
        var t = trozos[k++]; t.span.textContent = t.texto; salida.appendChild(t.span);
        escribiendo = setTimeout(siguiente, 38);
      })();
    }
    lista.addEventListener("click", function (e) { var b = e.target.closest("button[data-step]"); if (b) pintar(Number(b.dataset.step), true); });
    document.querySelectorAll("[data-term]").forEach(function (b) {
      b.addEventListener("click", function () {
        var a = b.dataset.term;
        pintar(a === "next" ? (actual + 1) % PASOS.length : a === "prev" ? (actual + PASOS.length - 1) % PASOS.length : actual, true);
      });
    });
    // pausa al pasar el ratón: se detiene el avance y la barra; al salir se retoma el mismo paso
    walk.addEventListener("mouseenter", function () { walk.classList.add("paused"); clearTimeout(avance); });
    walk.addEventListener("mouseleave", function () { walk.classList.remove("paused"); clearTimeout(avance); avance = setTimeout(function () { pintar((actual + 1) % PASOS.length, true); }, INTERVALO / 2); });
    walk.style.setProperty("--walk-ms", INTERVALO + "ms");
    pintar(0, false);
  }

  /* divulgación progresiva de la tabla comparativa */
  var tgl = document.getElementById("cmp-toggle");
  if (tgl) tgl.addEventListener("click", function () {
    var abierto = document.getElementById("cmp").classList.toggle("open");
    tgl.setAttribute("aria-expanded", String(abierto));
    tgl.textContent = abierto ? "Mostrar solo las principales" : "Mostrar las 14 filas";
  });

  /* aparición al entrar en pantalla */
  var obs = document.querySelectorAll(".js-chart, .rv");
  if (sinMovimiento || !("IntersectionObserver" in window)) obs.forEach(function (el) { el.classList.add("reveal", "in"); });
  else {
    var io = new IntersectionObserver(function (es) { es.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("reveal", "in"); io.unobserve(en.target); } }); }, { threshold: 0.2, rootMargin: "0px 0px -8% 0px" });
    obs.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------------------------------------------
     Vídeo de integración. Demo reproducible por escenas con los comandos
     y la API reales: instalar, instruir + llamar, diagnosticar y usar.
     Cada escena es una lista de líneas; cada línea, fragmentos [clase,
     texto] con la misma paleta que el terminal (k s n c p f e + E).
     ------------------------------------------------------------------ */
  var dv = document.getElementById("demo-integracion");
  if (dv) {
    var ESCENAS = [
      { titulo: "mi-django — terminal", dur: 5000,
        cap: "1 · Instala la biblioteca en tu proyecto Django. Sin servicios ni cambios de framework.",
        lineas: [
          [["p", "$ "], ["", "pip install mini_format-1.2.2-py3-none-any.whl\n"]],
          [["c", "… instalando mini-format 1.2.2\n"]],
          [["s", "mini-format 1.2.2 instalado\n"]],
          [["", "\n"]],
          [["p", "$ "], ["", "mini from-schema eventos.schema.json -p log --out contrato.json\n"]],
          [["s", "contrato.json creado para tus datos\n"]]
        ]},
      { titulo: "servicios/evaluacion.py", dur: 8000,
        cap: "2 · Pide el bloque de prompt, llama a tu proveedor como siempre y valida con parse().",
        lineas: [
          [["k", "from "], ["", "minifmt "], ["k", "import "], ["", "Contract, parse\n"]],
          [["k", "from "], ["", "minifmt "], ["k", "import "], ["", "spec_block\n"]],
          [["", "\n"]],
          [["", "c "], ["p", "= "], ["", "Contract"], ["p", "."], ["f", "load"], ["p", "("], ["s", '"contrato.json"'], ["p", ")\n"]],
          [["", "\n"]],
          [["k", "def "], ["f", "generar_items"], ["p", "("], ["", "tema"], ["p", "):\n"]],
          [["", "    prompt "], ["p", "= "], ["f", "spec_block"], ["p", "("], ["", "c"], ["p", ", "], ["", "lang"], ["p", "="], ["s", '"es"'], ["p", ")\n"]],
          [["", "    r "], ["p", "= "], ["", "cliente"], ["p", "."], ["f", "completar"], ["p", "("], ["", "prompt, tema"], ["p", ")\n"]],
          [["", "    doc "], ["p", "= "], ["f", "parse"], ["p", "("], ["", "r, c"], ["p", ", "], ["", "strict"], ["p", "="], ["k", "False"], ["p", ")\n"]],
          [["k", "    return "], ["", "doc"], ["p", "."], ["", "records, doc"], ["p", "."], ["", "errors\n"]]
        ]},
      { titulo: "mi-django — mini diagnose", dur: 7000,
        cap: "3 · Cada fallo trae código estable, línea y campo. Aquí, E10 en la línea 3.",
        lineas: [
          [["p", "$ "], ["", "mini diagnose respuesta.mini --contract contrato.json\n"]],
          [["", "log|n=3|env=prod\n"]],
          [["", "2026-09-15T10:00:00Z|INFO|api|OK\n"]],
          [["e", "2026-09-15T10:01:00Z|ALTO|api|E_DB\n"]],
          [["", "2026-09-15T10:02:00Z|WARN|api|LAT\n"]],
          [["", "\n"]],
          [["E", "E10"], ["", " line 3 [level]: fuera del enum\n"]],
          [["E", "E04"], ["", " document: n=3, 2 válidos\n"]]
        ]},
      { titulo: "mi-django — python", dur: 6000,
        cap: "4 · Te quedas con los registros tipados y regeneras solo la línea rechazada.",
        lineas: [
          [["p", ">>> "], ["", "doc"], ["p", "."], ["", "records\n"]],
          [["p", "[{"], ["s", '"level": "INFO"'], ["p", ", "], ["s", '"service": "api"'], ["p", "},\n"]],
          [["p", " {"], ["s", '"level": "WARN"'], ["p", ", "], ["s", '"service": "api"'], ["p", "}]\n"]],
          [["", "\n"]],
          [["p", ">>> "], ["", "doc"], ["p", "."], ["", "errors\n"]],
          [["E", "E10"], ["", " line 3 [level], "], ["E", "E04"], ["", " document\n"]],
          [["c", "# regenerar solo la línea 3\n"]]
        ]}
    ];
    var dvCuerpo = dv.querySelector("[data-dv-body]"), dvTitulo = dv.querySelector("[data-dv-title]"),
        dvTiempo = dv.querySelector("[data-dv-time]"), dvCap = dv.querySelector("[data-dv-cap]"),
        dvFill = dv.querySelector("[data-dv-fill]"), dvToggle = dv.querySelector("[data-dv-toggle]"),
        dvRestart = dv.querySelector("[data-dv-restart]"),
        dvDots = Array.prototype.slice.call(dv.querySelectorAll("[data-dv-goto]"));
    var dvTotal = ESCENAS.reduce(function (a, s) { return a + s.dur; }, 0);
    var dvActual = 0, dvVistos = 0, dvT0 = 0, dvBase = 0, dvLineaT = null, dvEscenaT = null,
        dvReloj = null, dvSonando = false, dvFin = false;

    function dvFormato(ms) { var s = Math.floor(ms / 1000); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
    function dvInicio(i) { var a = 0; for (var j = 0; j < i; j++) a += ESCENAS[j].dur; return a; }
    function dvTranscurrido() { return Math.min(dvBase + (dvSonando ? Date.now() - dvT0 : 0), dvTotal); }
    function dvPintarReloj() {
      var e = dvTranscurrido();
      dvTiempo.textContent = dvFormato(e) + " / " + dvFormato(dvTotal);
      dvFill.style.width = (100 * e / dvTotal).toFixed(1) + "%";
    }
    function dvPintarLinea(frags) {
      frags.forEach(function (t) {
        var s = document.createElement("span");
        if (t[0]) s.className = t[0] === "E" ? "cod" : t[0];
        s.textContent = t[1];
        dvCuerpo.appendChild(s);
      });
    }
    function dvRevelar() {
      clearTimeout(dvLineaT);
      var esc = ESCENAS[dvActual];
      var paso = Math.min(650, (esc.dur * 0.55) / Math.max(esc.lineas.length, 1));
      (function sig() {
        if (dvVistos >= esc.lineas.length) return;
        dvPintarLinea(esc.lineas[dvVistos++]);
        dvLineaT = setTimeout(sig, paso);
      })();
    }
    function dvProgramarAvance() {
      clearTimeout(dvEscenaT);
      if (!dvSonando) return;
      var espera = Math.max(dvInicio(dvActual) + ESCENAS[dvActual].dur - dvTranscurrido(), 0);
      dvEscenaT = setTimeout(function () {
        if (dvActual + 1 < ESCENAS.length) dvIrA(dvActual + 1);
        else dvTerminar();
      }, espera);
    }
    function dvIrA(i) {
      clearTimeout(dvLineaT); clearTimeout(dvEscenaT);
      dvActual = i; dvVistos = 0; dvFin = false;
      var esc = ESCENAS[i];
      dvTitulo.textContent = esc.titulo;
      dvCap.textContent = esc.cap;
      dvCuerpo.textContent = "";
      dvDots.forEach(function (d, k) { d.setAttribute("aria-current", String(k === i)); });
      dvBase = dvInicio(i);
      if (dvSonando) dvT0 = Date.now();
      else dvToggle.setAttribute("aria-label", "Reproducir el vídeo");
      if (sinMovimiento || !dvSonando) { esc.lineas.forEach(dvPintarLinea); dvVistos = esc.lineas.length; }
      else { dvVistos = 0; dvRevelar(); }
      dvProgramarAvance();
      dvPintarReloj();
    }
    function dvReproducir() {
      if (dvFin) { dvIrA(0); dvCuerpo.textContent = ""; dvVistos = 0; }
      dvSonando = true; dvT0 = Date.now();
      dv.dataset.playing = "1";
      dvToggle.setAttribute("aria-label", "Pausar el vídeo");
      if (!sinMovimiento) dvRevelar();
      dvProgramarAvance();
      clearInterval(dvReloj); dvReloj = setInterval(dvPintarReloj, 150);
      dvPintarReloj();
    }
    function dvPausar() {
      dvBase = dvTranscurrido();
      dvSonando = false;
      delete dv.dataset.playing;
      dvToggle.setAttribute("aria-label", "Reproducir el vídeo");
      clearTimeout(dvLineaT); clearTimeout(dvEscenaT); clearInterval(dvReloj);
      dvPintarReloj();
    }
    function dvTerminar() { dvPausar(); dvFin = true; dvToggle.setAttribute("aria-label", "Volver a reproducir el vídeo"); }
    dvToggle.addEventListener("click", function () { if (dvSonando) dvPausar(); else dvReproducir(); });
    dvRestart.addEventListener("click", function () { var s = dvSonando; dvPausar(); dvIrA(0); if (s) { dvCuerpo.textContent = ""; dvVistos = 0; dvReproducir(); } });
    dvDots.forEach(function (d) { d.addEventListener("click", function () { dvIrA(Number(d.dataset.dvGoto)); }); });
    dvIrA(0);
    // reproducción automática al entrar en pantalla; se pausa al salir
    var dvAuto = !sinMovimiento, dvEmpezo = false, dvFuera = false;
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        es.forEach(function (en) {
          if (en.isIntersecting) {
            if (!dvEmpezo && dvAuto) { dvEmpezo = true; dvReproducir(); }
            else if (dvFuera && dvAuto) { dvFuera = false; dvReproducir(); }
          } else if (dvSonando) { dvFuera = true; dvPausar(); }
        });
      }, { threshold: 0.35 }).observe(dv);
    } else if (dvAuto) { dvEmpezo = true; dvReproducir(); }
  }

  /* ------------------------------------------------------------------
     Resto de vídeos de la portada. Misma mecánica que el de
     integración, como factoría: dvInit(id, escenas, bucle). Con
     bucle=true el vídeo vuelve a empezar al terminar (playground).
     ------------------------------------------------------------------ */
  var DV_RELEASE = [
    { titulo: "mini build — JSON → .mini", dur: 6000,
      cap: "1 · Reúne muestras representativas de los JSON que necesita tu aplicación.",
      lineas: [
        [["p", "$ "], ["", "mini build phones.json more.json\n"]],
        [["", "  --prefix phone --out .mini\n"]],
        [["", "\n"]],
        [["c", "# teléfonos, precios, listas, variantes\n"]],
        [["s", "Tipos + campos opcionales + estructura\n"]],
        [["c", "# el contrato se construye una sola vez\n"]]
      ]},
    { titulo: ".mini/ — toolkit de dominio", dur: 6000,
      cap: "2 · Contrato, prompts y herramientas ejecutables listos para tu proyecto.",
      lineas: [
        [["f", ".mini/\n"]],
        [["", "  contract.json  schema.json\n"]],
        [["", "  prompt.es.md   prompt.en.md\n"]],
        [["", "  parser.py      validator.py\n"]],
        [["", "  repair.py      manifest.json\n"]],
        [["", "  example.json   example.mini\n"]],
        [["c", "  README.md\n"]]
      ]},
    { titulo: ".mini/ — validar y recuperar JSON", dur: 6000,
      cap: "3 · Usa el prompt con tu modelo y devuelve a tu aplicación el JSON validado.",
      lineas: [
        [["c", "# sistema: contenido de prompt.es.md\n"]],
        [["p", "$ "], ["", "python .mini/validator.py response.mini\n"]],
        [["", "\n"]],
        [["p", "$ "], ["", "python .mini/parser.py decode response.mini\n"]],
        [["c", "# salida: JSON con la estructura original\n"]]
      ]},
    { titulo: ".mini/ — detectar y reparar", dur: 6000,
      cap: "4 · Corrige lo seguro. Conserva el informe para lo que requiere un reintento.",
      lineas: [
        [["p", "$ "], ["", "python .mini/parser.py diagnose response.mini\n"]],
        [["p", "$ "], ["", "python .mini/repair.py response.mini\n"]],
        [["", "  --out corrected.mini\n"]],
        [["", "\n"]],
        [["c", "# no inventa valores ni registros ausentes\n"]],
        [["c", "# --fix-count exige aceptación explícita\n"]]
      ]}
  ];

  var DV_PLAYGROUND = [
    { titulo: "playground — ticket de muestra", dur: 6000,
      cap: "1 · Abre un ticket de muestra y observa su contrato .mini.",
      lineas: [
        [["f", "contrato: "], ["", "tk — tickets de soporte\n"]],
        [["", "ejemplo: 10 tickets grabados\n"]],
        [["", "\n"]],
        [["", "tk|n=10\n"]],
        [["", "T-1041|alta|acceso|No puede iniciar sesión|2\n"]],
        [["", "T-1042|media|pago|Cobro duplicado|3\n"]],
        [["", "\n"]],
        [["s", "10 tickets · 0 errores\n"]]
      ]},
    { titulo: "playground — editor", dur: 7000,
      cap: "2 · Inyecta errores y lee el diagnóstico: código, línea y campo.",
      lineas: [
        [["p", "> "], ["", "inyectar errores\n"]],
        [["", "\n"]],
        [["E", "E04"], ["", " document: n=11, 9 válidos\n"]],
        [["E", "E05"], ["", " línea 2: falta un campo\n"]],
        [["E", "E09"], ["", " línea 4: escape inválido\n"]],
        [["", "\n"]],
        [["c", "líneas a regenerar: [2, 4]\n"]]
      ]},
    { titulo: "playground — comparar", dur: 7000,
      cap: "3 · Compara el documento actual en varios formatos.",
      lineas: [
        [["c", "tokens del documento en el editor\n"]],
        [["", "\n"]],
        [["f", "mini "], ["", "   ← validación con contrato\n"]],
        [["", "toon   ← codificador oficial\n"]],
        [["", "json   ← objeto canónico\n"]],
        [["", "yaml   ← representación equivalente\n"]],
        [["", "xml    ← representación equivalente\n"]]
      ]},
    { titulo: "playground — tu contrato", dur: 4000,
      cap: "4 · Diseña tu propio contrato y descárgalo.",
      lineas: [
        [["p", "> "], ["", "descargar contract.json\n"]],
        [["p", "> "], ["", "probar en el editor\n"]],
        [["", "\n"]],
        [["s", "listo para adaptar a tus datos\n"]],
        [["", "\n"]],
        [["c", "(fin · la demo va en bucle)\n"]]
      ]}
  ];

  function dvInit(id, ESCENAS, bucle) {
    var dv = document.getElementById(id);
    if (!dv) return;
    var cuerpo = dv.querySelector("[data-dv-body]"), titulo = dv.querySelector("[data-dv-title]"),
        tiempo = dv.querySelector("[data-dv-time]"), cap = dv.querySelector("[data-dv-cap]"),
        fill = dv.querySelector("[data-dv-fill]"), toggle = dv.querySelector("[data-dv-toggle]"),
        restart = dv.querySelector("[data-dv-restart]"),
        dots = Array.prototype.slice.call(dv.querySelectorAll("[data-dv-goto]"));
    var total = ESCENAS.reduce(function (a, s) { return a + s.dur; }, 0);
    var actual = 0, vistos = 0, t0 = 0, base = 0, lineaT = null, escenaT = null,
        reloj = null, sonando = false, fin = false;

    function formato(ms) { var s = Math.floor(ms / 1000); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
    function inicio(i) { var a = 0; for (var j = 0; j < i; j++) a += ESCENAS[j].dur; return a; }
    function transcurrido() { return Math.min(base + (sonando ? Date.now() - t0 : 0), total); }
    function pintarReloj() {
      var e = transcurrido();
      tiempo.textContent = formato(e) + " / " + formato(total);
      fill.style.width = (100 * e / total).toFixed(1) + "%";
    }
    function pintarLinea(frags) {
      frags.forEach(function (t) {
        var s = document.createElement("span");
        if (t[0]) s.className = t[0] === "E" ? "cod" : t[0];
        s.textContent = t[1];
        cuerpo.appendChild(s);
      });
    }
    function revelar() {
      clearTimeout(lineaT);
      var esc = ESCENAS[actual];
      var paso = Math.min(650, (esc.dur * 0.55) / Math.max(esc.lineas.length, 1));
      (function sig() {
        if (vistos >= esc.lineas.length) return;
        pintarLinea(esc.lineas[vistos++]);
        lineaT = setTimeout(sig, paso);
      })();
    }
    function programarAvance() {
      clearTimeout(escenaT);
      if (!sonando) return;
      var espera = Math.max(inicio(actual) + ESCENAS[actual].dur - transcurrido(), 0);
      escenaT = setTimeout(function () {
        if (actual + 1 < ESCENAS.length) irA(actual + 1);
        else if (bucle) irA(0);
        else terminar();
      }, espera);
    }
    function irA(i) {
      clearTimeout(lineaT); clearTimeout(escenaT);
      actual = i; fin = false;
      var esc = ESCENAS[i];
      titulo.textContent = esc.titulo;
      cap.textContent = esc.cap;
      cuerpo.textContent = "";
      dots.forEach(function (d, k) { d.setAttribute("aria-current", String(k === i)); });
      base = inicio(i);
      if (sonando) t0 = Date.now();
      else toggle.setAttribute("aria-label", "Reproducir el vídeo");
      if (sinMovimiento || !sonando) { esc.lineas.forEach(pintarLinea); vistos = esc.lineas.length; }
      else { vistos = 0; revelar(); }
      programarAvance();
      pintarReloj();
    }
    function reproducir() {
      if (fin) { irA(0); cuerpo.textContent = ""; vistos = 0; }
      sonando = true; t0 = Date.now();
      dv.dataset.playing = "1";
      toggle.setAttribute("aria-label", "Pausar el vídeo");
      if (!sinMovimiento) revelar();
      programarAvance();
      clearInterval(reloj); reloj = setInterval(pintarReloj, 150);
      pintarReloj();
    }
    function pausar() {
      base = transcurrido();
      sonando = false;
      delete dv.dataset.playing;
      toggle.setAttribute("aria-label", "Reproducir el vídeo");
      clearTimeout(lineaT); clearTimeout(escenaT); clearInterval(reloj);
      pintarReloj();
    }
    function terminar() { pausar(); fin = true; toggle.setAttribute("aria-label", "Volver a reproducir el vídeo"); }
    toggle.addEventListener("click", function () { if (sonando) pausar(); else reproducir(); });
    restart.addEventListener("click", function () { var s = sonando; pausar(); irA(0); if (s) { cuerpo.textContent = ""; vistos = 0; reproducir(); } });
    dots.forEach(function (d) { d.addEventListener("click", function () { irA(Number(d.dataset.dvGoto)); }); });
    irA(0);
    var auto = !sinMovimiento, empezo = false, fuera = false;
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        es.forEach(function (en) {
          if (en.isIntersecting) {
            if (!empezo && auto) { empezo = true; reproducir(); }
            else if (fuera && auto) { fuera = false; reproducir(); }
          } else if (sonando) { fuera = true; pausar(); }
        });
      }, { threshold: 0.35 }).observe(dv);
    } else if (auto) { empezo = true; reproducir(); }
  }
  dvInit("demo-release", DV_RELEASE, false);
  dvInit("demo-playground", DV_PLAYGROUND, true);

  /* atajo "/" → documentación */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
    var t = e.target.tagName; if (t === "INPUT" || t === "TEXTAREA" || e.target.isContentEditable) return;
    e.preventDefault(); window.location.href = "/docs/";
  });
})();
