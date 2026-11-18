"""Zones (P4 prep): named polygons in normalized [0,1] image coordinates, stored in app_settings 'zones'.
Analytics are plain point-in-polygon over the existing event tracks (t, x, y in motion-frame px) — stdlib only;
roboflow/supervision would pull scipy/matplotlib onto the 4GB PC for the same ray-casting test.
visits = outside->inside transitions (a track starting inside counts once); dwell = time of track segments that start inside.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

KINDS = {"cage": "케이지", "wheel": "쳇바퀴", "food": "먹이 그릇", "water": "물병", "hide": "은신처", "toilet": "화장실", "custom": "직접 입력"}
MAX_ZONES, MAX_POINTS = 12, 32


def inside(x: float, y: float, pts: List[List[float]]) -> bool:
    """Ray casting."""
    hit = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def validate(zs: Any) -> List[Dict[str, Any]]:
    if not isinstance(zs, list) or len(zs) > MAX_ZONES:
        raise ValueError("zones must be a list")
    out, ids = [], set()
    for zn in zs:
        zid, name, kind, pts = str(zn.get("id", "")), str(zn.get("name", "")).strip(), zn.get("kind"), zn.get("points")
        if not zid or zid in ids or not 1 <= len(name) <= 20 or kind not in KINDS:
            raise ValueError("bad zone id/name/kind")
        if not isinstance(pts, list) or not 3 <= len(pts) <= MAX_POINTS or \
                not all(isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in p) for p in pts):
            raise ValueError("points: 3..32 normalized [x, y]")
        if kind == "cage" and any(o["kind"] == "cage" for o in out):
            raise ValueError("only one cage zone")
        ids.add(zid)
        out.append({"id": zid[:32], "name": name, "kind": kind, "points": [[round(float(v), 4) for v in p] for p in pts]})
    return out


def _space(db, space_id: Optional[int] = None) -> int:
    from .homespace import current_space, ensure
    ensure(db, backfill=False)
    if space_id is not None:
        return space_id
    sid = current_space.get()
    return 1 if sid is None else sid


def load(db, space_id: Optional[int] = None) -> List[Dict[str, Any]]:
    from .homespace import get_setting
    sid = _space(db, space_id)
    raw = get_setting(db, sid, "zones")
    if raw is None and sid == 1:
        with db._get_connection() as c:
            c.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            r = c.execute("SELECT value FROM app_settings WHERE key='zones'").fetchone()
        raw = r[0] if r else None
    return json.loads(raw) if raw else []


def save(db, zs, space_id: Optional[int] = None) -> List[Dict[str, Any]]:
    from .insights import _observation_epoch
    zs = validate(zs)
    sid = _space(db, space_id)
    raw = json.dumps(zs, ensure_ascii=False)
    with db._get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR REPLACE INTO space_settings VALUES (?, 'zones', ?)", (sid, raw))
        if sid == 1:  # vision and older readers still see the household that owns this camera
            c.execute("INSERT OR REPLACE INTO app_settings VALUES ('zones', ?)", (raw,))
        _observation_epoch(c, sid)
    return zs


def track_stats(track, zs, w: float, h: float) -> Dict[str, Dict[str, float]]:
    out = {}
    for zn in zs:
        if zn["kind"] == "cage":  # motion mask, not an activity zone
            continue
        flags = [inside(p[1] / w, p[2] / h, zn["points"]) for p in track]
        visits = sum(1 for i, f in enumerate(flags) if f and (i == 0 or not flags[i - 1]))
        dwell = sum(b[0] - a[0] for a, b, f in zip(track, track[1:], flags) if f)
        out[zn["id"]] = {"visits": visits, "dwell_sec": round(dwell, 2)}
    return out


def event_zones(e: Dict[str, Any], zs, size: Tuple[float, float]) -> List[str]:
    tr = json.loads(e.get("track_json") or "[]")
    return [k for k, v in track_stats(tr, zs, *size).items() if v["visits"]]


def day_stats(db, d: Optional[str], off: float, size: Tuple[float, float]) -> Dict[str, Any]:
    from .api import events_for, _day
    zs = load(db)
    tot = {zn["id"]: {**zn, "visits": 0, "dwell_sec": 0.0, "events": 0} for zn in zs if zn["kind"] != "cage"}
    for e in events_for(db, d, off):
        for k, v in track_stats(json.loads(e.get("track_json") or "[]"), zs, *size).items():
            tot[k]["visits"] += v["visits"]
            tot[k]["dwell_sec"] = round(tot[k]["dwell_sec"] + v["dwell_sec"], 2)
            tot[k]["events"] += 1 if v["visits"] else 0
    return {"date": _day(d).isoformat(), "zones": list(tot.values())}
