"""Run the public API benchmark from hash-verified snapshots, without network.

    python benchmark/public/run.py
    python benchmark/public/run.py --baselines-only

Requires the optional benchmark dependencies and Node >=22.6 for official TOON.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
from baselines import (  # noqa: E402
    compact, csv_decode, csv_encode, equivalent, flatten, toon_batch,
    unflatten, xml_decode, xml_encode,
)
from minifmt.tokens import get_tokenizer  # noqa: E402


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_coverage(document, source):
    """Deterministic interleaved holdouts; failure is reported, not discarded."""
    from minifmt.domain import DomainError, infer_contract, encode, decode
    key = source["records_key"]
    rows = document[key] if key is not None else document
    experiments = []
    for fraction in (20, 80):
        train = [row for index, row in enumerate(rows) if (index % 5 == 0) == (fraction == 20)]
        heldout = [row for index, row in enumerate(rows) if (index % 5 == 0) != (fraction == 20)]
        training_doc = {**document, key: train} if key is not None else train
        testing_doc = {**document, key: heldout} if key is not None else heldout
        experiment = {"training_percent": fraction, "training_records": len(train), "heldout_records": len(heldout)}
        try:
            learned = infer_contract([training_doc], prefix=source["id"])
            restored = decode(encode(testing_doc, learned), learned)
            if not equivalent(testing_doc, restored):
                raise AssertionError("Held-out round-trip lost JSON values")
            experiment["status"] = "exact_roundtrip"
        except DomainError as error:
            experiment.update(status="safely_rejected_unobserved_schema", error_code=error.code, error_path=error.path)
        experiments.append(experiment)
    return experiments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--baselines-only", action="store_true")
    args = parser.parse_args()
    if not args.baselines_only:
        from minifmt.domain import infer_contract, encode, decode, make_prompt
    tokenizer = get_tokenizer("o200k_base")
    manifest = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    report = {
        "methodology_version": 1,
        "tokenizer": "o200k_base",
        "tokenizer_backend": tokenizer.backend,
        "python": platform.python_version(),
        "tiktoken": version("tiktoken") if tokenizer.backend == "tiktoken" else None,
        "toon": {"implementation": "official vendored reference", "package_version": "4.1.1", "spec_version": "4.1"},
        "contract_training": "Complete snapshot; serialization measurement, not held-out LLM generation accuracy.",
        "comparison": "Identical JSON values, full wrappers and metadata; reusable schema and generation prompt measured separately.",
        "implementation_sha256": {"run.py": source_hash(Path(__file__)), "baselines.py": source_hash(HERE / "baselines.py")},
        "datasets": [],
    }
    if not args.baselines_only:
        report["implementation_sha256"]["src/minifmt/domain.py"] = source_hash(ROOT / "src" / "minifmt" / "domain.py")
    flat_rows = []
    for source in manifest:
        raw = (HERE / source["file"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {source['id']}; refresh intentionally with fetch.py")
        document = json.loads(raw)
        flat_variants = {
            "arrays_as_json_cells": flatten(document, source["records_key"]),
            "arrays_as_indexed_columns": flatten(document, source["records_key"], expand_arrays=True),
        }
        official = toon_batch([document] + [variant[0] for variant in flat_variants.values()], HERE / "toon.mjs", args.node)
        toon_variants = dict(zip(flat_variants, official[1:]))
        csv_variants = {name: csv_encode(flat, schema) for name, (flat, schema) in flat_variants.items()}
        # Choose the smaller transmitted document for each baseline, not the
        # easier baseline for .mini. Publish both candidates and their maps.
        chosen_toon = min(toon_variants, key=lambda name: tokenizer.count(toon_variants[name]["text"]))
        chosen_csv = min(csv_variants, key=lambda name: tokenizer.count(csv_variants[name]))
        csv_text = csv_variants[chosen_csv]
        for name, (flat, schema) in flat_variants.items():
            assert equivalent(document, unflatten(toon_variants[name]["decoded"], schema)), f"{name} TOON lost JSON"
            assert equivalent(document, csv_decode(csv_variants[name], schema)), f"{name} CSV lost JSON"
        xml_text = xml_encode(document)
        yaml_text = yaml.safe_dump(document, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6).rstrip("\n")
        texts = {
            "json_compact": compact(document),
            "json_pretty": json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False),
            "toon": official[0]["text"],
            "toon_flat": toon_variants[chosen_toon]["text"],
            "csv": csv_text,
            "yaml": yaml_text,
            "xml": xml_text,
        }
        restored = {
            "json_compact": json.loads(texts["json_compact"]),
            "json_pretty": json.loads(texts["json_pretty"]),
            "toon": official[0]["decoded"],
            "toon_flat": unflatten(toon_variants[chosen_toon]["decoded"], flat_variants[chosen_toon][1]),
            "csv": csv_decode(csv_text, flat_variants[chosen_csv][1]),
            "yaml": yaml.safe_load(yaml_text),
            "xml": xml_decode(xml_text),
        }
        selected_schema = flat_variants[chosen_toon][1]
        toon_schema = {**selected_schema, "columns": [{k: v for k, v in column.items() if k != "csv_type"} for column in selected_schema["columns"]]}
        schemas = {"toon_flat": compact(toon_schema), "csv": compact(flat_variants[chosen_csv][1])}
        prompts = {}
        if not args.baselines_only:
            contract = infer_contract([document], prefix=source["id"])
            texts["mini"] = encode(document, contract)
            restored["mini"] = decode(texts["mini"], contract)
            schemas["mini"] = compact(contract)
            prompts["mini"] = make_prompt(contract, lang="en")
        entry = {
            "id": source["id"], "title": source["title"],
            "records": source["records"], "unique_ids": source["unique_ids"],
            "source_kind": source["kind"], "source_url": source["url"],
            "sha256": digest, "formats": {},
            "flattening": {
                "selection": "Lowest output token count among both reversible variants; shared schema cost is reported separately.",
                "selected_toon": chosen_toon, "selected_csv": chosen_csv,
                "candidates": {
                    name: {"toon_tokens": tokenizer.count(toon_variants[name]["text"]),
                           "csv_tokens": tokenizer.count(csv_variants[name]), "roundtrip": True}
                    for name in flat_variants
                },
            },
        }
        for format_name, text in texts.items():
            roundtrip = equivalent(document, restored[format_name])
            if not roundtrip:
                raise AssertionError(f"{source['id']}/{format_name}: JSON round-trip lost values or types")
            schema = schemas.get(format_name, "")
            prompt = prompts.get(format_name, "")
            metrics = {
                "tokens": tokenizer.count(text),
                "bytes": len(text.encode("utf-8")), "roundtrip": roundtrip,
                "shared_schema_tokens": tokenizer.count(schema) if schema else 0,
                "prompt_tokens": tokenizer.count(prompt) if prompt else 0,
                "payload_plus_schema_tokens": tokenizer.count(schema + "\n" + text) if schema else tokenizer.count(text),
                "payload_plus_prompt_tokens": tokenizer.count(prompt + "\n" + text) if prompt else None,
            }
            entry["formats"][format_name] = metrics
            flat_rows.append({"dataset": source["id"], "records": source["records"], "format": format_name, **metrics})
        if not args.baselines_only:
            mini = entry["formats"]["mini"]["tokens"]
            entry["savings"] = {
                f"vs_{format_name}_pct": round(100 * (1 - mini / metrics["tokens"]), 2)
                for format_name, metrics in entry["formats"].items() if format_name != "mini"
            }
            entry["mini_fits_smaller_than_flat_toon_including_schema"] = (
                entry["formats"]["mini"]["payload_plus_schema_tokens"]
                < entry["formats"]["toon_flat"]["payload_plus_schema_tokens"]
            )
            entry["mini_without_document_factoring_tokens"] = tokenizer.count(
                encode(document, contract, shared=False, dictionaries=False)
            )
            entry["sample_coverage"] = sample_coverage(document, source)
        report["datasets"].append(entry)
        print(source["id"], {name: item["tokens"] for name, item in entry["formats"].items()}, flush=True)
    totals = {
        format_name: sum(dataset["formats"][format_name]["tokens"] for dataset in report["datasets"])
        for format_name in report["datasets"][0]["formats"]
    }
    report["summary"] = {
        "records": sum(dataset["records"] for dataset in report["datasets"]),
        "datasets": len(report["datasets"]), "tokens": totals,
        "all_roundtrips_passed": all(item["roundtrip"] for dataset in report["datasets"] for item in dataset["formats"].values()),
    }
    if not args.baselines_only:
        report["summary"]["weighted_savings_pct"] = {
            format_name: round(100 * (1 - totals["mini"] / count), 2)
            for format_name, count in totals.items() if format_name != "mini"
        }
        report["summary"]["wins_vs_flat_toon"] = sum(dataset["savings"]["vs_toon_flat_pct"] > 0 for dataset in report["datasets"])
    basename = "baseline-results" if args.baselines_only else "results"
    (HERE / f"{basename}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (HERE / f"{basename}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)


if __name__ == "__main__":
    main()
