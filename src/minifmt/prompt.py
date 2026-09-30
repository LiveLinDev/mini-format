"""Generate the transferable specification block for a contract.

The output is the text a developer pastes into a system prompt so that a
generative model produces valid documents of that fork, or so that a model
writes a parser for it without any other knowledge (Section V of the paper:
"an example illustrates, a specification defines").
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contract import Contract, Field


def _field_doc(f: Field, sep: str, lang: str) -> str:
    es = lang == "es"
    opt = (" (opcional)" if es else " (optional)") if f.optional else ""
    if f.type == "enum":
        return f"{f.name}: " + ("uno de " if es else "one of ") + "{" + "|".join(f.values or []) + "}" + opt
    if f.type in ("list", "mlist"):
        it = f.item if f.item != "enum" else "{" + "|".join(f.item_values or []) + "}"
        rng = ""
        if f.min is not None or f.max is not None:
            rng = (f", entre {int(f.min or 0)} y {int(f.max) if f.max is not None else '∞'} elementos" if es
                   else f", {int(f.min or 0)} to {int(f.max) if f.max is not None else '∞'} elements")
        base = (f"{f.name}: lista de {it} separada por '{sep}'{rng}" if es
                else f"{f.name}: '{sep}'-separated list of {it}{rng}")
        if f.type == "mlist":
            rule = {"exactly_one": ("exactamente un" if es else "exactly one"),
                    "at_least_one": ("al menos un" if es else "at least one"),
                    "at_most_one": ("como máximo un" if es else "at most one"),
                    "any": ("cero o más" if es else "zero or more")}[f.marker]
            base += (f"; {rule} elemento lleva el sufijo * (seleccionado)" if es
                     else f"; {rule} element carries the suffix * (selected)")
        return base + opt
    if f.type == "tuple":
        comps = sep.join(f"{c.name}:{c.type}" for c in f.items)
        return (f"{f.name}: tupla fija '{comps}' separada por '{sep}'" if es
                else f"{f.name}: fixed tuple '{comps}' separated by '{sep}'") + opt
    rng = ""
    if f.min is not None or f.max is not None:
        rng = f" [{'' if f.min is None else f.min}..{'' if f.max is None else f.max}]"
    return f"{f.name}: {f.type}{rng}" + _format_hint(f.type, es) + opt + (f" — {f.desc}" if f.desc else "")


def _format_hint(t: str, es: bool) -> str:
    """Textual form of the types whose lexical rule is not self-evident (SPEC 1.1 §6)."""
    if t == "date":
        return " (AAAA-MM-DD)" if es else " (YYYY-MM-DD)"
    if t == "decimal":
        return " (decimal exacto sin exponente, p. ej. 12.50)" if es else " (exact decimal without exponent, e.g. 12.50)"
    return ""


def spec_block(c: Contract, lang: str = "en", example: Optional[str] = None) -> str:
    es = lang == "es"
    sep = c.list_separator
    hdr_keys = [k for k in c.header_keys if k not in ("v",)]
    hdr_desc = ", ".join(f"{k}={'<'+c.header_keys[k].type+'>'}" + ("" if c.header_keys[k].required else "?") for k in hdr_keys)
    core = "\n".join(f"  {i+1}. {_field_doc(f, sep, lang)}" for i, f in enumerate(c.core))
    ext = "\n".join(f"  {len(c.core)+i+1}. {_field_doc(f, sep, lang)}" for i, f in enumerate(c.extensions))
    L: List[str] = []
    if es:
        L.append(f"FORMATO .mini — familia '{c.prefix}' v{c.version}" + (f" ({c.name})" if c.name else ""))
        if c.description:
            L.append(c.description)
        L.append("Reglas:")
        L.append(f"- Texto plano UTF-8. La PRIMERA línea es la cabecera: '{c.prefix}|{hdr_desc}'. n es obligatorio y debe ser igual al número exacto de líneas de registro.")
        L.append("- Después de la cabecera, UNA línea por registro; nada más (sin comentarios, sin bloques de código, sin líneas en blanco intermedias).")
        L.append(f"- Cada registro tiene los campos en ESTE orden, separados por '|' (el orden es la semántica; no se escriben nombres de campo):")
        L.append(core)
        if ext:
            L.append("  Campos de extensión (opcionales, solo al final, pueden omitirse):")
            L.append(ext)
        L.append(f"- Si un elemento de lista contiene el separador '{sep}', enciérralo entre comillas dobles al estilo CSV (\"impacto{sep} justicia y evidencia\"; el marcador * va después de la comilla de cierre) o escapa el separador como '\\{sep}'. Un asterisco final literal se escribe '\\*'.")
        L.append(f"- Escapes válidos en cualquier valor: '\\|' para una barra vertical literal, '\\\\' para una barra invertida, '\\n' para un salto de línea.")
        L.append("- Valores numéricos sin comillas; booleanos true/false. Los campos escalares no llevan comillas.")
        L.append("- Un campo vacío significa nulo (solo permitido en campos opcionales).")
        L.append(f"- Registro: {c.arity} campos núcleo" + (f" + hasta {len(c.extensions)} de extensión" if c.extensions else "") + ".")
    else:
        L.append(f".mini FORMAT — family '{c.prefix}' v{c.version}" + (f" ({c.name})" if c.name else ""))
        if c.description:
            L.append(c.description)
        L.append("Rules:")
        L.append(f"- Plain UTF-8 text. The FIRST line is the header: '{c.prefix}|{hdr_desc}'. n is mandatory and must equal the exact number of record lines.")
        L.append("- After the header, ONE line per record and nothing else (no comments, no code fences, no blank lines in between).")
        L.append("- Each record has these fields in THIS order, separated by '|' (position is the semantics; field names are never written):")
        L.append(core)
        if ext:
            L.append("  Extension fields (optional, tail only, may be omitted):")
            L.append(ext)
        L.append(f"- If a list element contains the separator '{sep}', enclose the element in double quotes CSV-style (\"impact{sep} justice and evidence\"; the * marker goes after the closing quote) or escape the separator as '\\{sep}'. A literal trailing asterisk is written '\\*'.")
        L.append(f"- Escapes valid in any value: '\\|' for a literal vertical bar, '\\\\' for a backslash, '\\n' for a line break.")
        L.append("- Numbers unquoted; booleans true/false. Scalar fields are never quoted.")
        L.append("- An empty field means null (allowed only for optional fields).")
        L.append(f"- Record: {c.arity} core fields" + (f" + up to {len(c.extensions)} extension fields" if c.extensions else "") + ".")
    if example:
        L.append(("Ejemplo válido:" if es else "Valid example:"))
        L.append(example)
    return "\n".join(L)


def parser_prompt(c: Contract, fixtures: Dict[str, str], lang: str = "en") -> str:
    """Prompt asking a model to write a deterministic parser for the contract."""
    es = lang == "es"
    L = [spec_block(c, lang)]
    L.append("")
    if es:
        L.append(f"TAREA: escribe un parser determinista en Python para la familia '{c.prefix}'. Debe: validar la cabecera y n; validar la aridad de cada registro; procesar listas, tuplas y el marcador *; aplicar los escapes; y devolver el objeto JSON canónico con la forma {{'prefix', 'header', '{c.records_key}': [registros]}} donde cada registro es un objeto con los nombres de campo indicados; una lista marcada se devuelve como dos claves hermanas del registro: la lista de elementos y el índice (o índices) seleccionado(s), con los nombres indicados en el contrato (p. ej. 'options' y 'correct'). Si la regla del marcador es exactly_one/at_most_one, el valor seleccionado es un único índice base 0 (o nulo); si es at_least_one/any, es siempre una lista de índices ascendentes base 0, incluso cuando solo hay un elemento marcado.")
        L.append("Rechaza con una excepción cualquier documento inválido, indicando la línea. No uses librerías externas.")
    else:
        L.append(f"TASK: write a deterministic Python parser for family '{c.prefix}'. It must: validate the header and n; validate the arity of every record; process lists, tuples and the * marker; apply the escapes; and return the canonical JSON object shaped {{'prefix', 'header', '{c.records_key}': [records]}} where each record is an object keyed by the field names above; a marked list is returned as two sibling keys of the record: the element list and the selected index (or indices), named as the contract states (e.g. 'options' and 'correct'). When the marker rule is exactly_one/at_most_one the selected value is a single 0-based index (or null); when it is at_least_one/any it is always a list of ascending 0-based indices, even when only one element is marked.")
        L.append("Reject any invalid document with an exception that reports the line. No external libraries.")
    for name, content in fixtures.items():
        L.append("")
        L.append(f"--- fixture: {name} ---")
        L.append(content)
    return "\n".join(L)
