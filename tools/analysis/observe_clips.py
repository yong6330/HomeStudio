"""Explicit, bounded analysis of existing camera events; never starts a worker."""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _available_memory():
    if os.name == "nt":
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        state = MEMORYSTATUSEX(); state.dwLength = ctypes.sizeof(state)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return None
        return int(state.ullAvailPhys)
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None


def _readiness(config):
    snapshot = config.thumbnails_dir / "latest.jpg"
    try:
        age = time.time() - snapshot.stat().st_mtime
    except OSError:
        return "snapshot_missing_or_stale"
    if age < 0 or age > 10:
        return "snapshot_missing_or_stale"
    memory = _available_memory()
    if memory is None or memory < 512 * 1024 * 1024:
        return "available_memory_below_512_mib" if memory is not None else "memory_unavailable"
    return None


def _read_only(db_path):
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--database", type=Path, help="Explicit SQLite source database (opened read-only).")
    parser.add_argument("--dry-run", action="store_true", help="Read and analyze without writing the database (default).")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 10:
        parser.error("--limit must be 1..10")
    from software.backend.config import PipelineConfig
    from software.vision.clip_observer import analyze_clip
    config = PipelineConfig()
    blocked = _readiness(config)
    if blocked:
        print(json.dumps({"status": "deferred", "reason": blocked, "items": []}))
        return 2
    base = config.base_dir.resolve()
    database = args.database or config.db_path
    conn = _read_only(database.resolve())
    try:
        row = conn.execute("SELECT value FROM space_settings WHERE homespace_id=1 AND key='zones'").fetchone()
        if row is None:
            row = conn.execute("SELECT value FROM app_settings WHERE key='zones'").fetchone()
        zones = json.loads(row[0]) if row else []
        revision_row = conn.execute("SELECT revision FROM baseline_revisions WHERE homespace_id=1").fetchone()
        roi_revision = int(revision_row[0]) if revision_row else None
        events = conn.execute("SELECT event_id, original_path, clip_path FROM events WHERE homespace_id=1 "
                               "ORDER BY started_at DESC LIMIT 500").fetchall()
    finally:
        conn.close()
    items = []
    for event_id, original_path, preview_path in events:
        original = Path(original_path).resolve() if original_path else None
        preview = Path(preview_path).resolve() if preview_path else None
        if original and base in original.parents and original.is_file():
            path, source, fallback = original, "original", False
        elif preview and base in preview.parents and preview.is_file():
            path, source, fallback = preview, "preview", True
        else:
            continue
        blocked = _readiness(config)
        if blocked:
            break
        result = analyze_clip(path, zones, config, source, roi_revision)
        if fallback:
            result["quality_reasons"] = sorted(set(result["quality_reasons"] + ["original_missing_preview_used"]))
        items.append({"event_id": event_id, **result})
        if len(items) >= args.limit:
            break
    blocked = _readiness(config)
    print(json.dumps({"status": "deferred" if blocked else "dry_run", "reason": blocked,
                      "analyzed_clips": len(items),
                      "analyzed_sec": round(sum(x["analyzed_sec"] for x in items), 2),
                      "items": items}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
