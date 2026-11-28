"""Paired cloud evaluation of compact .mini replies and native Structured Outputs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

from minifmt.domain import build_bundle
from minifmt.workflow import Workflow, WorkflowError


MODEL = "gpt-6-luna"
PRICES = {"input": 0.10, "cached_input": 0.01, "cache_write_input": 0.125, "output": 0.50}
ATTEMPTS = 2
USAGE = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
COMMON = "Resuelve la tarea de datos con exactitud. Devuelve solo la respuesta solicitada sin herramientas ni explicaciones."
RETRY = "Revisa el número y el orden de las filas, los códigos de cada ticket y el título literal."
CATEGORIES = {"C": "cuenta", "P": "pago", "E": "envio"}
PRIORITIES = {"H": "alta", "M": "media", "B": "baja"}
TITLES = (
    "No puedo entrar después de cambiar la contraseña",
    "Cobro duplicado en mi última factura",
    'El sistema muestra "sesión caducada" al guardar',
    "Confirmar el envío del paquete para mañana",
    "El soporte solicitó revisar la opción de reembolso",
    "La pantalla queda en blanco después de confirmar",
    "El correo de recuperación llega con varias horas de retraso",
    "La dirección de entrega incluye piso 4, puerta B",
    "Recibí dos avisos de pago por el mismo pedido",
    "Al pulsar Actualizar aparece una alerta sin descripción",
    "El pedido quedó pendiente tras la confirmación",
    "Necesito reactivar la cuenta con otro correo",
    "El recibo indica una moneda distinta de la original",
    "La aplicación se cierra al adjuntar un comprobante",
    "Solicito una copia de la factura con el domicilio actualizado",
    "El enlace de seguimiento abre una página de error",
    "La fecha prometida cambió por segunda vez este mes",
    "Aún figura un importe pendiente en la sección de pagos",
)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Cloud:
    def __init__(self, folder):
        self.folder = folder.resolve()
        if self.folder.exists() and any(self.folder.iterdir()):
            raise FileExistsError(f"Choose a new results directory: {self.folder}")
        self.folder.mkdir(parents=True, exist_ok=True)
        instructions = self.folder / "instructions.txt"
        instructions.write_text(COMMON, encoding="utf-8")
        self.command = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                        "--sandbox", "read-only", "--model", MODEL, "--json",
                        "-c", "model_reasoning_effort='none'", "-c", "web_search='disabled'",
                        "-c", "features.shell_tool=false", "-c", "project_doc_max_bytes=0",
                        "-c", "model_instructions_file=" + json.dumps(instructions.as_posix())]

    def complete(self, name, prompt, schema=None):
        options = []
        if schema is not None:
            schema_path = self.folder / f"{name}.schema.json"
            schema_path.write_text(compact(schema), encoding="utf-8")
            options = ["--output-schema", str(schema_path)]
        result = subprocess.run(self.command + options + ["-"], cwd=self.folder, input=prompt,
                                encoding="utf-8", capture_output=True, timeout=150, check=False)
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        turns = [e["usage"] for e in events if e["type"] == "turn.completed"]
        items = [e["item"] for e in events if e["type"] == "item.completed"]
        messages = [item["text"] for item in items if item["type"] == "agent_message"]
        if result.returncode or len(turns) != 1 or not messages:
            failures = [e for e in events if e["type"] in ("turn.failed", "error")]
            raise RuntimeError(f"Cloud call {name}: exit={result.returncode}, {str(failures)[:350]}")
        if any(i["type"] not in ("reasoning", "agent_message") for i in items):
            raise RuntimeError(f"Unexpected tool activity in cloud call {name}")
        return {"reply": messages[-1], "usage": {k: turns[0].get(k, 0) for k in USAGE},
                "prompt": prompt, "native_schema": schema}


def object_schema(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def ticket_schema(projected, single=False):
    fields = {"categoria": {"type": "string", "enum": list(CATEGORIES.values())},
              "prioridad": {"type": "string", "enum": list(PRIORITIES.values())}, "titulo": {"type": "string"}}
    if not projected:
        fields = {"id": {"type": "integer"}, **fields}
    record = object_schema(fields)
    return record if single else object_schema({"tickets": {"type": "array", "items": record}})


def tickets(case, count):
    categories = list(CATEGORIES)
    priorities = list(PRIORITIES)
    source, expected = [], []
    for index in range(count):
        category = categories[(case + index) % len(categories)]
        priority = priorities[(2 * case + index // 2) % len(priorities)]
        title = TITLES[(case * 7 + index * 5) % len(TITLES)]
        identifier = 1000 + 41 * case + index * 3
        source.append(f"{identifier}|{category}|{priority}|{title}")
        expected.append({"id": identifier, "categoria": CATEGORIES[category],
                         "prioridad": PRIORITIES[priority], "titulo": title})
    return source, expected


def generation(cloud, bundle, case, count, format_name, *, compact_single=False, literal_codes=False):
    source, expected = tickets(case, count)
    literal = " Usa los códigos como única fuente de categoría y prioridad, incluso si el título sugiere otras." if literal_codes else ""
    task = (f"Convierte {count} tickets en el orden dado. Columnas de entrada id|categoría|prioridad|título. "
            f"C=cuenta, P=pago, E=envio. H=alta, M=media, B=baja. Copia cada título literalmente.{literal}\n"
            + "\n".join(source))
    known = [{"id": item["id"]} for item in expected]
    attempts = []

    def ask(prompt, schema=None):
        label = f"gen-{case:02d}-{format_name}-{len(attempts) + 1}"
        answer = cloud.complete(label, prompt, schema)
        attempts.append(answer)
        return answer["reply"]

    parsed = None
    if format_name in ("mini", "mini_columnar"):
        flow = Workflow(bundle)
        options = {"expected_records": count, "known_rows": known}
        if format_name == "mini_columnar":
            run = flow.run_columnar
            options["allowed_values"] = {"categoria": list(CATEGORIES.values()), "prioridad": list(PRIORITIES.values())}
        else:
            run = flow.run
            options["last_text_field"] = "titulo"
        try:
            parsed = run(ask, task, max_repairs=ATTEMPTS - 1, **options)
            if parsed != expected and len(attempts) < ATTEMPTS:
                parsed = run(ask, RETRY + "\n" + task, max_repairs=0, **options)
        except WorkflowError:
            pass
    else:
        projected = format_name == "json_schema_projected"
        single = compact_single and count == 1
        native_schema = ticket_schema(projected, single)
        specificity = " La aplicación aporta los id en el mismo orden." if projected else ""
        prompt = f"{task}\nDevuelve JSON compacto con los campos indicados por el esquema.{specificity}"
        for retry in range(ATTEMPTS):
            reply = ask(prompt if not retry else RETRY + "\n" + prompt, native_schema)
            try:
                value = json.loads(reply)
                parsed = [value] if single else value["tickets"]
                if projected:
                    parsed = [{**known_row, **row} for known_row, row in zip(known, parsed)] if len(parsed) == count else parsed
            except (ValueError, TypeError, KeyError):
                continue
            if parsed == expected:
                break

    return {"suite": "generation", "case": case, "rows": count, "format": format_name,
            "exact": parsed == expected, "attempts": attempts}


def summarize(trials):
    result = {}
    for trial in trials:
        group = result.setdefault(trial["format"], {"exact": 0, "trials": 0, "retries": 0, **dict.fromkeys(USAGE, 0)})
        group["trials"] += 1
        group["exact"] += int(trial["exact"])
        group["retries"] += len(trial["attempts"]) - 1
        for attempt in trial["attempts"]:
            for key in USAGE:
                group[key] += attempt["usage"][key]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=18, choices=range(3, 31, 3))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--arms", nargs="+", choices=("mini", "json_schema", "json_schema_projected", "mini_columnar"),
                        default=("mini", "json_schema", "json_schema_projected"))
    parser.add_argument("--compact-single", action="store_true", help="use a single native object for one-row controls")
    parser.add_argument("--literal-codes", action="store_true", help="require code mapping even if the title suggests a different category")
    args = parser.parse_args()
    cloud = Cloud(args.out)
    bundle = cloud.folder / "kit"
    build_bundle([tickets(0, 3)[1]], prefix="ticket", out=bundle, lang="es")
    order = tuple(dict.fromkeys(args.arms))
    counts = (1, 8, 26, 1, 12, 32)

    def group(index):
        offset = index % len(order)
        return [generation(cloud, bundle, index, counts[index % len(counts)], arm,
                           compact_single=args.compact_single, literal_codes=args.literal_codes)
                for arm in order[offset:] + order[:offset]]

    trials = []
    with (cloud.folder / "trials.jsonl").open("w", encoding="utf-8") as ledger:
        with ThreadPoolExecutor(args.workers) as pool:
            for pair in pool.map(group, range(args.start, args.start + args.cases)):
                for trial in pair:
                    ledger.write(compact(trial) + "\n")
                ledger.flush()
                trials.extend(pair)
                print(f"Case {pair[0]['case']:02d}, {pair[0]['rows']} rows: " + ", ".join(
                    f"{trial['format']}={trial['exact']} ({len(trial['attempts'])} calls)" for trial in pair), flush=True)
    summary = {"model": MODEL, "price_usd_per_million": PRICES, "max_attempts": ATTEMPTS,
               "formats": summarize(trials), "single_object": args.compact_single, "literal_codes": args.literal_codes,
               "rows_per_case": [counts[index % len(counts)] for index in range(args.start, args.start + args.cases)]}
    (cloud.folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
