"""Compare multi-table reading on cloud requests that reuse the same document."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from importlib.metadata import version as package_version
import json
from pathlib import Path
import subprocess

from minifmt import transport
from minifmt.tokens import get_tokenizer
from run_cloud_reading import encode_toon
from run_native_schema import ATTEMPTS, COMMON, Cloud, MODEL, PRICES, compact, object_schema, summarize, tickets

ARMS = ("mini_tables", "mini_previous", "hedl", "gcf", "toon", "json_compact")
BPP_ARMS = ("bpp_refs", "bpp_plain")
SCHEMA = object_schema({
    "equipo": {"type": "string"}, "total": {"type": "integer"}, "prioridad": {"type": "string"},
    "titulo": {"type": "string"}, "responsable": {"type": "string"},
    "agente": {"type": "string"}, "sede": {"type": "string"},
})
NAMES = ("Elena Cruz", "Iván Peña", "Carlos Ruiz", "María Ramos", "Luz Reyes", "Alicia Gómez", "Bruno Silva",
         "Fabio Vera", "Leila Ríos", "Mauro López", "Isabel Ibarra", "Julia Núñez", "Sara Prado", "Marco Díaz")
HINTS = {
    "hedl": "En HEDL, %S nombra los campos de las filas que empiezan por |.",
    "gcf": "En GCF, la cabecera fija el orden de los campos de cada tabla.",
    "toon": "",
    "json_compact": "",
    "bpp_refs": "En BPP, &n define un texto compartido y *n recupera ese texto. nombre[n] indica el número de filas.",
    "bpp_plain": "En BPP, nombre[n] indica el número de filas. Las columnas siguen los nombres entre llaves.",
}
MINI_HINT = "En .mini, nombre[n] indica n filas. Las columnas siguen la cabecera y el último campo ocupa el resto de su línea."
REFS_HINT = "En .mini, [n] indica n filas. Si una columna lleva :r, busca su clave en @refs y copia el texto."


def hedl(executable, text, mode):
    result = subprocess.run([str(executable.resolve()), mode], input=text, capture_output=True, encoding="utf-8",
                            check=True, timeout=30)
    return result.stdout.strip()


def document(case, count):
    _, batch = tickets(case, count)
    agents = [{"id": f"A{case*3+i*6+4}", "sede": ("centro", "norte", "sur")[i%3], "nombre": name}
              for i, name in enumerate(NAMES[:(7 if count < 40 else 14)])]
    batch = [{"id": f"T{r['id']}", "categoria": r["categoria"], "prioridad": r["prioridad"],
              "responsable": agents[(i*3+case)%len(agents)]["id"], "titulo": r["titulo"]}
             for i, r in enumerate(batch)]
    return {"equipo": f"soporte-{case}", "tickets": batch, "agentes": agents, "turno": "mañana"}


def old_codec(path):
    spec = importlib.util.spec_from_file_location("minifmt._transport_for_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context(name, value):
    label = name
    if name.startswith("mini_"):
        label = "mini"
        hint = REFS_HINT if value.startswith("+++") else MINI_HINT
    else:
        hint = HINTS[name]
        if name in BPP_ARMS:
            label = "BPP"
    return f"Documento {label}:\n{hint + chr(10) if hint else ''}{value}\n\n"


def query(cloud, number, case, doc, arm, wire, token_count, *, lookup_steps=False):
    rows = doc["tickets"]
    target = rows[(number * 7 + case) % len(rows)]
    agent = next(a for a in doc["agentes"] if a["id"] == target["responsable"])
    expected = {"equipo": doc["equipo"], "total": len(rows), "prioridad": target["prioridad"],
                "titulo": target["titulo"], "responsable": target["responsable"],
                "agente": agent["nombre"], "sede": agent["sede"]}
    question = (f"Da equipo y total de tickets. Localiza el ticket con ID exacto {target['id']} y copia su prioridad, título "
                "literal e ID del responsable. Usa ese ID como clave en agentes para copiar su nombre y sede.")
    if lookup_steps:
        question = (f"Busca la fila de tickets con id exactamente {target['id']}. De esa fila copia prioridad, título y responsable. "
                    "Busca ese responsable en la columna id de agentes y copia su nombre y sede. Da equipo y total de tickets.")
    attempts = []
    exact = False
    for retry in range(ATTEMPTS):
        suffix = "\nConfirma el ID del ticket y enlaza su responsable por ID en la tabla agentes." if retry else ""
        answer = cloud.complete(f"read-{case}-{number}-{arm}-{retry+1}", question + suffix, SCHEMA)
        attempts.append(answer)
        try:
            exact = json.loads(answer["reply"]) == expected
        except ValueError:
            pass
        if exact:
            break
    return {"case": case, "question": number, "rows": len(rows), "format": arm, "exact": exact,
            "payload_tokens": token_count(wire), "prompt_tokens": token_count(context(arm, wire) + question),
            "attempts": attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous-transport", type=Path)
    parser.add_argument("--hedl-parser", type=Path)
    parser.add_argument("--toon-module", type=Path)
    parser.add_argument("--start", type=int, default=324)
    parser.add_argument("--sizes", type=int, nargs="+", default=[24, 38, 56])
    parser.add_argument("--questions", type=int, default=4)
    parser.add_argument("--arms", nargs="+", choices=(*ARMS, "mini_text_refs", *BPP_ARMS), default=ARMS)
    parser.add_argument("--lookup-steps", action="store_true", help="state the two ID lookups explicitly")
    args = parser.parse_args()
    arms = tuple(dict.fromkeys(args.arms))
    for arm, value, option in (("mini_previous", args.previous_transport, "--previous-transport"),
                               ("hedl", args.hedl_parser, "--hedl-parser"), ("toon", args.toon_module, "--toon-module")):
        if arm in arms and value is None:
            parser.error(f"{option} is required for {arm}")
    out = args.out
    tk = get_tokenizer("o200k_base")
    assert tk.backend == "tiktoken"
    base = old_codec(args.previous_transport) if "mini_previous" in arms else None
    docs = [document(args.start + i, count) for i, count in enumerate(args.sizes)]
    toon, version = encode_toon(docs, args.toon_module) if "toon" in arms else (None, None)
    format_versions = {}
    if "hedl" in arms:
        format_versions["hedl"] = "2.0.0"
    if "gcf" in arms:
        from gcf import decode_generic, encode_generic
        format_versions["gcf"] = "3.6.0"
    if set(arms).intersection(BPP_ARMS):
        import bpp
        format_versions["bpp"] = package_version("bpp-format")
    out.mkdir(parents=True)

    def batch(pair):
        index, doc = pair
        case = args.start + index
        wires = {"json_compact": compact(doc)}
        for name in ("mini_tables", "mini_text_refs"):
            if name in arms:
                wires[name] = transport.dumps(doc, for_model=True, text_refs=name == "mini_text_refs", count=tk.count)
                assert transport.loads(wires[name]) == doc
        if base is not None:
            wires["mini_previous"] = base.dumps(doc, for_model=True, count=tk.count)
            assert base.loads(wires["mini_previous"]) == doc
        if "hedl" in arms:
            wires["hedl"] = hedl(args.hedl_parser, wires["json_compact"], "encode")
            assert json.loads(hedl(args.hedl_parser, wires["hedl"], "decode")) == doc
        if "gcf" in arms:
            wires["gcf"] = encode_generic(doc)
            assert decode_generic(wires["gcf"]) == doc
        if toon is not None:
            wires["toon"] = toon[index]
        for name in BPP_ARMS:
            if name in arms:
                wires[name] = bpp.dumps(doc, refs=name == "bpp_refs")
                assert bpp.loads(wires[name]) == doc
        sessions = {name: Cloud(out / str(case) / name) for name in arms}
        for name, session in sessions.items():
            # A synthetic reference dataset stays in the same provider prefix for all questions.
            (session.folder / "instructions.txt").write_text(f"{COMMON}\n\n{context(name, wires[name])}", encoding="utf-8")
        trials = []
        for question in range(args.questions):
            rotation = (index + question) % len(arms)
            for arm in arms[rotation:] + arms[:rotation]:
                trials.append(query(sessions[arm], question, case, doc, arm, wires[arm], tk.count,
                                    lookup_steps=args.lookup_steps))
        return trials

    trials = []
    with (out / "trials.jsonl").open("w", encoding="utf-8") as ledger, ThreadPoolExecutor(3) as pool:
        for group in pool.map(batch, enumerate(docs)):
            for trial in group:
                ledger.write(compact(trial) + "\n")
                print(trial["case"], trial["question"], trial["format"], trial["exact"], len(trial["attempts"]), flush=True)
            ledger.flush()
            trials.extend(group)
    formats = summarize(trials)
    for name, result in formats.items():
        for metric in ("payload_tokens", "prompt_tokens"):
            result[metric] = sum(t[metric] for t in trials if t["format"] == name)
    summary = {"model": MODEL, "prices": PRICES, "max_attempts": ATTEMPTS, "toon_version": version,
               "shared_document_prefix": True, "questions_per_document": args.questions, "document_sizes": args.sizes,
               "lookup_steps": args.lookup_steps, "format_versions": format_versions, "formats": formats}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
