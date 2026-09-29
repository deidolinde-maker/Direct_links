"""Build a deduplicated URL input file for the availability check."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAM_NAMES = {
    "ad", "ad_id", "adgroupid", "added", "addedphrases", "addedphrasestext",
    "block", "campaign_id", "cm_id", "device", "gbid", "keyword", "phrase_id",
    "phrase", "position", "position_type", "region_id", "region_name", "retargeting",
    "roistat", "roistat_pos", "roistat_referrer", "rs_stat", "source",
    "source_type", "yclid", "gclid", "fbclid", "openstat", "yagla",
}


def is_tracking_param(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized in TRACKING_PARAM_NAMES or normalized.startswith("utm_")


def normalize_url(value: str) -> str:
    """Return the page URL without advertising and analytics parameters."""
    parsed = urlsplit(value.strip())
    query = []
    for name, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        if is_tracking_param(name):
            continue
        # A macro is not a concrete page region. If a URL contains both a
        # concrete region and {region_id}, keep only the concrete value.
        if name.strip().lower() == "region" and ("{" in query_value or "}" in query_value):
            continue
        query.append((name, query_value))
    query = sorted(set(query))
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            urlencode(query),
            "",
        )
    )


def build(input_path: Path, output_path: Path) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    merged: dict[str, dict] = {}
    for row in payload.get("urls", []):
        url = str(row.get("url", "")).strip()
        if not url:
            continue
        canonical_url = normalize_url(url)
        parsed = urlsplit(canonical_url)
        region = dict(parse_qsl(parsed.query, keep_blank_values=True)).get("region", "")
        current = merged.setdefault(
            canonical_url,
            {
                "url": canonical_url,
                "source_urls": set(),
                "campaign_ids": set(),
                "sources": set(),
                "regions": set(),
            },
        )
        current["source_urls"].add(url)
        current["campaign_ids"].update(str(value) for value in row.get("campaign_ids", []))
        current["sources"].update(str(value) for value in row.get("sources", []))
        if region and "{" not in region and "}" not in region:
            current["regions"].add(region)

    urls = []
    for row in merged.values():
        urls.append(
            {
                "url": row["url"],
                "source_urls": sorted(row["source_urls"]),
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
