"""Build a deduplicated URL input file for the availability check."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def build(input_path: Path, output_path: Path) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    merged: dict[str, dict] = {}
    for row in payload.get("urls", []):
        url = str(row.get("url", "")).strip()
        if not url:
            continue
        parsed = urlsplit(url)
        region = parse_qs(parsed.query).get("region", [""])[0]
        current = merged.setdefault(
            url,
            {
                "url": url,
                "campaign_ids": set(),
                "sources": set(),
                "regions": set(),
            },
        )
        current["campaign_ids"].update(str(value) for value in row.get("campaign_ids", []))
        current["sources"].update(str(value) for value in row.get("sources", []))
        if region and "{" not in region and "}" not in region:
            current["regions"].add(region)

    urls = []
    for row in merged.values():
        urls.append(
            {
                "url": row["url"],
                "campaign_ids": sorted(row["campaign_ids"]),
                "sources": sorted(row["sources"]),
                "regions": sorted(row["regions"]),
            }
        )
    urls.sort(key=lambda row: row["url"])
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(input_path),
        "stats": {
            "source_rows": len(payload.get("urls", [])),
            "unique_urls": len(urls),
            "urls_with_concrete_region": sum(1 for row in urls if row["regions"]),
        },
        "urls": urls,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="urls.json")
    parser.add_argument("--output", default="check_urls.json")
    args = parser.parse_args()
    result = build(Path(args.input), Path(args.output))
    print(f"Source rows: {result['stats']['source_rows']}")
    print(f"Unique URLs: {result['stats']['unique_urls']}")
    print(f"URLs with concrete region: {result['stats']['urls_with_concrete_region']}")
    print(f"Check file: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
