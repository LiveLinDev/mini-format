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
def test_resultados_publica_cifras_de_conformidad_y_familias(tmp_path):
    import construir
    import modulos
    import validacion

    ctx = modulos.crear_contexto(construir)
    ctx.escribir_pagina = lambda ruta, pagina: (tmp_path / f"{ruta}.html").write_text(pagina, encoding="utf-8")
    validacion.construir(ctx)
    pagina = leer(tmp_path / "validacion.html")
    assert f'{C["casos_conformidad"]} casos de conformidad' in pagina
    assert f'{C["casos_conformidad"]} conformance cases' in pagina
    assert f'{C["familias"]} familias' in pagina and f'{C["familias"]} families' in pagina


def test_ninguna_frase_de_la_portada_conserva_un_total_distinto():
    total = str(C["casos_conformidad"])
    for nombre, ruta in PUBLICADOS.items():
        for n in re.findall(r"\b(\d{3}) (?:casos|cases)\b", leer(ruta)):
            assert n == total, f"{nombre}: dice «{n} casos» y la suite vigente tiene {total}"


def test_los_enlaces_de_inicio_y_las_traducciones_del_recorrido():
    n = C["familias"]
    portada = leer(PUBLICADOS["index.html"])
    for ruta in ("/flujo/", "/validacion/", "/playground/", "/docs/quickstart/"):
        assert f'href="{ruta}"' in portada
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


def test_la_portada_compara_el_transporte_y_el_detalle_conserva_el_costo():
    from benchmarks import inject_benchmarks, resumen_costo

    datos = json.loads(leer(ROOT / "benchmark/public/cloud_results.json"))
    cohorte = datos["cohorts"]["projected_text_batches"]
    precios = datos["price_usd_per_million"]
    costo = {}
    for nombre in ("mini", "json_compact"):
        medicion = cohorte["formats"][nombre]
        gasto = (medicion["application_input_tokens"] * precios["input"]
                 + medicion["output_tokens"] * precios["output"])
        costo[nombre] = gasto / medicion["exact"] / 1000

    portada = leer(PUBLICADOS["index.html"])
    es = inject_benchmarks(portada, "es")
    en = inject_benchmarks(portada, "en")
    transporte = json.loads(leer(ROOT / "benchmark/public/transport_results.json"))
    totales = [sum(d["tokenizers"]["o200k_base"][k] for d in transporte["datasets"].values())
               for k in ("mini", "toon_4_4", "json_compact")]
    ahorro_transporte = f"{100 * (1 - totales[0] / totales[-1]):.1f}"
    assert f"{ahorro_transporte}&nbsp;%" in en
    assert ahorro_transporte.replace(".", ",") + "&nbsp;%" in es
    assert re.findall(r"--width:([0-9.]+)%", en) == [f"{100 * t / max(totales):.2f}" for t in totales]
    assert inject_benchmarks(es, "es") == es

    detalle = resumen_costo(datos, lambda es, en: en)
    ahorro = 100 * (1 - costo["mini"] / costo["json_compact"])
    assert f"{ahorro:.1f}&nbsp;%" in detalle
    for importe in costo.values():
        assert f"${importe:.4f}" in detalle
    assert re.findall(r"--width:([0-9.]+)%", detalle) == [
        f'{100 * costo["mini"] / costo["json_compact"]:.2f}', "100.00",
    ]
