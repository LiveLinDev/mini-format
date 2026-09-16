"""Construye el sitio de mini-format: documentación (desde los .md del repositorio,
los contratos de forks/ y los códigos de error del núcleo) y el playground re-vestido
con el sistema de diseño del sitio.

    python sitio/construir.py            # escribe sitio/docs/** y sitio/playground/index.html

No toca playground/ ni ningún archivo fuera de sitio/. Requiere `markdown` (pip).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import markdown

RAIZ = Path(__file__).resolve().parents[1]
SITIO = RAIZ / "sitio"
sys.path.insert(0, str(RAIZ / "src"))
from minifmt import Registry, __version__, SPEC_VERSION  # noqa: E402

REPO = "https://github.com/LiveLinDev/mini-format"
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800'
         '&family=Martian+Mono:wght@400;500;600;700&display=swap">')

# --------------------------------------------------------------------------- códigos de error
ERRORES = [
    ("E01", "E_NO_HEADER", "Falta la cabecera", "El documento no empieza con la línea de cabecera `prefijo|n=…`. Sin ella no hay contrato que aplicar: es el único error que impide construir el documento incluso en modo tolerante.", "§5, §8"),
    ("E02", "E_UNKNOWN_PREFIX", "Prefijo distinto del contrato", "El prefijo de la cabecera no coincide con el del contrato con el que se está validando (o no existe en el registro de familias).", "§5"),
    ("E03", "E_NO_COUNT", "Falta `n`", "La cabecera no declara `n`, el número de registros. `n` es obligatorio: permite detectar respuestas truncadas y registros perdidos.", "§5"),
    ("E04", "E_COUNT_MISMATCH", "Número de registros distinto de `n`", "Se declararon `n` registros pero se leyó otra cantidad de líneas válidas. En modo tolerante el documento se construye igual y este error queda registrado; el lector en streaming lo expone como `missing`.", "§5, §9"),
    ("E05", "E_ARITY", "Aridad del registro fuera de rango", "La línea tiene menos campos que el núcleo del contrato o más que núcleo + extensiones. La regla de compatibilidad hacia adelante (ignorar campos excedentes) está en borrador para SPEC 1.1.", "§6, §10"),
    ("E06", "E_TYPE", "Tipo incorrecto o requerido vacío", "El valor no se puede interpretar con el tipo declarado (`int`, `float`, `bool`…) o un campo requerido llegó vacío.", "§6"),
    ("E07", "E_LIST_ARITY", "Aridad de lista o tupla", "Una lista tiene menos o más elementos de los permitidos, o una tupla no tiene exactamente los declarados.", "§6"),
    ("E08", "E_MARKER", "Regla del marcador violada", "El marcador `*` de elemento seleccionado aparece donde no corresponde, falta cuando es obligatorio, o se repite en una lista de selección única.", "§3.2, §6"),
    ("E09", "E_ESCAPE", "Escape inválido", "Secuencia de escape no reconocida. Las válidas son `\\|`, `\\\\`, `\\n`, `\\,` (dentro de listas) y `\\*` (dentro de listas). En modo tolerante el registro se descarta.", "§3.3"),
    ("E10", "E_ENUM", "Valor fuera de la enumeración", "El valor no está entre los admitidos por un campo `enum`.", "§6"),
    ("E11", "E_UNIQUE", "Valor único duplicado", "Un campo declarado `unique` repite un valor ya visto en otro registro válido. Una línea rechazada no reserva su valor.", "§6"),
    ("E12", "E_HEADER_KEY", "Entrada de cabecera malformada o ausente", "Una clave requerida de la cabecera falta, o una entrada `clave=valor` está mal formada (por ejemplo, sin `=`).", "§5"),
    ("E13", "E_RANGE", "Fuera de rango numérico", "Un número está fuera del `min`/`max` declarado en el contrato.", "§6"),
    ("E20", "E_CONTRACT", "Contrato inválido", "El `contract.json` no cumple la norma: falta el prefijo, hay nombres duplicados, un tipo desconocido, un separador de lista no permitido… Se detecta al cargar el contrato, no al leer documentos.", "§10"),
    ("E21", "E_FORK", "Invariante de familia violado", "Una familia rompe alguno de los cinco invariantes: cambia el núcleo heredado, inserta campos fuera de la cola, o sus fixtures no hacen ida y vuelta. Lo comprueba `mini check-forks`.", "§10"),
]

# --------------------------------------------------------------------------- navegación de docs
GRUPOS = [
    ("Empezar", [("docs", "Introducción"), ("docs/quickstart", "Inicio rápido")]),
    ("Norma", [("docs/spec", "Especificación 1.0"), ("docs/spec/cambios", "Borrador 1.1"), ("docs/forking", "Extender: familias"), ("docs/forks", "Familias oficiales"), ("docs/errors", "Códigos de error")]),
    ("Bibliotecas", [("docs/python", "Python"), ("docs/typescript", "TypeScript"), ("docs/cli", "Herramienta de línea de comandos"), ("docs/conformance", "Suite de conformidad")]),
    ("Evidencia", [("docs/metodologia", "Metodología y experimentos")]),
    ("Proyecto", [("docs/contribuir", "Contribuir"), ("docs/licencia", "Licencia")]),
]
ORDEN = [ruta for _, items in GRUPOS for ruta, _ in items]


def md(texto: str) -> str:
    return markdown.markdown(texto, extensions=["tables", "fenced_code", "toc", "sane_lists"],
                             extension_configs={"toc": {"permalink": "#", "permalink_class": "anchor", "permalink_title": "Enlace a esta sección"}})


def reescribir_enlaces(h: str) -> str:
    """Enlaces relativos del repositorio -> rutas del sitio o al repositorio."""
    mapa = {"SPEC.md": "/docs/spec/", "FORKING.md": "/docs/forking/", "CONTRIBUTING.md": "/docs/contribuir/",
            "LICENSE": "/docs/licencia/", "README.md": "/docs/", "playground/index.html": "/playground/",
            "conformance/README.md": "/docs/conformance/", "ts/README.md": "/docs/typescript/"}
    def sub(m):
        href = m.group(1)
        if href.startswith(("http", "#", "/", "mailto:")):
            return m.group(0)
        base = href.split("#")[0]
        if base in mapa:
            return f'href="{mapa[base]}"'
        if base.startswith("forks/") and base.count("/") == 1:
            return f'href="/docs/forks/{base.split("/")[1]}/"'
        return f'href="{REPO}/blob/main/{href}"'
    h = re.sub(r'href="([^"]+)"', sub, h)
    h = re.sub(r'src="(?!http)([^"]+)"', lambda m: f'src="{REPO}/raw/main/{m.group(1)}"', h)
    return h


def cabecera(activo: str = "") -> str:
    def a(ruta, txt):
        cur = ' aria-current="page"' if activo.startswith(ruta) else ""
        return f'<li><a href="/{ruta}/"{cur}>{txt}</a></li>'
    return f'''<a class="skip" href="#contenido">Saltar al contenido</a>
<header class="site-header"><div class="wrap nav">
  <a class="brand" href="/"><svg class="glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" aria-hidden="true"><path d="M3 6h18M3 12h12M3 18h7"/><circle cx="20" cy="15" r="2.6"/></svg>mini-format</a>
  <ul class="nav-links">{a("docs","Documentación")}{a("docs/spec","Especificación")}{a("docs/errors","Errores")}{a("docs/forks","Familias")}{a("playground","Playground")}</ul>
  <span class="spacer"></span>
  <a class="icon-link" href="{REPO}" aria-label="Repositorio en GitHub"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18-6-6 6-6M15 6l6 6-6 6"/></svg></a>
  <a class="btn btn-solid" href="/docs/quickstart/">Instalar</a>
</div></header>'''


PIE = f'''<footer class="site-footer"><div class="wrap"><div class="fgrid">
<div><h3>Aprender</h3><ul><li><a href="/docs/">Introducción</a></li><li><a href="/docs/quickstart/">Inicio rápido</a></li><li><a href="/docs/spec/">Especificación 1.0</a></li><li><a href="/docs/errors/">Índice de errores</a></li></ul></div>
<div><h3>Componente</h3><ul><li><a href="/docs/python/">Biblioteca Python</a></li><li><a href="/docs/typescript/">Biblioteca TypeScript</a></li><li><a href="/docs/cli/">Herramienta</a></li><li><a href="/docs/conformance/">Conformidad</a></li></ul></div>
<div><h3>Evidencia</h3><ul><li><a href="{REPO}/tree/main/experiments/v5_ancho">Eje de ancho (V5)</a></li><li><a href="{REPO}/tree/main/experiments/v1_tokens">Tokens (V1)</a></li><li><a href="{REPO}/tree/main/experiments/v4_costos">Costos (V4)</a></li><li><a href="/docs/metodologia/">Metodología</a></li></ul></div>
<div><h3>Proyecto</h3><ul><li><a href="{REPO}">Repositorio</a></li><li><a href="/playground/">Playground</a></li><li><a href="/docs/licencia/">Licencia MIT</a></li><li><a href="/docs/contribuir/">Contribuir</a></li></ul></div>
</div><div class="colophon">mini-format {__version__} · SPEC {SPEC_VERSION} · Adrián Palma Obispo y Erick Palomino Santa Cruz · UPC, 2026.</div></div></footer>'''


def lateral(activo: str) -> str:
    out = []
    for titulo, items in GRUPOS:
        out.append(f"<h4>{titulo}</h4><ul>")
        for ruta, txt in items:
            cur = ' aria-current="page"' if ruta == activo else ""
            out.append(f'<li><a href="/{ruta}/"{cur}>{txt}</a></li>')
        out.append("</ul>")
    return "".join(out)


def pagina_docs(ruta: str, titulo: str, cuerpo: str, lang: str | None = None, crumbs: str = "") -> None:
    i = ORDEN.index(ruta) if ruta in ORDEN else -1
    prev = f'<a href="/{ORDEN[i-1]}/">← anterior<b>{dict((r, t) for _, it in GRUPOS for r, t in it)[ORDEN[i-1]]}</b></a>' if i > 0 else "<span></span>"
    nxt = f'<a href="/{ORDEN[i+1]}/">siguiente →<b>{dict((r, t) for _, it in GRUPOS for r, t in it)[ORDEN[i+1]]}</b></a>' if 0 <= i < len(ORDEN) - 1 else "<span></span>"
    aviso = ('<p class="lang">Este documento se publica en inglés porque es el texto normativo del repositorio; '
             'la traducción no es la fuente de verdad.</p>') if lang == "en" else ""
    doc = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)} — mini-format</title>{FONTS}<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/docs.css"></head>
<body>{cabecera(ruta)}
<div class="docs-shell"><aside class="docs-side" aria-label="Documentación">{lateral(ruta)}</aside>
<main class="docs-main" id="contenido"><article class="docs-article"><p class="crumbs"><a href="/docs/">docs</a> / {crumbs or html.escape(titulo)}</p>{aviso}<div class="prose">{cuerpo}</div>
<nav class="pager">{prev}{nxt}</nav></article></main></div>{PIE}</body></html>'''
    destino = SITIO / ruta / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(doc, encoding="utf-8")


def md_archivo(rel: str) -> str:
    return reescribir_enlaces(md((RAIZ / rel).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- páginas
def construir_docs() -> int:
    n = 0
    pagina_docs("docs", "Introducción", md_archivo("README.md"), lang="en"); n += 1

    pagina_docs("docs/quickstart", "Inicio rápido", md(f"""
# Inicio rápido

mini-format {__version__} implementa la especificación `.mini` {SPEC_VERSION}. Los paquetes en PyPI y npm están
previstos en el plan de tareas; hasta entonces se instala desde el repositorio.

## Python

```bash
git clone {REPO}
cd mini-format
pip install -e .            # o bien: PYTHONPATH=src
mini forks                  # lista las 14 familias
mini validate forks/a/fixtures/valid.mini
mini prompt log --lang es   # bloque de especificación para el modelo
```

```python
from minifmt import Registry, parse, dumps, spec_block

reg = Registry.load()                    # descubre forks/*/contract.json
c = reg.get("log")
instruccion = spec_block(c, lang="es")   # va en el prompt de sistema
doc = parse(respuesta, c, strict=False)  # tolerante: acumula errores en doc.errors
doc.records                              # registros válidos, tipados
for e in doc.errors:
    print(e)                             # E10 line 3 [level]: …
```

## TypeScript

Requiere Node ≥ 22.6. El código corre sin compilar con `--experimental-strip-types`.

```bash
cd mini-format/ts
npm test
```

```ts
import {{ Registry, parse, specBlock, createReader }} from './src/index.ts';
const c = Registry.load().get('log');
const lenient = parse(texto, c, {{ strict: false }});
lenient.invalidLines();   // líneas que hay que regenerar
```

## Siguiente paso

Lee la [especificación](/docs/spec/) para entender la cabecera, los tipos y los escapes, o abre el
[playground](/playground/) para validar y comparar tokens sin instalar nada.
""")); n += 1

    pagina_docs("docs/spec", f"Especificación {SPEC_VERSION}", md_archivo("SPEC.md"), lang="en"); n += 1

    pagina_docs("docs/spec/cambios", "Borrador de SPEC 1.1", md("""
# Borrador de SPEC 1.1

Esta página lista lo que está **en preparación**. Nada de esto forma parte todavía del componente publicado
(mini-format 1.0, SPEC 1.0), y no debe citarse como implementado.

## 1. Compatibilidad hacia adelante

SPEC 1.0 §11 declara que un lector debe ignorar los campos añadidos al final por una versión posterior del
contrato. Hoy las dos implementaciones **rechazan con E05** cualquier registro con más campos que
núcleo + extensiones, también en modo tolerante. El borrador define la regla exacta (qué se ignora, qué se
conserva en el canónico, cómo se informa) y añade los casos de conformidad correspondientes.

Reproducción del fallo actual: `python pendientes/prueba_compatibilidad_hacia_adelante.py` en el repositorio de la tesis.

## 2. Diagnósticos con rango

`MiniError` trae código, línea, campo y mensaje. El borrador añade columna inicial y final del fragmento
ofensivo, para que un editor pueda subrayar el rango exacto.

## 3. Publicación de paquetes

`minifmt` en PyPI y `@mini-format/core` en npm, con las 14 familias oficiales incluidas como datos del paquete.

## 4. Experimentos

Tercer tokenizador (de un modelo abierto) en V1; latencia en V4; piloto real de V2/V3 con al menos dos proveedores.
""", ), crumbs='<a href="/docs/spec/">spec</a> / cambios'); n += 1

    pagina_docs("docs/forking", "Extender: familias", md_archivo("FORKING.md"), lang="en"); n += 1

    # familias
    reg = Registry.load(RAIZ / "forks")
    filas = []
    for c in sorted(reg.contracts.values() if hasattr(reg, "contracts") and isinstance(reg.contracts, dict) else reg, key=lambda c: c.prefix):
        padre = f"<code>{c.parent}</code>" if c.parent else "—"
        filas.append(f'<tr><td><a href="/docs/forks/{c.prefix}/"><code>{c.prefix}</code></a></td><td>{html.escape(c.name)}</td><td>{html.escape(c.domain)}</td><td>{len(c.core)}</td><td>{len(c.extensions)}</td><td>{padre}</td></tr>')
    pagina_docs("docs/forks", "Familias oficiales", f"""
<h1>Familias oficiales</h1>
<p>Catorce contratos publicados en <code>forks/</code>. Cada familia es un archivo de datos (<code>contract.json</code>) que
la misma implementación interpreta: parser, serializador, validador y bloque de prompt se derivan de él.
Para crear la tuya, lee <a href="/docs/forking/">Extender: familias</a>.</p>
<table><thead><tr><th>Prefijo</th><th>Nombre</th><th>Dominio</th><th>Núcleo</th><th>Ext.</th><th>Padre</th></tr></thead><tbody>{''.join(filas)}</tbody></table>
"""); n += 1

    for c in sorted(reg, key=lambda c: c.prefix):
        p = reg.paths[c.prefix]
        campos = []
        for f in list(c.core) + list(c.extensions):
            d = f.to_dict()
            extra = []
            if d.get("values"): extra.append("valores: " + ", ".join(map(str, d["values"])))
            for k in ("min", "max", "unique", "optional", "items", "arity"):
                if k in d and d[k] not in (None, False, ""):
                    extra.append(f"{k}: {d[k]}")
            ext = " · ".join(extra)
            campos.append(f"<tr><td><code>{html.escape(f.name)}</code></td><td><code>{html.escape(str(d.get('type','')))}</code></td><td>{html.escape(d.get('desc',''))}{(' <small>(' + html.escape(ext) + ')</small>') if ext else ''}</td><td>{'extensión' if f in c.extensions else 'núcleo'}</td></tr>")
        ejemplo = (p / "fixtures" / "valid.mini").read_text(encoding="utf-8") if (p / "fixtures" / "valid.mini").exists() else ""
        readme = md_archivo(str((p / "README.md").relative_to(RAIZ))) if (p / "README.md").exists() else ""
        cuerpo = f"""
<h1><code>{c.prefix}</code> — {html.escape(c.name)}</h1>
<p>{html.escape(c.description)}</p>
<dl class="errbox"><dt>Dominio</dt><dd>{html.escape(c.domain)}</dd><dt>Versión</dt><dd>{c.version}</dd><dt>Padre</dt><dd>{('<a href="/docs/forks/' + c.parent + '/"><code>' + c.parent + '</code></a>') if c.parent else '— (raíz)'}</dd><dt>Clave de registros</dt><dd><code>{c.records_key}</code></dd><dt>Separador de lista</dt><dd><code>{html.escape(c.list_separator)}</code></dd><dt>Archivo</dt><dd><a href="{REPO}/blob/main/forks/{c.prefix}/contract.json">forks/{c.prefix}/contract.json</a></dd></dl>
<h2>Campos por posición</h2>
<table><thead><tr><th>#</th><th>Tipo</th><th>Descripción</th><th>Parte</th></tr></thead><tbody>{''.join(campos)}</tbody></table>
<h2>Ejemplo válido</h2>
<pre><code>{html.escape(ejemplo)}</code></pre>
<p>Cárgalo en el <a href="/playground/">playground</a> o valida con <code>mini validate forks/{c.prefix}/fixtures/valid.mini</code>.</p>
{('<h2>Notas de la familia</h2>' + readme) if readme else ''}
"""
        pagina_docs(f"docs/forks/{c.prefix}", f"Familia {c.prefix}", cuerpo, crumbs=f'<a href="/docs/forks/">familias</a> / {c.prefix}'); n += 1

    # errores
    filas = "".join(f'<tr><td><a href="/docs/errors/{cod}/"><span class="errcode">{cod}</span></a></td><td>{html.escape(t)}</td><td><code>{const}</code></td><td>{sec}</td></tr>' for cod, const, t, _, sec in ERRORES)
    pagina_docs("docs/errors", "Códigos de error", f"""
<h1>Códigos de error</h1>
<p>Quince códigos estables, definidos en <code>src/minifmt/errors.py</code> y reproducidos por la biblioteca TypeScript.
Son parte del contrato público del formato: un validador escrito en otro lenguaje debe producir los mismos códigos
para los mismos documentos, y la <a href="/docs/conformance/">suite de conformidad</a> lo comprueba.</p>
<p>Cada error lleva <strong>código</strong>, <strong>línea</strong> (1-based; 0 para errores de documento), <strong>campo</strong> cuando aplica y un mensaje legible.
La columna exacta está en <a href="/docs/spec/cambios/">borrador para 1.1</a>.</p>
<table><thead><tr><th>Código</th><th>Condición</th><th>Constante</th><th>SPEC</th></tr></thead><tbody>{filas}</tbody></table>
"""); n += 1
    for i, (cod, const, t, desc, sec) in enumerate(ERRORES):
        prev_ = f'<a href="/docs/errors/{ERRORES[i-1][0]}/">← {ERRORES[i-1][0]}</a>' if i else ""
        nxt_ = f'<a href="/docs/errors/{ERRORES[i+1][0]}/">{ERRORES[i+1][0]} →</a>' if i < len(ERRORES) - 1 else ""
        cuerpo = f"""
<h1><span class="errcode">{cod}</span> {html.escape(t)}</h1>
<dl class="errbox"><dt>Constante</dt><dd><code>{const}</code></dd><dt>Especificación</dt><dd><a href="/docs/spec/">{sec}</a></dd><dt>Modo tolerante</dt><dd>{'Impide construir el documento' if cod == 'E01' else ('Se detecta al cargar el contrato' if cod in ('E20','E21') else 'Se registra y el documento se construye igual')}</dd></dl>
{md(desc)}
<h2>Cómo verlo</h2>
<p>En el <a href="/playground/">playground</a>, pestaña «Editor y validador», el botón «Inyectar 3 errores» provoca E04, E05, E08 y E09 sobre el ejemplo cargado.
Desde la línea de comandos, <code>mini diagnose archivo.mini</code> imprime un informe JSON con todos los errores y las líneas a regenerar.</p>
<p style="display:flex;justify-content:space-between">{prev_}<span></span>{nxt_}</p>
"""
        pagina_docs(f"docs/errors/{cod}", f"{cod} — {t}", cuerpo, crumbs=f'<a href="/docs/errors/">errores</a> / {cod}'); n += 1

    # bibliotecas
    pagina_docs("docs/python", "Biblioteca Python", md(f"""
# Biblioteca Python (`minifmt` {__version__})

Implementación de referencia. Sin dependencias en tiempo de ejecución; `tiktoken` es opcional para contar tokens.

## API pública

```python
from minifmt import (Contract, Field, MiniError, MiniValidationError, Document,
                     parse, dumps, detect_prefix, Registry, spec_block, parser_prompt,
                     canonical_equal, roundtrip_ok, __version__, SPEC_VERSION)
```

| Función | Qué hace |
|---|---|
| `Registry.load(dir=…)` | Descubre `forks/*/contract.json`; `reg.get("a")` devuelve el `Contract`. |
| `parse(text, contract, strict=True)` | Analiza y valida. Estricto: lanza `MiniValidationError` con todos los errores. Tolerante (`strict=False`): devuelve `Document` con `records` válidos y `errors`. |
| `Document.to_canonical()` | JSON canónico: `{{"prefix", "header", "<records_key>": [...]}}`. |
| `dumps(obj, contract)` | Canónico → `.mini`. |
| `spec_block(contract, lang="en"|"es")` | Bloque de especificación para el prompt del modelo. |
| `parser_prompt(contract, fixtures, lang)` | Prompt para que un modelo escriba un parser de la familia. |
| `roundtrip_ok(obj, contract)` | `parse(dumps(obj)) == obj` y serialización estable. |
| `detect_prefix(text)` | Prefijo declarado en la cabecera, sin validar. |

## `MiniError`

Campos: `code`, `line` (1-based, 0 = documento), `message`, `field`. `str(e)` produce `E10 line 3 [level]: …`.
Los códigos están en el [índice de errores](/docs/errors/).

## Modo tolerante

```python
doc = parse(texto, c, strict=False)
doc.records          # solo los válidos, con tipos del contrato
doc.errors           # lista de MiniError
doc.record_lines     # línea física de cada registro aceptado
doc.diagnostics()    # informe con las líneas a regenerar (mismo que `mini diagnose`)
```
""")); n += 1

    pagina_docs("docs/typescript", "Biblioteca TypeScript", md_archivo("ts/README.md")); n += 1

    pagina_docs("docs/cli", "Herramienta de línea de comandos", md("""
# Herramienta `mini`

Se instala con la biblioteca Python (`pip install -e .`). Todos los comandos aceptan `--forks DIR` para usar
otro directorio de familias.

| Comando | Qué hace |
|---|---|
| `mini forks` | Lista las familias del registro. |
| `mini validate ARCHIVO` | Validación estricta; sale con 1 si hay errores. |
| `mini diagnose ARCHIVO` | Validación tolerante; imprime un informe JSON con errores y líneas a regenerar. |
| `mini to-json ARCHIVO` | `.mini` → JSON canónico. |
| `mini from-json ARCHIVO --contract PREFIJO` | JSON canónico → `.mini`. |
| `mini prompt PREFIJO --lang es` | Bloque de especificación para el prompt del modelo. |
| `mini tokens ARCHIVO --enc o200k_base` | Tokens y bytes, declarando el tokenizador. |
| `mini check-forks` | Comprueba los cinco invariantes y la ida y vuelta de los fixtures. |
| `mini new-fork PREFIJO --from PADRE --add "campo:tipo"` | Crea una familia nueva a partir de otra. |

```bash
mini validate forks/a/fixtures/valid.mini
mini diagnose respuesta.mini | jq '.errors'
mini prompt log --lang es > prompt_sistema.txt
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
mini check-forks
```
""")); n += 1

    pagina_docs("docs/conformance", "Suite de conformidad", md_archivo("conformance/README.md")); n += 1

    pagina_docs("docs/metodologia", "Metodología y experimentos", md_archivo("experiments/README.md") + md(f"""
## V5 — ancho del registro

Barre el número de campos por registro (3–50) y el tamaño del lote (1–1000) con datos sintéticos deterministas
(semilla 20260915) y tres tokenizadores. Es el experimento del que salen las cifras de la portada.
Script: [`experiments/v5_ancho/correr.py`]({REPO}/tree/main/experiments/v5_ancho).

## Reglas de integridad

* Ninguna cifra publicada sale de un cálculo que no esté en un script del repositorio con sus datos archivados.
* Los pilotos simulados no se citan como resultados.
* Los casos donde mini-format pierde se publican con la misma prominencia que los casos donde gana.
""")); n += 1

    pagina_docs("docs/contribuir", "Contribuir", md_archivo("CONTRIBUTING.md"), lang="en"); n += 1
    lic = html.escape((RAIZ / "LICENSE").read_text(encoding="utf-8"))
    pagina_docs("docs/licencia", "Licencia", f"<h1>Licencia MIT</h1><pre><code>{lic}</code></pre>"); n += 1
    return n


# --------------------------------------------------------------------------- playground
TRADUCCIONES = [
    ('<html lang="en">', '<html lang="es">'),
    ("<title>.mini Playground</title>", "<title>Playground — mini-format</title>"),
    # (las pestañas se traducen al sustituir la cabecera, más arriba)
    ("<b>.mini</b> is a family of contracts. Each card is a fork: a contract (data, not code) that the same parser interprets. Click a card to load its example in the editor. Lineage arrows show <code>parent → child</code> forks that keep the core stable and only append fields.",
     "<b>.mini</b> es una familia de contratos. Cada tarjeta es una familia: un contrato (datos, no código) que interpreta el mismo parser. Pulsa una tarjeta para cargar su ejemplo en el editor. Las flechas de linaje muestran <code>padre → hija</code>: familias que conservan el núcleo y solo añaden campos."),
    ("<label>Fork <select", "<label>Familia <select"),
    (">Load example<", ">Cargar ejemplo<"), (">Load escaping example<", ">Cargar ejemplo con escapes<"), (">Inject 3 errors<", ">Inyectar 3 errores<"),
    ("<h2>.mini document</h2>", "<h2>Documento .mini</h2>"),
    ("<h2>Canonical JSON <span class=\"muted\">(edit and press “JSON → .mini”)</span></h2>", "<h2>JSON canónico <span class=\"muted\">(edita y pulsa «JSON → .mini»)</span></h2>"),
    ("<h2>Contract signature</h2>", "<h2>Firma del contrato</h2>"),
    ("<summary>Prompt block for a generative model (EN)</summary>", "<summary>Bloque de prompt para un modelo generativo (EN)</summary>"),
    ("The current editor document (canonical object) serialized into every format from the <em>same</em> data. TOON is encoded with the <b>official TOON reference implementation</b> (v4.1.1, bundled). Token counts use",
     "El documento actual del editor (objeto canónico) serializado en todos los formatos a partir de los <em>mismos</em> datos. TOON se codifica con la <b>implementación oficial de referencia de TOON</b> (v4.1.1, incluida). El recuento de tokens usa"),
    ("<h2>Tokens per format</h2>", "<h2>Tokens por formato</h2>"), ("<h2>Serialized output</h2>", "<h2>Salida serializada</h2>"),
    ("<label>Show <select", "<label>Mostrar <select"),
    ('<option value="toon">TOON (official, as-is)</option><option value="toon_flat">TOON (flattened, tabular)</option><option value="csv">CSV (flattened)</option><option value="json">JSON compact</option><option value="json_pretty">JSON pretty</option>',
     '<option value="toon">TOON (oficial, tal cual)</option><option value="toon_flat">TOON (aplanado, tabular)</option><option value="csv">CSV (aplanado)</option><option value="json">JSON compacto</option><option value="json_pretty">JSON indentado</option>'),
    ("Design a fork in four steps: (1) choose a parent or start blank, (2) add fields — inherited fields stay fixed, new ones are appended, (3) read the contract + prompt block, (4) download <code>contract.json</code> and run <code>mini check-forks</code>. The invariants of §10 are checked live.",
     "Diseña una familia en cuatro pasos: (1) elige un padre o empieza en blanco, (2) añade campos — los heredados quedan fijos, los nuevos se añaden al final, (3) lee el contrato y el bloque de prompt, (4) descarga <code>contract.json</code> y ejecuta <code>mini check-forks</code>. Los invariantes de §10 se comprueban en vivo."),
    ("<h2>1 · Identity</h2>", "<h2>1 · Identidad</h2>"), ("<h2 style=\"margin-top:14px\">2 · Fields</h2>", "<h2 style=\"margin-top:14px\">2 · Campos</h2>"),
    ("<label>Prefix <input", "<label>Prefijo <input"), ("<label>Name <input", "<label>Nombre <input"), ("<label>Parent <select", "<label>Padre <select"),
    ('<option value="">(none — blank contract)</option>', '<option value="">(ninguno — contrato en blanco)</option>'),
    ("<label>List separator <input", "<label>Separador de lista <input"), ("<label>Records key <input", "<label>Clave de registros <input"),
    (">+ add field<", ">+ añadir campo<"), ('<span class="note">types:', '<span class="note">tipos:'),
    ("<h2 style=\"margin-top:14px\">Invariant check</h2>", "<h2 style=\"margin-top:14px\">Comprobación de invariantes</h2>"),
    ("<h2>3 · Generated contract</h2>", "<h2>3 · Contrato generado</h2>"), (">Download contract.json<", ">Descargar contract.json<"), (">Open example in editor<", ">Abrir ejemplo en el editor<"),
    ("<h2 style=\"margin-top:14px\">Prompt block</h2>", "<h2 style=\"margin-top:14px\">Bloque de prompt</h2>"), ("<h2 style=\"margin-top:14px\">Example document</h2>", "<h2 style=\"margin-top:14px\">Documento de ejemplo</h2>"),
    ("Pre-computed results of <code>benchmark/run_benchmark.py</code> (o200k_base, n = 12 records per fork). Bars are tokens; the dotted line is the content-only lower bound (payload).",
     "Resultados precalculados de <code>benchmark/run_benchmark.py</code> (o200k_base, n = 12 registros por familia). Las barras son tokens; la línea punteada es la cota inferior de solo contenido (carga útil)."),
    ("<h2>Tokens by format and fork (n = 12)</h2>", "<h2>Tokens por formato y familia (n = 12)</h2>"), ("<h2>Summary</h2>", "<h2>Resumen</h2>"),
    ("<h2>Structure</h2>", "<h2>Estructura</h2>"), ("<h2 style=\"margin-top:14px\">Escapes</h2>", "<h2 style=\"margin-top:14px\">Escapes</h2>"),
    ("<h2 style=\"margin-top:14px\">Fork invariants</h2>", "<h2 style=\"margin-top:14px\">Invariantes de familia</h2>"), ("<h2>Error codes</h2>", "<h2>Códigos de error</h2>"),
    ("<tr><th>Code</th><th>Condition</th></tr>", "<tr><th>Código</th><th>Condición</th></tr>"),
    ("Full specification: <code>SPEC.md</code> in the repository. Reference implementation: Python (<code>src/minifmt</code>) and JavaScript (<code>js/mini.js</code>, the engine of this page).",
     'Especificación completa: <a href="/docs/spec/">/docs/spec/</a>. Índice de errores con una página por código: <a href="/docs/errors/">/docs/errors/</a>. Motor de esta página: <code>js/mini.js</code>, el port JavaScript de la referencia Python.'),
]


def construir_playground() -> None:
    tpl = (RAIZ / "playground" / "template.html").read_text(encoding="utf-8")
    # 1) estilos del sitio en lugar de los propios
    tpl = re.sub(r"<style>.*?</style>", FONTS + '<link rel="stylesheet" href="/base.css"><link rel="stylesheet" href="/playground.css">', tpl, count=1, flags=re.S)
    # 2) cabecera del sitio + barra de pestañas (mismo <nav> y #themeBtn que espera el motor)
    cab = cabecera("playground") + '''
<div class="pg-nav"><div class="wrap">
  <nav>
    <button data-tab="forks" class="active">Familias</button>
    <button data-tab="editor">Editor y validador</button>
    <button data-tab="compare">Comparar formatos</button>
    <button data-tab="wizard">Asistente de familias</button>
    <button data-tab="bench">Benchmark</button>
    <button data-tab="spec">Chuleta de la norma</button>
  </nav>
  <button class="toggle" id="themeBtn" title="Cambiar tema" aria-label="Cambiar tema">◐</button>
</div></div>
<main>
<div class="pg-intro"><div><h1>Playground</h1><p>Valida documentos, convierte JSON ↔ .mini, compara tokens contra JSON, YAML, XML, CSV y el codificador oficial de TOON, y diseña tu propia familia. Todo corre en tu navegador.</p></div>
<p class="meta">mini-format ''' + __version__ + ''' · SPEC ''' + SPEC_VERSION + '''<br>motor: js/mini.js · 14 familias</p></div>'''
    tpl = re.sub(r"<header>.*?</header>\s*<main>", cab, tpl, count=1, flags=re.S)
    # 3) pie del sitio
    tpl = re.sub(r"<footer>.*?</footer>", PIE, tpl, count=1, flags=re.S)
    # 4) traducción de las etiquetas visibles de la plantilla
    faltan = []
    for a, b in TRADUCCIONES:
        if a in tpl: tpl = tpl.replace(a, b)
        else: faltan.append(a[:60])
    if faltan:
        print("  aviso: cadenas no encontradas en template.html:", *faltan, sep="\n    ")
    # 5) datos embebidos, igual que playground/build.py
    mini_js = (RAIZ / "js" / "mini.js").read_text(encoding="utf-8")
    toon_js = (RAIZ / "benchmark" / "toon_ref" / "toon.bundle.js").read_text(encoding="utf-8")
    reg = Registry.load(RAIZ / "forks")
    orden = ["a", "q", "card", "sum", "map", "r", "s", "code", "tc", "us", "log", "ner", "cat", "cls"]
    forks = []
    for c in sorted(reg, key=lambda c: (orden.index(c.prefix) if c.prefix in orden else 99, c.prefix)):
        p = reg.paths[c.prefix]
        e = {"prefix": c.prefix, "contract": json.loads((p / "contract.json").read_text(encoding="utf-8")),
             "example": (p / "fixtures" / "valid.mini").read_text(encoding="utf-8")}
        if (p / "fixtures" / "escaping.mini").exists():
            e["escaping"] = (p / "fixtures" / "escaping.mini").read_text(encoding="utf-8")
        forks.append(e)
    import csv
    bench = []
    summ = RAIZ / "benchmark" / "results" / "summary_12.csv"
    if summ.exists():
        for r in csv.DictReader(open(summ, encoding="utf-8")):
            bench.append({k: (float(v) if k != "prefix" and "." in v else (int(v) if k != "prefix" else v)) for k, v in r.items()})
    safe = lambda js: js.replace("</script", "<\\/script")
    out = (tpl.replace("__MINI_JS__", safe(mini_js)).replace("__TOON_JS__", safe(toon_js))
              .replace("__FORKS_JSON__", safe(json.dumps(forks, ensure_ascii=False))).replace("__BENCH_JSON__", safe(json.dumps(bench))))
    destino = SITIO / "playground" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(out, encoding="utf-8")
    print(f"  playground: {len(out.encode('utf-8'))//1024} KB, {len(forks)} familias, {len(bench)} filas de benchmark")


def sellar() -> None:
    """version.json: qué commit construyó lo publicado (GITHUB_SHA en CI, 'local' fuera)."""
    import os
    from datetime import datetime, timezone
    datos = {"commit": os.environ.get("GITHUB_SHA", "local"), "construido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "mini_format": __version__, "spec": SPEC_VERSION}
    (SITIO / "version.json").write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sellar()
    n = construir_docs()
    print(f"  docs: {n} páginas")
    construir_playground()
    print("listo")
