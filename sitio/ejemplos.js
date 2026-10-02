/* Recorrido: la selección, la animación y las anotaciones comparten un único paso. */
(function () {
  "use strict";
  var walk = document.querySelector(".ej-walk");
  if (!walk) return;
  var list = walk.querySelector(".ej-steps");
  var tabs = Array.from(list.querySelectorAll('[role="tab"]'));
  var connectors = Array.from(list.querySelectorAll(".ej-connector"));
  var play = document.getElementById("recorrido-play");
  var prev = document.getElementById("recorrido-prev");
  var next = document.getElementById("recorrido-next");
  var counter = document.getElementById("recorrido-counter");
  var reduced = matchMedia("(prefers-reduced-motion: reduce)");
  var current = 0, timer = null, playing = false, finished = false;
  function english() { return document.documentElement.lang === "en"; }
  function labels() {
    play.querySelector("[data-play-label]").textContent = playing ?
      (english() ? "Pause the journey" : "Pausar recorrido") :
      (finished ? (english() ? "Play again" : "Volver a ver") :
        (english() ? "Animate the journey" : "Animar recorrido"));
    play.setAttribute("aria-pressed", String(playing));
    prev.disabled = current === 0;
    next.disabled = current === tabs.length - 1;
    counter.textContent = (current + 1) + " / " + tabs.length;
  }
  function stop() {
    clearTimeout(timer);
    timer = null;
    playing = false;
    walk.dataset.playing = "false";
    labels();
  }
  function select(index, manual) {
    if (manual) stop();
    current = index;
    walk.dataset.phase = String(index);
    tabs.forEach(function (tab, i) {
      var active = i === index;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
    });
    connectors.forEach(function (connector, i) { connector.dataset.live = String(i === index); });
    labels();
    if (index === 2) requestAnimationFrame(pointToToken);
  }
  function tick() {
    timer = setTimeout(function () {
      if (!playing) return;
      if (current === tabs.length - 1) {
        finished = true;
        stop();
        return;
      }
      select(current + 1, false);
      tick();
    }, 4400);
  }
  play.addEventListener("click", function () {
    if (playing) { stop(); return; }
    if (current === tabs.length - 1) select(0, false);
    finished = false;
    playing = true;
    walk.dataset.playing = "true";
    labels();
    tick();
  });
  list.addEventListener("click", function (event) {
    var tab = event.target.closest('[role="tab"]');
    if (tab) select(tabs.indexOf(tab), true);
  });
  list.addEventListener("keydown", function (event) {
    var i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    var j = event.key === "ArrowRight" || event.key === "ArrowDown" ? (i + 1) % tabs.length :
      event.key === "ArrowLeft" || event.key === "ArrowUp" ? (i + tabs.length - 1) % tabs.length :
      event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
    if (j === null) return;
    event.preventDefault();
    select(j, true);
    tabs[j].focus();
  });
  prev.addEventListener("click", function () { if (current > 0) select(current - 1, true); });
  next.addEventListener("click", function () { if (current < tabs.length - 1) select(current + 1, true); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting) stop();
    }).observe(walk);
  }
  reduced.addEventListener("change", stop);

  var descriptions = {
    formato: ["tk identifica las reglas. Tu aplicación sabe qué contrato debe usar para leer las filas de esta respuesta.", "tk identifies the rules. Your application knows which contract to use to read these rows."],
    cantidad: ["n=2 anuncia dos solicitudes. Si solo llega una, mini puede detectar que falta otra.", "n=2 announces two requests. If only one arrives, mini can detect that another is missing."],
    id: ["T-1041 identifica esta solicitud. Es el mismo identificador que tenía el mensaje del cliente.", "T-1041 identifies this request. It is the same ID as the customer's message."],
    prioridad: ["alta ocupa el campo prioridad. Las reglas permiten alta, media o baja; mini comprueba que el valor esté permitido.", "alta fills the priority field. The rules allow alta, media or baja; mini checks that the value is allowed."],
    categoria: ["acceso ocupa el campo categoria. Indica que esta solicitud trata de un problema para entrar a la cuenta.", "acceso fills the category field. This request is about accessing an account."],
    resumen: ["Este texto ocupa el campo resumen. Conserva la descripción del problema en una sola línea.", "This text fills the summary field. It keeps the problem description on one line."],
    horas: ["2 ocupa el campo horas. mini lo convierte en un número entero, para que tu aplicación pueda calcular con él.", "2 fills the hours field. mini reads it as an integer, so your application can use it in calculations."]
  };
  var board = walk.querySelector(".ej-annotated");
  var tokenButtons = Array.from(board.querySelectorAll("[data-token]"));
  var selectedToken = tokenButtons[0];
  var ns = "http://www.w3.org/2000/svg";
  var wire = document.createElementNS(ns, "svg");
  wire.setAttribute("class", "ej-annotation-wire");
  wire.setAttribute("aria-hidden", "true");
  wire.innerHTML = '<defs><marker id="ej-annotation-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0l10 5-10 5z"/></marker></defs><path class="ej-wire-path" marker-end="url(#ej-annotation-arrow)"/>';
  board.appendChild(wire);
  function pointToToken() {
    if (board.getBoundingClientRect().width === 0) return;
    var bounds = board.getBoundingClientRect();
    var token = selectedToken.getBoundingClientRect();
    var note = board.querySelector(".ej-token-explainer").getBoundingClientRect();
    var x = token.left + token.width / 2 - bounds.left;
    var y = token.bottom - bounds.top + 4;
    var bottom = note.top - bounds.top - 7;
    wire.setAttribute("viewBox", "0 0 " + bounds.width + " " + bounds.height);
    var route = selectedToken.closest(".ej-mini-header") ?
      "M24 " + bottom + " H8 V" + (y + 12) + " H" + x + " V" + y :
      "M24 " + bottom + " V" + (bottom - 9) + " H" + x + " V" + y;
    wire.querySelector(".ej-wire-path").setAttribute("d", route);
  }
  function explainToken() {
    board.querySelector("[data-token-description]").textContent = descriptions[selectedToken.dataset.token][english() ? 1 : 0];
    tokenButtons.forEach(function (button) { button.setAttribute("aria-pressed", String(button === selectedToken)); });
    requestAnimationFrame(pointToToken);
  }
  tokenButtons.forEach(function (button) {
    button.addEventListener("click", function () { selectedToken = button; explainToken(); });
  });
  if ("ResizeObserver" in window) new ResizeObserver(pointToToken).observe(board);

  var buildParts = {
    datos: ["mis-datos.json es tu archivo de muestra. mini aprende qué campos y tipos necesita tu aplicación.", "mis-datos.json is your sample file. mini infers the fields and types your application needs."],
    nombre: ["--prefix app pone el nombre app a tu formato. Puedes elegir productos, pedidos o el nombre de tu proyecto.", "--prefix app names your format app. You can choose products, orders or your project's name."],
    carpeta: ["--out .mini guarda el contrato, las instrucciones y las herramientas en una carpeta nueva llamada .mini.", "--out .mini saves the contract, instructions and tools in a new folder named .mini."]
  };
  var buildNote = document.querySelector("[data-build-description]");
  var buildButtons = Array.from(document.querySelectorAll("[data-build-part]"));
  var selectedBuild = buildButtons[0];
  function explainBuild() {
    if (!selectedBuild) return;
    buildButtons.forEach(function (button) { button.setAttribute("aria-pressed", String(button === selectedBuild)); });
    buildNote.textContent = buildParts[selectedBuild.dataset.buildPart][english() ? 1 : 0];
  }
  buildButtons.forEach(function (button) {
    button.addEventListener("click", function () { selectedBuild = button; explainBuild(); });
  });
  document.querySelectorAll("[data-copy-command]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(button.dataset.copyCommand).then(function () {
        var label = button.querySelector("[data-copy-label]");
        var original = label.innerHTML;
        label.textContent = english() ? "Copied" : "Copiado";
        setTimeout(function () { label.innerHTML = original; }, 1600);
      }).catch(function () {});
    });
  });
  new MutationObserver(function () { labels(); explainToken(); explainBuild(); }).observe(document.documentElement, {attributes: true, attributeFilter: ["lang"]});
  select(0, false);
  explainToken();
  explainBuild();
})();
