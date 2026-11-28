"""Measure what a cloud model can recover from equivalent .mini, TOON, and JSON inputs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

from minifmt import transport
from minifmt.tokens import get_tokenizer
from run_native_schema import ATTEMPTS, MODEL, PRICES, Cloud, compact, object_schema, summarize, tickets


FORMATS = ("mini", "toon", "json_compact")
SIZES = (8, 20, 32)
READ_SCHEMA = object_schema({
    "equipo": {"type": "string"}, "total": {"type": "integer"},
    "prioridad": {"type": "string"}, "titulo": {"type": "string"},
    "pagos_urgentes": {"type": "array", "items": {"type": "integer"}},
})
MINI_HINT = ("En .mini, la cabecera #[metadatos,secciones] precede a la tabla. "
             "^id=inicio:paso genera los id en orden. Los encabezados nombran las columnas; "
             "el título ocupa el resto de la línea.")
TABLE_HINT = ("En .mini, tickets[n] indica n filas. Los campos siguen la cabecera "
              "y el título ocupa el resto de su línea.")


def encode_toon(documents, module):
    path = module.resolve()
    package = json.loads((path.parents[1] / "package.json").read_text(encoding="utf-8"))
    encoder = f'''import fs from 'node:fs';
import {{encode,decode}} from {json.dumps(path.as_uri())};
const values=JSON.parse(fs.readFileSync(0,'utf8'));
const texts=values.map(value=>encode(value));
process.stdout.write(JSON.stringify(texts.map(text=>[text,decode(text,{{strict:true}})])));
'''
    result = subprocess.run(["node", "--input-type=module", "-e", encoder], input=compact(documents),
                            encoding="utf-8", capture_output=True, check=True)
    records = json.loads(result.stdout)
    if [decoded for _, decoded in records] != documents:
        raise ValueError("TOON did not reconstruct the documents")
    return [text for text, _ in records], package["version"]


def reading(cloud, case, document, name, encoded, count_tokens):
    rows = document["tickets"]
    target = rows[(case * 3 + 1) % len(rows)]
    expected = {"equipo": document["equipo"], "total": len(rows),
                "prioridad": target["prioridad"], "titulo": target["titulo"],
                "pagos_urgentes": [row["id"] for row in rows
                                   if row["categoria"] == "pago" and row["prioridad"] == "alta"]}
    question = (f"A partir del documento, da equipo, total de tickets, prioridad y título del id {target['id']}, "
                "y los id de pago con prioridad alta en el orden de la tabla. Copia el título literal.")
    hint = ""
    if name == "mini":
        hint = (TABLE_HINT if encoded.startswith("+") else MINI_HINT) + "\n"
    prompt = f"{question}\n{hint}Documento {name}:\n{encoded}"
    attempts, exact = [], False
    for retry in range(ATTEMPTS):
        correction = "Revisa el conteo, el id pedido y todos los pagos urgentes.\n" if retry else ""
        answer = cloud.complete(f"read-{case:02d}-{name}-{retry+1}", correction + prompt, READ_SCHEMA)
        attempts.append(answer)
        try:
            exact = json.loads(answer["reply"]) == expected
        except (ValueError, TypeError):
            pass
        if exact:
            break
    return {"suite": "reading", "case": case, "rows": len(rows), "format": name, "exact": exact,
            "payload_tokens": count_tokens(encoded), "prompt_tokens": count_tokens(prompt), "attempts": attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--toon-module", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=9, choices=range(3, 31, 3))
    parser.add_argument("--start", type=int, default=21)
    parser.add_argument("--workers", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--model-table", action="store_true")
    args = parser.parse_args()
    tokenizer = get_tokenizer("o200k_base")
    if tokenizer.backend != "tiktoken":
        parser.error("the reading benchmark requires tiktoken")
    indices = range(args.start, args.start + args.cases)
    docs = [{"equipo": f"soporte-{index % 4 + 1}", "tickets": tickets(index, SIZES[index % 3])[1],
             "turno": ("mañana", "tarde", "noche")[index % 3]} for index in indices]
    toon_texts, version = encode_toon(docs, args.toon_module)
    minis = [transport.dumps(doc, count=tokenizer.count, for_model=args.model_table) for doc in docs]
    for text, document in zip(minis, docs):
        matches_hint = text.startswith("+") if args.model_table else text.startswith("#[") and "\n^id=" in text
        if transport.loads(text) != document or not matches_hint:
            raise ValueError("The .mini reading hints must match the exact published wire form")
    inputs = {"mini": minis, "toon": toon_texts, "json_compact": [compact(doc) for doc in docs]}
    cloud = Cloud(args.out)

    def pair(offset):
        rotation = offset % len(FORMATS)
        order = FORMATS[rotation:] + FORMATS[:rotation]
        return [reading(cloud, indices[offset], docs[offset], name, inputs[name][offset], tokenizer.count)
                for name in order]

    trials = []
    with (cloud.folder / "trials.jsonl").open("w", encoding="utf-8") as ledger:
        with ThreadPoolExecutor(args.workers) as pool:
            for group in pool.map(pair, range(len(indices))):
                for trial in group:
                    ledger.write(compact(trial) + "\n")
                ledger.flush()
                trials.extend(group)
                print(f"Case {group[0]['case']}, {group[0]['rows']} rows: " + ", ".join(
                    f"{trial['format']}={trial['exact']} ({len(trial['attempts'])} calls)" for trial in group), flush=True)

    formats = summarize(trials)
    for name, values in formats.items():
        for metric in ("payload_tokens", "prompt_tokens"):
            values[metric] = sum(t[metric] for t in trials if t["format"] == name)
    summary = {"model": MODEL, "price_usd_per_million": PRICES, "max_attempts": ATTEMPTS,
               "toon_version": version, "model_table": args.model_table, "formats": formats,
               "rows_per_case": [len(doc["tickets"]) for doc in docs]}
    (cloud.folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
