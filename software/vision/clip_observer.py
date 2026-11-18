"""Bounded, offline motion candidates from an existing clip (never animal identity)."""
from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ANALYSIS_REVISION = "motion-candidate-v1"
MAX_FRAMES = 300
MAX_SECONDS = 60
SAMPLE_FPS = 5
SIZE = (320, 180)
MEMORY_CAP = 256 * 1024 * 1024
QUALITY_REASONS = {"no_cage_roi", "empty_cage_roi", "global_light_change", "multiple_motion_regions",
                   "large_motion_region", "insufficient_frames", "decode_timeout", "decode_failed",
                   "memory_limit", "memory_measurement_unavailable", "original_missing_preview_used",
                   "source_file_missing"}


def _mask(zones, width, height, config):
    import cv2
    import numpy as np
    cage = next((z for z in zones if z.get("kind") == "cage"), None)
    if cage is None:
        return None, "no_cage_roi"
    points = cage.get("points")
    if not isinstance(points, list) or len(points) < 3:
        return None, "empty_cage_roi"
    mask = np.zeros((height, width), np.uint8)
    coords = np.asarray([[round(float(x) * (width - 1)), round(float(y) * (height - 1))] for x, y in points], np.int32)
    cv2.fillPoly(mask, [coords], 255)
    border = max(0, min(0.49, float(getattr(config, "motion_border", .03))))
    bx, by = round(border * width), round(border * height)
    if by:
        mask[:by] = 0
        mask[height-by:] = 0
    if bx:
        mask[:, :bx] = 0
        mask[:, width-bx:] = 0
    box = getattr(config, "motion_osd_box", (0, 0, .30, .09))
    if box:
        x0, y0, x1, y1 = box
        mask[max(0, int(y0 * height)):min(height, math.ceil(y1 * height)),
             max(0, int(x0 * width)):min(width, math.ceil(x1 * width))] = 0
    if cv2.countNonZero(mask) == 0:
        return None, "empty_cage_roi"
    return mask, None


def analyze_frames(frames, zones, config=None, source="original", roi_revision=None):
    """Analyze at most 300 BGR byte frames; intervals are relative to this file."""
    import cv2
    import numpy as np
    config = config or object()
    mask, mask_error = _mask(zones, SIZE[0], SIZE[1], config)
    reasons = [mask_error] if mask_error else []
    if mask is None:
        return {"status": "failed", "source": source, "source_time_quality": "unknown", "frame_size": list(SIZE),
                "sample_fps": SAMPLE_FPS, "analyzed_sec": 0.0, "quality_reasons": reasons, "intervals": [],
                "analysis_revision": ANALYSIS_REVISION, "roi_revision": roi_revision}
    prev = None
    active = None
    intervals = []
    tracks = []
    unknown = None
    frame_count = 0
    for index, raw in enumerate(frames):
        if index >= MAX_FRAMES:
            break
        frame_count = index + 1
        frame = np.frombuffer(raw, dtype=np.uint8)
        if frame.size != SIZE[0] * SIZE[1] * 3:
            reasons.append("decode_failed")
            break
        gray = cv2.cvtColor(frame.reshape((SIZE[1], SIZE[0], 3)), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            diff = cv2.absdiff(gray, prev)
            vals = diff[mask != 0]
            if vals.size and float(np.mean(vals)) > 20:
                reasons.append("global_light_change")
                t = index / SAMPLE_FPS
                if unknown is None:
                    unknown = {"start_sec": max(0, t - 1 / SAMPLE_FPS), "end_sec": t,
                               "label": "movement_candidate", "state": "unknown", "zone_id": None}
                    intervals.append(unknown)
                else:
                    unknown["end_sec"] = t
                active = None
                prev = gray
                continue
            changed = cv2.threshold(diff, max(20, int(getattr(config, "motion_diff_threshold", 25))), 255,
                                    cv2.THRESH_BINARY)[1]
            changed = cv2.bitwise_and(changed, mask)
            changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            contours, _ = cv2.findContours(changed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            blobs = [c for c in contours if cv2.contourArea(c) >= 6]
            t = index / SAMPLE_FPS
            if len(blobs) > 2:
                reasons.append("multiple_motion_regions")
                if unknown is None:
                    unknown = {"start_sec": max(0, t - 1 / SAMPLE_FPS), "end_sec": t,
                               "label": "movement_candidate", "state": "unknown", "zone_id": None}
                    intervals.append(unknown)
                else:
                    unknown["end_sec"] = t
                active = None
            elif blobs:
                blob = max(blobs, key=cv2.contourArea)
                area = cv2.contourArea(blob)
                if area > mask.size * .15:
                    reasons.append("large_motion_region")
                    if unknown is None:
                        unknown = {"start_sec": max(0, t - 1 / SAMPLE_FPS), "end_sec": t,
                                   "label": "movement_candidate", "state": "unknown", "zone_id": None}
                        intervals.append(unknown)
                    else:
                        unknown["end_sec"] = t
                    active = None
                else:
                    unknown = None
                    m = cv2.moments(blob)
                    if m["m00"]:
                        cx, cy = m["m10"] / m["m00"] / SIZE[0], m["m01"] / m["m00"] / SIZE[1]
                        tracks.append([t, cx * SIZE[0], cy * SIZE[1]])
                        zone_id = next((z.get("id") for z in zones if z.get("kind") == "wheel" and
                                        _inside(cx, cy, z.get("points", []))), None)
                        label = "wheel_motion_candidate" if zone_id else "movement_candidate"
                        if active is None or active["label"] != label or t - active["end_sec"] > .6:
                            active = {"start_sec": max(0, t - 1 / SAMPLE_FPS), "end_sec": t,
                                      "label": label, "state": "candidate", "zone_id": zone_id}
                            intervals.append(active)
                        else:
                            active["end_sec"] = t
            elif active is not None and t - active["end_sec"] > .6:
                active = None
        prev = gray
    analyzed = min(frame_count / SAMPLE_FPS, MAX_SECONDS)
    if frame_count < 3:
        reasons.append("insufficient_frames")
    if len(tracks) >= 6:
        from ..backend.behavior import features
        if features(tracks).get("pace"):
            start_sec, end_sec = tracks[0][0], tracks[-1][0]
            intervals = [i for i in intervals if i["state"] != "candidate" or
                         i["end_sec"] < start_sec or i["start_sec"] > end_sec]
            intervals.append({"start_sec": start_sec, "end_sec": max(start_sec + .2, end_sec),
                              "label": "repeated_path_candidate", "state": "candidate", "zone_id": None})
    # Do not infer a source clock from clip timestamps.
    for interval in intervals:
        interval["end_sec"] = max(interval["start_sec"] + .2, interval["end_sec"])
    return {"status": "ready" if frame_count >= 3 else "failed", "source": source,
            "source_time_quality": "unknown", "frame_size": list(SIZE), "sample_fps": SAMPLE_FPS,
            "analyzed_sec": round(analyzed, 2), "quality_reasons": sorted(set(reasons)), "intervals": intervals,
            "analysis_revision": ANALYSIS_REVISION, "roi_revision": roi_revision}


def _inside(x, y, points):
    from ..backend.zones import inside
    return bool(points and inside(x, y, points))


def _ffprobe(path, config, timeout=10):
    proc = subprocess.run([config.ffprobe_bin, "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height", "-of", "json", str(path)], capture_output=True, timeout=timeout)
    data = json.loads(proc.stdout or b"{}")
    stream = (data.get("streams") or [{}])[0]
    return [int(stream["width"]), int(stream["height"])]


def _windows_working_set(pid):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x0400 | 0x0010, False, int(pid))
    if not handle:
        return None
    try:
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        kernel32.CloseHandle(handle)


def _read_frames(path, config, timeout=90, baseline_ws=None):
    args = [config.ffmpeg_bin, "-v", "error", "-threads", "1", "-filter_threads", "1", "-i", str(path),
            "-t", str(MAX_SECONDS), "-vf", "fps=5,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,format=bgr24",
            "-frames:v", str(MAX_FRAMES), "-f", "rawvideo", "pipe:1"]
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=flags)
    q = queue.Queue(maxsize=1)
    frame_bytes = SIZE[0] * SIZE[1] * 3
    stopped = threading.Event()
    reached_cap = False
    def reader():
        try:
            while True:
                data = proc.stdout.read(frame_bytes)
                if not data:
                    break
                if len(data) != frame_bytes:
                    value = RuntimeError("partial decoded frame")
                else:
                    value = data
                while not stopped.is_set():
                    try:
                        q.put(value, timeout=.2)
                        break
                    except queue.Full:
                        continue
                if isinstance(value, Exception):
                    break
        except Exception as exc:
            if not stopped.is_set():
                try:
                    q.put(exc, timeout=.2)
                except queue.Full:
                    pass
        finally:
            while not stopped.is_set():
                try:
                    q.put(None, timeout=.2)
                    break
                except queue.Full:
                    continue
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    def generate():
        nonlocal reached_cap
        deadline = time.monotonic() + timeout
        count = 0
        try:
            while count < MAX_FRAMES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("decode_timeout")
                try:
                    item = q.get(timeout=min(.5, remaining))
                except queue.Empty:
                    continue
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                count += 1
                if os.name == "nt":
                    own_ws = _windows_working_set(os.getpid())
                    child_ws = _windows_working_set(proc.pid)
                    if own_ws is None or child_ws is None or baseline_ws is None:
                        raise RuntimeError("memory_measurement_unavailable")
                    if max(0, own_ws - baseline_ws) + child_ws > MEMORY_CAP:
                        raise MemoryError("memory_limit")
                yield item
            if count >= MAX_FRAMES:
                reached_cap = True
                if proc.poll() is None:
                    proc.kill()
            try:
                proc.wait(timeout=max(.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("decode_timeout") from exc
            if proc.returncode and not reached_cap:
                raise RuntimeError("decode_failed")
        finally:
            stopped.set()
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            if proc.stdout:
                proc.stdout.close()
            thread.join(timeout=1)
    return generate()


def analyze_clip(path, zones, config=None, source="original", roi_revision=None):
    path = Path(path)
    if not path.is_file():
        return {"status": "failed", "source": source, "source_time_quality": "unknown", "frame_size": list(SIZE),
                "sample_fps": SAMPLE_FPS, "analyzed_sec": 0.0, "quality_reasons": ["source_file_missing"],
                "intervals": [], "analysis_revision": ANALYSIS_REVISION, "roi_revision": roi_revision}
    try:
        if config is None:
            from ..backend.config import PipelineConfig
            config = PipelineConfig()
        import cv2  # Include the runtime's one-time native allocation in the baseline.
        import numpy
        baseline_ws = _windows_working_set(os.getpid()) if os.name == "nt" else None
        native_size = _ffprobe(path, config)
        frames = _read_frames(path, config, baseline_ws=baseline_ws)
        result = analyze_frames(frames, zones, config, source, roi_revision)
        result["frame_size"] = native_size
        return result
    except MemoryError:
        reason = "memory_limit"
    except TimeoutError:
        reason = "decode_timeout"
    except Exception:
        reason = "memory_measurement_unavailable" if "memory_measurement_unavailable" in str(sys.exc_info()[1]) else "decode_failed"
    return {"status": "failed", "source": source, "source_time_quality": "unknown", "frame_size": list(SIZE),
            "sample_fps": SAMPLE_FPS, "analyzed_sec": 0.0, "quality_reasons": [reason], "intervals": [],
            "analysis_revision": ANALYSIS_REVISION, "roi_revision": roi_revision}
