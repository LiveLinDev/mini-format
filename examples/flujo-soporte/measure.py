"""Recount identical output data with the repository's tokenizer and TOON encoder.

Run from a source checkout with benchmark dependencies available. No AI calls.
"""
from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))


def measure():
    from minifmt.bench import toon_encode
    from minifmt.domain import (
        infer_contract, encode, encode_v2, encode_rows, make_prompt, make_lean_prompt,
        make_rows_prompt, decode, decode_rows,
    )
    from minifmt.tokens import get_tokenizer
    sys.path.insert(0, str(HERE.parents[1]))
    from benchmark import competitors

    sample = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    contract = infer_contract([sample], "ticket")
    wire = encode(sample, contract, shared=False, dictionaries=False)
    wire_v2 = encode_v2(sample, contract)
    wire_rows = encode_rows(sample, contract, last_text_field="titulo")
    wire_rows_opt = encode_rows(sample, contract, last_text_field="titulo", allow_nullable=True, compact_bools=True)
    assert decode(wire, contract) == sample
    assert decode(wire_v2, contract) == sample
    assert decode_rows(wire_rows_opt, contract, last_text_field="titulo", expected_records=len(sample),
                       allow_nullable=True, compact_bools=True) == sample
    toon, roundtrip = toon_encode([sample])[0]
    assert roundtrip
    tokenizer = get_tokenizer("o200k_base")
    texts = {
        "json": json.dumps(sample, ensure_ascii=False, separators=(",", ":")),
        "toon": toon,
        "mini": wire,
        "mini_v2": wire_v2,
        "mini_rows": wire_rows_opt,
    }
    comp = {
        "ison": tokenizer.count(competitors.ison_encode(sample, "ticket")),
        "lean": tokenizer.count(competitors.lean_encode(sample, "ticket")),
        "tonl": tokenizer.count(competitors.tonl_encode(sample, "ticket")),
        "hedl": tokenizer.count(competitors.hedl_encode(sample, "ticket")),
        "raif": tokenizer.count(competitors.raif_encode(sample, "ticket")),
        "json_positional": tokenizer.count(competitors.json_positional_encode(sample, "ticket")),
        "json_short": tokenizer.count(competitors.json_short_encode(sample, "ticket")),
    }
    return {
        "encoding": "o200k_base",
        "scope": "output only; same 20 tickets",
        "tokens": {key: tokenizer.count(text) for key, text in texts.items()},
        "competitors": comp,
        "mini_prompt_tokens": tokenizer.count(make_prompt(contract, "es", sample[:2])),
        "mini_lean_prompt_tokens": tokenizer.count(make_lean_prompt(contract, "es", sample[:1])),
        "mini_rows_prompt_tokens": tokenizer.count(make_rows_prompt(contract, last_text_field="titulo", expected_records=len(sample), lang="es")),
        "note": "Prompt and repair calls are extra; output counts exclude prompt overhead.",
    }


if __name__ == "__main__":
    result = measure()
    (HERE / "comparison.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
