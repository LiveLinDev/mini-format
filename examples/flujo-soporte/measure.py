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
    from minifmt.domain import infer_contract, encode, make_prompt, decode
    from minifmt.tokens import get_tokenizer
    sample = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    contract = infer_contract([sample], "ticket")
    wire = encode(sample, contract, shared=False, dictionaries=False)
    assert decode(wire, contract) == sample
    toon, roundtrip = toon_encode([sample])[0]
    assert roundtrip
    tokenizer = get_tokenizer("o200k_base")
    texts = {"json": json.dumps(sample, ensure_ascii=False, separators=(",", ":")), "toon": toon, "mini": wire}
    return {"encoding": "o200k_base", "scope": "output only; same 20 tickets",
            "tokens": {key: tokenizer.count(text) for key, text in texts.items()},
            "mini_prompt_tokens": tokenizer.count(make_prompt(contract, "es", sample[:2])),
            "note": "Prompt and repair calls are extra; these output counts do not measure end-to-end cost."}


if __name__ == "__main__":
    result = measure()
    (HERE / "comparison.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
