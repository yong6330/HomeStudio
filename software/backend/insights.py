"""Baseline change analysis and in-app notifications (computed on demand; no scheduler, no external services).

Rules follow docs/01_product/ACTIVITY_HEALTH_GUIDELINES.md:
- baseline = the latest 7 *valid* care days (data coverage >= 90% of minutes with a healthy frame), looked up to 28 days back;
  fewer -> status 'learning' with progress. Today is compared at the same elapsed time of the care day.
- robust stats: median and MAD; a change is flagged only if |robust z| >= 2.5 AND |change| >= 30%,
  today's coverage >= 90% and >= 4 h of the care day elapsed (minimum duration). Wording is observational, never diagnostic.
"""
import json
import logging
import statistics
from datetime import date as Date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from .db import Database

KST = timezone(timedelta(hours=9))
NEED_DAYS, LOOKBACK_DAYS, MIN_COVERAGE = 7, 28, 0.90
Z, PCT, MIN_ELAPSED_H, SHIFT_H = 2.5, 30, 4.0, 3.0
FLOOR = {"active_sec": 120.0, "distance_px": 200.0, "session_count": 1.0}
OFFLINE_MIN, STORAGE_RATIO = 10, 0.90
INACTIVE_FLOOR_H, INACTIVE_X, INACTIVE_MAD = 3.0, 1.5, 3.0
DETECTOR_ALGORITHM_VERSION = "roi-normalization-v4-active-span"
# Meaning and units of the values compared by the health baseline. Detector code
# and zone geometry can change without changing these stored measurements.
OBSERVATION_MEASUREMENT_SPEC_VERSION = "activity-seconds-counts-distance-px-160x90-v1"
LEGACY_SIGNATURE_MEASUREMENT_SPECS = {
    "roi-normalization-v4-active-span": "activity-seconds-counts-distance-px-160x90-v1",
}
log = logging.getLogger("homestudio.notify")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _parse(v: str) -> datetime:
    v = v.replace(" ", "T").replace("Z", "+00:00")
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def mark_online(db: Database, start: datetime, end: datetime) -> None:
    """Record healthy minutes in [start, end) (the service does this per heartbeat; used for seeding/tests)."""
    t, rows = start, []
    while t < end:
        rows.append((_utc(t),))
        t += timedelta(minutes=1)
    with db._get_connection() as c:
        c.executemany("INSERT OR IGNORE INTO online_minutes VALUES (?)", rows)


def coverage(db: Database, start: datetime, end: datetime) -> float:
    mins = (end - start).total_seconds() / 60
    if mins <= 0:
        return 0.0
    with db._get_connection() as c:
        n = c.execute("SELECT COUNT(*) FROM online_minutes WHERE minute >= ? AND minute < ?", (_utc(start), _utc(end))).fetchone()[0]
    return min(1.0, n / mins)


def _start(day: Date, off: float) -> datetime:
    return datetime.combine(day, time(), KST) + timedelta(hours=off)


def _space_id() -> int:
    from .homespace import current_space
    sid = current_space.get()
    return 1 if sid is None else sid


def observation_epoch(db: Database, off: float, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Persist the origin of observations that share the same measurement contract."""
    with db._get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        return _observation_epoch(c, _space_id(), off, now)


def _normalize_legacy_signature(signature: str) -> Optional[str]:
    """Translate only observed detector signatures with the unchanged metric contract."""
    try:
        value = json.loads(signature)
        if (not isinstance(value, list) or len(value) != 4 or
                value[0] not in LEGACY_SIGNATURE_MEASUREMENT_SPECS or
                not isinstance(value[1], (int, float)) or not isinstance(value[2], list) or
                not isinstance(value[3], list)):
            return None
        targets = []
        for target in value[2]:
            if not isinstance(target, list) or len(target) not in (2, 3):
                return None
            target_id, care_start = target[0], target[-1]
            if not isinstance(target_id, str) or not isinstance(care_start, str):
                return None
            targets.append([target_id, care_start])
        normalized = [LEGACY_SIGNATURE_MEASUREMENT_SPECS[value[0]], float(value[1]), targets]
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _observation_epoch(c, sid: int, off: Optional[float] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Also called inside configuration-write transactions after the edit."""
    since = (now or datetime.now(KST)).astimezone(timezone.utc).isoformat()
    targets = [tuple(r) for r in c.execute(
        "SELECT care_target_id, care_day_start_local FROM care_targets WHERE homespace_id=? ORDER BY care_target_id", (sid,))]
    if off is None:
        h, m = (targets[0][1] if targets else "00:00").split(":")
        off = int(h) + int(m) / 60
    signature = json.dumps([OBSERVATION_MEASUREMENT_SPEC_VERSION, float(off), targets], ensure_ascii=False, separators=(",", ":"))
    row = c.execute("SELECT * FROM baseline_revisions WHERE homespace_id=?", (sid,)).fetchone()
    if row is None:
        legacy = c.execute("SELECT 1 FROM events WHERE homespace_id=? LIMIT 1", (sid,)).fetchone() is not None
        legacy = legacy or c.execute("SELECT 1 FROM online_minutes WHERE minute < ? LIMIT 1", (_utc(_parse(since)),)).fetchone() is not None
        c.execute("INSERT INTO baseline_revisions VALUES (?, ?, ?, 1, ?)", (sid, signature, since, int(legacy)))
    elif row["signature"] != signature:
        if _normalize_legacy_signature(row["signature"]) == signature:
            c.execute("UPDATE baseline_revisions SET signature=? WHERE homespace_id=?", (signature, sid))
        else:
            c.execute("UPDATE baseline_revisions SET signature=?, since=?, revision=revision+1, rebuilding=1 WHERE homespace_id=?",
                      (signature, since, sid))
    row = c.execute("SELECT * FROM baseline_revisions WHERE homespace_id=?", (sid,)).fetchone()
    return dict(row)


def comparison_status(epoch: Dict[str, Any], days: int, cov: float, cutoff: float) -> str:
    if days < NEED_DAYS:
        return "rebuilding" if epoch["rebuilding"] else "learning"
    if cov < MIN_COVERAGE:
        return "low_coverage"
    return "early" if cutoff < MIN_ELAPSED_H else "ready"


_DAY_CACHE: Dict[tuple, tuple] = {}


def _day_rows(db: Database, day: Date, off: float, now: Optional[datetime]):
    from . import api
    from .homespace import current_space
    key = (str(db.db_path), _space_id(), db.event_revision(), day, off)
    if key in _DAY_CACHE:
        return _DAY_CACHE[key]
    token = current_space.set(_space_id())
    try:
        rows = ([{k: e[k] for k in ("started_at", "duration_sec", "distance_px")} for e in api.events_for(db, day.isoformat(), off)],
                api.sessions_for(db, day.isoformat(), off))
    finally:
        current_space.reset(token)
    if _start(day, off) + timedelta(hours=24) <= (now or datetime.now(KST)):  # only the open day is recomputed
        if len(_DAY_CACHE) > 400:
            _DAY_CACHE.clear()
        _DAY_CACHE[key] = rows
    return rows


def day_metrics(db: Database, day: Date, off: float, cutoff_h: float, now: Optional[datetime] = None) -> Dict[str, Any]:
    from .api import _ts
    s = _start(day, off)
    end = s + timedelta(hours=cutoff_h)
    evs_all, ses_all = _day_rows(db, day, off, now)
    evs = [e for e in evs_all if _ts(e["started_at"]) < end]
    ses = [x for x in ses_all if _ts(x["started_at"]) < end]
    act = sum(e["duration_sec"] for e in evs)
    center = sum(((_ts(e["started_at"]) - s).total_seconds() / 3600) * e["duration_sec"] for e in evs) / act if act else None
    return {"active_sec": round(act, 2), "distance_px": round(sum(e["distance_px"] or 0 for e in evs), 2),
            "session_count": len(ses), "center_h": round(center, 2) if center is not None else None}


def valid_days(db: Database, day: Date, off: float, now: Optional[datetime] = None) -> List[Date]:
    """Latest covered full care days entirely inside the current observation epoch."""
    now = now or datetime.now(KST)
    since = _parse(observation_epoch(db, off, now)["since"])
    out = []
    for k in range(1, LOOKBACK_DAYS + 1):
        pd = day - timedelta(days=k)
        ps = _start(pd, off)
        if ps >= since and ps + timedelta(hours=24) <= now and coverage(db, ps, ps + timedelta(hours=24)) >= MIN_COVERAGE:
            out.append(pd)
            if len(out) == NEED_DAYS:
                break
    return out


def _spans(db: Database, now: Optional[datetime] = None):
    lo = _utc((now or datetime.now(KST)) - timedelta(days=LOOKBACK_DAYS + 2))  # baseline window only, not all history
    with db._get_connection() as c:
        rows = c.execute("SELECT started_at, ended_at FROM events WHERE started_at >= ? AND homespace_id=?", (lo, _space_id())).fetchall()
    return sorted((_parse(r[0]), _parse(r[1])) for r in rows)


def inactivity_threshold(db: Database, day: Date, off: float, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Typical longest no-motion gap per valid baseline day (gap counted on the day its next event starts);
    threshold = max(1.5 x median, median + 3 x scaled MAD, 3 h). None until the baseline is ready."""
    days = valid_days(db, day, off, now)
    if len(days) < NEED_DAYS:
        return None
    spans, longest = _spans(db, now), []
    for d in days:
        s = _start(d, off)
        gaps = [(b[0] - a[1]).total_seconds() / 3600 for a, b in zip(spans, spans[1:]) if s <= b[0] < s + timedelta(hours=24)]
        if gaps:
            longest.append(max(gaps))
    if len(longest) < NEED_DAYS // 2 + 1:
        return None
    med = statistics.median(longest)
    mad = 1.4826 * statistics.median([abs(x - med) for x in longest])
    return {"median_longest_h": round(med, 2), "threshold_h": round(max(INACTIVE_X * med, med + INACTIVE_MAD * mad, INACTIVE_FLOOR_H), 2),
            "days": len(longest)}


def _stat(key: str, today: float, past: List[float], judge: bool) -> Dict[str, Any]:
    med = statistics.median(past) if past else None
    out = {"today": today, "median": med, "pct": None, "z": None, "flag": "unknown"}
    if med is None:
        return out
    mad = statistics.median([abs(x - med) for x in past])
    scale = max(1.4826 * mad, 0.15 * med, FLOOR[key])
    out["z"] = round((today - med) / scale, 2)
    out["pct"] = round((today - med) / med * 100) if med else None
    if judge:
        big = out["pct"] is not None and abs(out["pct"]) >= PCT
        out["flag"] = "low" if out["z"] <= -Z and big else "high" if out["z"] >= Z and big else "usual"
    return out


def baseline(db: Database, d: Optional[str], off: float, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(KST)
    day = Date.fromisoformat(d) if d else (now.astimezone(KST) - timedelta(hours=off)).date()
    s = _start(day, off)
    cutoff = max(0.0, min(24.0, (now - s).total_seconds() / 3600))
    epoch = observation_epoch(db, off, now)
    past = []
    for pd in valid_days(db, day, off, now):
        m = day_metrics(db, pd, off, cutoff, now)
        m["center_full"] = day_metrics(db, pd, off, 24, now)["center_h"]
        past.append(m)
    today = day_metrics(db, day, off, cutoff, now)
    cov = coverage(db, s, s + timedelta(hours=cutoff)) if cutoff else 0.0
    status = comparison_status(epoch, len(past), cov, cutoff)
    judge = status == "ready"
    metrics = {k: _stat(k, today[k], [p[k] for p in past], judge) for k in ("active_sec", "distance_px", "session_count")}
    centers = [p["center_full"] for p in past if p["center_full"] is not None]
    usual = statistics.median(centers) if centers else None
    shift = round(today["center_h"] - usual, 2) if usual is not None and today["center_h"] is not None else None
    pflag = "unknown"
    if judge and cutoff >= 24 and shift is not None and today["active_sec"] >= 0.3 * (metrics["active_sec"]["median"] or 0):
        pflag = "later" if shift >= SHIFT_H else "earlier" if shift <= -SHIFT_H else "usual"
    n, covp = len(past), round(cov * 100)
    period = f"지난 {n}일의 같은 시간대" + ("" if cutoff >= 24 else f"(돌봄 하루 {cutoff:g}시간 경과 기준)")
    tail = f" 카메라 수집률은 {covp}%였지만, 은신처 안 활동은 보이지 않을 수 있어요. 먹이·물·주변 환경과 실제 모습을 함께 확인해 주세요."
    signals = []
    f = metrics["active_sec"]["flag"]
    if f in ("low", "high"):
        signals.append({"kind": f"active_{f}", "text": f"{period}보다 활동 시간이 {'적게' if f == 'low' else '많이'} 관찰됐어요." + tail})
    if pflag in ("later", "earlier"):
        signals.append({"kind": f"hours_{pflag}", "text": f"지난 {n}일보다 활동 시간대가 약 {abs(shift):.0f}시간 {'늦어' if pflag == 'later' else '빨라'}졌어요." + tail})
    return {"date": day.isoformat(), "status": status, "valid_days": n, "need_days": NEED_DAYS, "cutoff_h": round(cutoff, 2),
            "coverage": round(cov, 3), "revision": epoch["revision"], "since": epoch["since"], "metrics": metrics,
            "profile": {"today_center_h": today["center_h"], "usual_center_h": usual, "shift_h": shift, "flag": pflag},
            "signals": signals}


# ---------------- notifications ----------------
class InAppChannel:
    """In-app delivery = the notifications table itself. Web push / email channels can implement the same send()."""
    def send(self, n: Dict[str, Any]) -> None:
        log.info("notification %s: %s", n["kind"], n["title"])


def _init(db: Database) -> None:
    with db._get_connection() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, level TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, silent INTEGER NOT NULL DEFAULT 0, read_at TEXT);
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS user_app_settings (user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(user_id,key));
        CREATE TABLE IF NOT EXISTS user_notification_state (user_id INTEGER NOT NULL, notification_id INTEGER NOT NULL,
            silent INTEGER NOT NULL DEFAULT 0, read_at TEXT, PRIMARY KEY(user_id,notification_id));""")
        columns = {r[1] for r in c.execute("PRAGMA table_info(notifications)")}
        if "homespace_id" not in columns:
            c.execute("ALTER TABLE notifications ADD COLUMN homespace_id INTEGER NOT NULL DEFAULT 1")


def _space_id() -> int:
    from .homespace import current_space
    sid = current_space.get()
    return 1 if sid is None else int(sid)


def _users_in_space(db: Database, sid: int, user_id: Optional[int] = None) -> List[int]:
    with db._get_connection() as c:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='homespace_members'").fetchone()
        if exists:
            rows = c.execute("SELECT user_id FROM homespace_members WHERE homespace_id=?", (sid,)).fetchall()
            if rows:
                return [int(r[0]) for r in rows]
    return [int(user_id)] if user_id is not None else []


def _personal_silent(db: Database, user_id: int, now: datetime, level: str) -> int:
    return int(level != "alert" and in_quiet(db, now, user_id=user_id))


def _setting(db: Database, key: str):
    with db._get_connection() as c:
        r = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else None


def _put(db: Database, key: str, value) -> None:
    with db._get_connection() as c:
        c.execute("INSERT OR REPLACE INTO app_settings VALUES (?, ?)", (key, json.dumps(value)))


def get_quiet(db: Database, user_id: Optional[int] = None) -> Dict[str, Any]:
    _init(db)
    if user_id is not None:
        with db._get_connection() as c:
            row = c.execute("SELECT value FROM user_app_settings WHERE user_id=? AND key='quiet'", (user_id,)).fetchone()
        if row:
            return json.loads(row[0])
        return {"enabled": True, "start": "23:00", "end": "07:00"}
    return _setting(db, "quiet") or {"enabled": True, "start": "23:00", "end": "07:00"}  # Stitch default


def set_quiet(db: Database, enabled: bool, start: str = "23:00", end: str = "07:00", user_id: Optional[int] = None) -> None:
    _init(db)
    value = json.dumps({"enabled": bool(enabled), "start": start, "end": end})
    if user_id is None:
        _put(db, "quiet", json.loads(value))
    else:
        with db._get_connection() as c:
            c.execute("INSERT OR REPLACE INTO user_app_settings (user_id,key,value) VALUES (?, 'quiet', ?)", (user_id, value))


def in_quiet(db: Database, now: datetime, user_id: Optional[int] = None) -> bool:
    q = get_quiet(db, user_id=user_id)
    if not q["enabled"]:
        return False
    t = now.astimezone(KST).strftime("%H:%M")
    return q["start"] <= t or t < q["end"] if q["start"] > q["end"] else q["start"] <= t < q["end"]


def check_notifications(db: Database, now: Optional[datetime] = None, max_storage_bytes: int = 15 * 1024**3,
                        channels: Optional[list] = None, off: Optional[float] = None, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Evaluate rules, insert new (deduplicated by key) notifications and deliver them. Returns the new ones."""
    from .api import care_offset
    _init(db)
    now = now or datetime.now(KST)
    off = care_offset(db) if off is None else off
    channels = [InAppChannel()] if channels is None else channels
    found = []
    with db._get_connection() as c:
        cam = c.execute("SELECT status, last_seen_at FROM sensors WHERE sensor_id='camera-primary'").fetchone()
        last_ok = c.execute("SELECT MAX(minute) FROM online_minutes WHERE minute <= ?", (_utc(now),)).fetchone()[0]
    status, seen = (cam["status"], _parse(cam["last_seen_at"])) if cam and cam["last_seen_at"] else ("unknown", None)
    # camera offline / dark for more than OFFLINE_MIN minutes
    if status == "dark":
        since = _parse(last_ok + ":00+00:00") + timedelta(minutes=1) if last_ok else seen
        if since and now - since >= timedelta(minutes=OFFLINE_MIN):
            found.append((f"camera:{_utc(since)}", "camera", "alert", f"카메라 화면이 {OFFLINE_MIN}분 넘게 어두워요",
                          f"{since.astimezone(KST):%H:%M}부터 화면이 어두워 활동을 기록하지 못하고 있어요. 조명·렌즈 가림을 확인해 주세요."))
    elif status != "privacy" and seen and now - seen >= timedelta(minutes=OFFLINE_MIN):
        found.append((f"camera:{_utc(seen)}", "camera", "alert", f"카메라 신호가 {OFFLINE_MIN}분 넘게 없어요",
                      f"마지막 신호는 {seen.astimezone(KST):%H:%M}이에요. 이 시간 동안은 활동이 없었던 것이 아니라 기록되지 않았어요. 카메라 전원·네트워크와 HomeStudio 서비스를 확인해 주세요."))
    # privacy mode changes (first observation only records the state)
    if cam:
        sid = _space_id()
        cur, prev = status == "privacy", _setting(db, f"space:{sid}:notif_privacy")
        if prev is not None and prev != cur:
            found.append((f"privacy:{_utc(now)}:{int(cur)}", "privacy", "info", f"프라이버시 모드가 {'켜졌어요' if cur else '꺼졌어요'}",
                          "렌즈가 수납되고 감지·저장이 멈췄어요." if cur else "렌즈가 나오고 감지·저장이 다시 시작돼요."))
        _put(db, f"space:{sid}:notif_privacy", cur)
    # end-of-day verdict: the last closed care day vs the 7 valid baseline days (whole-day totals)
    closed = (now.astimezone(KST) - timedelta(hours=off)).date() - timedelta(days=1)
    b = baseline(db, closed.isoformat(), off, now)
    if b["status"] == "ready" and b["cutoff_h"] >= 24:
        names = {"active_sec": "활동 시간", "distance_px": "이동 거리", "session_count": "활동 횟수"}
        fmt = {"active_sec": lambda v: f"{v / 60:.0f}분", "distance_px": lambda v: f"{v:,.0f}px", "session_count": lambda v: f"{v:.0f}회"}
        low = [k for k, m in b["metrics"].items() if m["flag"] == "low"]
        high = [k for k, m in b["metrics"].items() if m["flag"] == "high"]
        if low or high:
            lvl, word, keys = ("alert", "적게", low) if low else ("info", "많이", high)
            detail = ", ".join(f"{names[k]} {fmt[k](b['metrics'][k]['today'])}(평소 {fmt[k](b['metrics'][k]['median'])}, {b['metrics'][k]['pct']:+d}%)" for k in keys)
            s0 = _start(closed, off)
            found.append((f"verdict:{closed}", "verdict", lvl, f"지난 돌봄 하루 활동이 평소보다 {word} 관찰됐어요",
                          f"{s0:%m.%d %H:%M}부터 24시간, 지난 {b['valid_days']}일과 비교: {detail}. 카메라 수집률 {round(b['coverage'] * 100)}%. "
                          "은신처 안 활동은 보이지 않을 수 있어요." + (" 먹이·물·주변 환경과 실제 모습을 함께 확인해 주세요." if low else "")))
    # 행동 건강: gentle hints after 2 consecutive high days (circling is reference-only)
    from . import behavior
    found.extend(behavior.alerts(db, closed, off, now))
    # long inactivity: current no-motion stretch longer than the usual longest daily gap (time-of-day independent)
    if status == "online" and seen and now - seen < timedelta(minutes=OFFLINE_MIN):
        ends = [e for _, e in _spans(db, now) if e <= now]
        last = max(ends) if ends else None
        thr = inactivity_threshold(db, (now.astimezone(KST) - timedelta(hours=off)).date(), off, now) if last else None
        if thr and (now - last).total_seconds() / 3600 >= thr["threshold_h"] and coverage(db, last, now) >= MIN_COVERAGE:
            hrs = (now - last).total_seconds() / 3600
            found.append((f"inactive:{_utc(last)}", "inactivity", "alert", "평소보다 오래 움직임이 보이지 않아요",
                          f"마지막 움직임은 {last.astimezone(KST):%m.%d %H:%M}(약 {hrs:.0f}시간 전)이에요. 지난 {thr['days']}일 중 하루의 가장 긴 무움직임은 보통 약 {thr['median_longest_h']:.0f}시간이었어요. "
                          "그동안 카메라는 정상이었지만 은신처 안 휴식은 보이지 않을 수 있어요. 실제 모습과 먹이·물을 확인해 주세요."))
    # storage near cap
    used = db.get_total_media_bytes()
    if max_storage_bytes and used >= STORAGE_RATIO * max_storage_bytes:
        found.append((f"storage:{now.astimezone(KST):%Y-%m-%d}", "storage", "warn", "저장 공간이 거의 찼어요",
                      f"영상이 상한의 {used / max_storage_bytes * 100:.0f}%를 쓰고 있어요. 오래된 클립부터 자동 정리되며, 보관할 클립은 즐겨찾기로 보호해 주세요."))
    sid, new = _space_id(), []
    for key, kind, level, title, body in found:
        space_key = f"space:{sid}:{key}"
        users = _users_in_space(db, sid, user_id)
        quiet_by_user = {uid: _personal_silent(db, uid, now, level) for uid in users}
        with db._get_connection() as c:
            cur = c.execute("INSERT OR IGNORE INTO notifications (key, kind, level, title, body, created_at, silent, homespace_id) VALUES (?,?,?,?,?,?,?,?)",
                            (space_key, kind, level, title, body, now.astimezone(timezone.utc).isoformat(), 0, sid))
            if not cur.rowcount:
                continue
            nid = cur.lastrowid
            for uid in users:
                c.execute("INSERT OR IGNORE INTO user_notification_state (user_id, notification_id, silent) VALUES (?,?,?)",
                          (uid, nid, quiet_by_user[uid]))
        silent = bool(users) and all(quiet_by_user.values())
        n = {"key": key, "kind": kind, "level": level, "title": title, "body": body, "silent": int(silent)}
        new.append(n)
        if not silent:
            for ch in channels:
                ch.send(n)
    return new


def add_notification(db: Database, key: str, kind: str, level: str, title: str, body: str,
                     now: Optional[datetime] = None, channels: Optional[list] = None) -> bool:
    """Insert one notification (deduplicated by key) outside the rule loop, e.g. from the vision service."""
    _init(db)
    now = now or datetime.now(KST)
    sid = _space_id()
    space_key = f"space:{sid}:{key}"
    users = _users_in_space(db, sid)
    quiet_by_user = {uid: _personal_silent(db, uid, now, level) for uid in users}
    with db._get_connection() as c:
        cur = c.execute("INSERT OR IGNORE INTO notifications (key, kind, level, title, body, created_at, silent, homespace_id) VALUES (?,?,?,?,?,?,?,?)",
                        (space_key, kind, level, title, body, now.astimezone(timezone.utc).isoformat(), 0, sid))
        new = bool(cur.rowcount)
        nid = cur.lastrowid if new else None
        if new:
            for uid in users:
                c.execute("INSERT OR IGNORE INTO user_notification_state (user_id, notification_id, silent) VALUES (?,?,?)",
                          (uid, nid, quiet_by_user[uid]))
    silent = bool(users) and all(quiet_by_user.values())
    if new and not silent:
        for ch in channels or [InAppChannel()]:
            ch.send({"key": key, "kind": kind, "level": level, "title": title, "body": body, "silent": int(silent)})
    return new


def list_notifications(db: Database, limit: int = 50, user_id: Optional[int] = None) -> Dict[str, Any]:
    _init(db)
    sid = _space_id()
    with db._get_connection() as c:
        if user_id is None:
            rows = [dict(r) for r in c.execute("SELECT id, kind, level, title, body, created_at, silent, read_at FROM notifications WHERE homespace_id=? ORDER BY id DESC LIMIT ?", (sid, limit))]
            unread = c.execute("SELECT COUNT(*) FROM notifications WHERE homespace_id=? AND read_at IS NULL AND silent=0", (sid,)).fetchone()[0]
        else:
            rows = [dict(r) for r in c.execute("""SELECT n.id,n.kind,n.level,n.title,n.body,n.created_at,
                COALESCE(s.silent,n.silent,0) AS silent,CASE WHEN s.user_id IS NOT NULL THEN s.read_at ELSE n.read_at END AS read_at
                FROM notifications n LEFT JOIN user_notification_state s ON s.notification_id=n.id AND s.user_id=?
                WHERE n.homespace_id=? ORDER BY n.id DESC LIMIT ?""", (user_id, sid, limit))]
            unread = c.execute("""SELECT COUNT(*) FROM notifications n LEFT JOIN user_notification_state s
                ON s.notification_id=n.id AND s.user_id=? WHERE n.homespace_id=?
                AND (CASE WHEN s.user_id IS NOT NULL THEN s.read_at ELSE n.read_at END) IS NULL
                AND COALESCE(s.silent,n.silent,0)=0""", (user_id, sid)).fetchone()[0]
    return {"items": rows, "unread": unread}


def mark_read(db: Database, user_id: Optional[int] = None) -> None:
    _init(db)
    sid, now = _space_id(), datetime.now(timezone.utc).isoformat()
    with db._get_connection() as c:
        if user_id is None:
            c.execute("UPDATE notifications SET read_at=? WHERE homespace_id=? AND read_at IS NULL", (now, sid))
        else:
            rows = c.execute("SELECT id,read_at FROM notifications WHERE homespace_id=?", (sid,)).fetchall()
            for row in rows:
                c.execute("INSERT INTO user_notification_state (user_id,notification_id,silent,read_at) VALUES (?,?,0,?) ON CONFLICT(user_id,notification_id) DO UPDATE SET read_at=excluded.read_at",
                          (user_id, row[0], now if row[1] is None else row[1]))
