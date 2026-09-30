"""One self-contained help-desk example for both playground builds."""
from __future__ import annotations

import json
from pathlib import Path

from minifmt import from_json_schema


def sample_forks(root: Path) -> list[dict]:
    base = root / "examples" / "mesa-de-ayuda"
    schema = json.loads((base / "ticket.schema.json").read_text(encoding="utf-8"))
    contract = from_json_schema(schema, "tk").to_dict()
    example = (base / "grabaciones" / "mini" / "ok.mini").read_text(encoding="utf-8")
    return [{"prefix": "tk", "contract": contract, "example": example}]
