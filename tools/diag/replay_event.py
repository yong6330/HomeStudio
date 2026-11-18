"""Replay a recorded event clip through the current MotionDetector settings (service config + saved cage zone).

    python tools/diag/replay_event.py <clip.mp4> [<clip.mp4> ...]

The background is primed with the clip's first frame (as if the scene had been static), then every clip frame is
processed at the snapshot rate. Prints whether the pipeline would record an event. Read-only: no DB writes.
"""
import json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
from software.backend.config import PipelineConfig  # noqa: E402
from software.vision.motion import MotionDetector  # noqa: E402


def detector(cfg, cage):
    d = MotionDetector(width=cfg.motion_downscale_width, height=cfg.motion_downscale_height, fps=cfg.snapshot_fps,
                       diff_threshold=cfg.motion_diff_threshold, start_ratio=cfg.motion_ratio_start_threshold,
                       end_ratio=cfg.motion_ratio_end_threshold, min_duration_sec=cfg.motion_min_duration_sec,
                       max_duration_sec=cfg.motion_max_duration_sec, post_roll_sec=cfg.post_roll_sec,
                       min_blob_px=cfg.motion_min_blob_px, warmup_sec=cfg.motion_warmup_sec, border=cfg.motion_border,
                       osd_box=cfg.motion_osd_box, max_aspect=cfg.motion_max_aspect, min_fill=cfg.motion_min_fill,
                       max_speed_px=cfg.motion_max_speed_px, static_sec=cfg.motion_static_sec,
                       bright_jump=cfg.motion_bright_jump, edge_band=cfg.motion_edge_band)
    d.set_roi(cage)
    return d


def frames(path, w, h):
    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, f = cap.read()
        if not ok:
            return out
        out.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (w, h), interpolation=cv2.INTER_AREA).tobytes())


def replay(path, cfg, cage):
    d, events, peak = detector(cfg, cage), [], 0.0
    d.on_event_end = events.append
    fr = frames(path, d.width, d.height)
    t, dt = 0.0, 1.0 / cfg.snapshot_fps
    for f in [fr[0]] * (d.warmup_frames + 30) + fr + [fr[-1]] * int(cfg.post_roll_sec * cfg.snapshot_fps + 4):
        r, _ = d.process_frame(f, t)
        peak, t = max(peak, r), t + dt
    return events, peak


if __name__ == "__main__":
    cfg = PipelineConfig()
    row = sqlite3.connect(cfg.db_path).execute("SELECT value FROM app_settings WHERE key='zones'").fetchone()
    cage = next((z["points"] for z in json.loads(row[0]) if z["kind"] == "cage"), None) if row else None
    for p in sys.argv[1:]:
        ev, peak = replay(p, cfg, cage)
        print(f"{Path(p).name}: {'EVENT' if ev else 'no event'} (peak ratio {peak:.3f}, events {len(ev)})")
        for e in ev:
            print("  track", e.track)
