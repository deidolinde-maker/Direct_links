"""Merge targeted URL discovery results into the regular export file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge(base_path: Path, required_path: Path, output_path: Path) -> int:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    required = json.loads(required_path.read_text(encoding="utf-8"))
    rows: dict[str, dict] = {}
    for row in base.get("urls", []):
        url = str(row.get("url", "")).strip()
        if url:
            rows[url] = {
                "url": url,
                "campaign_ids": set(str(value) for value in row.get("campaign_ids", [])),
                "sources": set(str(value) for value in row.get("sources", [])),
                "impressions": str(row.get("impressions", "")),
            }

    added = 0
    for match in required.get("matches", []):
        url = str(match.get("url", "")).strip()
        if not url:
            continue
        row = rows.setdefault(
            url,
            {"url": url, "campaign_ids": set(), "sources": set(), "impressions": ""},
        )
        before = (len(row["campaign_ids"]), len(row["sources"]))
        campaign_id = str(match.get("campaign_id", "")).strip()
        if campaign_id:
            row["campaign_ids"].add(campaign_id)
        source = str(match.get("source", "")).strip()
        if source:
            row["sources"].add(f"required_{source}")
        if match.get("impressions") and not row["impressions"]:
            row["impressions"] = str(match["impressions"])
        if before != (len(row["campaign_ids"]), len(row["sources"])):
            added += 1

    result = {
        "updated_at": required.get("updated_at", base.get("updated_at", "")),
        "stats": {
            **base.get("stats", {}),
            "required_matches": len(required.get("matches", [])),
            "required_rows_added": added,
            "merged_url_rows": len(rows),
        },
        "urls": [
            {
                "url": row["url"],
                "campaign_ids": sorted(row["campaign_ids"]),
                "sources": sorted(row["sources"]),
                "impressions": row["impressions"],
            }
            for row in sorted(rows.values(), key=lambda item: item["url"])
        ],
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Base URL rows: {len(base.get('urls', []))}")
    print(f"Required matches: {len(required.get('matches', []))}")
    print(f"Merged URL rows: {len(rows)}")
    print(f"Output: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="urls.json")
    parser.add_argument("--required", default="required_urls.json")
    parser.add_argument("--output", default="urls_with_required.json")
    args = parser.parse_args()
    return merge(Path(args.base), Path(args.required), Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
