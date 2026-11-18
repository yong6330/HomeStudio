"""Scoped, versioned observation results tied to existing camera events."""
import json
import math
from datetime import date as Date, datetime, time, timedelta, timezone

from .homespace import current_space

ANALYSIS_REVISION = "motion-candidate-v1"
LABELS = {"movement_candidate", "wheel_motion_candidate", "repeated_path_candidate"}
QUALITY_REASONS = {"no_cage_roi", "empty_cage_roi", "global_light_change", "multiple_motion_regions",
                   "large_motion_region", "insufficient_frames", "decode_timeout", "decode_failed",
                   "memory_limit", "memory_measurement_unavailable", "original_missing_preview_used",
                   "source_file_missing"}
_RESULT_FIELDS = ("status", "source", "source_time_quality", "frame_size", "sample_fps",
                  "analyzed_sec", "quality_reasons", "intervals", "analysis_revision", "roi_revision")


def ensure(db):
    """Keep explicit for callers; Database initialization creates this table idempotently."""
    with db._get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS event_observations (
            event_id TEXT PRIMARY KEY, homespace_id INTEGER NOT NULL,
            analysis_revision TEXT NOT NULL, roi_revision INTEGER,
            result_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_observations_space ON event_observations(homespace_id, event_id)")


def _space_id():
    return current_space.get() or 1


def _empty(event_id):
    return {"event_id": event_id, "status": "not_analyzed", "source": None,
            "source_time_quality": "unknown", "frame_size": None, "sample_fps": None,
            "analyzed_sec": 0.0, "quality_reasons": [], "intervals": [],
            "analysis_revision": None, "roi_revision": None}


def _validate(result):
    if not isinstance(result, dict) or result.get("status") not in ("ready", "failed"):
        raise ValueError("invalid observation status")
    if result.get("source") not in ("original", "preview"):
        raise ValueError("invalid observation source")
    if result.get("source_time_quality") != "unknown":
        raise ValueError("source time mapping is not stored")
    revision = result.get("analysis_revision")
    if not isinstance(revision, str) or not revision or len(revision) > 64:
        raise ValueError("invalid analysis revision")
    roi_revision = result.get("roi_revision")
    if roi_revision is not None and (not isinstance(roi_revision, int) or roi_revision < 0):
        raise ValueError("invalid ROI revision")
    size = result.get("frame_size")
    if not isinstance(size, (list, tuple)) or len(size) != 2 or any(type(v) is not int or not 1 <= v <= 8192 for v in size):
        raise ValueError("invalid frame size")

    def number(value, name, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"invalid {name}")
        return float(value)

    sample_fps = number(result.get("sample_fps"), "sample fps", 0.01, 30)
    analyzed_sec = number(result.get("analyzed_sec"), "analyzed seconds", 0, 60)
    reasons = result.get("quality_reasons")
    if not isinstance(reasons, list) or len(reasons) > 32 or any(x not in QUALITY_REASONS for x in reasons):
        raise ValueError("invalid quality reasons")
    intervals = result.get("intervals")
    if not isinstance(intervals, list) or len(intervals) > 300:
        raise ValueError("invalid intervals")
    clean_intervals = []
    for item in intervals:
        if not isinstance(item, dict) or item.get("label") not in LABELS or item.get("state") not in ("candidate", "unknown"):
            raise ValueError("invalid interval label or state")
        start = number(item.get("start_sec"), "interval start", 0, analyzed_sec)
        end = number(item.get("end_sec"), "interval end", 0, analyzed_sec)
        if start >= end:
            raise ValueError("invalid interval range")
        zone = item.get("zone_id")
        if zone is not None and (not isinstance(zone, str) or len(zone) > 32):
            raise ValueError("invalid interval zone")
        clean_intervals.append({"start_sec": start, "end_sec": end, "label": item["label"],
                                "state": item["state"], "zone_id": zone})
    return {"status": result["status"], "source": result["source"],
            "source_time_quality": result["source_time_quality"], "frame_size": list(size),
            "sample_fps": sample_fps, "analyzed_sec": analyzed_sec,
            "quality_reasons": reasons[:], "intervals": clean_intervals,
            "analysis_revision": revision, "roi_revision": roi_revision}


def save_analysis(db, event_id, result):
    clean = _validate(result)
    space_id = _space_id()
    with db._get_connection() as conn:
        event = conn.execute("SELECT 1 FROM events WHERE event_id=? AND homespace_id=?", (event_id, space_id)).fetchone()
        if event is None:
            raise LookupError("event not found")
        conn.execute("""INSERT INTO event_observations
            (event_id, homespace_id, analysis_revision, roi_revision, result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET homespace_id=excluded.homespace_id,
                analysis_revision=excluded.analysis_revision, roi_revision=excluded.roi_revision,
                result_json=excluded.result_json, updated_at=excluded.updated_at""",
                     (event_id, space_id, clean["analysis_revision"], clean["roi_revision"],
                      json.dumps(clean, separators=(",", ":")), datetime.now(timezone.utc).isoformat()))
    return {"event_id": event_id, **clean}


def for_event(db, event_id):
    space_id = _space_id()
    with db._get_connection() as conn:
        event = conn.execute("SELECT 1 FROM events WHERE event_id=? AND homespace_id=?", (event_id, space_id)).fetchone()
        if event is None:
            raise LookupError("event not found")
        row = conn.execute("SELECT result_json FROM event_observations WHERE event_id=? AND homespace_id=?",
                           (event_id, space_id)).fetchone()
    if row is None:
        return _empty(event_id)
    try:
        value = json.loads(row[0])
        return {"event_id": event_id, **_validate(value)}
    except (TypeError, ValueError, json.JSONDecodeError):
        return _empty(event_id)


def for_day(db, day, off):
    space_id = _space_id()
    token = current_space.set(space_id)
    try:
        day = Date.fromisoformat(day) if isinstance(day, str) else day
        start = datetime.combine(day, time.min, timezone(timedelta(hours=9))) + timedelta(hours=off)
        to_utc = lambda value: value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        from .homespace import sql_space
        frag, extra = sql_space("e.homespace_id")
        with db._get_connection() as conn:
            rows = conn.execute("""SELECT e.event_id, e.started_at, o.result_json
                FROM events e JOIN event_observations o
                  ON o.event_id=e.event_id AND o.homespace_id=e.homespace_id
                WHERE e.started_at>=? AND e.started_at<=?""" + frag + " ORDER BY e.started_at DESC",
                (to_utc(start - timedelta(hours=2)), to_utc(start + timedelta(hours=26)), *extra)).fetchall()
        items = []
        for row in rows:
            observed = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")).astimezone(
                timezone(timedelta(hours=9))) - timedelta(hours=off)
            if observed.date() != day:
                continue
            try:
                items.append({"event_id": row["event_id"], **_validate(json.loads(row["result_json"]))})
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    finally:
        current_space.reset(token)
    ready = [item for item in items if item["status"] == "ready"]
    return {"items": items, "analyzed_clips": len(ready),
            "analyzed_sec": round(sum(item["analyzed_sec"] for item in ready), 2)}
