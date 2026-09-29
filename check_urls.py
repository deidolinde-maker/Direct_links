"""Check URL availability with retries and write a machine-readable result file."""

from __future__ import annotations

import argparse
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


MOSCOW = ZoneInfo("Europe/Moscow")


def now_moscow() -> str:
    return datetime.now(MOSCOW).isoformat(timespec="seconds")


def check_one(item: dict, retries: int, timeout: float, retry_delay: float) -> dict:
    url = item["url"]
    attempts = retries + 1
    last_error = ""
    last_code = None
    started = monotonic()
    for attempt in range(1, attempts + 1):
        try:
            request = Request(
                url,
                headers={"User-Agent": "DirectLinksAvailabilityChecker/1.0"},
                method="GET",
            )
            with urlopen(request, timeout=timeout) as response:
                response.read(1)
                last_code = response.status
            if last_code == 200:
                result_status = "OK"
                last_error = ""
            else:
                result_status = "ERROR"
                last_error = f"Unexpected HTTP status: {last_code}"
            break
        except HTTPError as exc:
            last_code = exc.code
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except (TimeoutError, socket.timeout):
            last_error = "TIMEOUT"
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            last_error = f"URL_ERROR: {reason}"
        except (ValueError, UnicodeError) as exc:
            last_error = f"INVALID_URL: {exc}"
            break
        except OSError as exc:
            last_error = f"NETWORK_OS_ERROR: {exc}"
        if attempt < attempts:
            sleep(retry_delay)

    if "result_status" not in locals():
        result_status = "ERROR"
    result = {
        "url": url,
        "checked_at": now_moscow(),
        "status": result_status,
        "http_code": last_code,
        "error": last_error,
        "attempts": attempt,
        "duration_seconds": round(monotonic() - started, 3),
        "campaign_ids": item.get("campaign_ids", []),
        "sources": item.get("sources", []),
        "regions": item.get("regions", []),
        "source_urls": item.get("source_urls", []),
    }
    return result


def write_output(path: Path, input_file: str, results: list[dict], args: argparse.Namespace, complete: bool) -> None:
    ok_count = sum(row["status"] == "OK" for row in results)
    error_count = len(results) - ok_count
    output = {
        "checked_at": now_moscow(),
        "complete": complete,
        "input_file": input_file,
        "stats": {
            "total": len(results),
            "ok": ok_count,
            "errors": error_count,
            "workers": args.workers,
            "timeout_seconds": args.timeout,
            "retries": args.retries,
        },
        "results": sorted(results, key=lambda row: row["url"]),
    }
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="check_urls.json")
    parser.add_argument("--output", default="availability.json")
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=0.2)
    args = parser.parse_args()
    if args.workers < 1 or args.retries < 0 or args.timeout <= 0:
        raise SystemExit("workers must be positive, retries non-negative, timeout positive")

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    items = payload.get("urls", [])
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(check_one, item, args.retries, args.timeout, args.retry_delay): item
            for item in items
        }
        completed = 0
        for future in as_completed(futures):
            item = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # Keep one unexpected URL failure from aborting the run.
                results.append(
                    {
                        "url": item["url"],
                        "checked_at": now_moscow(),
                        "status": "ERROR",
                        "http_code": None,
                        "error": f"CHECKER_EXCEPTION: {exc}",
                        "attempts": 0,
                        "duration_seconds": 0,
                        "campaign_ids": item.get("campaign_ids", []),
                        "sources": item.get("sources", []),
                        "regions": item.get("regions", []),
                        "source_urls": item.get("source_urls", []),
                    }
                )
            completed += 1
            if completed == len(items) or completed % 500 == 0:
                print(f"Progress: {completed}/{len(items)}")
            if completed % 500 == 0:
                write_output(Path(args.output), args.input, results, args, complete=False)
    write_output(Path(args.output), args.input, results, args, complete=True)
    ok_count = sum(row["status"] == "OK" for row in results)
    error_count = len(results) - ok_count
    print(f"Checked: {len(results)}")
    print(f"OK: {ok_count}")
    print(f"Errors: {error_count}")
    print(f"Availability file: {args.output}")
    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
