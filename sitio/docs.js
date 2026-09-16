/* mini-format docs: conmutador de idioma ES/EN. Sin dependencias; persiste en localStorage. */
(function () {
  "use strict";
  var KEY = "mini-lang";
  var englishRoute = location.pathname === "/en" || location.pathname.indexOf("/en/") === 0;
  var path = location.pathname.replace(/^\/en(?=\/|$)/, "") || "/";
  function elegir() {
    try {
      var v = localStorage.getItem(KEY);
      if (v === "es" || v === "en") return v;
    } catch (e) { /* Las preferencias del navegador funcionan sin almacenamiento. */ }
    if (englishRoute) return "en";
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
  var selected = elegir();
  if (document.documentElement.dataset.localizedRoutes === "1") {
    if (!englishRoute && selected === "en") { location.replace(route("en")); return; }
    aplicar(englishRoute ? "en" : "es");
  } else aplicar(selected);
})();
