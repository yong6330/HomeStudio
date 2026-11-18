"""행동 건강 (stereotypy hints) from the existing centroid tracks — stdlib only, no AI API.

Per event (computed when the event ends, stored in events.behavior_json; older rows are computed on the fly):
- pacing (같은 길 왕복): >= PACE_REV reversals between full-length legs (>= PACE_SPAN px and >= 60% of the lane)
  along the track's main axis,
  while staying on a narrow lane (perpendicular spread <= PACE_LANE px).
- circling (제자리 빙빙 돌기, reference only): cumulative heading rotation >= CIRCLE_TURNS full turns within a
  small radius (<= CIRCLE_R px), turning mostly one way (|net| / total rotation >= CIRCLE_COHERENT). 2 fps sampling misses fast spins, so it never raises alerts.
Per care day: wheel dwell (쳇바퀴 zones), pacing events, circling events -> compared with the same 7 valid baseline days
as insights.baseline (median + scaled MAD). Coordinates are motion-frame px (160x90).
"""
import json
import math
import statistics
from datetime import date as Date, datetime, timedelta
from typing import Any, Dict, List, Optional

PACE_REV, PACE_SPAN, PACE_LANE, STEP = 4, 15.0, 5.0, 4.0
CIRCLE_TURNS, CIRCLE_R, CIRCLE_COHERENT = 2.0, 15.0, 0.6
Z, RATIO = 2.0, 1.5
FLOOR = {"wheel_sec": 300.0, "pace": 2.0, "circle": 2.0}
LABEL = {"wheel_sec": "쳇바퀴 구역 체류", "pace": "같은 길 왕복", "circle": "제자리 빙빙 돌기"}
REF_ONLY = {"circle"}
_CACHE: Dict[tuple, Dict[str, float]] = {}


def features(track) -> Dict[str, Any]:
    pts = [(float(p[1]), float(p[2])) for p in track or []]
    out = {"rev": 0, "turns": 0.0, "pace": False, "circle": False}
    if len(pts) < 6:
        return out
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts); syy = sum((y - my) ** 2 for _, y in pts); sxy = sum((x - mx) * (y - my) for x, y in pts)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)  # main axis
    ux, uy = math.cos(a), math.sin(a)
    s = [(x - mx) * ux + (y - my) * uy for x, y in pts]
    lane = statistics.pstdev([-(x - mx) * uy + (y - my) * ux for x, y in pts])
    exts, d, ext = [s[0]], 0, s[0]  # turning points with hysteresis STEP px
    for v in s[1:]:
        if d == 0:
            if abs(v - ext) >= STEP:
                d, ext = (1 if v > ext else -1), v
        elif (v - ext) * d > 0:
            ext = v
        elif abs(v - ext) >= STEP:
            exts.append(ext); d, ext = -d, v
    exts.append(ext)
    span = max(s) - min(s)
    # only full-length legs count (end to end of the lane), so jitter in place is not pacing
    legs = sum(1 for p, q in zip(exts, exts[1:]) if abs(q - p) >= max(PACE_SPAN, 0.6 * span))
    rev = max(0, legs - 1)
    turn, absturn, prev = 0.0, 0.0, None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if math.hypot(x1 - x0, y1 - y0) < 1.0:
            continue
        h = math.atan2(y1 - y0, x1 - x0)
        if prev is not None:
            dh = (h - prev + math.pi) % (2 * math.pi) - math.pi
            turn += dh; absturn += abs(dh)
        prev = h
    radius = max(math.hypot(x - mx, y - my) for x, y in pts)
    out.update(rev=rev, turns=round(abs(turn) / (2 * math.pi), 2))
    out["pace"] = rev >= PACE_REV and span >= PACE_SPAN and lane <= PACE_LANE
    coherent = absturn > 0 and abs(turn) / absturn >= CIRCLE_COHERENT  # mostly one rotation direction, not jitter
    out["circle"] = out["turns"] >= CIRCLE_TURNS and radius <= CIRCLE_R and coherent and not out["pace"]
    return out


def event_features(e: Dict[str, Any]) -> Dict[str, Any]:
    if e.get("behavior_json"):
        return json.loads(e["behavior_json"])
    return features(json.loads(e.get("track_json") or "[]"))


def day_values(db, day: Date, off: float, cutoff_h: float = 24.0, now: Optional[datetime] = None) -> Dict[str, float]:
    from . import api, insights, zones
    from .config import PipelineConfig
    end = insights._start(day, off) + timedelta(hours=cutoff_h)
    w = PipelineConfig().motion_downscale_width
    size = (w, round(w * 9 / 16))
    wheels = [z for z in zones.load(db) if z["kind"] == "wheel"]
    key = (str(db.db_path), insights._space_id(), db.event_revision(), day, off, json.dumps(wheels))
    if cutoff_h >= 24 and key in _CACHE:  # closed full days only (zone edits change the key)
        return dict(_CACHE[key])
    out = {"wheel_sec": 0.0, "pace": 0, "circle": 0}
    from .homespace import current_space
    token = current_space.set(insights._space_id())
    try:
        events = api.events_for(db, day.isoformat(), off)
    finally:
        current_space.reset(token)
    for e in events:
        if api._ts(e["started_at"]) >= end:
            continue
        f = event_features(e)
        out["pace"] += f["pace"]; out["circle"] += f["circle"]
        if wheels:
            out["wheel_sec"] += sum(v["dwell_sec"] for v in zones.track_stats(json.loads(e.get("track_json") or "[]"), wheels, *size).values())
    out["wheel_sec"] = round(out["wheel_sec"], 1)
    if cutoff_h >= 24 and insights._start(day, off) + timedelta(hours=24) <= (now or datetime.now(insights.KST)):
        if len(_CACHE) > 400:
            _CACHE.clear()
        _CACHE[key] = dict(out)
    return out


def _flag(key: str, today: float, past: List[float]) -> Dict[str, Any]:
    med = statistics.median(past)
    scale = max(1.4826 * statistics.median([abs(x - med) for x in past]), 0.15 * med, FLOOR[key])
    z = (today - med) / scale
    high = z >= Z and today >= max(RATIO * med, FLOOR[key])
    return {"key": key, "label": LABEL[key], "today": today, "median": round(med, 1), "z": round(z, 2),
            "pct": round((today - med) / med * 100) if med else None, "flag": "high" if high else "usual", "ref_only": key in REF_ONLY}


def summary(db, d: Optional[str], off: float, now: Optional[datetime] = None) -> Dict[str, Any]:
    from . import insights
    now = now or datetime.now(insights.KST)
    day = Date.fromisoformat(d) if d else (now.astimezone(insights.KST) - timedelta(hours=off)).date()
    cutoff = max(0.0, min(24.0, (now - insights._start(day, off)).total_seconds() / 3600))
    epoch = insights.observation_epoch(db, off, now)
    today = day_values(db, day, off, cutoff, now)
    days = insights.valid_days(db, day, off, now)
    cov = insights.coverage(db, insights._start(day, off), insights._start(day, off) + timedelta(hours=cutoff))
    status = insights.comparison_status(epoch, len(days), cov, cutoff)
    base = {"date": day.isoformat(), "cutoff_h": round(cutoff, 2), "valid_days": len(days), "need_days": insights.NEED_DAYS,
            "coverage": round(cov, 3), "revision": epoch["revision"], "since": epoch["since"]}
    from . import observations
    base["camera_observations"] = observations.for_day(db, day.isoformat(), off)
    if status != "ready":
        return {**base, "status": status, "items": [{"key": k, "label": LABEL[k], "today": v, "median": None, "pct": None,
                                                         "flag": "unknown", "ref_only": k in REF_ONLY} for k, v in today.items()]}
    past = [day_values(db, pd, off, cutoff, now) for pd in days]
    return {**base, "status": "ready", "items": [_flag(k, today[k], [p[k] for p in past]) for k in today]}


def alerts(db, closed: Date, off: float, now: datetime) -> List[tuple]:
    """Gentle notifications only when the same signal is high on 2 consecutive closed care days (circling: never)."""
    a, b = summary(db, closed.isoformat(), off, now), summary(db, (closed - timedelta(days=1)).isoformat(), off, now)
    if a["status"] != "ready" or b["status"] != "ready" or a["cutoff_h"] < 24:
        return []
    prev = {i["key"]: i["flag"] for i in b["items"]}
    out = []
    for i in a["items"]:
        if i["ref_only"] or i["flag"] != "high" or prev.get(i["key"]) != "high":
            continue
        if i["key"] == "wheel_sec":
            out.append((f"behavior:wheel:{closed}", "behavior", "info", "이틀 연속 쳇바퀴 구역 체류가 평소보다 길어요",
                        f"어제 쳇바퀴 구역 체류 {i['today'] / 60:.0f}분(평소 {i['median'] / 60:.0f}분). 구역 방문은 실제 쳇바퀴 달리기를 뜻하지 않아요. "
                        "케이지 크기·은신처·놀이감 같은 환경을 한번 살펴봐 주세요."))
        else:
            out.append((f"behavior:pace:{closed}", "behavior", "warn", "이틀 연속 같은 길을 오가는 모습이 자주 보여요",
                        f"어제 같은 길 왕복 {i['today']:.0f}번(평소 {i['median']:.0f}번). 영상으로 실제 모습을 확인해 보고, "
                        "케이지 크기·베딩 깊이·놀이감 같은 환경을 한번 살펴봐 주세요."))
    return out
