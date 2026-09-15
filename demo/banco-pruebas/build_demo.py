from pathlib import Path
aqui = Path(__file__).parent
mini = (aqui.parents[1] / "js/mini.js").read_text(encoding="utf-8")
assert "</script" not in mini
html = (aqui / "plantilla.html").read_text(encoding="utf-8")
html = html.replace("/*MINI_JS*/", mini).replace("/*LOGICA_JS*/", (aqui / "logica.js").read_text(encoding="utf-8"))
html = html.replace("/*DATOS*/", (aqui / "datos_demo.json").read_text(encoding="utf-8"))
(aqui / "banco_pruebas_mini.html").write_text(html, encoding="utf-8")
print("ok", len(html))
