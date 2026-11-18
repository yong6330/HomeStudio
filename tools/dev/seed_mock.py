"""Deterministic MOCK data for development in a SEPARATE base dir (never the real HomeStudio data).

    python tools/dev/seed_mock.py --out C:\\HomeStudioDev [--days 12] [--seed 7] [--force]
    set HOMESTUDIO_BASE_DIR=C:\\HomeStudioDev & python -m software.backend.api     (see tools/dev/README.md)

Creates <out>/data/homestudio.db, <out>/thumbnails, <out>/events with:
- nocturnal hamster activity (most 20:00-04:00 KST) on 12:00-12:00 care days, events <=60 s grouped into sessions
  (gaps <=30 s), each with a centroid track, distance_px and active_frames;
- camera coverage minutes with a few status episodes: a 3 h offline gap (that day is excluded from the baseline),
  a 40 min dark spell, a privacy on/off pair -> past notifications are generated at their simulated times;
- two anomalous low-activity days (one past with its end-of-day verdict, plus today so far) and a long no-motion
  stretch ending now (> the usual longest daily gap; disable with --no-inactivity) so verdict/inactivity alerts show;
- synthetic placeholder thumbnails (JPEG) and short clips (H.264 via ffmpeg if available, else none). No real photos.
"""
import argparse, json, math, os, random, shutil, subprocess, sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from software.backend import insights  # noqa: E402
from software.backend.config import PipelineConfig  # noqa: E402
from software.backend.db import Database  # noqa: E402

KST = timezone(timedelta(hours=9))
W, H = 160, 90
# mock cage layout (normalized rectangles) shared by the zones setting and the synthetic pictures
ZONES = [
    {"id": "wheel", "name": "쳇바퀴", "kind": "wheel", "box": (0.08, 0.20, 0.29, 0.58)},
    {"id": "water", "name": "물병", "kind": "water", "box": (0.82, 0.08, 0.95, 0.30)},
    {"id": "food", "name": "먹이 그릇", "kind": "food", "box": (0.70, 0.66, 0.86, 0.90)},
    {"id": "hide", "name": "은신처", "kind": "hide", "box": (0.38, 0.60, 0.56, 0.92)},
]
ZONE_W = {"wheel": 0.4, "water": 0.15, "food": 0.15, "hide": 0.15}  # rest: open floor


def zone_rows():
    return [{"id": z["id"], "name": z["name"], "kind": z["kind"],
             "points": [[z["box"][0], z["box"][1]], [z["box"][2], z["box"][1]], [z["box"][2], z["box"][3]], [z["box"][0], z["box"][3]]]}
            for z in ZONES]


def refuse_real(out: Path) -> None:
    """Real installs: C:/D:\\HomeStudio, the non-Windows default ./homestudio_data, or anything with a service log."""
    real = {Path(r"C:\HomeStudio"), Path(r"D:\HomeStudio"), Path("./homestudio_data"), ROOT / "homestudio_data"}
    if out.resolve() in {p.resolve() for p in real} or (out / "logs" / "service.log").exists():
        sys.exit(f"refusing to seed the real data dir: {out}")


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat()


def picture(path: Path, x: float, y: float, night: bool, ffmpeg: str = "", frames=None) -> None:
    """Synthetic cage scene: dark/light background, wheel circle, hamster blob at (x, y). JPEG, or H.264 clip if frames."""
    import cv2
    import numpy as np

    def frame(px, py):
        img = np.full((H * 2, W * 2, 3), (38, 34, 30) if night else (170, 180, 185), np.uint8)
        cv2.rectangle(img, (8, 8), (W * 2 - 8, H * 2 - 8), (90, 90, 90), 2)
        cv2.circle(img, (60, 70), 34, (120, 120, 120), 3)  # wheel
        sx, sy = W * 2, H * 2
        for z in ZONES[1:]:
            x0, y0, x1, y1 = z["box"]
            p0, p1 = (int(x0 * sx), int(y0 * sy)), (int(x1 * sx), int(y1 * sy))
            if z["kind"] == "food":
                cv2.ellipse(img, ((p0[0] + p1[0]) // 2, (p0[1] + p1[1]) // 2), ((p1[0] - p0[0]) // 2, (p1[1] - p0[1]) // 2), 0, 0, 360, (60, 120, 160), -1)
            elif z["kind"] == "water":
                cv2.rectangle(img, p0, p1, (170, 120, 60), -1)
            else:
                cv2.rectangle(img, p0, p1, (40, 70, 90), -1)
        cv2.ellipse(img, (int(px * 2), int(py * 2)), (14, 9), 0, 0, 360, (95, 170, 230), -1)
        cv2.putText(img, "MOCK", (W * 2 - 70, H * 2 - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return img

    path.parent.mkdir(parents=True, exist_ok=True)
    if frames is None:
        cv2.imwrite(str(path), frame(x, y), [cv2.IMWRITE_JPEG_QUALITY, 70])
        return
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W * 2}x{H * 2}", "-r", "5",
           "-i", "pipe:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
    data = b"".join(frame(px, py).tobytes() for _, px, py in frames)
    subprocess.run(cmd, input=data, check=True, timeout=60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="separate dev base dir, e.g. C:\\HomeStudioDev or ./dev_data")
    ap.add_argument("--days", type=int, default=12, help="past care days before today (>= 11 so day -3 has a ready baseline)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--now", help="ISO time to treat as now (default: current time)")
    ap.add_argument("--clips-days", type=int, default=2, help="generate clips/thumbnails for the last N days")
    ap.add_argument("--no-inactivity", action="store_true", help="skip the long no-motion stretch ending now")
    ap.add_argument("--force", action="store_true", help="wipe an existing dev dir first")
    a = ap.parse_args()
    out = Path(a.out)
    refuse_real(out)
    if out.exists() and any(out.iterdir()):
        if not a.force:
            sys.exit(f"{out} is not empty (use --force to recreate)")
        if not (out / ".homestudio_mock").exists():
            sys.exit(f"refusing to wipe {out}: not created by seed_mock.py")
        shutil.rmtree(out)
    cfg = PipelineConfig(base_dir=out)
    cfg.ensure_directories()
    (out / ".homestudio_mock").write_text("created by tools/dev/seed_mock.py\n")
    db = Database(cfg.db_path)
    from software.backend import zones as zmod
    zmod.save(db, zone_rows())  # mock cage zones (wheel/water/food/hide)
    picture(cfg.thumbnails_dir / "latest.jpg", 30, 35, True)  # mock live snapshot for the camera/zones screens
    ffmpeg = shutil.which(cfg.ffmpeg_bin) or shutil.which("ffmpeg") or ""
    rnd = random.Random(a.seed)
    now = datetime.fromisoformat(a.now).astimezone(KST) if a.now else datetime.now(KST).replace(second=0, microsecond=0)
    off = 12.0
    with db._get_connection() as c:
        c.execute("UPDATE care_targets SET name='보리', care_day_start_local='12:00'")
    today0 = datetime.combine((now - timedelta(hours=off)).date(), time(), KST) + timedelta(hours=off)
    offline_day, low_day = 6, 3  # days ago
    n_ev = 0
    for k in range(a.days, -1, -1):
        s = today0 - timedelta(days=k)
        end = min(s + timedelta(hours=24), now)
        insights.mark_online(db, s, end)
        if k == offline_day:  # 3 h camera offline 02:00-05:00 -> coverage 87.5% -> excluded from baseline
            with db._get_connection() as c:
                c.execute("DELETE FROM online_minutes WHERE minute >= ? AND minute < ?",
                          (insights._utc(s + timedelta(hours=14)), insights._utc(s + timedelta(hours=17))))
        n_sessions = rnd.randint(2, 4) if k in (low_day, 0) else rnd.randint(9, 14)
        for si in range(n_sessions):
            # nocturnal: care-day hour 8-16 == 20:00-04:00 KST, a few dusk/dawn sessions
            hh = rnd.gauss(12, 2.2) if rnd.random() < 0.85 else rnd.uniform(5, 20)
            t = s + timedelta(hours=min(23.5, max(0.2, hh)))
            if t >= now:
                continue
            x, y = rnd.uniform(30, 130), rnd.uniform(25, 70)
            for ei in range(rnd.randint(1, 6)):  # one session = consecutive <=60 s events (60 s split) with short gaps
                r = rnd.random()
                for z in ZONES:  # most events start at a cage object (wheel/water/food/hide), the rest on open floor
                    if r < ZONE_W[z["id"]]:
                        x0, y0, x1, y1 = z["box"]
                        x, y = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H
                        break
                    r -= ZONE_W[z["id"]]
                dur = rnd.choice([60.0, 60.0, rnd.uniform(8, 59)])
                track, dist = [], 0.0
                for j in range(int(dur * 2)):  # 2 fps centroid samples
                    nx = min(152, max(8, x + rnd.gauss(0, 2)))
                    ny = min(84, max(6, y + rnd.gauss(0, 1.5)))
                    dist += math.hypot(nx - x, ny - y)
                    x, y = nx, ny
                    if j % 2 == 0:
                        track.append([round(j / 2, 1), round(x, 1), round(y, 1)])
                # 행동 건강 mock: days -1/-2 have more wheel time and pacing (2 consecutive days -> alerts),
                # a few circling tracks; other days a rare pacing/circling event
                hot = k in (1, 2)
                r2 = rnd.random()
                if hot and r2 < 0.5:  # stays on the wheel
                    x0, y0, x1, y1 = ZONES[0]["box"]
                    cx, cy = (x0 + x1) / 2 * W, (y0 + y1) / 2 * H
                    track = [[float(i), round(cx + rnd.gauss(0, 2), 1), round(cy + rnd.gauss(0, 2), 1)] for i in range(int(dur))]
                elif r2 < (0.8 if hot else 0.02):  # back-and-forth along the front wall
                    track = [[float(i), round(40 + 30 * abs((i % 8) - 4) / 4 + rnd.gauss(0, 0.8), 1), round(78 + rnd.gauss(0, 0.8), 1)] for i in range(int(dur))]
                elif r2 < (0.85 if hot else 0.03):  # circling in place
                    track = [[float(i), round(110 + 6 * math.cos(i * 0.9), 1), round(50 + 6 * math.sin(i * 0.9), 1)] for i in range(int(dur))]
                if len(track) > 1 and r2 < (0.85 if hot else 0.03):
                    x, y = track[-1][1], track[-1][2]
                eid = f"mock_{k}_{si}_{ei}"
                clip = thumb = None
                size = 0
                if k < a.clips_days and ei == 0:
                    night = not (6 <= t.hour < 18)
                    thumb = cfg.thumbnails_dir / f"{eid}.jpg"
                    picture(thumb, x, y, night)
                    if ffmpeg:
                        clip = cfg.events_dir / f"{eid}.mp4"
                        picture(clip, x, y, night, ffmpeg, track[:15])
                        size = clip.stat().st_size
                    size += thumb.stat().st_size
                db.insert_event("motion", iso(t), iso(t + timedelta(seconds=dur)), round(dur, 1),
                                activity_score=min(1.0, dist / 300), clip_path=str(clip) if clip else None,
                                thumbnail_path=str(thumb) if thumb else None, file_size_bytes=size, event_id=eid,
                                distance_px=round(dist, 1), active_frames=int(dur * 2 * rnd.uniform(0.6, 1.0)),
                                track_json=json.dumps(track))
                n_ev += 1
                t += timedelta(seconds=dur + rnd.uniform(1, 25))
                if t >= now:
                    break

    def status(st, at):
        with db._get_connection() as c:
            c.execute("UPDATE sensors SET status=?, last_seen_at=? WHERE sensor_id='camera-primary'", (st, iso(at)))

    # replay status episodes so notifications carry their simulated times
    d6 = today0 - timedelta(days=offline_day)
    status("online", d6 + timedelta(hours=13.9)); insights.check_notifications(db, d6 + timedelta(hours=13.95), off=off)  # records privacy=off
    insights.check_notifications(db, d6 + timedelta(hours=14.3), off=off)  # offline > 10 min
    # past end-of-day verdict for the low day (-3), delivered when that care day closed
    d_low_end = today0 - timedelta(days=low_day - 1)
    status("online", d_low_end + timedelta(minutes=5)); insights.check_notifications(db, d_low_end + timedelta(minutes=5), off=off)
    d2 = today0 - timedelta(days=2)
    with db._get_connection() as c:
        c.execute("DELETE FROM online_minutes WHERE minute >= ? AND minute < ?", (insights._utc(d2 + timedelta(hours=9)), insights._utc(d2 + timedelta(hours=9, minutes=40))))
    status("dark", d2 + timedelta(hours=9, minutes=20)); insights.check_notifications(db, d2 + timedelta(hours=9, minutes=20), off=off)
    d1 = today0 - timedelta(days=1)
    status("privacy", d1 + timedelta(hours=1)); insights.check_notifications(db, d1 + timedelta(hours=1), off=off)
    status("online", d1 + timedelta(hours=2)); insights.check_notifications(db, d1 + timedelta(hours=2), off=off)
    # long inactivity scenario: no motion for (typical longest daily gap threshold + 1 h) up to now, camera watching
    if not a.no_inactivity:
        thr = insights.inactivity_threshold(db, (now - timedelta(hours=off)).date(), off, now)
        if thr:
            cut = now - timedelta(hours=thr["threshold_h"] + 1)
            with db._get_connection() as c:
                gone = [r[0] for r in c.execute("SELECT event_id, ended_at FROM events") if insights._parse(r[1]) > cut]
                c.executemany("DELETE FROM events WHERE event_id=?", [(g,) for g in gone])
            print(f"inactivity scenario: threshold {thr['threshold_h']} h, removed {len(gone)} events after {cut:%m-%d %H:%M} KST")
    status("online", now)  # healthy now; yesterday's verdict and the inactivity alert are raised live by the API
    with db._get_connection() as c:
        c.execute("DELETE FROM online_minutes WHERE minute > ?", (insights._utc(now),))
    print(f"mock data: {out} | days={a.days}+today events={n_ev} clips={'yes' if ffmpeg else 'no (ffmpeg missing)'} "
          f"anomalous days: -{low_day}, today | offline gap day: -{offline_day}")


if __name__ == "__main__":
    main()
