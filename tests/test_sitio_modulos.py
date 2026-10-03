"""Módulos opcionales del sitio (sitio/modulos.py): descubrimiento, contexto, anclas de la portada y fallos ruidosos."""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SITIO))

import modulos  # noqa: E402

A = modulos.ANCLA
PORTADA = f"""<html><head><title>x</title></head><body>
<p>antes</p>
<!-- {A} COMO FUNCIONA {A} -->
<!-- {A} /COMO FUNCIONA {A} -->
<!-- {A} CUATRO PIEZAS {A} -->
<p>después</p>
</body></html>"""


def escribir(carpeta: Path, nombre: str, codigo: str) -> None:
    (carpeta / f"{nombre}.py").write_text(textwrap.dedent(codigo), encoding="utf-8")


def ctx_falso(sitio: Path, registradas=None) -> SimpleNamespace:
    registradas = [] if registradas is None else registradas
    construir = SimpleNamespace(
        RAIZ=sitio.parent, SITIO=sitio, cabecera=lambda activo="": f"<header data-activo='{activo}'></header>", pie=lambda: "<footer></footer>",
        ambos=lambda es, en: f"{es}|{en}", prefijar_ids=lambda h, p: h, cabeza=lambda: "<!--cabeza-->", __version__="9.9.9",
        SPEC_VERSION="1.1", CIFRAS={"casos_conformidad": 372})
    publicar = SimpleNamespace(registrar_en_linea=registradas.append)
    ctx = modulos.crear_contexto(construir, publicar)
    ctx.registradas = registradas
    return ctx


# --------------------------------------------------------------------------- anclas de la portada
def test_region_reemplaza_solo_lo_que_hay_entre_las_anclas():
    salida = modulos.region(PORTADA, "COMO FUNCIONA", "<section id='cf'>hola</section>")
    assert "<section id='cf'>hola</section>" in salida
    assert salida.index("<p>antes</p>") < salida.index("<section id='cf'>") < salida.index("CUATRO PIEZAS") < salida.index("<p>después</p>")
    assert f"<!-- {A} COMO FUNCIONA {A} -->" in salida and f"<!-- {A} /COMO FUNCIONA {A} -->" in salida


def test_region_es_idempotente():
    una = modulos.region(PORTADA, "COMO FUNCIONA", "<section>uno</section>")
    dos = modulos.region(una, "COMO FUNCIONA", "<section>uno</section>")
    assert una == dos
    tres = modulos.region(dos, "COMO FUNCIONA", "<section>otro</section>")
    assert tres.count("<section>") == 1 and "otro" in tres and "uno" not in tres


@pytest.mark.parametrize("html", ["<p>sin anclas</p>", PORTADA + PORTADA])
def test_region_sin_anclas_o_con_anclas_repetidas_falla(html):
    with pytest.raises(modulos.ModuloError):
        modulos.region(html, "COMO FUNCIONA", "x")


def test_region_no_interpreta_barras_invertidas_del_contenido():
    salida = modulos.region(PORTADA, "COMO FUNCIONA", r"<code>\1 \g<0> \n</code>")
    assert r"<code>\1 \g<0> \n</code>" in salida


def test_recursos_se_añaden_una_sola_vez_aunque_el_sellado_ponga_v():
    una = modulos.recursos(PORTADA, css=["/cf.css"], js=["/cf.js"])
    assert una.count('href="/cf.css"') == 1 and una.index('href="/cf.css"') < una.index("</head>")
    assert una.count('<script defer src="/cf.js">') == 1 and una.index("/cf.js") < una.index("</body>")
    sellada = una.replace('href="/cf.css"', 'href="/cf.css?v=0123456789abcdef"')
    assert modulos.recursos(sellada, css=["/cf.css"], js=["/cf.js"]).count("/cf.css") == 1
    assert modulos.recursos(una, css=["/cf.css"], js=["/cf.js"]) == una


def test_la_portada_simplificada_conserva_las_anclas_antes_de_instalar():
    portada = (SITIO / "index.html").read_text(encoding="utf-8")
    abre, cierra = f"<!-- {A} COMO FUNCIONA {A} -->", f"<!-- {A} /COMO FUNCIONA {A} -->"
    assert portada.count(abre) == portada.count(cierra) == 1
    tira = portada.index("20 mensajes.")
    piezas = portada.index('id="instalar"')
    assert tira < portada.index(abre) < portada.index(cierra) < piezas
    # las anclas de benchmarks.py no se han tocado ni movido
    assert portada.count('    <div class="bench">') == 1 and portada.count(f"<!-- {A} BENCHMARK COMPLETO {A} -->") == 1
    assert modulos.region(portada, "COMO FUNCIONA", "<p>x</p>").count("<p>x</p>") == 1


# --------------------------------------------------------------------------- descubrimiento y fallos
def test_un_modulo_ausente_se_omite_con_un_aviso_claro(tmp_path):
    avisos = []
    estado = modulos.ejecutar(ctx_falso(tmp_path), salida=avisos.append)
    assert estado == {n: "omitido" for n in modulos.MODULOS}
    assert len(avisos) == len(modulos.MODULOS) and all("aviso" in a and "se omite" in a for a in avisos)
    assert "comofunciona" in avisos[0] and "sitio/comofunciona.py" in avisos[0]


def test_un_modulo_que_falla_rompe_el_build(tmp_path):
    escribir(tmp_path, "validacion", """
        def construir(ctx):
            raise ValueError("datos rotos")
    """)
    with pytest.raises(modulos.ModuloError, match="validacion.*datos rotos"):
        modulos.ejecutar(ctx_falso(tmp_path), nombres=("validacion",), salida=lambda *_: None)


@pytest.mark.parametrize("codigo, mensaje", [
    ("def otra(ctx): pass", "construir"),
    ("construir = 3", "construir"),
    ("raise RuntimeError('al importar')", "no se pudo importar"),
    ("def construir(ctx: pass", "no se pudo importar"),  # error de sintaxis
])
def test_un_modulo_mal_formado_rompe_el_build(tmp_path, codigo, mensaje):
    (tmp_path / "economia.py").write_text(codigo, encoding="utf-8")
    with pytest.raises(modulos.ModuloError, match=mensaje):
        modulos.ejecutar(ctx_falso(tmp_path), nombres=("economia",), salida=lambda *_: None)


def test_comofunciona_exige_inyectar_portada(tmp_path):
    escribir(tmp_path, "comofunciona", "def construir(ctx): pass")
    with pytest.raises(modulos.ModuloError, match="inyectar_portada"):
        modulos.ejecutar(ctx_falso(tmp_path), nombres=("comofunciona",), salida=lambda *_: None)


def test_inyectar_portada_que_no_devuelve_texto_rompe_el_build(tmp_path):
    (tmp_path / "index.html").write_text(PORTADA, encoding="utf-8")
    escribir(tmp_path, "comofunciona", """
        def construir(ctx): pass
        def inyectar_portada(html, ctx): return None
    """)
    with pytest.raises(modulos.ModuloError, match="HTML de la portada"):
        modulos.ejecutar(ctx_falso(tmp_path), nombres=("comofunciona",), salida=lambda *_: None)


def test_camino_feliz_inyecta_en_la_portada_y_escribe_paginas(tmp_path):
    (tmp_path / "index.html").write_text(PORTADA, encoding="utf-8")
    escribir(tmp_path, "comofunciona", """
        def construir(ctx):
            ctx.vistos = ctx.cifras["casos_conformidad"]
        def inyectar_portada(html, ctx):
            html = ctx.region(html, "COMO FUNCIONA", '<section id="como-funciona">' + ctx.ambos("Hola", "Hi") + "</section>")
            return ctx.recursos(html, css=["/comofunciona.css"], js=["/comofunciona.js"])
    """)
    escribir(tmp_path, "validacion", """
        def construir(ctx):
            ctx.escribir_pagina("validacion", ctx.pagina("validacion", "Validación", "Validation", "<p>" + ctx.ambos("x", "y") + "</p>"))
    """)
    ctx = ctx_falso(tmp_path)
    estado = modulos.ejecutar(ctx, salida=lambda *_: None)
    assert estado == {"comofunciona": "ok", "validacion": "ok", "economia": "omitido", "flujo": "omitido"}
    portada = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<section id="como-funciona">Hola|Hi</section>' in portada and "/comofunciona.css" in portada
    pagina = (tmp_path / "validacion" / "index.html").read_text(encoding="utf-8")
    assert "<header data-activo='validacion'>" in pagina and "<footer>" in pagina and 'id="contenido"' in pagina
    assert 'data-title-es="Validación — mini-format"' in pagina and "/docs.js" in pagina
    assert ctx.registradas == ["validacion"]
    # ejecutar de nuevo no cambia la portada (idempotente)
    modulos.ejecutar(ctx, salida=lambda *_: None)
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == portada


@pytest.mark.parametrize("ruta", ["../fuera", "en/x", "source/x", "downloads", "docs/x", "", "a/../../b"])
def test_escribir_pagina_rechaza_rutas_reservadas_o_fuera_del_sitio(tmp_path, ruta):
    with pytest.raises(modulos.ModuloError):
        ctx_falso(tmp_path).escribir_pagina(ruta, "<p>x</p>")


def test_escribir_pagina_permite_nombres_que_empiezan_como_una_carpeta_reservada(tmp_path):
    ctx = ctx_falso(tmp_path)
    ctx.escribir_pagina("entrenamiento", "<p>x</p>")   # empieza por «en» pero no es la carpeta /en/
    assert (tmp_path / "entrenamiento" / "index.html").is_file()


def test_leer_json_da_errores_claros(tmp_path):
    (tmp_path.parent / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path.parent / "mal.json").write_text("{", encoding="utf-8")
    ctx = ctx_falso(tmp_path)
    assert ctx.leer_json("ok.json") == {"a": 1}
    with pytest.raises(modulos.ModuloError, match="no existe"):
        ctx.leer_json("falta.json")
    with pytest.raises(modulos.ModuloError, match="no es JSON válido"):
        ctx.leer_json("mal.json")


# --------------------------------------------------------------------------- contrato documentado y módulos reales
def test_el_contexto_real_ofrece_todo_lo_que_documenta_el_docstring():
    import construir
    import publicar
    ctx = modulos.crear_contexto(construir, publicar)
    documentados = {n for par in re.findall(r"^    ctx\.(\w+)(?: / ctx\.(\w+))?", modulos.__doc__, re.M) for n in par if n}
    assert {"root", "sitio", "cabecera", "pie", "ambos", "prefijar_ids", "cabeza", "cabeza_docs", "version", "spec", "leer_json",
            "cifras", "escribir_pagina", "region", "recursos", "pagina"} <= documentados
    for nombre in documentados:
        assert hasattr(ctx, nombre), f"ctx.{nombre} está documentado y no existe"
    assert ctx.cifras["casos_conformidad"] >= 372 and ctx.version == construir.__version__
    assert ctx.cabeza_docs == ctx.cabeza() and "/base.css" in ctx.cabeza_docs
    assert ctx.leer_json("forks/registry.json") is not None
    assert (SITIO / "LEEME_MODULOS.md").is_file()


def test_los_marcadores_de_validacion_y_economia_son_modulos_validos(tmp_path):
    import construir
    import publicar
    ctx = modulos.crear_contexto(construir, publicar)
    destino = {}
    ctx.escribir_pagina = lambda ruta, html: destino.__setitem__(ruta, html)
    for nombre in ("validacion", "economia"):
        modulos.cargar(nombre, SITIO).construir(ctx)
    assert set(destino) == {"validacion", "economia"}
    for ruta, pagina in destino.items():
        assert 'class="site-header"' in pagina and 'class="site-footer"' in pagina, ruta
        assert "en construcción" in pagina and "under construction" in pagina
        assert "<h1>" in pagina and f'data-title-es=' in pagina
        assert not re.search(r"[☀-➿\U0001F300-\U0001FAFF]", pagina), "sin emojis ni dingbats"
    assert construir.ruta_activa("validacion") == ""
