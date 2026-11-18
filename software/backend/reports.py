"""On-demand daily care report projection from existing observation records."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from . import insights, zones
from .homespace import current_space

KST = timezone(timedelta(hours=9))


def _parse(value):
    value = value.replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _start(day, offset):
    return datetime.combine(day, time(), KST) + timedelta(hours=offset)


def _media_path(config, value):
    if not value:
        return False
    base = Path(config.base_dir).resolve()
    path = Path(value).resolve()
    return base in path.parents and path.is_file()


def _clip_track(track, original_start, left, right):
    """Keep only sampled points inside this report interval; event paths remain separate."""
    out = []
    for p in track:
        if not isinstance(p, (list, tuple)) or len(p) < 3:
            continue
        try:
            t, x, y = float(p[0]), float(p[1]), float(p[2])
        except (TypeError, ValueError):
            continue
        at = original_start + timedelta(seconds=t)
        if left <= at < right:
            out.append([t, x, y])
    return out


def daily_report(db, config, day, now=None):
    from .api import care_offset, _bounds
    from . import zones as zmod
    now = (now or datetime.now(KST)).astimezone(KST)
    if day.year < 1970:
        raise ValueError("date outside supported range")
    offset = care_offset(db)
    start, finish = _start(day, offset), _start(day + timedelta(days=1), offset)
    if start >= now:
        raise ValueError("future care day")
    observed_end = min(finish, now)
    state = "closed" if now >= finish else "in_progress"
    elapsed = max(0.0, (observed_end - start).total_seconds())
    sid = current_space.get() or 1
    # Keep a coarse margin because stored ISO timestamps may use Z or +00:00;
    # exact overlap is decided below after timezone-aware parsing.
    lo, hi = _bounds(day, offset)
    rows = db.list_events(limit=100000, start_time=lo, end_time=hi)
    events = []
    for row in rows:
        a, b = _parse(row["started_at"]), _parse(row["ended_at"])
        left, right = max(a, start), min(b, observed_end)
        if right <= left:
            continue
        duration = max(0.0, float(row.get("duration_sec") or 0))
        overlap = (right - left).total_seconds()
        ratio = min(1.0, overlap / duration) if duration > 0 else 0.0
        track = json.loads(row.get("track_json") or "[]")
        if not isinstance(track, list):
            track = []
        track = _clip_track(track, a, left, right)
        events.append({**row, "_start": left, "_end": right, "_duration": overlap,
                       "_distance": float(row.get("distance_px") or 0) * ratio, "_track": track})
    events.sort(key=lambda e: (e["_start"], e["event_id"]))

    sessions = []
    for e in events:
        if not sessions or (e["_start"] - sessions[-1]["_end"]).total_seconds() > 30:
            sessions.append({"_start": e["_start"], "_end": e["_end"], "active_sec": 0.0, "distance_px": 0.0, "event_count": 0})
        s = sessions[-1]
        s["_end"] = max(s["_end"], e["_end"])
        s["active_sec"] += e["_duration"]
        s["distance_px"] += e["_distance"]
        s["event_count"] += 1
    hourly = []
    for i in range(24):
        bucket_start = start + timedelta(hours=i)
        bucket_end = min(bucket_start + timedelta(hours=1), observed_end)
        active, dist, count = 0.0, 0.0, 0
        if bucket_end > bucket_start:
            for e in events:
                overlap = max(0.0, (min(e["_end"], bucket_end) - max(e["_start"], bucket_start)).total_seconds())
                if overlap:
                    active += overlap
                    dist += e["_distance"] * overlap / e["_duration"] if e["_duration"] else 0
                    count += 1
        hourly.append({"hour": bucket_start.hour, "active_sec": round(active, 2), "distance_px": round(dist, 2), "event_count": count})
    # The current camera/coverage collector is assigned to the original home only.
    # A new homespace cannot inherit that camera's uptime as its own evidence.
    coverage = insights.coverage(db, start, observed_end) if elapsed and sid == 1 else 0.0
    quality = "valid" if elapsed >= 24 * 3600 and coverage >= insights.MIN_COVERAGE else "insufficient_data"
    baseline = insights.baseline(db, day.isoformat(), offset, now)
    if sid != 1:
        baseline = {**baseline, "status": "low_coverage", "coverage": 0.0, "signals": [],
                    "metrics": {k: {**v, "flag": "unknown"} for k, v in baseline["metrics"].items()}}
    zs = zmod.load(db)
    width, height = config.motion_downscale_width, config.motion_downscale_height
    zone_totals = {z["id"]: {**z, "visits": 0, "dwell_sec": 0.0, "events": 0} for z in zs if z["kind"] != "cage"}
    tracks, clips = [], []
    for e in events:
        if e["_track"]:
            tracks.append({"event_id": e["event_id"], "started_at": e["_start"].astimezone(KST).isoformat(),
                           "ended_at": e["_end"].astimezone(KST).isoformat(), "track": e["_track"]})
            stats = zmod.track_stats(e["_track"], zs, width, height)
            for zid, stat in stats.items():
                if zid in zone_totals:
                    zone_totals[zid]["visits"] += stat["visits"]
                    zone_totals[zid]["dwell_sec"] += stat["dwell_sec"]
                    zone_totals[zid]["events"] += bool(stat["visits"])
        playable = _media_path(config, e.get("clip_path"))
        thumbnail = _media_path(config, e.get("thumbnail_path"))
        clips.append({"id": e["event_id"], "started_at": e["_start"].astimezone(KST).isoformat(),
                      "ended_at": e["_end"].astimezone(KST).isoformat(), "playable": playable,
                      "clip_url": f"/media/clip/{quote(str(e['event_id']), safe='')}" if playable else None,
                      "thumbnail_url": f"/media/thumb/{quote(str(e['event_id']), safe='')}" if thumbnail else None,
                      "protected": bool(e.get("is_protected")), "duration_sec": round(e["_duration"], 2)})
    clips.sort(key=lambda c: (-int(c["protected"]), -c["duration_sec"], c["started_at"], c["id"]))
    with db._get_connection() as conn:
        target = conn.execute("SELECT care_target_id,name,target_type,timezone,care_day_start_local FROM care_targets WHERE homespace_id=? ORDER BY care_target_id LIMIT 1", (sid,)).fetchone()
    care_signature = json.dumps(tuple(target) if target else (), ensure_ascii=False, separators=(",", ":"))
    care_revision = hashlib.sha256(care_signature.encode()).hexdigest()[:16]
    epoch = insights.observation_epoch(db, offset, now)
    result = {"date": day.isoformat(), "start_at": start.isoformat(), "end_at": finish.isoformat(), "state": state,
            "quality": quality, "coverage": round(coverage, 3), "generated_at": now.isoformat(),
            "care_revision": care_revision, "observation_epoch": {"revision": epoch["revision"], "since": epoch["since"], "rebuilding": bool(epoch["rebuilding"])},
            "data_revision": db.event_revision(),
            "summary": {"observed_sec": round(elapsed, 2), "active_sec": round(sum(s["active_sec"] for s in sessions), 2),
                        "session_count": len(sessions), "clip_count": sum(1 for c in clips if c["playable"]),
                        "distance_px": round(sum(s["distance_px"] for s in sessions), 2), "distance_unit": "px"},
            "frame_size": {"width": width, "height": height},
            "hourly": hourly, "baseline": baseline, "zones": list(zone_totals.values()), "tracks": tracks,
            "highlights": clips[:3],
            "limitations": ["coverage_does_not_verify_motion_detection_accuracy", "distance_is_image_pixels_only",
                            "food_water_are_zone_visits_not_intake", "sleep_heart_rate_identity_and_csi_location_unmeasured",
                            "recomputed_with_current_configuration"]}
    from . import observations
    result["camera_observations"] = observations.for_day(db, day.isoformat(), offset)
    return result
