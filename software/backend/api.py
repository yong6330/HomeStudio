"""Aggregation API (P3-01) + accounts (P3-07, auth.py). Bind to 127.0.0.1 or the Tailscale IP only, never 0.0.0.0.

Run: python -m software.backend.api   (HOMESTUDIO_API_HOST default 127.0.0.1, HOMESTUDIO_API_PORT default 8080)
"""
import json
import logging
import re
import os
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import insights
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from . import zones as zmod
from . import behavior
from . import reports, sensors as sensor_registry
from .config import PipelineConfig
from .db import Database

KST = timezone(timedelta(hours=9))
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
VISION_ACTIVITY_KEY = "vision_activity_v1"
VISION_ACTIVITY_STALE_SEC = 45


def _ts(v: str) -> datetime:
    return datetime.fromisoformat(v).astimezone(KST)


def _day(d: Optional[str]) -> Date:
    return Date.fromisoformat(d) if d else datetime.now(KST).date()


def vision_activity_status(db: Database, space_id: Optional[int], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return fresh observed detector state, never infer it from completed events."""
    unknown = {"activity_state": "unknown", "activity_seen_at": None}
    if space_id != 1:  # the single installed camera/pipeline currently belongs to homespace 1
        return unknown
    now = now or datetime.now(timezone.utc)
    with db._get_connection() as conn:
        setting = conn.execute("SELECT value FROM space_settings WHERE homespace_id=? AND key=?",
                               (space_id, VISION_ACTIVITY_KEY)).fetchone()
        camera = conn.execute("SELECT status,last_seen_at FROM sensors WHERE sensor_id='camera-primary'").fetchone()
    if not setting or not camera:
        return unknown
    try:
        payload = json.loads(setting[0])
        if not isinstance(payload, dict):
            return unknown
        state = payload.get("state")
        seen = datetime.fromisoformat(payload["activity_seen_at"]) if payload.get("activity_seen_at") else None
        if seen and seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        camera_seen = datetime.fromisoformat(camera["last_seen_at"]) if camera["last_seen_at"] else None
        if camera_seen and camera_seen.tzinfo is None:
            camera_seen = camera_seen.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return unknown
    seen_iso = seen.astimezone(timezone.utc).isoformat() if seen else None
    camera_age = (now.astimezone(timezone.utc) - camera_seen.astimezone(timezone.utc)).total_seconds() if camera_seen else None
    seen_age = (now.astimezone(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds() if seen else None
    healthy = camera["status"] == "online" and camera_age is not None and 0 <= camera_age < VISION_ACTIVITY_STALE_SEC
    fresh = seen_age is not None and 0 <= seen_age < VISION_ACTIVITY_STALE_SEC
    if healthy and fresh and state in ("active", "idle"):
        return {"activity_state": state, "activity_seen_at": seen_iso}
    return {"activity_state": "unknown", "activity_seen_at": seen_iso}


def _in_day(v: str, day: Date, off: float = 0) -> bool:
    return (_ts(v) - timedelta(hours=off)).date() == day


def care_offset(db: Database) -> float:
    """Care-day start (e.g. '12:00') as hours; a care day D runs D 12:00 -> D+1 12:00 KST."""
    from .homespace import current_space
    sid = current_space.get()
    with db._get_connection() as conn:
        if sid is not None and sid > 0:
            row = conn.execute("SELECT care_day_start_local FROM care_targets WHERE homespace_id=? LIMIT 1", (sid,)).fetchone()
        else:
            row = conn.execute("SELECT care_day_start_local FROM care_targets LIMIT 1").fetchone()
    try:
        h, m = (row[0] or "00:00").split(":")
        return int(h) + int(m) / 60
    except Exception:
        return 0.0


def _bounds(day: Date, off: float):
    """Coarse UTC string bounds of a (care) day with a 2 h margin; the exact KST filter is applied after the query."""
    s = datetime.combine(day, datetime.min.time(), KST) + timedelta(hours=off)
    f = lambda t: t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    return f(s - timedelta(hours=2)), f(s + timedelta(hours=26))


def events_for(db: Database, d: Optional[str], off: float = 0) -> List[Dict[str, Any]]:
    day = _day(d)
    lo, hi = _bounds(day, off)
    rows = db.list_events(limit=100000, start_time=lo, end_time=hi)  # one day only, not the whole history
    return sorted((r for r in rows if _in_day(r["started_at"], day, off)), key=lambda r: _ts(r["started_at"]))


def sessions_for(db: Database, d: Optional[str], off: float = 0) -> List[Dict[str, Any]]:
    day = _day(d)
    lo, hi = _bounds(day, off)
    return [s for s in db.list_sessions(start_time=lo, end_time=hi) if _in_day(s["started_at"], day, off)]


def hourly(db: Database, d: Optional[str], off: float = 0) -> List[Dict[str, Any]]:
    """24 buckets in display order; with a care-day offset the first bucket is the start hour (e.g. 12)."""
    first = int(off) % 24
    buckets = [{"hour": (first + i) % 24, "active_sec": 0.0, "distance_px": 0.0, "event_count": 0} for i in range(24)]
    for e in events_for(db, d, off):  # shortcut: event counted in its start hour (events are <= 60s)
        b = buckets[(_ts(e["started_at"]).hour - first) % 24]
        b["active_sec"] = round(b["active_sec"] + e["duration_sec"], 2)
        b["distance_px"] = round(b["distance_px"] + (e["distance_px"] or 0.0), 2)
        b["event_count"] += 1
    return buckets


def summary(db: Database, d: Optional[str], off: float = 0) -> Dict[str, Any]:
    ses = sessions_for(db, d, off)
    with db._get_connection() as conn:
        cam = conn.execute("SELECT status, last_seen_at FROM sensors WHERE sensor_id='camera-primary'").fetchone()
    return {
        "date": _day(d).isoformat(),
        "session_count": len(ses),
        "active_sec": round(sum(s["active_sec"] for s in ses), 2),
        "distance_px": round(sum(s["distance_px"] for s in ses), 2),
        "event_count": sum(s["event_count"] for s in ses),
        "camera_status": cam["status"] if cam else "unknown",
        "camera_last_seen": _ts(cam["last_seen_at"].replace(" ", "T") + ("" if "+" in cam["last_seen_at"] or "Z" in cam["last_seen_at"] else "+00:00")).isoformat() if cam else None,
    }


def compare(db: Database, d: Optional[str], off: float = 0) -> Dict[str, Any]:
    day = _day(d)
    prev = [summary(db, (day - timedelta(days=i)).isoformat(), off)["active_sec"] for i in range(1, 8)]
    today = summary(db, day.isoformat(), off)["active_sec"]
    avg = round(sum(prev) / 7, 2)
    return {"date": day.isoformat(), "today_active_sec": today, "avg7_active_sec": avg,
            "change_pct": round((today - avg) / avg * 100) if avg else None}


LEGAL_DIR = Path(__file__).resolve().parents[2] / "docs" / "legal"


def md_to_html(md: str, title: str) -> str:
    """Tiny Markdown subset (headings, lists, tables, links, paragraphs) for the legal pages; no extra deps."""
    import html
    import re
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    inline = lambda t: re.sub(r"\[([^\]]+)\]\((/[a-z]+)\)", r'<a href="\2">\1</a>', html.escape(t, quote=False))
    out, para, in_list, in_table = [], [], None, False

    def flush():
        nonlocal para, in_list, in_table
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para = []
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None
        if in_table:
            out.append("</table>")
            in_table = False

    for line in md.splitlines():
        t = line.strip()
        m = re.match(r"^(#{1,3}) (.*)", t)
        li = re.match(r"^(-|\d+\.) (.*)", t)
        if not t:
            flush()
        elif m:
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif t.startswith("|"):
            if re.match(r"^\|[-| ]+\|$", t):
                continue
            if not in_table:
                flush()
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<td>{inline(c.strip())}</td>" for c in t.strip("|").split("|")) + "</tr>")
        elif li:
            tag = "ol" if li.group(1)[0].isdigit() else "ul"
            if in_list != tag:
                flush()
                out.append(f"<{tag}>")
                in_list = tag
            out.append(f"<li>{inline(li.group(2))}</li>")
        else:
            para.append(inline(t))
    flush()
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>body{{margin:0;background:#121317;color:#e3e2e7;font:15px/1.7 Inter,system-ui,sans-serif}}main{{max-width:720px;margin:0 auto;padding:24px 20px 64px}}'
            f'a{{color:#5af0b3}}h1{{font-size:24px}}h2{{font-size:18px;margin-top:2em}}table{{border-collapse:collapse;width:100%}}td{{border:1px solid #343439;padding:6px 8px;vertical-align:top}}</style></head><body><main>'
            f'<p><a href="/#home">← HomeStudio</a></p>{"".join(out)}</main></body></html>')


def _kst(row: Dict[str, Any]) -> Dict[str, Any]:
    return {**row, "started_at": _ts(row["started_at"]).isoformat(), "ended_at": _ts(row["ended_at"]).isoformat()}


def create_app(config: Optional[PipelineConfig] = None, db: Optional[Database] = None, sender=None) -> FastAPI:
    config = config or PipelineConfig()
    db = db or Database(config.db_path)
    base = config.base_dir.resolve()
    app = FastAPI(title="HomeStudio API", docs_url=None, redoc_url=None)
    import threading
    app.state.sensor_scan_lock = threading.RLock()
    app.state.sensor_discovery_scans = {}
    auth.install(app, db, sender)

    def _file(p: Optional[str]) -> FileResponse:
        if not p:
            raise HTTPException(404)
        f = Path(p).resolve()
        if base not in f.parents or not f.is_file():  # only files under base_dir, paths come from DB not the client
            raise HTTPException(404)
        return FileResponse(f)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "time": datetime.now(KST).isoformat()}

    def recording_preview():
        from .homespace import current_space
        try:
            item = json.loads((config.data_dir / "recording_preview.json").read_text(encoding="utf-8"))
            path = Path(item["path"]).resolve()
            if item["homespace_id"] != (current_space.get() or 1) or base not in path.parents or not path.is_file():
                return None
            return item
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @app.get("/api/recording-preview")
    def get_recording_preview(request: Request):
        app.state.need(request)
        item = recording_preview()
        if item is None:
            return {"status": "missing", "url": None}
        return {"status": "ready", "url": "/media/recording-preview",
                **{k: item.get(k) for k in ("created_at", "width", "height", "fps", "duration_sec")}}

    @app.get("/media/recording-preview")
    def preview_media(request: Request):
        app.state.need(request)
        item = recording_preview()
        if item is None:
            raise HTTPException(404)
        return _file(item["path"])

    @app.get("/api/summary")
    def get_summary(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        return summary(db, date, care_offset(db) if care else 0)

    @app.get("/api/reports/daily")
    def get_daily_report(request: Request, date: Optional[str] = Query(None, pattern=DATE_RE)):
        app.state.need(request)
        now = datetime.now(KST)
        off = care_offset(db)
        if date:
            try:
                day = Date.fromisoformat(date)
            except ValueError:
                raise HTTPException(422, "invalid date")
        else:
            current_day = (now - timedelta(hours=off)).date()
            day = current_day - timedelta(days=1)
        try:
            return reports.daily_report(db, config, day, now)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/api/sensors")
    def get_sensors(request: Request):
        app.state.need(request)
        return sensor_registry.list_sensors(db)

    @app.post("/api/sensors")
    def post_sensor(body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        raise HTTPException(409, "USB discovery and a successful CSI connection test are required")

    @app.post("/api/sensors/discover")
    def discover_sensors(request: Request):
        app.state.need(request, admin=True)
        try:
            return sensor_registry.discover_usb(app, sensor_registry.current_space_id(), db)
        except (TimeoutError, RuntimeError) as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/sensors/connect")
    def connect_sensor(body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        try:
            return sensor_registry.connect_usb_candidate(app, sensor_registry.current_space_id(), body, db)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (TimeoutError, RuntimeError) as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post("/api/sensors/register")
    def register_sensor(body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        try:
            return sensor_registry.register_discovered_sensor(db, app, sensor_registry.current_space_id(), body)
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except sensor_registry.SensorAlreadyRegistered as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.patch("/api/sensors/{sensor_id}")
    def patch_sensor(sensor_id: str, body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        try:
            result = sensor_registry.update_sensor(db, sensor_id, body)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if result is None:
            raise HTTPException(404, "sensor not found")
        return result

    @app.get("/api/hourly")
    def get_hourly(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        return hourly(db, date, care_offset(db) if care else 0)

    @app.get("/api/sessions")
    def get_sessions(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        return [_kst(s) for s in sessions_for(db, date, care_offset(db) if care else 0)]

    @app.get("/api/events")
    def get_events(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        zs, size = zmod.load(db), frame_size()
        return [_kst({**{k: v for k, v in e.items() if k != "track_json"}, "zones": zmod.event_zones(e, zs, size),
                     "repeat": (lambda f: bool(f["pace"] or f["circle"]))(behavior.event_features(e))})
                for e in events_for(db, date, care_offset(db) if care else 0)]

    @app.get("/api/events/dates")
    def get_event_dates(care: bool = False):
        from .homespace import current_space
        sid = current_space.get()
        if sid is None or sid < 1:
            return {"dates": []}
        with db._get_connection() as conn:
            rows = conn.execute("SELECT started_at FROM events WHERE homespace_id=?", (sid,))
            off = care_offset(db) if care else 0
            dates = sorted({(_ts(row[0]) - timedelta(hours=off)).date().isoformat() for row in rows})
        return {"dates": dates}

    def frame_size():
        return (config.motion_downscale_width, round(config.motion_downscale_width * 9 / 16))  # track coordinate space

    @app.get("/api/zones")
    def get_zones():
        return zmod.load(db)

    @app.post("/api/zones")
    def set_zones(body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        try:
            return zmod.save(db, body.get("zones"))
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/zones/stats")
    def zone_stats(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        return zmod.day_stats(db, date, care_offset(db) if care else 0, frame_size())

    @app.get("/api/compare")
    def get_compare(date: Optional[str] = Query(None, pattern=DATE_RE), care: bool = False):
        return compare(db, date, care_offset(db) if care else 0)

    def _cam_addr():
        if os.getenv("HOMESTUDIO_CAM_IP"):
            return {"camera_ip": os.getenv("HOMESTUDIO_CAM_IP"), "camera_iface": "manual"}
        b = cl.load_binding(db) or {}
        return {"camera_ip": b.get("ip") or config.camera_ip, "camera_iface": b.get("iface") or "unbound"}

    @app.get("/api/status")
    def get_status():
        import shutil
        from . import homespace
        with db._get_connection() as conn:
            care = conn.execute("SELECT care_day_start_local FROM care_targets LIMIT 1").fetchone()
        s = summary(db, None)
        sid = homespace.current_space.get()
        activity = vision_activity_status(db, sid if sid is not None else 1)
        try:
            snapshot_seen = datetime.fromtimestamp((config.thumbnails_dir / "latest.jpg").stat().st_mtime,
                                                   timezone.utc).isoformat()
        except OSError:
            snapshot_seen = None
        return {"camera_status": s["camera_status"], "camera_last_seen": s["camera_last_seen"],
                "media_bytes": db.get_total_media_bytes(), "max_storage_bytes": config.max_storage_bytes,
                "disk_free_bytes": shutil.disk_usage(base).free, "care_day_start": care[0] if care else None,
                "stream_source": config.stream_source, "snapshot_fps": config.snapshot_fps,
                "snapshot_seen_at": snapshot_seen, **activity, "online_24h_min": _online_24h(), **_cam_addr()}

    def _online_24h():
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
        with db._get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM online_minutes WHERE minute >= ?", (since,)).fetchone()[0]

    @app.get("/api/events/{event_id}")
    def get_event(event_id: str):
        e = db.get_event(event_id)
        if not e:
            raise HTTPException(404)
        out = _kst({k: v for k, v in e.items() if k != "track_json"})
        out["track"] = json.loads(e["track_json"] or "[]")
        feat = behavior.event_features(e)
        zs, size = zmod.load(db), frame_size()
        visited = set(zmod.event_zones(e, zs, size))
        out["zone_names"] = [z["name"] for z in zs if z["id"] in visited]
        out["pace"] = bool(feat.get("pace"))
        out["circle"] = bool(feat.get("circle"))
        cp = Path(e["clip_path"]).resolve() if e.get("clip_path") else None
        op = Path(e["original_path"]).resolve() if e.get("original_path") else None
        out["original_url"] = f"/media/original/{event_id}" if op and base in op.parents and op.is_file() else None
        out["frame_size"] = [config.motion_downscale_width, round(config.motion_downscale_width * 9 / 16)]  # track coords
        out["clip_bytes"] = cp.stat().st_size if cp and base in cp.parents and cp.is_file() else None
        return out

    @app.get("/api/events/{event_id}/observations")
    def get_event_observations(event_id: str, request: Request):
        app.state.need(request)
        if not db.get_event(event_id):
            raise HTTPException(404)
        from . import observations
        return observations.for_event(db, event_id)

    app.state.camera = None  # SnapshotSource built lazily (needs HOMESTUDIO_CAM_PASSWORD); tests inject a fake

    def camera():
        if app.state.camera is None:
            from ..vision.camera_locator import make_source
            app.state.camera = make_source(config, db)
        return app.state.camera

    from ..vision import camera_locator as cl
    app.state.locator = None  # tests inject a fake; built lazily with LAPI DeviceInfo model check
    app.state.ws_discovery = cl.ws_discovery

    def locator():
        if app.state.locator is None:
            app.state.locator = cl.CameraLocator(db, cl.lapi_model(config))
        return app.state.locator

    @app.get("/api/camera/binding")
    def get_binding():
        return cl.load_binding(db) or {}

    @app.post("/api/camera/discover")
    def discover(request: Request):
        """Wizard camera list: every private /24 of the PC (wired + Wi-Fi). Credentials go only to WS-Discovery
        responders / bound MACs, one Digest try each (digest.py gate); a rejected login pauses the rest of the scan."""
        app.state.need(request, admin=True)
        from ..vision import digest
        loc, ips, out = locator(), app.state.ws_discovery(), []
        prefixes = [loc.prefix] if loc.prefix else loc.prefixes()
        for p in prefixes:
            for c in loc.discover(ips, p):
                if c["ip"] not in {o["ip"] for o in out}:
                    out.append(c)
        b = cl.load_binding(db) or {}
        labels = {m["mac"]: m["iface"] for m in b.get("macs", [])}
        for c in out:
            mac = cl.norm_mac(c["mac"]) if c.get("mac") else None
            c["mac"] = mac
            c["registered"] = bool(mac and mac in labels)
            c["iface"] = labels.get(mac) or "unknown"
        found = {c["ip"] for c in out}
        unverified = [ip for ip in ips if ip not in found and any(ip.startswith(p + ".") for p in prefixes)]
        return {"candidates": out, "prefixes": prefixes,
                "auth_error": bool(unverified) and not digest.GATE.allowed()}

    @app.post("/api/camera/bind")
    def bind(body: Dict[str, Any], request: Request):
        """Store the camera's MAC list (+ interface labels) and model, then resolve it now (read-only on the camera)."""
        app.state.need(request, admin=True)
        macs = [m for m in body.get("macs", []) if isinstance(m, dict) and re.fullmatch(r"([0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2}", str(m.get("mac", "")))]
        if not macs or not body.get("model"):
            raise HTTPException(422, "macs and model required")
        prev = cl.load_binding(db)
        if prev and prev.get("model") == body["model"] and any(cl.norm_mac(m["mac"]) in {x["mac"] for x in prev["macs"]} for m in macs):
            known = {x["mac"]: x for x in prev["macs"]}  # same camera: keep the wired/Wi-Fi labels already learned
            macs = list(known.values()) + [m for m in macs if cl.norm_mac(m["mac"]) not in known]
        cl.save_binding(db, macs, str(body["model"]), None)
        found = locator().resolve()
        if not found:
            if prev:
                cl.save_binding(db, prev["macs"], prev["model"], prev.get("ip"), prev.get("mac"), prev.get("iface"))
            else:
                with db._get_connection() as c:
                    c.execute("DELETE FROM app_settings WHERE key='camera_binding'")
            raise HTTPException(404, "camera with these MACs and model not found on the LAN")
        app.state.camera = None  # rebuild with the new binding
        idn = locator().last_ident or {}
        _set_setting("camera_info", json.dumps({"firmware": idn.get("firmware")}))
        return cl.save_binding(db, macs, str(body["model"]), found[0], found[1], found[2],
                               idn.get("serial_hash"))  # hash only, never the serial

    def _set_setting(k, v):
        with db._get_connection() as c:
            c.execute("INSERT OR REPLACE INTO app_settings VALUES (?, ?)", (k, v))

    @app.get("/api/camera/info")
    def camera_info():
        with db._get_connection() as c:
            rows = dict(c.execute("SELECT key, value FROM app_settings WHERE key IN ('camera_name','camera_info')").fetchall())
        b = cl.load_binding(db) or {}
        return {"name": rows.get("camera_name"), "model": b.get("model"), **json.loads(rows.get("camera_info") or "{}"), **_cam_addr()}

    @app.post("/api/camera/name")
    def camera_name(body: Dict[str, Any], request: Request):
        app.state.need(request, admin=True)
        name = str(body.get("name") or "").strip()
        if not 1 <= len(name) <= 20:
            raise HTTPException(422, "1-20 chars")
        _set_setting("camera_name", name)
        return {"name": name}

    @app.get("/api/camera/privacy")
    def get_privacy():
        return {"enabled": camera().fetch_privacy()}  # real LAPI state (None = unreachable)

    @app.post("/api/camera/privacy")
    def set_privacy(body: Dict[str, bool], request: Request):
        app.state.need(request, admin=True)
        if not camera().set_privacy(bool(body.get("enabled"))):
            raise HTTPException(502, "camera did not accept the change")
        logging.getLogger("homestudio.api").info("privacy set to %s by %s", body.get("enabled"), app.state.need(request)["email"])
        return {"enabled": camera().fetch_privacy()}

    @app.get("/api/behavior")
    def get_behavior(date: Optional[str] = Query(None, pattern=DATE_RE)):
        return behavior.summary(db, date, care_offset(db))

    @app.get("/api/baseline")
    def get_baseline(date: Optional[str] = Query(None, pattern=DATE_RE)):
        return insights.baseline(db, date, care_offset(db))

    @app.get("/api/notifications")
    def get_notifications(request: Request):
        user = app.state.need(request)
        insights.check_notifications(db, max_storage_bytes=config.max_storage_bytes, user_id=user["user_id"])  # rules evaluated on demand
        return insights.list_notifications(db, user_id=user["user_id"])

    @app.post("/api/notifications/read")
    def read_notifications(request: Request):
        user = app.state.need(request)
        insights.mark_read(db, user_id=user["user_id"])
        return {"ok": True}

    @app.get("/api/settings/quiet")
    def get_quiet(request: Request):
        user = app.state.need(request)
        return insights.get_quiet(db, user_id=user["user_id"])

    @app.post("/api/settings/quiet")
    def set_quiet(body: Dict[str, Any], request: Request):
        user = app.state.need(request)
        q = {**insights.get_quiet(db, user_id=user["user_id"]), **{k: body[k] for k in ("enabled", "start", "end") if k in body}}
        import re
        if not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(q[k])) for k in ("start", "end")):
            raise HTTPException(422, "HH:MM")
        insights.set_quiet(db, bool(q["enabled"]), q["start"], q["end"], user_id=user["user_id"])
        return insights.get_quiet(db, user_id=user["user_id"])

    def _unlink_media(path_str: Optional[str]) -> None:
        if not path_str:
            return
        p = Path(path_str).resolve()
        if p.name.lower() == "latest.jpg":
            return
        roots = [config.events_dir.resolve(), config.thumbnails_dir.resolve()]
        if p.is_file() and any(r == p or r in p.parents for r in roots):
            p.unlink()

    @app.delete("/api/events/{event_id}")
    def delete_event(event_id: str, request: Request):
        user = app.state.need(request)
        from . import homespace as hs
        if not hs.can_delete_events(db, user):
            raise HTTPException(403, "household member required")
        e = db.get_event(event_id)
        if not e:
            raise HTTPException(404)
        _unlink_media(e.get("original_path"))
        _unlink_media(e.get("clip_path"))
        _unlink_media(e.get("thumbnail_path"))
        if not db.delete_event(event_id):
            raise HTTPException(404)
        return {"ok": True}

    @app.post("/api/events/{event_id}/favorite")
    def favorite(event_id: str, body: Dict[str, bool]):
        if not db.set_event_protection(event_id, bool(body.get("on"))):
            raise HTTPException(404)
        return {"event_id": event_id, "favorite": bool(body.get("on"))}

    @app.get("/media/clip/{event_id}")
    def clip(event_id: str):
        e = db.get_event(event_id)
        return _file(e and e["clip_path"])

    @app.get("/media/original/{event_id}")
    def original(event_id: str):
        e = db.get_event(event_id)
        response = _file(e and e.get("original_path"))
        response.headers["Content-Disposition"] = f'attachment; filename="{Path(response.path).name}"'
        return response

    @app.get("/media/thumb/{event_id}")
    def thumb(event_id: str):
        e = db.get_event(event_id)
        return _file(e and e["thumbnail_path"])

    @app.get("/media/latest.jpg")
    def latest():
        return _file(str(config.thumbnails_dir / "latest.jpg"))

    @app.get("/terms", response_class=HTMLResponse)
    def terms():
        return md_to_html((LEGAL_DIR / "TERMS_OF_SERVICE.md").read_text(encoding="utf-8"), "HomeStudio 이용약관")

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy():
        return md_to_html((LEGAL_DIR / "PRIVACY_POLICY.md").read_text(encoding="utf-8"), "HomeStudio 개인정보 처리방침")

    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="ui")
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host=os.getenv("HOMESTUDIO_API_HOST", "127.0.0.1"),
                port=int(os.getenv("HOMESTUDIO_API_PORT", "8080")), log_level="warning")
