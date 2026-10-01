/* Recorrido accesible: cada paso muestra la misma muestra de principio a fin. */
(function () {
  "use strict";
  var list = document.querySelector(".ej-steps");
  if (!list) return;
  var tabs = Array.from(list.querySelectorAll('[role="tab"]'));
  function select(tab) {
    tabs.forEach(function (item) {
      var active = item === tab;
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
    });
  }
  list.addEventListener("click", function (event) {
    var tab = event.target.closest('[role="tab"]');
    if (tab) select(tab);
  });
  list.addEventListener("keydown", function (event) {
    var i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    var next = event.key === "ArrowRight" || event.key === "ArrowDown" ? (i + 1) % tabs.length :
      event.key === "ArrowLeft" || event.key === "ArrowUp" ? (i + tabs.length - 1) % tabs.length :
      event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    select(tabs[next]);
    tabs[next].focus();
  });
  select(tabs[0]);
})();
