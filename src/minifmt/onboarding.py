"""Interactive first run for a domain-specific .mini toolkit.

The wizard uses the same builder as ``mini build``. It needs no optional
dependencies and never changes an existing toolkit directory.
"""
from __future__ import annotations

import csv
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
    answer = input(f"  {label}{suffix}  › ").strip()
    return answer or default


def _choice(label: str, choices: tuple[str, ...]) -> str:
    while True:
        value = _ask(label)
        if value in choices:
            return value
        print(f"  Elige {' o '.join(choices)}.")


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


def _new_sample():
    print("\n  Define un registro. Puedes ampliar el formato más adelante con otras muestras.")
    collection = _ask("Nombre del conjunto de registros", "registros")
    row = {}
    while True:
        name = _ask("Campo (Enter para terminar)" if row else "Primer campo")
        if not name:
            if row:
                break
            print("  Añade al menos un campo.")
            continue
        if name in row:
            print("  Ese campo ya existe.")
            continue
        print("  1 Texto    2 Entero    3 Decimal    4 Sí/No")
        kind = _choice("Tipo", ("1", "2", "3", "4"))
        default = {"1": "ejemplo", "2": "1", "3": "1.5", "4": "sí"}[kind]
        while True:
            try:
                row[name] = _value(kind, _ask("Valor de muestra", default))
                break
            except ValueError:
                print("  Ese valor no corresponde al tipo elegido. Inténtalo de nuevo.")
        print(f"  ✓ {name} añadido")
    return {collection: [row]}


def run() -> int:
    """Guide the user through a first toolkit; return 130 on interruption."""
    try:
        print(_style("\n  ╭──────────────────────────────────────────╮\n  │  mini setup  ·  tu .mini, paso a paso      │\n  ╰──────────────────────────────────────────╯", "35"))
        print("\n  Tú eliges los datos. mini prepara las instrucciones para la IA")
        print("  y las herramientas para comprobar y leer sus respuestas.")
        print("\n  ¿Cómo quieres empezar?\n  1  Tengo un archivo con datos\n  2  Quiero definir mis campos aquí\n  3  Salir\n")
        mode = _choice("Elige una opción", ("1", "2", "3"))
        if mode == "3":
            return 0
        print(_style("\n  Paso 1/3  ·  Tu punto de partida", "1;36"))
        if mode == "1":
            while True:
                source = Path(_ask("Ruta del archivo con tus datos").strip('"\''))
                try:
                    sample = _read_sample(source)
                    break
                except (OSError, ValueError, ET.ParseError) as exc:
                    print(f"  No pude leerlo: {exc}")
            suggested = _slug(source.stem)
            sources = [source.name]
        else:
            sample = _new_sample()
            suggested = "mi-formato"
            sources = ["campos definidos en el asistente"]
        print(_style("\n  Paso 2/3  ·  Nombre y carpeta", "1;35"))
        print("  El nombre corto identifica tu formato dentro de cada documento .mini.")
        while True:
            prefix = _ask("¿Cómo se llama tu formato?", suggested)
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", prefix):
                break
            print("  Usa letras, números, guion o guion bajo; empieza con una letra.")
        destination = Path(_ask("¿Dónde guardamos los archivos?", ".mini"))
        print(_style("\n  Paso 3/3  ·  Preparando tu .mini", "1;35"))
        contract = build_bundle([sample], prefix, destination, source_names=sources)
        print(_style(f"\n  ✓ Toolkit creado en {destination}", "1;32"))
        print(f"  {contract['sample_records']} registro(s) de muestra · {len(contract['record_fields'])} campo(s)")
        print("\n  Tus datos → reglas e instrucciones → respuesta .mini → datos comprobados")
        print("  contract.json    las reglas de tus datos")
        print("  prompt.es.md     las instrucciones que añades a tu petición de IA")
        print("  parser.py        convierte la respuesta en datos de tu aplicación")
        print("  validator.py     avisa si falta algo o un valor no es válido")
        print(f"\n  Empieza por {destination / 'GUIA.md'} y {destination / 'example.mini'}")
        print(f'  Para validar una respuesta de IA: python "{destination / "validator.py"}" respuesta.mini')
        print(f'  Para convertirla a datos: python "{destination / "parser.py"}" decode respuesta.mini')
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\n  Asistente cancelado.")
        return 130
