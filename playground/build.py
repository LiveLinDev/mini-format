"""Assemble playground/index.html (single self-contained file for GitHub Pages).

    python playground/build.py
Embeds js/mini.js, the official TOON browser bundle and one help-desk sample.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from sample import sample_forks  # noqa: E402


def main() -> None:
    tpl = (ROOT / "playground" / "template.html").read_text(encoding="utf-8")
    mini_js = (ROOT / "js" / "mini.js").read_text(encoding="utf-8")
    toon_js = (ROOT / "benchmark" / "toon_ref" / "toon.bundle.js").read_text(encoding="utf-8")
    forks = sample_forks(ROOT)

    def safe(js: str) -> str:  # never let the JSON close the script tag
        return js.replace("</script", "<\\/script")

    html = (tpl.replace("__MINI_JS__", safe(mini_js)).replace("__TOON_JS__", safe(toon_js))
               .replace("__FORKS_JSON__", safe(json.dumps(forks, ensure_ascii=False))))
    out = ROOT / "playground" / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html.encode('utf-8'))/1024:.0f} KB, {len(forks)} sample contract)")


if __name__ == "__main__":
    main()
