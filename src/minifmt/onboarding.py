"""Interactive first run for a domain-specific .mini toolkit.

The wizard uses the same builder as ``mini build``. It needs no optional
dependencies and never changes an existing toolkit directory.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from .domain import _strict_json, build_bundle


def _style(text: str, code: str) -> str:
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[{code}m{text}\033[0m"
    return text


def _ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    # Some shells (PowerShell with UTF-8 output encoding) prefix piped answers with a BOM.
    answer = input(f"  {label}{suffix}  › ").replace("﻿", "").strip()
    return answer or default


def _choice(label: str, choices: tuple[str, ...], lang="es") -> str:
    while True:
        value = _ask(label)
        if value in choices:
            return value
        print(f"  {'Elige' if lang == 'es' else 'Choose'} {' / '.join(choices)}.")


def _slug(text: str) -> str:
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_").lower()
    return value if value and value[0].isalpha() else f"datos-{value}" if value else "datos"


def _xml_value(element: ET.Element):
    value = {f"@{key}": val for key, val in element.attrib.items()}
    for child in element:
        tag = child.tag.split("}")[-1]
        item = _xml_value(child)
        if tag in value:
            if not isinstance(value[tag], list):
                value[tag] = [value[tag]]
            value[tag].append(item)
        else:
            value[tag] = item
    text = (element.text or "").strip()
    if text:
        if value:
            value["#text"] = text
        else:
            return text
    return value


def _read_sample(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _strict_json(path.read_text(encoding="utf-8-sig"))
    if suffix in (".csv", ".tsv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t" if suffix == ".tsv" else ",")
            if not reader.fieldnames or any(not name for name in reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("La tabla necesita encabezados únicos y no vacíos.")
            rows = list(reader)
        if not rows or any(None in row for row in rows):
            raise ValueError("La tabla necesita al menos una fila y el mismo número de columnas en cada una.")
        return rows
    if suffix == ".xml":
        root = ET.parse(path).getroot()
        return _xml_value(root)
    raise ValueError("Formato no reconocido. Usa un archivo JSON, CSV, TSV o XML.")


def _value(kind: str, raw: str):
    if kind == "1":
        return raw or "ejemplo"
    if kind == "2":
        return int(raw or "1")
    if kind == "3":
        return float(raw or "1.5")
    answer = (raw or "sí").lower()
    if answer not in ("sí", "si", "s", "true", "1", "no", "n", "false", "0"):
        raise ValueError("usa sí o no")
    return answer in ("sí", "si", "s", "true", "1")


def _new_sample(lang="es"):
    t = lambda es, en: es if lang == "es" else en
    print(t("\n  Define un registro. Puedes ampliar el formato con otras muestras.", "\n  Define one record. You can extend the format with more samples."))
    collection = _ask(t("Nombre del conjunto de registros", "Record collection name"), t("registros", "records"))
    row = {}
    while True:
        name = _ask(t("Campo (Enter para terminar)", "Field (Enter to finish)") if row else t("Primer campo", "First field"))
        if not name:
            if row:
                break
            print(t("  Añade al menos un campo.", "  Add at least one field."))
            continue
        if name in row:
            print(t("  Ese campo ya existe.", "  That field already exists."))
            continue
        print(t("  1 Texto    2 Entero    3 Decimal    4 Sí/No", "  1 Text    2 Integer    3 Decimal    4 Yes/No"))
        kind = _choice(t("Tipo", "Type"), ("1", "2", "3", "4"), lang)
        default = {"1": t("ejemplo", "example"), "2": "1", "3": "1.5", "4": t("sí", "yes")}[kind]
        while True:
            try:
                raw = _ask(t("Valor de muestra", "Sample value"), default)
                row[name] = _value(kind, "sí" if raw.lower() in ("yes", "y") else raw)
                break
            except ValueError:
                print(t("  Ese valor no corresponde al tipo elegido.", "  That value does not match the selected type."))
        print(f"  ✓ {name} {t('añadido', 'added')}")
    return {collection: [row]}


def run() -> int:
    """Guide through language, contract, test and application integration."""
    lang = "es"
    try:
        print(_style("\n  mini setup · .mini → JSON", "1;35"))
        while True:
            lang = _ask("Idioma / Language: es / en", "es").lower()
            if lang in ("es", "en"):
                break
        t = lambda es, en: es if lang == "es" else en
        print(t("\n  Tu IA genera .mini. Tu aplicación sigue recibiendo JSON.",
                "\n  Your AI generates .mini. Your application still receives JSON."))
        print(t("  1 Tengo un JSON de mi IA   2 Definir campos   3 Salir   4 Probar con tickets",
                "  1 I have AI-generated JSON   2 Define fields   3 Exit   4 Try support tickets"))
        mode = _choice(t("¿Cómo empezamos?", "Where do we start?"), ("1", "2", "3", "4"), lang)
        if mode == "3":
            return 0
        if mode == "1":
            while True:
                source = Path(_ask(t("Ruta de tu JSON de muestra (también CSV/XML)", "Sample JSON path (CSV/XML also accepted)")).strip('"\''))
                try:
                    sample = _read_sample(source)
                    break
                except (OSError, ValueError, ET.ParseError) as exc:
                    print(t("  No pude leerlo: ", "  Could not read it: ") + str(exc))
            suggested, sources = _slug(source.stem), [source.name]
        elif mode == "2":
            sample = _new_sample(lang)
            suggested, sources = "data", ["wizard fields"]
        else:
            sample = [{"id": 1, "titulo": "No puedo entrar", "categoria": "acceso", "prioridad": "alta"},
                      {"id": 2, "titulo": "Factura duplicada", "categoria": "facturacion", "prioridad": "media"}]
            suggested, sources = "ticket", ["support example"]
        while True:
            prefix = _ask(t("Nombre corto de tu formato", "Short format name"), suggested)
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", prefix):
                break
            print(t("  Empieza con una letra; usa letras, números o guiones.", "  Start with a letter; use letters, numbers or dashes."))
        destination = Path(_ask(t("Carpeta de salida", "Output folder"), ".mini"))
        contract = build_bundle([sample], prefix, destination, source_names=sources, lang=lang)
        print(_style(t(f"\n  ✓ Toolkit creado en {destination}", f"\n  ✓ Toolkit created in {destination}"), "1;32"))
        print(t("  contract.json: reglas de los campos y sus tipos.", "  contract.json: field and type rules."))
        print(t(f"  prompt.{lang}.md: instrucciones que tu código enviará a la IA.",
                f"  prompt.{lang}.md: instructions your code will send to AI."))
        print(t("  workflow.py: valida, repara, vuelve a comprobar y entrega JSON a tu aplicación.",
                "  workflow.py: validates, repairs, checks again and delivers JSON to your application."))
        print(t("\n  Ahora conectamos el formato al código que llama a tu IA.",
                "\n  Now connect the format to the code that calls your AI."))
        print(t("  1 Todavía no tengo un flujo   2 Elegir mi archivo   3 Buscar en mi proyecto",
                "  1 I do not have a workflow yet   2 Select my file   3 Search my project"))
        integration = _choice(t("¿Ya tienes esa llamada a IA?", "Do you already have that AI call?"), ("1", "2", "3"), lang)
        project = "ruta/a/tu/app.py" if lang == "es" else "path/to/app.py"
        if integration != "1":
            from .integration import prepare
            while True:
                project = _ask(t("Archivo que llama a la IA" if integration == "2" else "Carpeta de tu proyecto",
                                 "File that calls AI" if integration == "2" else "Project directory")).strip('"\'')
                candidate = Path(project)
                if (candidate.is_file() if integration == "2" else candidate.is_dir()):
                    break
                print(t("  Esa ruta no existe o no es del tipo elegido. Inténtalo otra vez.",
                        "  That path does not exist or has the wrong type. Try again."))
            report = prepare(project, destination, lang=lang, apply=False)
            print(t("  Guía de integración: ", "  Integration guide: ") + report["plan"])
            if report["supported"]:
                print(t(f"  Encontré la llamada a la IA en {report['file']}. Cambio propuesto:",
                        f"  Found the AI call in {report['file']}. Proposed change:"))
                diff = Path(report["diff"]).read_text(encoding="utf-8").splitlines()
                for line in [l for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---"))][:12]:
                    print("    " + line.rstrip())
                print(t("  1 Dejar preparado   2 Conectar ahora (guarda una copia del original)",
                        "  1 Keep prepared   2 Connect now (backs up the original)"))
                if _choice(t("Cambio de código", "Code change"), ("1", "2"), lang) == "2":
                    report = prepare(project, destination, lang=lang, apply=True)
                    print(_style(t("  ✓ Código conectado: la IA responde en .mini; tu aplicación recibe el mismo JSON.",
                                   "  ✓ Code connected: AI responds in .mini; your application receives the same JSON."), "1;32"))
                    print(t(f"  Copia del original: {report['backup']}", f"  Original backup: {report['backup']}"))
            else:
                print(t("  Entrega INTEGRATE.md a tu IA de código para adaptar esta llamada y conectar el workflow.",
                        "  Give INTEGRATE.md to your coding AI to adapt this call and connect the workflow."))
        resume = f'mini integrate "{project}" --bundle "{destination}" --lang {lang}'
        if integration == "1":
            print(t(f"  Prueba sin código: copia el contenido de {destination / 'try-prompt.md'} a tu IA y valida su respuesta con:",
                    f"  Test without code: paste the contents of {destination / 'try-prompt.md'} into your AI and check its answer with:"))
            print(f'  python "{destination / "workflow.py"}" response.mini --out result.json')
            print(t("  Tu kit está listo. Cuando tengas el archivo que llama a la IA, sustituye la ruta en:",
                    "  Your toolkit is ready. Once you have the AI call file, replace the path in:"))
        else:
            print(t("  Puedes retomar la integración con:", "  You can resume integration with:"))
        print("  " + resume)
        _save_integration_choice(destination, project, lang, integration == "1")
        print(t(f"  Guía: {destination / 'GUIA.md'}", f"  Guide: {destination / 'README.md'}"))
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\n  Asistente cancelado." if lang == "es" else "\n  Setup cancelled.")
        return 130


def _save_integration_choice(destination, project, lang, deferred):
    """Keep the chosen next action in the offline guides and their integrity manifest."""
    import hashlib
    command = f'mini integrate "{project}" --bundle "{destination}" --lang {lang}'
    for name, heading, text in (
        ("GUIA.md", "Tu siguiente paso", "Todavía no tienes un flujo. Cuando crees el archivo que llama a la IA, sustituye la ruta y ejecuta:" if deferred else "Archivo o proyecto elegido durante setup. Para retomar la integración, ejecuta:"),
        ("README.md", "Your next step", "You do not have a workflow yet. Once you create the file that calls AI, replace the path and run:" if deferred else "File or project selected during setup. To resume integration, run:"),
    ):
        path = destination / name
        path.write_bytes((path.read_text(encoding="utf-8") + f"\n## {heading}\n\n{text}\n\n```sh\n{command}\n```\n").encode("utf-8"))
    settings = destination / "setup.json"
    settings.write_bytes((json.dumps({"language": lang, "integration": {"deferred": deferred, "project": None if deferred else project, "resume_command": command}}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("README.md", "GUIA.md", "setup.json"):
        manifest["files"][name] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
