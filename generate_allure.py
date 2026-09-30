"""Convert availability.json into Allure result files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path


def timestamp_ms(value: str, duration_seconds: float) -> tuple[int, int]:
    checked_at = datetime.fromisoformat(value)
    started = checked_at - timedelta(seconds=duration_seconds or 0)
    return int(started.timestamp() * 1000), int(checked_at.timestamp() * 1000)


def write_result(output_dir: Path, result: dict) -> None:
    url = result.get("url", "")
    status = "passed" if result.get("status") == "OK" else "failed"
    start, stop = timestamp_ms(result["checked_at"], result.get("duration_seconds", 0))
    status_details = {}
    if status == "failed":
        status_details = {"message": result.get("error") or "URL check failed"}

    payload = {
        "uuid": str(uuid.uuid4()),
        "historyId": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "name": f"Проверка URL: {url}",
        "fullName": f"URL availability::{url}",
        "status": status,
        "statusDetails": status_details,
        "stage": "finished",
        "start": start,
        "stop": stop,
        "labels": [
            {"name": "suite", "value": "URL availability"},
            {"name": "feature", "value": "Advertising landing pages"},
        ],
        "parameters": [
            {"name": "url", "value": url},
            {"name": "http_code", "value": str(result.get("http_code") or "")},
            {"name": "attempts", "value": str(result.get("attempts", ""))},
            {"name": "campaign_ids", "value": ",".join(result.get("campaign_ids", []))},
            {"name": "sources", "value": ",".join(result.get("sources", []))},
            {"name": "regions", "value": ",".join(result.get("regions", []))},
        ],
    }
    (output_dir / f"{payload['uuid']}-result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="availability.json")
    parser.add_argument("--output", default="allure-results")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    for result in payload.get("results", []):
        write_result(output_dir, result)

    stats = payload.get("stats", {})
    (output_dir / "environment.properties").write_text(
        "\n".join(
            [
                f"total={stats.get('total', 0)}",
                f"ok={stats.get('ok', 0)}",
                f"errors={stats.get('errors', 0)}",
                f"workers={stats.get('workers', 0)}",
                f"timeout_seconds={stats.get('timeout_seconds', 0)}",
                f"retries={stats.get('retries', 0)}",
                f"proxy_enabled={stats.get('proxy_enabled', False)}",
                f"jenkins_build={os.getenv('BUILD_NUMBER', '')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Allure results: {len(payload.get('results', []))}")
    print(f"Allure directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
