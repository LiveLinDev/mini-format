"""Qué se publica en el servidor, qué entra en el zip de fuentes y qué rutas dispara el workflow del sitio."""
from __future__ import annotations

import io
import re
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITIO = ROOT / "sitio"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(SITIO / "servidor"))

import empaquetar  # noqa: E402
import build_release  # noqa: E402

WORKFLOW = (ROOT / ".github" / "workflows" / "sitio.yml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- política de exclusión
@pytest.mark.parametrize("ruta", [
    "construir.py", "publicar.py", "benchmarks.py", "ejemplo_lote.py", "modulos.py", "cifras.py", "comofunciona.py",
    "validacion.py", "economia.py", "nuevo_generador.py",
    "landing.en.json", "animation.en.json", "desplegar.sh", "LEEME_MODULOS.md",
    "content/build.es.md", "content/quickstart.en.md", "i18n/comofunciona.en.json",
    "servidor/recibir-sitio.sh", "servidor/NGINX_404.md", "servidor/empaquetar.py",
    "__pycache__/modulos.cpython-312.pyc", "docs/__pycache__/x.pyc", "otra.pyc",
])
def test_archivos_de_construccion_no_se_publican(ruta):
    assert not empaquetar.incluir(Path(ruta)), ruta


@pytest.mark.parametrize("ruta", [
    "index.html", "404.html", "base.css", "docs.css", "landing.css", "playground.css", "app.js", "app.en.js", "docs.js",
    "comofunciona.css", "comofunciona.js", "validacion.css", "validacion.js", "favicon.svg", "version.json", "sitemap.xml", "robots.txt",
    "assets/workflow.mp4", "docs/index.html", "en/index.html", "downloads/manifest.json", "playground/index.html",
    # la evidencia enlazada en /source/ se publica aunque sea .py: la exclusión de *.py es solo de la raíz
    "source/experiments/v1_tokens/run.py", "source/benchmark/public/run.py", "source/conformance/cases/types.json",
])
def test_lo_que_el_navegador_necesita_si_se_publica(ruta):
    assert empaquetar.incluir(Path(ruta)), ruta


def arbol(tmp_path: Path, extra=()) -> Path:
    sitio = tmp_path / "sitio"
    for ruta in (*empaquetar.OBLIGATORIOS, "construir.py", "landing.en.json", "content/a.md", "source/x/run.py", *extra):
        archivo = sitio / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text("x", encoding="utf-8")
    return sitio


def test_el_paquete_contiene_lo_publicado_y_nada_mas(tmp_path):
    sitio = arbol(tmp_path)
    buffer = io.BytesIO()
    n = empaquetar.empaquetar(buffer, sitio)
    buffer.seek(0)
    with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
        nombres = sorted(tar.getnames())
        modos = {m.mode for m in tar.getmembers()}
    assert n == len(nombres)
    assert "construir.py" not in nombres and "landing.en.json" not in nombres and "content/a.md" not in nombres
    assert "source/x/run.py" in nombres and "404.html" in nombres and "index.html" in nombres
    assert modos == {0o644}
    assert not any(nombre.startswith(("/", "./", "..")) for nombre in nombres), "rutas relativas a la raíz del sitio"


def test_sin_los_archivos_obligatorios_no_se_empaqueta(tmp_path):
    sitio = arbol(tmp_path)
    (sitio / "404.html").unlink()
    with pytest.raises(SystemExit, match="404.html"):
        empaquetar.empaquetar(io.BytesIO(), sitio)


def test_un_enlace_simbolico_aborta_porque_el_receptor_lo_rechaza(tmp_path):
    sitio = arbol(tmp_path)
    try:
        (sitio / "enlace").symlink_to(sitio / "index.html")
    except (OSError, NotImplementedError):
        pytest.skip("este sistema no permite crear enlaces simbólicos")
    with pytest.raises(SystemExit, match="enlace simbólico"):
        empaquetar.empaquetar(io.BytesIO(), sitio)


def test_el_receptor_exige_lo_mismo_que_el_empaquetador():
    receptor = (SITIO / "servidor" / "recibir-sitio.sh").read_text(encoding="utf-8")
    exigidos = re.search(r"for f in ([^;]+); do", receptor).group(1).split()
    assert set(exigidos) <= set(empaquetar.OBLIGATORIOS), "el receptor exige un archivo que el empaquetador no garantiza"
    assert "404.html" in exigidos


def referencias_locales(html: str) -> set[str]:
    return {m.split("#")[0].split("?")[0] for m in re.findall(r'(?:href|src|poster)="(/[^"]*)"', html)}


@pytest.mark.skipif(not (SITIO / "index.html").exists() or not (SITIO / "docs" / "index.html").exists(), reason="el sitio no está construido")
def test_ninguna_pagina_construida_enlaza_un_archivo_que_se_excluye():
    excluidos = {}
    for pagina in SITIO.rglob("*.html"):
        partes = pagina.relative_to(SITIO).parts
        if partes[0] in {"servidor", "downloads"} and pagina.name != "index.html":
            continue
        for ref in referencias_locales(pagina.read_text(encoding="utf-8")):
            destino = SITIO / ref.lstrip("/")
            if destino.is_dir():
                destino = destino / "index.html"
            if destino.is_file() and not empaquetar.incluir(destino.relative_to(SITIO)):
                excluidos.setdefault(ref, pagina.relative_to(SITIO).as_posix())
    assert excluidos == {}, f"el navegador pide archivos que el despliegue no sube: {excluidos}"


def test_el_js_y_las_plantillas_no_piden_archivos_de_construccion():
    fuentes = [*SITIO.glob("*.js"), *(ROOT / "examples").glob("*/plantilla.html"), ROOT / "playground" / "template.html"]
    for fuente in fuentes:
        texto = fuente.read_text(encoding="utf-8")
        for ruta in re.findall(r"""fetch\(\s*["'](/[^"']+)["']""", texto):
            relativo = Path(ruta.split("?")[0].lstrip("/"))
            assert empaquetar.incluir(relativo), f"{fuente.name} hace fetch de {ruta}, que no se publica"


def test_workflow_y_despliegue_manual_usan_el_empaquetador():
    assert "python sitio/servidor/empaquetar.py" in WORKFLOW
    assert not re.search(r"tar czf - -C sitio", WORKFLOW), "el tar con --exclude a mano volvió al workflow"
    manual = (SITIO / "desplegar.sh").read_text(encoding="utf-8")
    assert "servidor/empaquetar.py" in manual and "tar czf - -C" not in manual


# --------------------------------------------------------------------------- workflow sitio.yml
def test_el_workflow_se_dispara_con_los_datos_del_sitio_y_de_la_validacion():
    import yaml
    datos = yaml.safe_load(WORKFLOW)
    paths = set(datos[True]["push"]["paths"])   # `on:` se lee como True en YAML 1.1
    for requerido in ("evidencia/**", "docs/adr/**", "conformance/cases/**", "experiments/**", "js/**", "tools/**", "sitio/**",
                      "examples/**", ".github/workflows/sitio.yml"):
        assert requerido in paths, requerido
    assert datos[True]["push"]["branches"] == ["main"], "los despliegues solo salen de main"


def test_el_workflow_verifica_las_rutas_nuevas_y_no_toca_los_secretos():
    assert "/validacion/ /economia/" in WORKFLOW
    assert "verificar_publicacion.py" in WORKFLOW
    # mecanismo de secretos y SSH intactos
    for intacto in ("SITIO_SSH_KEY", "SITIO_KNOWN_HOSTS", "environment: produccion", "erick@162.243.33.172 desplegar",
                    "StrictHostKeyChecking=yes", "rm -f ~/.ssh/despliegue"):
        assert intacto in WORKFLOW, intacto


# --------------------------------------------------------------------------- zip de fuentes
def test_el_zip_de_fuentes_incluye_todos_los_modulos_y_ejemplo_lote():
    nombres = set(build_release.site_files())
    assert {"construir.py", "publicar.py", "benchmarks.py", "ejemplo_lote.py", "modulos.py", "cifras.py", "validacion.py", "economia.py",
            "404.html", "LEEME_MODULOS.md", "base.css", "docs.js", "landing.en.json", "animation.en.json", "index.html"} <= nombres
    assert not nombres & build_release.SITE_GENERATED
    assert not any(n in nombres for n in ("desplegar.sh",)), "el despliegue no va en el zip de fuentes"
    # todo archivo fuente de la raíz de sitio/ está incluido, salvo lo generado (un módulo nuevo no se olvida)
    en_disco = {p.name for p in SITIO.iterdir() if p.is_file() and p.suffix in build_release.SITE_SUFFIXES} - build_release.SITE_GENERATED
    assert nombres == en_disco


def test_el_zip_de_fuentes_trae_lo_que_el_sitio_lee_y_no_trae_lo_restringido():
    assert {"docs", "evidencia", "sitio/i18n", "sitio/content", "sitio/assets"} <= set(build_release.SOURCE_DIRS)
    assert "tools/verificar_publicacion.py" in build_release.SOURCE_FILES
    assert build_release.is_excluded_tree(ROOT / "evidencia" / "restringida" / "sesion.json")
    assert build_release.is_excluded_tree(ROOT / "evidencia" / "restringida")
    assert not build_release.is_excluded_tree(ROOT / "evidencia" / "esquemas" / "corrida.schema.json")
    assert not build_release.is_excluded_tree(ROOT / "evidencia" / "restringida_no" / "x")
    copiados = {p.relative_to(ROOT / "evidencia").as_posix() for p in build_release.files_under(ROOT / "evidencia")}
    assert "esquemas/corrida.schema.json" in copiados and not any(c.startswith("restringida") for c in copiados)
