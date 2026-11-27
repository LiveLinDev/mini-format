"""Reproducible 2026 multi-competitor benchmark across public & real-workflow datasets.

Measures .mini (domain/2, domain/1, compact-rows) against direct 2026 LLM
structured-output competitors (TOON, ISON, LEAN, TONL, HEDL, RAIF, Positional
JSON, Short-Key JSON) and standard data formats (CSV, YAML, XML, JSON) across
3 real BPE tokenizers (o200k_base, cl100k_base, p50k_base). Every competitor is
round-trip verified via ``equivalent()`` before counting tokens.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from minifmt import domain
from minifmt.tokens import get_tokenizer
from benchmark.public import baselines
from benchmark import competitors

DIR = Path(__file__).resolve().parent
SNAP_DIR = DIR / "snapshots"
SOURCES_PATH = DIR / "sources.json"
OUT_JSON = DIR / "competitors_results.json"
OUT_MD = DIR / "competitors_table.md"


def _yaml_dump(doc) -> str:
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6)


def _node_bridge() -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    bridge = DIR / "toon.mjs"
    return node if bridge.is_file() else None


def measure_workloads() -> dict:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    meta_map = {s["id"]: s for s in sources}
    node_bin = _node_bridge()
    tokenizers = {
        "o200k_base": get_tokenizer("o200k_base"),
        "cl100k_base": get_tokenizer("cl100k_base"),
        "p50k_base": get_tokenizer("p50k_base"),
    }
    primary_tk = tokenizers["o200k_base"]

    workloads = []
    for name in ("products", "users", "comments", "earthquakes"):
        info = meta_map[name]
        data_file = DIR / info["file"]
        if not data_file.is_file():
            data_file = SNAP_DIR / f"{name}.json"
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        rk = info["records_key"]
        rec_count = len(raw[rk]) if rk is not None else len(raw)
        workloads.append({
            "name": name,
            "label": info["title"],
            "source_url": info["url"],
            "license": info.get("license", "public"),
            "records_key": rk,
            "records_count": rec_count,
            "doc": raw,
            "tail_field": None,
        })

    support_doc = json.loads((ROOT / "examples" / "flujo-soporte" / "expected.json").read_text(encoding="utf-8"))
    workloads.append({
        "name": "flujo-soporte",
        "label": "Support Ticket Triage (20 records)",
        "source_url": "examples/flujo-soporte/expected.json",
        "license": "MIT",
        "records_key": None,
        "records_count": len(support_doc),
        "doc": support_doc,
        "tail_field": "titulo",
    })

    # Pre-encode TOON batch if Node bridge is installed
    toon_outputs: dict[str, dict[str, str | None]] = {}
    if node_bin:
        toon_script = DIR / "toon.mjs"
        raw_docs = [w["doc"] for w in workloads]
        raw_res = baselines.toon_batch(raw_docs, toon_script, node_bin)
        flat_items = []
        for idx, w in enumerate(workloads):
            ok_r = baselines.equivalent(raw_res[idx]["decoded"], w["doc"])
            toon_outputs[w["name"]] = {"toon": raw_res[idx]["text"] if ok_r else None, "toon_flat": None}
            wrapped = w["doc"] if w["records_key"] else {"records": w["doc"]}
            rk_eff = w["records_key"] or "records"
            for exp in (False, True):
                fd, fs = baselines.flatten(wrapped, rk_eff, expand_arrays=exp)
                flat_items.append((w["name"], w["doc"], w["records_key"] is None, fd, fs))
        flat_res = baselines.toon_batch([x[3] for x in flat_items], toon_script, node_bin)
        for idx, (nm, orig, is_root_list, _, fs) in enumerate(flat_items):
            unflat = baselines.unflatten(flat_res[idx]["decoded"], fs)
            recovered = unflat["records"] if is_root_list else unflat
            if baselines.equivalent(recovered, orig):
                cand = flat_res[idx]["text"]
                cur = toon_outputs[nm]["toon_flat"]
                if cur is None or primary_tk.count(cand) < primary_tk.count(cur):
                    toon_outputs[nm]["toon_flat"] = cand

    report_datasets = []
    for w in workloads:
        name = w["name"]
        doc = w["doc"]
        contract = domain.infer_contract([doc], name if name != "flujo-soporte" else "ticket")
        formats_text: dict[str, str] = {}

        # .mini family
        v2_txt = domain.encode_v2(doc, contract, token_counter=primary_tk.count)
        assert baselines.equivalent(domain.decode(v2_txt, contract), doc), f"mini_v2 roundtrip failed for {name}"
        formats_text["mini_v2"] = v2_txt

        v1_txt = domain.encode(doc, contract)
        assert baselines.equivalent(domain.decode(v1_txt, contract), doc), f"mini_v1 roundtrip failed for {name}"
        formats_text["mini_v1"] = v1_txt

        if w["tail_field"]:
            rows_txt = domain.encode_rows(
                doc, contract, last_text_field=w["tail_field"], allow_nullable=True, compact_bools=True
            )
            dec_rows = domain.decode_rows(
                rows_txt, contract, last_text_field=w["tail_field"],
                expected_records=w["records_count"], allow_nullable=True, compact_bools=True
            )
            assert baselines.equivalent(dec_rows, doc), f"mini_rows roundtrip failed for {name}"
            formats_text["mini_rows"] = rows_txt

        # Direct 2026 LLM competitors (100% lossless round-trip verified)
        for cname, enc_fn, dec_fn in (
            ("ison", competitors.ison_encode, competitors.ison_decode),
            ("lean", competitors.lean_encode, competitors.lean_decode),
            ("tonl", competitors.tonl_encode, competitors.tonl_decode),
            ("hedl", competitors.hedl_encode, competitors.hedl_decode),
            ("raif", competitors.raif_encode, competitors.raif_decode),
            ("json_positional", competitors.json_positional_encode, competitors.json_positional_decode),
            ("json_short", competitors.json_short_encode, competitors.json_short_decode),
        ):
            enc_txt = enc_fn(doc, name)
            dec_obj = dec_fn(enc_txt, name, doc)
            assert baselines.equivalent(dec_obj, doc), f"{cname} roundtrip failed for {name}"
            formats_text[cname] = enc_txt

        # TOON
        if name in toon_outputs:
            for tk_key in ("toon_flat", "toon"):
                if toon_outputs[name].get(tk_key):
                    formats_text[tk_key] = toon_outputs[name][tk_key]

        # Standard formats (choose smallest lossless variant of CSV, matching run.py)
        wrapped = doc if w["records_key"] is not None else {"records": doc}
        rk_eff = w["records_key"]
        csv_best = None
        for exp in (False, True):
            fd, fs = baselines.flatten(doc if rk_eff else wrapped, rk_eff or "records", expand_arrays=exp)
            cand_csv = baselines.csv_encode(fd, fs)
            dec_csv = baselines.csv_decode(cand_csv, fs)
            rec_csv = dec_csv if rk_eff else dec_csv["records"]
            if baselines.equivalent(rec_csv, doc):
                if csv_best is None or primary_tk.count(cand_csv) < primary_tk.count(csv_best):
                    csv_best = cand_csv
        assert csv_best is not None
        formats_text["csv"] = csv_best
        xml_txt = baselines.xml_encode(doc if rk_eff else wrapped)
        dec_xml = baselines.xml_decode(xml_txt)
        assert baselines.equivalent(dec_xml if rk_eff else dec_xml["records"], doc)
        formats_text["xml"] = xml_txt

        yaml_txt = _yaml_dump(doc)
        assert baselines.equivalent(yaml.safe_load(yaml_txt), doc)
        formats_text["yaml"] = yaml_txt
        formats_text["json_compact"] = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        formats_text["json_pretty"] = json.dumps(doc, ensure_ascii=False, indent=2)

        # Count tokens across all 3 BPE encodings
        table: dict[str, dict] = {}
        base_o200 = primary_tk.count(formats_text["json_compact"])
        for fmt, txt in formats_text.items():
            row_stats = {"bytes": len(txt.encode("utf-8")), "roundtrip": True}
            for tname, tk in tokenizers.items():
                tok_n = tk.count(txt)
                row_stats[tname] = tok_n
            row_stats["saving_vs_json_compact"] = round((base_o200 - row_stats["o200k_base"]) / base_o200 * 100, 2)
            table[fmt] = row_stats

        report_datasets.append({
            "name": name,
            "label": w["label"],
            "records": w["records_count"],
            "v2_header": v2_txt.splitlines()[0],
            "formats": table,
        })

    # Prompt overhead comparison for support workflow
    sup_c = domain.infer_contract([support_doc], "ticket")
    prompt_stats = {
        "make_prompt_full": primary_tk.count(domain.make_prompt(sup_c, "en")),
        "make_prompt_lean": primary_tk.count(domain.make_lean_prompt(sup_c, "en")),
        "make_rows_prompt": primary_tk.count(domain.make_rows_prompt(sup_c, last_text_field="titulo", expected_records=20, lang="en")),
        "positional_json_prompt": primary_tk.count(domain.positional_json_request("Classify", sup_c, expected_records=20, lang="en")["prompt"]),
    }

    summary = {
        "tokenizers": list(tokenizers.keys()),
        "datasets": report_datasets,
        "prompt_overhead_o200k": prompt_stats,
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# 2026 Multi-Competitor Benchmark (o200k_base / cl100k_base / p50k_base)\n"]
    for ds in report_datasets:
        lines.append(f"\n## {ds['label']} ({ds['records']} records)\n")
        lines.append(f"Header (`domain/2`): `{ds['v2_header'][:120]}`\n")
        lines.append("| Format | o200k_base | cl100k_base | p50k_base | Bytes | Saving vs JSON compact |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        ordered = sorted(ds["formats"].items(), key=lambda kv: kv[1]["o200k_base"])
        for fmt, st in ordered:
            lines.append(f"| `{fmt}` | {st['o200k_base']:,} | {st['cl100k_base']:,} | {st['p50k_base']:,} | {st['bytes']:,} | {st['saving_vs_json_compact']:+.1f}% |")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    result = measure_workloads()
    for ds in result["datasets"]:
        best = min(ds["formats"].items(), key=lambda kv: kv[1]["o200k_base"])
        print(f"{ds['name']:15s}: WINNER={best[0]} ({best[1]['o200k_base']:,} tok, {best[1]['saving_vs_json_compact']:+.1f}% vs JSON compact) | v1={ds['formats']['mini_v1']['o200k_base']:,}")
    print("Prompts (o200k_base):", result["prompt_overhead_o200k"])
