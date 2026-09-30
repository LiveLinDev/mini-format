"""Genera repair_parity.json: salidas de la referencia Python (minifmt.ai.repair) para
comparar con ts/src/repair.ts. Sin red ni modelos.

    PYTHONPATH=src python ts/test/fixtures/gen_repair_parity.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from minifmt import Registry
from minifmt.ai import extract_document, merge_repair, repair_request

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("repair_parity.json")
REG = Registry.load(ROOT / "forks")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def mutate(lines, rng):
    """Daños típicos de una salida generada, deterministas por semilla."""
    ls = list(lines)
    kinds = []
    for _ in range(rng.randint(1, 3)):
        i = rng.randrange(1, len(ls)) if len(ls) > 1 else 0
        k = rng.choice(["pipe", "type", "prose", "newline", "drop_field", "extra_field", "dup", "backslash"])
        kinds.append(k)
        line = ls[i]
        if k == "pipe" and "," in line:
            ls[i] = line.replace(",", "|", 1)
        elif k == "type":
            parts = line.split("|")
            j = rng.randrange(len(parts))
            parts[j] = "x" + parts[j]
            ls[i] = "|".join(parts)
        elif k == "prose":
            ls.insert(i, "Nota del modelo sin barras")
        elif k == "newline" and " " in line:
            ls[i] = line.replace(" ", "\n", 1)
        elif k == "drop_field":
            ls[i] = line.rsplit("|", 1)[0]
        elif k == "extra_field":
            ls[i] = line + "|EXTRA|MAS"
        elif k == "dup":
            ls.insert(i, ls[i])
        elif k == "backslash":
            ls[i] = line + "\\"
    return ls, kinds


def wrap(text, rng):
    r = rng.random()
    if r < 0.25:
        return "Aquí tienes:\n```mini\n" + text + "\n```\nEspero que sirva."
    if r < 0.4:
        return "Resultado:\n" + text + "\nFin del documento"
    if r < 0.5:
        return "```\n" + text + "\n```"
    return text


def answers(req, valid_lines, rng):
    """Respuestas de reparación: correcta, parcial, con eliminación, sin cabecera, vacía."""
    good = []
    for it in req.items:
        if it.is_header:
            good.append(valid_lines[0])
        elif "|" not in it.text:
            good.append("-")
        else:
            best = max(valid_lines[1:], key=lambda v: len(set(v.split("|")) & set(it.text.replace("\n", " ").split("|"))))
            good.append(best)
    k = len(req.items)
    out = ["%s|n=%d\n" % (req.prefix, k) + "\n".join(good)]
    if k:
        out.append("```\n%s|n=%d\n" % (req.prefix, k + 1) + "\n".join(good[:-1] + ["m|roto|\\"]) + "\n```")
        out.append("\n".join(good))
        out.append("%s|n=%d\n" % (req.prefix, k) + "\n".join(good[: max(0, k - 1)]))
    out.append("")
    return out


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def system_key(text):
    # JSON no distingue 3.0 de 3 en JavaScript: el bloque de especificación TS escribe [1.3..3]
    return sha(re.sub(r"(\d)\.0(?=\]|\.\.)", r"\1", text))


def dump_request(req):
    return {"system_key": system_key(req.system), "user": req.user, "document_sha256": sha(req.document), "prefix": req.prefix,
            "max_tokens_hint": req.max_tokens_hint, "needed": req.needed, "lines": req.lines,
            "items": [{"line": it.line, "text": it.text, "is_header": it.is_header, "lines": it.lines,
                       "errors": [[e.code, e.line, e.field, e.message] for e in it.errors]} for it in req.items]}


def dump_merge(m):
    return {"text_sha256": sha(m.text), "ok": m.ok, "replaced": m.replaced, "dropped": m.dropped, "unresolved": m.unresolved,
            "notes": m.notes, "has_document": m.document is not None,
            "errors": [[e.code, e.line, e.field] for e in m.errors]}


def unique_cases():
    """Defecto D-3 (auditoría V5): una corrección no puede repetir un valor `unique` de otro registro.

    Documentos escritos a mano con la familia `cls` (unique: id); las respuestas son fijas para que
    las dos implementaciones reciban exactamente lo mismo. Las expectativas por caso (qué se
    sustituye y qué queda sin resolver) están además escritas a mano en tests/test_nucleo_reparacion.py.
    """
    c = REG.get("cls")
    tail = "|question*,feedback,bug,request,praise,other|0.9|"
    m = lambda i, t="texto": f"m{i}|{t}{tail}"  # noqa: E731
    rotas = {"m2": "m2|registro roto sin campos suficientes"}
    base = "\n".join(["cls|n=3|k=6", m(1), rotas["m2"], m(3, "tercero")])
    escenarios = [
        ("d3-duplica-un-valido-posterior", base, "cls|n=1\n" + m(3, "corregido")),
        ("d3-duplica-un-valido-anterior", base, "cls|n=1\n" + m(1, "corregido")),
        ("d3-id-nuevo-se-acepta", base, "cls|n=1\n" + m(9, "corregido")),
        ("d3-dos-correcciones-mismo-id-nuevo",
         "\n".join(["cls|n=4|k=6", m(1), rotas["m2"], "otra linea rota", m(4)]),
         "cls|n=2\n" + m(9, "uno") + "\n" + m(9, "dos")),
        ("d3-corrige-su-propio-id", base, "cls|n=1\n" + m(2, "corregido")),
    ]
    out = []
    for name, doc, answer in escenarios:
        req = repair_request(doc, c, "es")
        out.append({"prefix": "cls", "name": name, "input": doc, "lang": "es", "options": {"include_spec": True},
                    "extracted_sha256": sha(extract_document(doc, c)), "request": dump_request(req),
                    "merges": [{"answer": answer, "result": dump_merge(merge_repair(doc, answer, c, req)),
                                "result_no_request": None}]})
    return out


def main():
    rng = random.Random(20260916)
    cases = []
    for c in REG:
        fx = ROOT / "forks" / c.prefix / "fixtures"
        valid = read(fx / "valid.mini").strip("\n")
        vlines = valid.split("\n")
        docs = [("valid", valid)]
        for bad in sorted(fx.glob("bad_*.mini")):
            docs.append((bad.name, read(bad)))
        docs.append(("header_sin_n", "\n".join([c.prefix + "|zz=1"] + vlines[1:])))
        for s in range(4):
            ls, kinds = mutate(vlines, rng)
            docs.append(("mut%d:%s" % (s, ",".join(kinds)), "\n".join(ls)))
        for name, doc in docs:
            raw = wrap(doc, rng)
            lang = rng.choice(["es", "en"])
            opts = {"include_spec": rng.random() < 0.7}
            if rng.random() < 0.3:
                opts["context"] = "FUENTE: " + vlines[-1]
            if rng.random() < 0.2:
                opts["max_items"] = 1
            req = repair_request(raw, c, lang, **opts)
            merges = []
            for a in answers(req, vlines, rng):
                with_req, without = dump_merge(merge_repair(raw, a, c, req)), dump_merge(merge_repair(raw, a, c))
                # sin solicitud se recalculan los ítems; solo se guarda si el resultado difiere
                merges.append({"answer": a, "result": with_req, "result_no_request": None if without == with_req else without})
            cases.append({"prefix": c.prefix, "name": name, "input": raw, "lang": lang, "options": opts,
                          "extracted_sha256": sha(extract_document(raw, c)), "request": dump_request(req), "merges": merges})
    cases.extend(unique_cases())
    text = json.dumps({"generator": "minifmt.ai.repair", "cases": cases}, ensure_ascii=False, separators=(",", ":")) + "\n"
    OUT.write_bytes(text.encode("utf-8"))
    print(f"{len(cases)} casos -> {OUT}")


if __name__ == "__main__":
    main()
