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
    { titulo: "~/proyecto — mini forks", lineas: [
      ['p','$ '], ['','mini forks\n'],
      ['f','a    '], ['','Assessment items (multiple choice, Bloom + IRT 3PL + CAT)\n'],
      ['f','q    '], ['','Formative quiz items  '], ['c','← extiende a\n'],
      ['f','card '], ['','Flashcards (spaced repetition)\n'],
      ['f','log  '], ['','Service events / incident records\n'],
      ['f','tc   '], ['','Software test cases\n'],
      ['f','us   '], ['','User stories with acceptance criteria\n'],
      ['c','… 14 familias · forks/<prefijo>/contract.json\n\n'],
      ['p','$ '], ['cursor','']
    ]},
    { titulo: "~/proyecto — mini prompt", lineas: [
      ['p','$ '], ['','mini prompt log --lang es\n\n'],
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
      ['k','from '], ['','minifmt '], ['k','import '], ['','Registry, parse, spec_block\n\n'],
      ['','c '], ['p','= '], ['','Registry'], ['p','.'], ['f','load'], ['p','()'], ['p','.'], ['f','get'], ['p','('], ['s','"log"'], ['p',')\n'],
      ['','r '], ['p','= '], ['','cliente'], ['p','.'], ['f','completar'], ['p','('], ['','sistema'], ['p','='], ['f','spec_block'], ['p','('], ['','c'], ['p',', '], ['','lang'], ['p','='], ['s','"es"'], ['p','), '], ['','usuario'], ['p','='], ['','fuente'], ['p',')\n'],
      ['','doc '], ['p','= '], ['f','parse'], ['p','('], ['','r'], ['p',', '], ['','c'], ['p',', '], ['','strict'], ['p','='], ['k','False'], ['p',')\n\n'],
      ['c','# strict=False: acumula errores en doc.errors en vez de lanzar\n'],
      ['c','# cualquier proveedor; mini-format no se interpone en la llamada\n']
    ]},
    { titulo: "~/proyecto — mini diagnose", lineas: [
      ['p','$ '], ['','mini diagnose respuesta.mini\n'],
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

  /* atajo "/" → documentación */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey) return;
    var t = e.target.tagName; if (t === "INPUT" || t === "TEXTAREA" || e.target.isContentEditable) return;
    e.preventDefault(); window.location.href = "/docs/";
  });
})();
