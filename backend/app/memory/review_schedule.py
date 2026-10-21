"""Helpers for the lightweight interval-based review schedule memory."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_INTERVAL_PATTERNS = (
    re.compile(r"(?:每|隔)\s*(\d+)\s*天\s*复习(?:\s*一次)?"),
    re.compile(r"间隔\s*(\d+)\s*天"),
)


def parse_review_interval_days(content: str | None) -> int | None:
    """Return a safe interval in days from a supported natural-language rule."""
    if not content:
        return None
    if re.search(r"每天(?:\s*复习)?", content):
        return 1
    for pattern in _INTERVAL_PATTERNS:
        match = pattern.search(content)
        if match:
            interval = int(match.group(1))
            return interval if 1 <= interval <= 365 else None
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_review_due(
    content: str | None,
    baseline: datetime,
    *,
    now: datetime | None = None,
) -> bool:
    """Whether an interval review is due at ``now``."""
    interval = parse_review_interval_days(content)
    if interval is None:
        return False
    current = _as_utc(now or datetime.now(timezone.utc))
    return current >= _as_utc(baseline) + timedelta(days=interval)


def review_reminder(content: str) -> str:
    """Build the single canonical sentence shown when a review is due."""
    interval = parse_review_interval_days(content)
    if interval == 1:
        schedule = "每天复习"
    elif interval is not None:
        schedule = f"每{interval}天复习一次"
    else:
        schedule = content.strip()
    return f"复习提醒：根据你设置的{schedule}，当前已到复习时间。"
