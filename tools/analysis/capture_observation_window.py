#!/usr/bin/env python3
"""Explicitly retain a short window of already-closed original TS segments.

This utility never connects to the camera or changes the existing recorder. It
copies only files named by the current OriginalBuffer CSV index, while the
normal service is already producing them. Captured media is private runtime
data and is not suitable for training until reviewed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import uuid

DEFAULT_SECONDS = 60
MIN_SECONDS = 10
MAX_SECONDS = 120
MAX_BYTES = 64 * 1024 * 1024
MIN_FREE_BYTES = 3 * 1024 * 1024 * 1024
POLL_SECONDS = 1.0
MAX_FRESH_AGE_SEC = 10.0
CONTIGUITY_TOLERANCE_SEC = 0.1
CHUNK_BYTES = 1024 * 1024
SEGMENT_NAME = re.compile(r"\d{6}\.ts\Z", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def _read_sensor_status(db_path: Path) -> tuple[str | None, datetime | None]:
    """Read camera heartbeat without creating/upgrading the database."""
    if not db_path.is_file():
        return None, None
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            row = connection.execute(
                "SELECT status, last_seen_at FROM sensors WHERE sensor_id='camera-primary'"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None, None
    if not row:
        return None, None
    return str(row[0]), _parse_utc(str(row[1]))


def _safe_session_dirs(buffer_root: Path) -> list[Path]:
    try:
        root = buffer_root.resolve(strict=True)
        if buffer_root.is_symlink() or not root.is_dir():
            return []
        sessions = []
        for child in buffer_root.iterdir():
            if child.is_symlink() or not child.is_dir():
                continue
            index = child / "index.csv"
            if index.is_symlink() or not index.is_file():
                continue
            resolved = child.resolve(strict=True)
            if resolved.parent == root:
                sessions.append(resolved)
        return sessions
    except OSError:
        return []


def _closed_segments(session: Path) -> list[dict]:
    """Return extant, indexed closed files only; never glob the active writer."""
    index = session / "index.csv"
    if index.is_symlink() or not index.is_file():
        return []
    rows: list[dict] = []
    try:
        with index.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.reader(stream):
                if len(row) != 3:
                    continue
                name = Path(row[0]).name
                if name != row[0] or not SEGMENT_NAME.fullmatch(name):
                    continue
                try:
                    start, end = float(row[1]), float(row[2])
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                    continue
                source = session / name
                try:
                    if source.is_symlink() or not source.is_file():
                        continue
                    resolved = source.resolve(strict=True)
                    if resolved.parent != session.resolve(strict=True):
                        continue
                    stat = resolved.stat()
                    if stat.st_size <= 0:
                        continue
                except OSError:
                    continue
                rows.append({"name": name, "start_pts_sec": start, "end_pts_sec": end,
                             "path": resolved, "size_bytes": stat.st_size,
                             "mtime_ns": stat.st_mtime_ns})
    except (OSError, csv.Error, UnicodeError):
        return []
    # The recorder appends in PTS order; reject ambiguous duplicate filenames.
    unique: dict[str, dict] = {}
    for item in rows:
        unique[item["name"]] = item
    return sorted(unique.values(), key=lambda item: (item["start_pts_sec"], item["name"]))


def _latest_indexed_file_exists(session: Path) -> bool:
    """The newest CSV row must name a present closed file; older rows may expire."""
    index = session / "index.csv"
    try:
        with index.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        if not rows or len(rows[-1]) != 3:
            return False
        name = Path(rows[-1][0]).name
        start, end = float(rows[-1][1]), float(rows[-1][2])
        if name != rows[-1][0] or not SEGMENT_NAME.fullmatch(name):
            return False
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            return False
        path = session / name
        if path.is_symlink() or not path.is_file():
            return False
        resolved = path.resolve(strict=True)
        return resolved.parent == session.resolve(strict=True) and resolved.stat().st_size > 0
    except (OSError, csv.Error, UnicodeError, TypeError, ValueError):
        return False


def _fresh(path: Path, now_epoch: float, max_age: float = MAX_FRESH_AGE_SEC) -> bool:
    try:
        age = now_epoch - path.stat().st_mtime
        # Windows file timestamp granularity and wall-clock sampling can put a
        # just-written file fractionally ahead of the observed host clock.
        return -2.0 <= age <= max_age
    except OSError:
        return False


def readiness(base_dir: Path, now_epoch: float | None = None) -> dict:
    """Read-only gates. A fresh active buffer is evidence of the producer privacy guard."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    base = base_dir.resolve()
    reasons: list[str] = []
    snapshot = base / "thumbnails" / "latest.jpg"
    db_path = base / "data" / "homestudio.db"
    buffer_root = base / "original_buffer"
    if not _fresh(snapshot, now_epoch):
        reasons.append("snapshot_missing_or_stale")
    status, heartbeat = _read_sensor_status(db_path)
    if status != "online" or heartbeat is None:
        reasons.append("camera_heartbeat_unavailable")
    elif (datetime.fromtimestamp(now_epoch, timezone.utc) - heartbeat).total_seconds() > MAX_FRESH_AGE_SEC or heartbeat.timestamp() > now_epoch + 1:
        reasons.append("camera_heartbeat_stale")
    sessions = _safe_session_dirs(buffer_root)
    if len(sessions) != 1:
        reasons.append("source_session_missing_or_ambiguous")
        session = None
    else:
        session = sessions[0]
    segments: list[dict] = []
    index_fresh = False
    latest_fresh = False
    latest_present = False
    if session:
        index_fresh = _fresh(session / "index.csv", now_epoch)
        if not index_fresh:
            reasons.append("source_index_missing_or_stale")
        segments = _closed_segments(session)
        if not segments:
            reasons.append("no_closed_source_segments")
        else:
            latest = segments[-1]
            latest_fresh = _fresh(latest["path"], now_epoch)
            if not latest_fresh:
                reasons.append("latest_closed_segment_stale")
            latest_present = _latest_indexed_file_exists(session)
            if not latest_present:
                reasons.append("latest_indexed_segment_missing")
    try:
        free_bytes = shutil.disk_usage(base).free
    except OSError:
        free_bytes = None
    if free_bytes is None or free_bytes < MIN_FREE_BYTES + MAX_BYTES:
        reasons.append("free_space_reserve_below_minimum")
    # A fresh, extant same-session closed index is only producer-guard evidence:
    # service.py pauses OriginalBuffer for privacy=True/unknown, and pause removes
    # its session directory. This does not independently read the camera flag.
    producer_guard = bool(session and index_fresh and latest_fresh and latest_present and segments)
    if not producer_guard:
        reasons.append("producer_privacy_guard_unproven")
    return {
        "status": "ready" if not reasons else "blocked",
        "reasons": reasons,
        "privacy_evidence": "active_original_buffer_guard" if producer_guard else "unproven",
        "session": session,
        "segments": segments,
        "free_bytes": free_bytes,
        "base_dir": base,
    }


def _manifest_payload(status: str, started_at: str, ended_at: str | None,
                      source_session: str, segments: list[dict], total_bytes: int,
                      error: str | None = None) -> dict:
    payload = {
        "schema_version": 1,
        "status": status,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "source_session_id": source_session,
        "source_time_quality": "unknown",
        "utc_note": "Window and per-copy times are host receive times; PTS is segment-relative and is not anchored to UTC.",
        "segments": segments,
        "total_bytes": total_bytes,
        "max_bytes": MAX_BYTES,
    }
    if error:
        payload["failure_reason"] = error
    return payload


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _new_output(base: Path, when: datetime | None = None) -> Path:
    when = when or datetime.now(timezone.utc)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    return base / "data" / "runtime" / f"observation-window-{stamp}-{uuid.uuid4().hex[:8]}"


def _copy_segment(source: Path, destination: Path, byte_limit: int) -> tuple[int, str]:
    before = source.stat()
    digest = hashlib.sha256()
    copied = 0
    created = False
    try:
        with source.open("rb") as src:
            with destination.open("xb") as dst:
                created = True
                while True:
                    chunk = src.read(min(CHUNK_BYTES, byte_limit - copied + 1))
                    if not chunk:
                        break
                    if copied + len(chunk) > byte_limit:
                        raise RuntimeError("byte_cap_reached")
                    dst.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
        after = source.stat()
        if copied != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
            raise RuntimeError("source_changed_during_copy")
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return copied, digest.hexdigest()


def capture(base_dir: Path, seconds: int, *, clock=time.monotonic,
            sleeper=time.sleep, output_dir: Path | None = None) -> dict:
    """Capture only while the existing privacy-gated producer remains ready."""
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError("invalid_duration")
    base = base_dir.resolve()
    gates = readiness(base)
    if gates["reasons"]:
        return {"status": "blocked", "reasons": gates["reasons"]}
    session = gates["session"]
    assert session is not None
    output = output_dir or _new_output(base)
    output = output.resolve()
    private_root = base / "data" / "runtime"
    if (base / "data").is_symlink() or private_root.is_symlink():
        return {"status": "blocked", "reasons": ["unsafe_runtime_directory"]}
    runtime = private_root.resolve()
    if base not in runtime.parents or output.parent != runtime:
        return {"status": "blocked", "reasons": ["output_outside_private_runtime"]}
    if output.exists():
        return {"status": "blocked", "reasons": ["output_already_exists"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)
    start_utc = utc_now()
    start_mono = clock()
    manifest_segments: list[dict] = []
    # The window starts after READY; already closed pre-window segments are not
    # copied even if they remain briefly in the rolling buffer.
    copied_names: set[str] = {item["name"] for item in gates["segments"]}
    total_bytes = 0
    _atomic_json(output / "READY.json", {
        "status": "READY", "duration_sec": seconds, "max_bytes": MAX_BYTES,
        "source_time_quality": "unknown", "privacy_evidence": gates["privacy_evidence"],
        "started_at_utc": start_utc,
    })
    print(json.dumps({"status": "READY", "duration_sec": seconds, "max_bytes": MAX_BYTES,
                      "source_time_quality": "unknown",
                      "privacy_evidence": gates["privacy_evidence"]}, separators=(",", ":")), flush=True)

    failure: str | None = None
    prior_end: float | None = gates["segments"][-1]["end_pts_sec"]
    try:
        while clock() - start_mono < seconds:
            current = readiness(base)
            if current["reasons"]:
                failure = current["reasons"][0]
                break
            if current["session"] != session:
                failure = "source_session_changed"
                break
            for item in current["segments"]:
                name = item["name"]
                if name in copied_names:
                    continue
                if prior_end is not None and abs(item["start_pts_sec"] - prior_end) > CONTIGUITY_TOLERANCE_SEC:
                    failure = "source_sequence_gap"
                    break
                if total_bytes + item["size_bytes"] > MAX_BYTES:
                    failure = "byte_cap_reached"
                    break
                destination = output / f"segment-{len(manifest_segments) + 1:03d}.ts"
                receive_time = utc_now()
                count, fingerprint = _copy_segment(item["path"], destination, MAX_BYTES - total_bytes)
                if total_bytes + count > MAX_BYTES:
                    destination.unlink(missing_ok=True)
                    failure = "byte_cap_reached"
                    break
                total_bytes += count
                prior_end = item["end_pts_sec"]
                copied_names.add(name)
                manifest_segments.append({
                    "source_relative_path": item["path"].relative_to(base).as_posix(),
                    "output_file": destination.name,
                    "start_pts_sec": item["start_pts_sec"],
                    "end_pts_sec": item["end_pts_sec"],
                    "received_at_utc": receive_time,
                    "size_bytes": count,
                    "sha256": fingerprint,
                })
                _atomic_json(output / "manifest.json", _manifest_payload(
                    "running", start_utc, None, session.name, manifest_segments, total_bytes))
            if failure:
                break
            sleeper(POLL_SECONDS)
    except KeyboardInterrupt:
        failure = "interrupted"
    except RuntimeError as exc:
        failure = "byte_cap_reached" if str(exc) == "byte_cap_reached" else "copy_or_read_error"
    except (OSError, sqlite3.Error):
        failure = "copy_or_read_error"

    ended_utc = utc_now()
    if failure:
        final_status = "partial" if manifest_segments else "failed"
        payload = _manifest_payload(final_status, start_utc, ended_utc, session.name,
                                    manifest_segments, total_bytes, failure)
        _atomic_json(output / "manifest.json", payload)
        _atomic_json(output / "FAILED.json", {"status": final_status, "reason": failure,
                                                "ended_at_utc": ended_utc})
    elif not manifest_segments:
        final_status = "failed"
        payload = _manifest_payload(final_status, start_utc, ended_utc, session.name,
                                    manifest_segments, total_bytes, "no_segments_copied")
        _atomic_json(output / "manifest.json", payload)
        _atomic_json(output / "FAILED.json", {"status": final_status, "reason": "no_segments_copied",
                                                "ended_at_utc": ended_utc})
    else:
        final_status = "complete"
        _atomic_json(output / "manifest.json", _manifest_payload(
            final_status, start_utc, ended_utc, session.name, manifest_segments, total_bytes))
    return {"status": final_status, "segment_count": len(manifest_segments), "total_bytes": total_bytes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Read-only readiness check; never copies media.")
    action.add_argument("--capture", action="store_true", help="Capture a bounded window from the already privacy-gated original buffer.")
    parser.add_argument("--base-dir", type=Path,
                        default=Path(os.environ.get("HOMESTUDIO_BASE_DIR", r"C:\HomeStudio")))
    parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    args = parser.parse_args(argv)
    if not MIN_SECONDS <= args.seconds <= MAX_SECONDS:
        parser.error("--seconds must be 10..120")
    try:
        if args.check:
            state = readiness(args.base_dir)
            print(json.dumps({"status": state["status"], "reasons": state["reasons"],
                              "privacy_evidence": state["privacy_evidence"],
                              "source_time_quality": "unknown"}, separators=(",", ":")))
            return 0 if state["status"] == "ready" else 2
        result = capture(args.base_dir, args.seconds)
        # This response intentionally excludes destination/source paths and identifiers.
        print(json.dumps(result, separators=(",", ":")), flush=True)
        return 0 if result["status"] == "complete" else 2
    except Exception:
        # Keep unexpected local path/credential context out of stdout/stderr.
        print(json.dumps({"status": "failed", "reason": "internal_error"}, separators=(",", ":")), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
