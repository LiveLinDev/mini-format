"""Las cifras que el sitio repite a mano deben coincidir con las calculadas desde el repositorio.

`sitio/cifras.py` calcula (casos de conformidad, códigos de error, familias, versiones) y estas pruebas FALLAN si la
portada, sus traducciones, el JS de la portada, el contenido Markdown del sitio o la documentación que alimenta
/docs/ dicen otra cosa (por ejemplo «303 casos» cuando la suite 1.1 tiene 372).

El cálculo no se valida contra sí mismo: se contrasta con oráculos independientes (el runner de conformidad, los
atributos de `minifmt.errors`, el registro de familias, la versión de `minifmt` y `pyproject.toml`).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SITIO))

import cifras  # noqa: E402

C = cifras.calcular(ROOT)
PUBLICADOS = {
    "index.html": SITIO / "index.html",
    "landing.en.json": SITIO / "landing.en.json",
    "animation.en.json": SITIO / "animation.en.json",
    "app.js": SITIO / "app.js",
}
# Markdown que alimenta /docs/** (README, SPEC, guías...) y el contenido propio del sitio.
FUENTES_DOCS = [*ROOT.glob("README*.md"), *ROOT.glob("SPEC*.md"), *ROOT.glob("BUILD_GUIDE*.md"),
                *ROOT.glob("DOMAIN_PROFILE*.md"), *ROOT.glob("FORKING*.md"), *ROOT.glob("CONTRIBUTING*.md"),
                *ROOT.glob("conformance/README*.md"), *ROOT.glob("ts/README*.md"), *SITIO.glob("content/*.md"),
                *ROOT.glob("benchmark/public/README*.md")]


def leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def sin_etiquetas(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# --------------------------------------------------------------------------- el cálculo contra oráculos independientes
def test_casos_coinciden_con_el_runner_de_conformidad():
    salida = subprocess.run([sys.executable, str(ROOT / "conformance" / "run_python.py")], capture_output=True, text=True,
                            encoding="utf-8", cwd=str(ROOT), env={"PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8",
                                                                   "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}).stdout
    pasados, total = map(int, re.search(r"(\d+)/(\d+) cases passed", salida).groups())
    assert total == C["casos_conformidad"]
    assert pasados == total, "la suite no pasa entera: la portada no puede decir «N/N»"


def test_la_suite_1_1_es_la_1_0_mas_los_nuevos():
    assert C["casos_suite_1_0"] + C["casos_nuevos_1_1"] == C["casos_conformidad"]
    assert C["casos_nuevos_1_1"] > 0
    assert "303 from 1.0" in leer(ROOT / "CHANGELOG.md"), "el dato histórico de la suite 1.0 ya no está en el CHANGELOG"


def test_codigos_de_error_coinciden_con_el_modulo_en_ejecucion():
    from minifmt import errors
    en_ejecucion = sorted(v for k, v in vars(errors).items() if k.startswith("E_") and isinstance(v, str))
    assert C["codigos"] == en_ejecucion
    assert C["codigos_error"] == len(en_ejecucion) == 15


def test_familias_coinciden_con_el_registro():
    from minifmt import Registry
    assert sorted(c.prefix for c in Registry.load(ROOT / "forks")) == C["prefijos_familias"]


def test_versiones_coinciden_con_el_paquete():
    import minifmt
    assert C["version_paquete"] == minifmt.__version__
    assert C["version_spec"] == minifmt.SPEC_VERSION


def test_las_palabras_de_los_numeros_existen():
    assert C["palabra_familias_es"] and C["palabra_familias_en"]
    assert C["palabra_codigos_es"] and C["palabra_codigos_en"]


# --------------------------------------------------------------------------- el texto publicado
def test_portada_dice_el_total_de_casos_vigente():
    total = C["casos_conformidad"]
    texto = sin_etiquetas(leer(PUBLICADOS["index.html"]))
    # «372 casos independientes del lenguaje ... pasan 372/372.»
    assert [int(n) for n in re.findall(r"(\d+) casos independientes", texto)] == [total]
    assert [tuple(map(int, m)) for m in re.findall(r"pasan (\d+)/(\d+)\.", texto)] == [(total, total)]
    # bloque de la terminal «N casos · N pasan · 0 fallan»
    assert re.findall(r"(\d+) casos · (\d+) pasan · (\d+) fallan", texto) == [(str(total), str(total), "0")]
    assert re.findall(r"conformance\.test\.ts · (\d+)/(\d+)", texto) == [(str(total), str(total))]
    # fila de la tabla comparativa
    fila = re.search(r"Suite de conformidad publicada\s*(\d+)", texto)
    assert fila and int(fila.group(1)) == total


def test_traduccion_inglesa_del_total_de_casos():
    total = C["casos_conformidad"]
    mapa = json.loads(leer(PUBLICADOS["landing.en.json"]))
    claves = [k for k in mapa if "casos independientes" in k]
    assert len(claves) == 1, "la frase de la portada debe tener una sola clave de traducción"
    es, en = claves[0], mapa[claves[0]]
    assert re.findall(r"(\d+) casos", es) == [str(total)] and re.findall(r"pasan (\d+)/(\d+)", es) == [(str(total), str(total))]
    assert re.findall(r"(\d+) language-independent cases", en) == [str(total)]
    assert re.findall(r"pass (\d+)/(\d+)", en) == [(str(total), str(total))]
    # y la frase que sigue en la portada es EXACTAMENTE la clave: si no, la traducción se pierde en silencio
    assert claves[0] in re.sub(r"\s+", " ", sin_etiquetas(leer(PUBLICADOS["index.html"]))).replace("  ", " ")


def test_ninguna_frase_de_la_portada_conserva_un_total_distinto():
    total = str(C["casos_conformidad"])
    for nombre, ruta in PUBLICADOS.items():
        for n in re.findall(r"\b(\d{3}) (?:casos|cases)\b", leer(ruta)):
            assert n == total, f"{nombre}: dice «{n} casos» y la suite vigente tiene {total}"


def test_codigos_de_error_en_la_portada():
    n = str(C["codigos_error"])
    html = leer(PUBLICADOS["index.html"])
    assert re.findall(r"(\d+) códigos de error", html) == [n]
    assert re.search(r"Códigos de error estables en la norma</th><td class=\"yes\">(\d+)</td>", html).group(1) == n
    mapa = json.loads(leer(PUBLICADOS["landing.en.json"]))
    for clave, valor in mapa.items():
        if "códigos de error" in clave:
            assert re.findall(r"(\d+) códigos", clave) == [n] and re.findall(r"(\d+) stable error codes", valor) == [n]


def test_familias_en_la_portada_y_sus_traducciones():
    n = C["familias"]
    html = sin_etiquetas(leer(PUBLICADOS["index.html"]))
    assert f"Las {n} familias publicadas son muestras opcionales" in html
    assert "Ver ejemplos de .mini" in html
    assert re.findall(r"(\d+) dominios", html) == [str(n)]
    # «Mostrar las N filas» cuenta las filas de la tabla comparativa (no son familias): debe coincidir con la tabla
    fuente = leer(PUBLICADOS["index.html"])
    tabla = re.search(r'<div class="tablewrap" id="cmp">.*?</table>', fuente, re.S).group(0)
    assert re.findall(r"Mostrar las (\d+) filas", html) == [str(len(re.findall(r"<tr[ >]", tabla)) - 1)]
    mapa = json.loads(leer(PUBLICADOS["landing.en.json"]))
    assert "optional samples" in mapa["Los ejemplos muestran cómo funciona el formato con tickets de soporte. Después creas tu contrato a partir de tus datos. Las 14 familias publicadas son muestras opcionales para estudiar."]
    app = leer(PUBLICADOS["app.js"])
    assert "mini forks" not in app
    anim = json.loads(leer(PUBLICADOS["animation.en.json"]))
    for clave, valor in anim.items():
        assert set(re.findall(r"(\d+) familias", clave)) <= {str(n)}
        assert set(re.findall(r"(\d+) families", valor)) <= {str(n)}


def test_versiones_de_paquete_en_la_portada_y_el_js():
    version = C["version_paquete"]
    patron = re.compile(r"(?:mini[-_]format(?:-core)?[-_ ]|minifmt |softwareVersion\"?:? \"?)v?(\d+\.\d+\.\d+)")
    for nombre, ruta in PUBLICADOS.items():
        for v in patron.findall(leer(ruta)):
            assert v == version, f"{nombre}: menciona la versión {v} y el paquete es {version}"
    for ruta in SITIO.glob("content/*.md"):
        for v in patron.findall(leer(ruta)):
            assert v == version, f"{ruta.name}: menciona la versión {v} y el paquete es {version}"


def test_la_portada_no_llama_mini_format_1_1_a_la_version_del_paquete():
    """«1.1» es la versión de la ESPECIFICACIÓN; el paquete es 1.2.x (auditoría: index.html:25,62)."""
    for nombre in ("index.html", "landing.en.json"):
        assert not re.search(r"mini-format 1\.1\b", leer(PUBLICADOS[nombre])), nombre
    html = leer(PUBLICADOS["index.html"])
    assert f'<span class="badge">{C["version_paquete"]}</span>' in html
    assert f"mini-format {C['version_paquete']} · SPEC {C['version_spec']}" in html


# --------------------------------------------------------------------------- documentación que alimenta /docs/**
@pytest.mark.parametrize("ruta", sorted(FUENTES_DOCS), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_las_fuentes_de_la_documentacion_no_contradicen_las_cifras(ruta):
    texto = leer(ruta)
    total = str(C["casos_conformidad"])
    for m in re.finditer(r"\b(\d{3}) (casos|cases)\b", texto):
        n = m.group(1)
        if n == total:
            continue
        # 303 solo vale como dato histórico de la suite 1.0
        contexto = texto[max(0, m.start() - 160): m.end() + 160]
        assert n == str(C["casos_suite_1_0"]) and "1.0" in contexto, f"{ruta.name}: «{m.group(0)}» sin marcarlo como suite 1.0"
    for m in re.finditer(r"\b(\d+) (familias|families|dominios|domains)\b", texto):
        if int(m.group(1)) > 3:
            assert m.group(1) == str(C["familias"]), f"{ruta.name}: «{m.group(0)}» y hay {C['familias']} familias"


def test_conformidad_publica_el_total_de_la_suite_vigente():
    """/docs/conformance/ debe decir cuántos casos tiene la suite 1.1 (hoy solo citaba los 303 de la 1.0)."""
    import construir
    es, en = construir.aviso_conformidad()
    total = C["casos_conformidad"]
    assert f"<strong>{total} casos</strong>" in es and f"{C['casos_suite_1_0']} heredados" in es and f"{C['casos_nuevos_1_1']} nuevos" in es
    assert f"<strong>{total} cases</strong>" in en and f"{C['casos_suite_1_0']} inherited" in en and f"{C['casos_nuevos_1_1']} new" in en
    assert C["version_spec"] in es and C["version_spec"] in en


def test_las_paginas_generadas_usan_las_cifras_calculadas():
    import construir
    fuente = leer(SITIO / "construir.py") + leer(SITIO / "publicar.py")
    for duro in ("Catorce contratos", "Fourteen contracts", "Quince códigos", "Fifteen stable", "14 familias</p>"):
        assert duro not in fuente, f"construir/publicar vuelven a escribir a mano «{duro}»"
    assert construir.cuenta(C["familias"], C, "familias_es") == C["palabra_familias_es"]
    assert construir.cuenta(99, {}, "familias_es") == "99"


@pytest.mark.skipif(not (SITIO / "docs" / "conformance" / "index.html").exists(), reason="el sitio no está construido (python sitio/construir.py)")
def test_el_sitio_construido_dice_el_total():
    texto = sin_etiquetas(leer(SITIO / "docs" / "conformance" / "index.html"))
    assert f"{C['casos_conformidad']} casos" in texto and f"{C['casos_conformidad']} cases" in texto
    errores = sin_etiquetas(leer(SITIO / "docs" / "errors" / "index.html"))
    assert f"{C['palabra_codigos_es']} códigos estables" in errores
    families = sin_etiquetas(leer(SITIO / "docs" / "forks" / "index.html"))
    assert f"Estas {C['familias']} familias son contratos de muestra" in families
    assert f"Descargar las {C['familias']} familias" in families


# --------------------------------------------------------------------------- ahorros escritos a mano en la portada
def _es(valor: float, decimales: int = 1) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")


def test_los_ahorros_por_ancho_de_la_portada_salen_del_csv_de_v5():
    """«Cuantos más campos, más gana»: mediana del ahorro frente a JSON compacto (o200k_base, lote 1000) de experiments/v5_ancho."""
    import csv
    filas = {int(r["ancho"]): float(r["mediana"]) for r in csv.DictReader(
        (ROOT / "experiments" / "v5_ancho" / "results" / "ancho_resumen.csv").open(encoding="utf-8"))
        if r["tokenizador"] == "o200k_base" and r["formato"] == "json_compact" and r["lote"] == "1000"}
    html = leer(PUBLICADOS["index.html"])
    seccion = html[html.index("Cuantos más campos"): html.index("Mismos datos.")]
    valores = re.findall(r'<figcaption>(\d+) campos</figcaption>.*?--w:([\d.]+)%.*?class="val">([\d,]+) %', seccion, re.S)
    assert [int(a) for a, _, _ in valores] == [3, 20, 50]
    for ancho, barra, etiqueta in valores:
        esperado = filas[int(ancho)]
        assert etiqueta == _es(esperado), f"{ancho} campos: la portada dice {etiqueta} % y el CSV da {esperado}"
        assert float(barra) == round(2 * float(etiqueta.replace(",", ".")), 1), f"{ancho} campos: la barra no corresponde a la escala 0-50 %"
    assert "máximo del eje 50 %" in seccion


def test_los_ahorros_por_tokenizador_de_la_portada_salen_del_csv_de_v1():
    """«El mismo documento no cuesta lo mismo en cada modelo»: mediana e IC95 de experiments/v1_tokens (lote 10, muestreo, k=14)."""
    import csv
    filas = {r["tokenizador"]: r for r in csv.DictReader((ROOT / "experiments" / "v1_tokens" / "results" / "ahorro_resumen.csv").open(encoding="utf-8"))
             if r["n"] == "10" and r["referencia"] == "json_compact" and r["variante"] == "muestreo"}
    html = leer(PUBLICADOS["index.html"])
    seccion = html[html.index("no cuesta lo mismo en cada modelo"): html.index("<!-- ═══════════ API")]
    figuras = re.findall(r"<figcaption>(\w+)</figcaption>.*?class=\"val\">([\d,]+) %</span>.*?IC95 \[([\d,]+) % · ([\d,]+) %\] · k=(\d+)", seccion, re.S)
    assert [f[0] for f in figuras] == ["r50k_base", "cl100k_base", "o200k_base"]
    for nombre, valor, inf, sup, k in figuras:
        fila = filas[nombre]
        assert (valor, inf, sup, k) == (_es(float(fila["mediana"])), _es(float(fila["ic95_inf"])), _es(float(fila["ic95_sup"])), fila["k"]), nombre
