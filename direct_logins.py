"""Credential helpers for querying several Direct client accounts."""

from __future__ import annotations

import os
import re


def required_logins() -> list[str]:
    raw = os.getenv("YANDEX_DIRECT_LOGINS", "").strip()
    if not raw:
        raw = os.getenv("YANDEX_DIRECT_LOGIN", "").strip()
    if not raw:
        raise RuntimeError("Required environment variable is missing: YANDEX_DIRECT_LOGINS")
    logins = [value for value in re.split(r"[,;\s]+", raw) if value]
    if not logins:
        raise RuntimeError("YANDEX_DIRECT_LOGINS does not contain any client login")
    return list(dict.fromkeys(logins))
