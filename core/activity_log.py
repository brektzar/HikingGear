"""Application activity logging helpers."""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument

from .db import get_collection, utc_now

DEFAULT_MAX_LOGS_PER_USER = 150
MIN_MAX_LOGS_PER_USER = 50
MAX_MAX_LOGS_PER_USER = 2000


def _get_max_logs_per_user() -> int:
    """Read configured per-user log cap, or return default value."""
    try:
        settings = get_collection("app_settings")
        doc = settings.find_one({"_id": "activity_log_settings"}, {"max_logs_per_user": 1}) or {}
        value = int(doc.get("max_logs_per_user", DEFAULT_MAX_LOGS_PER_USER))
        return max(MIN_MAX_LOGS_PER_USER, min(MAX_MAX_LOGS_PER_USER, value))
    except Exception:
        return DEFAULT_MAX_LOGS_PER_USER


def log_activity(
    actor: str,
    action: str,
    *,
    module: str = "",
    target: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Write a best-effort audit entry using per-user ring buffer slots."""
    try:
        normalized_actor = str(actor or "unknown").strip().lower() or "unknown"
        logs = get_collection("activity_logs")
        counters = get_collection("activity_log_counters")
        counter_doc = counters.find_one_and_update(
            {"_id": normalized_actor},
            {"$inc": {"seq": 1}, "$setOnInsert": {"created_at": utc_now()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        sequence = int((counter_doc or {}).get("seq", 1))
        max_logs_per_user = _get_max_logs_per_user()
        slot = ((sequence - 1) % max_logs_per_user) + 1
        now = utc_now()
        logs.replace_one(
            {"_id": f"{normalized_actor}:{slot}"},
            {
                "_id": f"{normalized_actor}:{slot}",
                "actor": normalized_actor,
                "slot": slot,
                "max_slots": max_logs_per_user,
                "sequence": sequence,
                "action": str(action).strip(),
                "module": str(module).strip(),
                "target": str(target).strip(),
                "details": details or {},
                "event_at": now,
                "created_at": now,
            },
            upsert=True,
        )
    except Exception:
        # Never block user flow if audit logging fails.
        return
