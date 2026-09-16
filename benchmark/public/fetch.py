"""Refresh the public API snapshots. Does not run during an offline benchmark."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SOURCES = [
    {
        "id": "products",
        "title": "DummyJSON products",
        "url": "https://dummyjson.com/products?limit=0",
        "documentation": "https://dummyjson.com/docs/products",
        "kind": "public synthetic test data",
        "records_key": "products",
        "selection": "All products returned by the public endpoint; no field selection.",
    },
    {
        "id": "users",
        "title": "DummyJSON users",
        "url": "https://dummyjson.com/users?limit=0",
        "documentation": "https://dummyjson.com/docs/users",
        "kind": "public synthetic test data; identities and credentials are fictional",
        "records_key": "users",
        "selection": "All users returned by the public endpoint; no field selection.",
    },
    {
        "id": "comments",
        "title": "JSONPlaceholder comments",
        "url": "https://jsonplaceholder.typicode.com/comments",
        "documentation": "https://jsonplaceholder.typicode.com/",
        "kind": "public synthetic test data",
        "records_key": None,
        "selection": "The complete comments collection; no field selection.",
    },
    {
        "id": "earthquakes",
        "title": "USGS earthquake observations",
        "url": "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2025-01-01&endtime=2025-02-01&limit=1000&orderby=time-asc",
        "documentation": "https://earthquake.usgs.gov/fdsnws/event/1/",
        "kind": "real historical earthquake observations",
        "records_key": "features",
        "selection": "First 1000 events chronologically in January 2025; no magnitude filter or field selection.",
    },
]


def main() -> None:
    target = HERE / "data"
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in SOURCES:
        request = Request(source["url"], headers={"User-Agent": "mini-format-reproducible-benchmark/1.0"})
        with urlopen(request, timeout=90) as response:
            raw = response.read()
        document = json.loads(raw)
        records = document[source["records_key"]] if source["records_key"] else document
        ids = [row["id"] for row in records]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate source IDs in {source['id']}")
        path = target / f"{source['id']}.json"
        path.write_bytes(raw)
        manifest.append({
            **source,
            "file": path.relative_to(HERE).as_posix(),
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "records": len(records),
            "unique_ids": len(set(ids)),
        })
        print(f"{source['id']}: {len(records)} unique records, {len(raw)} bytes", flush=True)
    (HERE / "sources.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
