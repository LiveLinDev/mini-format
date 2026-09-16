"""Check generated public pages and downloadable artifacts without a network."""
from __future__ import annotations

from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "sitio"
ORIGIN = "https://mini-format.pmoluna.com"


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ("href", "src", "poster"):
            if attrs.get(key):
                self.links.append(attrs[key])


def main():
    pages = {path: Page(path.read_text(encoding="utf-8")) for path in SITE.rglob("*.html")
             if not any(p in {"downloads", "servidor"} for p in path.relative_to(SITE).parts[:-1])}
    # Download indexes are public; exclude only potential HTML inside artifacts.
    for path in (SITE / "downloads/index.html", SITE / "en/downloads/index.html"):
        if path.exists():
            pages[path] = Page(path.read_text(encoding="utf-8"))
    problems = []
    for path, page in pages.items():
        relative = path.relative_to(SITE).as_posix()
        for name, count in Counter(page.ids).items():
            if count > 1:
                problems.append(f"{relative}: duplicate id {name}")
        for link in page.links:
            url = urlsplit(urljoin(ORIGIN + "/" + relative, link))
            if url.scheme not in {"http", "https"} or url.netloc != urlsplit(ORIGIN).netloc:
                continue
            target = (SITE / unquote(url.path).lstrip("/")).resolve()
            if not target.is_relative_to(SITE):
                problems.append(f"{relative}: outside site {link}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                problems.append(f"{relative}: missing {link}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                problems.append(f"{relative}: missing anchor {link}")
    manifest = json.loads((SITE / "downloads/manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        data = (SITE / "downloads" / entry["name"]).read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            problems.append(f"invalid release checksum: {entry['name']}")
    if problems:
        raise SystemExit("\n".join(sorted(set(problems))))
    print(f"PASS: {len(pages)} HTML pages, internal links/anchors, unique IDs and {len(manifest['files'])} artifact checksums")


if __name__ == "__main__":
    main()
