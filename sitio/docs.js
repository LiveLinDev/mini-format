/* mini-format docs: conmutador de idioma ES/EN. Sin dependencias; persiste en localStorage. */
(function () {
  "use strict";
  var KEY = "docs-lang";
  function elegir() {
    try {
      var v = localStorage.getItem(KEY);
      if (v === "es" || v === "en") return v;
    } catch (e) { /* sin almacenamiento: español */ }
    return "es";
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
  btns.forEach(function (b) {
    b.addEventListener("click", function () {
      try { localStorage.setItem(KEY, b.dataset.langBtn); } catch (e) {}
      aplicar(b.dataset.langBtn);
    });
  });
  aplicar(elegir());
})();
