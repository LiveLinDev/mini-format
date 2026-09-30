/* mini-format docs: menú móvil y conmutador de idioma ES/EN. Sin dependencias; persiste en localStorage. */
(function () {
  "use strict";
  /* ---- menú móvil: patrón de botón de despliegue (aria-expanded/aria-controls). Sin JavaScript los
     enlaces se muestran en línea (base.css, html:not(.js)); con JavaScript el botón los abre y cierra. ---- */
  (function () {
    var header = document.querySelector(".site-header");
    var boton = header && header.querySelector(".nav-toggle");
    var lista = document.getElementById("nav-links");
    if (!header || !boton || !lista) return;
    var punto = window.matchMedia ? window.matchMedia("(max-width: 1339.98px)") : null;
    function abierto() { return boton.getAttribute("aria-expanded") === "true"; }
    function fijar(abrir) {
      boton.setAttribute("aria-expanded", String(abrir));
      header.classList.toggle("menu-open", abrir);
    }
    boton.addEventListener("click", function () { fijar(!abierto()); });
    lista.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest("a")) fijar(false);
    });
    document.addEventListener("keydown", function (ev) {
      if ((ev.key === "Escape" || ev.key === "Esc") && abierto()) {
        var dentro = lista.contains(document.activeElement);
        fijar(false);
        if (dentro || document.activeElement === boton) boton.focus();
      }
    });
    document.addEventListener("click", function (ev) {
      if (abierto() && !header.contains(ev.target)) fijar(false);
    });
    if (punto && punto.addEventListener) punto.addEventListener("change", function (ev) { if (!ev.matches) fijar(false); });
  })();

  /* ---- idioma ---- */
  var KEY = "mini-lang";
  var SESION = "mini-lang-sesion";
  var englishRoute = location.pathname === "/en" || location.pathname.indexOf("/en/") === 0;
  var path = location.pathname.replace(/^\/en(?=\/|$)/, "") || "/";
  function elegir() {
    try {
      var v = localStorage.getItem(KEY);
      if (v === "es" || v === "en") return v;
    } catch (e) { /* Las preferencias del navegador funcionan sin almacenamiento. */ }
    if (englishRoute) return "en";
    /* Quien entró por /en/ y sigue a una página bilingüe en línea (taller, SIMA, validación...) conserva el inglés
       durante la visita, sin guardar nada de forma permanente. */
    try { if (sessionStorage.getItem(SESION) === "en") return "en"; } catch (e) {}
    var languages = navigator.languages || [navigator.language || ""];
    if (languages.some(function (lang) { return /^es(?:-|$)/i.test(lang); })) return "es";
    var zone = "";
    try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) {}
    if (/^(Europe\/(Madrid|Canary)|Atlantic\/Canary|America\/(Lima|Bogota|Santiago|Buenos_Aires|Argentina\/|Mexico_City|Monterrey|Merida|Cancun|Guatemala|Costa_Rica|El_Salvador|Managua|Tegucigalpa|Panama|Caracas|Guayaquil|La_Paz|Asuncion|Montevideo|Havana|Santo_Domingo|Puerto_Rico))/.test(zone)) return "es";
    return "en";
  }
  function aplicar(lang) {
    document.querySelectorAll("[data-lang]").forEach(function (el) { el.hidden = el.dataset.lang !== lang; });
    document.querySelectorAll("[data-lang-body]").forEach(function (el) { el.hidden = el.dataset.langBody !== lang; });
    document.querySelectorAll("[data-lang-btn]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.langBtn === lang)); });
    var root = document.documentElement;
    root.setAttribute("lang", lang);
    var t = lang === "es" ? root.dataset.titleEs : root.dataset.titleEn;
    if (t) document.title = t;
  }
  var btns = document.querySelectorAll("[data-lang-btn]");
  if (!btns.length) return;
  function route(lang) {
    var hash = location.hash.replace(/^#(?:es|en)-/, "#" + lang + "-");
    return (lang === "en" ? "/en" : "") + path + location.search + hash;
  }
  btns.forEach(function (b) {
    b.addEventListener("click", function () {
      try { localStorage.setItem(KEY, b.dataset.langBtn); } catch (e) {}
      if (document.documentElement.dataset.localizedRoutes === "1") location.assign(route(b.dataset.langBtn));
      else aplicar(b.dataset.langBtn);
    });
  });
  if (englishRoute) { try { sessionStorage.setItem(SESION, "en"); } catch (e) {} }
  var selected = elegir();
  if (document.documentElement.dataset.localizedRoutes === "1") {
    if (!englishRoute && selected === "en") { location.replace(route("en")); return; }
    aplicar(englishRoute ? "en" : "es");
  } else aplicar(selected);
})();
