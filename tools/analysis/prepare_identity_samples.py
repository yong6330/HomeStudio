"""Prepare a small, private, manually reviewed identity sample set."""
import argparse
import hashlib
import html
import json
import math
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_EVENTS, MAX_WIDTH, TIMEOUT_SEC = 6, 640, 20
SPLITS = ("train", "validation", "test")
INTERFERENCE = {"caregiver", "reflection", "light", "none", "unknown"}
VISIBILITY = {"visible", "occluded", "not_visible", "unknown"}
APPEARANCE = {"color", "monochrome", "dark", "unknown"}
DAYPART = {"day", "night", "unknown"}


def _available_memory():
    import os
    if os.name == "nt":
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        state = MEMORYSTATUSEX(); state.dwLength = ctypes.sizeof(state)
        return int(state.ullAvailPhys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)) else None
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None


def readiness(snapshot, available_memory=None):
    try:
        age = time.time() - Path(snapshot).stat().st_mtime
    except OSError:
        return "snapshot_missing_or_stale"
    if age < 0 or age > 10:
        return "snapshot_missing_or_stale"
    if available_memory is None:
        available_memory = _available_memory()
    if available_memory is None or available_memory < 512 * 1024 * 1024:
        return "available_memory_below_512_mib" if available_memory is not None else "memory_unavailable"
    return None


def _db_readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def _contained_file(path, base):
    if not path:
        return None
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(Path(base).resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def validate_review(record):
    if record.get("review_state") not in {"unreviewed", "reviewed"}:
        raise ValueError("invalid review_state")
    if record.get("interference") not in INTERFERENCE or record.get("visibility") not in VISIBILITY:
        raise ValueError("invalid interference or visibility")
    if record.get("appearance") not in APPEARANCE:
        raise ValueError("invalid appearance")
    if record.get("scene") not in DAYPART:
        raise ValueError("invalid camera clock daypart")
    if record.get("hamster_presence") not in {"yes", "no", "uncertain"}:
        raise ValueError("invalid hamster_presence")
    if record["review_state"] == "reviewed" and not str(record.get("reviewer", "")).strip():
        raise ValueError("reviewed labels require reviewer provenance")
    bbox = record.get("bbox")
    if bbox is not None:
        if not isinstance(bbox, dict) or set(bbox) != {"x", "y", "width", "height"}:
            raise ValueError("bbox must contain x, y, width, height")
        try:
            raw = [bbox[k] for k in ("x", "y", "width", "height")]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw):
                raise ValueError("bbox values must be numeric")
            x, y, w, h = map(float, raw)
        except (TypeError, ValueError):
            raise ValueError("bbox values must be finite numbers")
        if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1 or y + h > 1:
            raise ValueError("bbox must be finite, positive, and normalized within the frame")
        if record["hamster_presence"] == "no":
            raise ValueError("negative presence cannot have a hamster bbox")
    if record["hamster_presence"] == "yes" and record["visibility"] == "not_visible":
        raise ValueError("present hamster cannot be marked not_visible")


def validate_export(payload, manifest):
    if payload.get("schema") != "homestudio-identity-review-v1":
        raise ValueError("unsupported review schema")
    expected = {item["sample_id"]: item for item in manifest["samples"]}
    records = payload.get("samples")
    if not isinstance(records, list) or any(not isinstance(x, dict) for x in records) or len({x.get("sample_id") for x in records}) != len(records):
        raise ValueError("review samples must be a unique list")
    review_fields = {"sample_id", "source_sha256", "review_state", "hamster_presence", "visibility", "interference", "appearance", "scene", "reviewer", "bbox"}
    for record in records:
        if set(record) != review_fields:
            raise ValueError("review export may contain only review fields")
        sample = expected.get(record.get("sample_id"))
        if sample is None or record.get("source_sha256") != sample["source_sha256"]:
            raise ValueError("unknown sample or source fingerprint mismatch")
        validate_review(record)
    return records


def _observation_times(conn, event_id, duration):
    try:
        row = conn.execute("SELECT result_json FROM event_observations WHERE event_id=?", (event_id,)).fetchone()
    except sqlite3.Error:
        return []
    if not row:
        return []
    try:
        result = json.loads(row[0])
        intervals = result.get("intervals", [])
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    valid = []
    for interval in intervals:
        try:
            a, b = float(interval["start_sec"]), float(interval["end_sec"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(a) and math.isfinite(b) and 0 <= a <= b <= duration:
            valid.append((a, b))
    if not valid:
        return []
    center = (valid[len(valid) // 2][0] + valid[len(valid) // 2][1]) / 2
    return sorted({round(max(0.0, min(duration - .001, center + offset)), 3) for offset in (-.4, 0, .4)})


def _probe_duration(ffprobe, source):
    output = subprocess.run([str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(source)],
                           capture_output=True, text=True, timeout=TIMEOUT_SEC, check=True)
    metadata = json.loads(output.stdout)
    duration = float(metadata["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid source duration")
    stream = metadata["streams"][0]
    return duration, int(stream["width"]), int(stream["height"])


def _extract(ffmpeg, source, second, target):
    command = [str(ffmpeg), "-nostdin", "-v", "error", "-threads", "1", "-filter_threads", "1", "-ss", f"{second:.3f}", "-i", str(source),
               "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", "-q:v", "3", "-y", str(target)]
    subprocess.run(command, capture_output=True, timeout=TIMEOUT_SEC, check=True)
    if not target.is_file() or not target.stat().st_size:
        raise RuntimeError("decoder produced no frame")


def _require_complete_output(output):
    output = Path(output)
    if (output / "FAILED.txt").exists():
        raise ValueError("sampling output is marked incomplete")
    if not (output / "manifest.json").is_file():
        raise ValueError("sampling manifest is missing")


def _review_html(manifest):
    cards = []
    for s in manifest["samples"]:
        cards.append(f'''<article data-id="{html.escape(s['sample_id'])}" data-sha="{s['source_sha256']}">
<img src="{html.escape(s['image'])}" alt="sample {html.escape(s['sample_id'])}">
<p>Recorded time bucket: {html.escape(s['recorded_time_bucket'])} · {s['frame_sec']:.2f}s · {html.escape(s['split'])}</p>
<label>Review <select data-k="review_state"><option>unreviewed</option><option>reviewed</option></select></label>
<label>Presence <select data-k="hamster_presence"><option>uncertain</option><option>yes</option><option>no</option></select></label>
<label>Visibility <select data-k="visibility"><option>unknown</option><option>visible</option><option>occluded</option><option>not_visible</option></select></label>
<label>Interference <select data-k="interference"><option>unknown</option><option>caregiver</option><option>reflection</option><option>light</option><option>none</option></select></label>
<label>Appearance <select data-k="appearance"><option>unknown</option><option>color</option><option>monochrome</option><option>dark</option></select></label>
<label>Camera clock daypart <select data-k="scene"><option>unknown</option><option>day</option><option>night</option></select></label>
<label>Reviewer <input data-k="reviewer" autocomplete="off"></label>
<fieldset><legend>Optional normalized bbox (not pose)</legend>
<label>x <input data-b="x" type="number" min="0" max="1" step="0.001"></label><label>y <input data-b="y" type="number" min="0" max="1" step="0.001"></label>
<label>width <input data-b="width" type="number" min="0.001" max="1" step="0.001"></label><label>height <input data-b="height" type="number" min="0.001" max="1" step="0.001"></label></fieldset></article>''')
    details = []
    for detail in manifest.get("review_addenda", []):
        details.append(f'''<article><h2>Full-resolution review only</h2>
<img src="{html.escape(detail['file'])}" alt="full resolution review sample">
<p>{html.escape(detail['sample_id'])} · {detail['frame_sec']:.2f}s · 2304×1296 · excluded from training export</p></article>''')
    data = json.dumps(manifest, separators=(",", ":")).replace("</", "<\\/")
    return '''<!doctype html><meta charset="utf-8"><title>Private identity sample review</title>
<style>body{font:16px system-ui;max-width:1100px;margin:auto;background:#181818;color:#eee}article{display:inline-block;vertical-align:top;width:320px;margin:10px;padding:10px;background:#292929}img{width:100%;height:auto}label{display:block;margin:6px 0}input,select,button{font:inherit}fieldset label{display:inline-block;width:45%}</style>
<h1>Private identity sample review</h1><p>Manual review only. Unreviewed is not a negative label. Camera clock daypart must be reviewed from the frame. Visible color/monochrome does not establish infrared mode. Bounding boxes are normalized and are not pose labels.</p>
<button id="export">Validate and download review JSON</button><main>''' + "".join(cards) + "".join(details) + '''</main><script id="manifest" type="application/json">''' + data + '''</script><script>
const manifest=JSON.parse(document.getElementById('manifest').textContent);
function read(){return [...document.querySelectorAll('article[data-id]')].map(card=>{const r={sample_id:card.dataset.id,source_sha256:card.dataset.sha,review_state:card.querySelector('[data-k="review_state"]').value,hamster_presence:card.querySelector('[data-k="hamster_presence"]').value,visibility:card.querySelector('[data-k="visibility"]').value,interference:card.querySelector('[data-k="interference"]').value,appearance:card.querySelector('[data-k="appearance"]').value,scene:card.querySelector('[data-k="scene"]').value,reviewer:card.querySelector('[data-k="reviewer"]').value.trim(),bbox:null};const vals=Object.fromEntries([...card.querySelectorAll('[data-b]')].map(x=>[x.dataset.b,x.value]));if(Object.values(vals).some(Boolean)){if(Object.values(vals).some(v=>!v))throw Error('Complete all bbox coordinates or leave all blank');r.bbox=Object.fromEntries(Object.entries(vals).map(([k,v])=>[k,Number(v)]));}if(r.review_state==='reviewed'&&!r.reviewer)throw Error('Reviewed samples require reviewer provenance');if(r.bbox){const b=r.bbox;if(!Object.values(b).every(Number.isFinite)||b.x<0||b.y<0||b.width<=0||b.height<=0||b.x+b.width>1||b.y+b.height>1)throw Error('Invalid normalized bbox');}return r;});}
document.getElementById('export').onclick=()=>{try{const payload={schema:'homestudio-identity-review-v1',samples:read()};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='identity-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}catch(e){alert(e.message);}};
</script>'''


def _select_events(events, base, limit):
    candidates = []
    for event_id, raw_path, started, has_candidate in events:
        source = _contained_file(raw_path, base)
        if source is None:
            continue
        try:
            dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            local_dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))) if dt.tzinfo is None else dt.astimezone(timezone(timedelta(hours=9)))
        except ValueError:
            continue
        scene = "day" if 7 <= local_dt.hour < 19 else "night"
        candidates.append({"event_id": event_id, "source": source, "source_relative_path": source.relative_to(Path(base).resolve()).as_posix(),
            "started_at": str(started), "capture_day": local_dt.date().isoformat(), "recorded_time_bucket": scene,
            "has_candidate": bool(has_candidate)})
    # Round-robin capture days first, then balance day/night; candidate events lead each bucket.
    buckets = {}
    for item in sorted(candidates, key=lambda x: (not x["has_candidate"], x["started_at"])):
        buckets.setdefault((item["capture_day"], item["recorded_time_bucket"]), []).append(item)
    keys = sorted(buckets, key=lambda key: (key[0], key[1]))
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))
    return selected


def _assign_splits(items):
    dates = sorted({item["capture_day"] for item in items})
    parent = {day: day for day in dates}
    def find(day):
        while parent[day] != day:
            parent[day] = parent[parent[day]]
            day = parent[day]
        return day
    sha_day = {}
    for item in items:
        day, sha = item["capture_day"], item["source_sha256"]
        if sha in sha_day:
            parent[find(day)] = find(sha_day[sha])
        else:
            sha_day[sha] = day
    groups = sorted({find(day) for day in dates})
    group_split = {group: SPLITS[index % len(SPLITS)] for index, group in enumerate(groups)}
    return {day: (group_split[find(day)], f"capture-day:{find(day)}") for day in dates}, groups


def _reviewed_truth(records, manifest):
    samples = {sample["sample_id"]: sample for sample in manifest["samples"]}
    truth = []
    for record in records:
        if record["review_state"] != "reviewed" or record["hamster_presence"] == "uncertain":
            continue
        if record["hamster_presence"] == "yes" and record["bbox"] is None:
            continue
        bbox = record["bbox"]
        truth.append({**samples[record["sample_id"]], **{key: record[key] for key in ("review_state", "hamster_presence", "visibility", "interference", "appearance", "scene", "reviewer", "bbox")},
            "target_type": "centroid", "centroid_normalized": {"x": round(bbox["x"] + bbox["width"] / 2, 6), "y": round(bbox["y"] + bbox["height"] / 2, 6)} if bbox else None})
    return {"schema": "homestudio-reviewed-centroid-input-v1", "training_ready": False, "samples": truth}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--base-dir", type=Path)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=MAX_EVENTS)
    parser.add_argument("--validate-review", type=Path)
    args = parser.parse_args(argv)
    if args.validate_review:
        try:
            _require_complete_output(args.output)
        except ValueError as exc:
            parser.error(str(exc))
        manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
        records = validate_export(json.loads(args.validate_review.read_text(encoding="utf-8")), manifest)
        export = _reviewed_truth(records, manifest)
        target = args.output / "reviewed-truth.json"
        if target.exists():
            parser.error("refusing to overwrite existing reviewed truth export")
        target.write_text(json.dumps(export, indent=2), encoding="utf-8")
        print(json.dumps({"valid_review_records": len(records), "reviewed_truth_records": len(export["samples"]), "training_ready": False}, separators=(",", ":")))
        return 0
    required_sampling = ("database", "base_dir", "ffmpeg", "ffprobe", "snapshot")
    missing = [name for name in required_sampling if getattr(args, name) is None]
    if missing:
        parser.error("sampling requires " + ", ".join("--" + name.replace("_", "-") for name in missing))
    if not 1 <= args.limit <= MAX_EVENTS:
        parser.error(f"--limit must be 1..{MAX_EVENTS}")
    if args.output.exists():
        parser.error("refusing to overwrite existing output directory")
    if "runtime" not in {part.lower() for part in args.output.parts}:
        parser.error("output must be inside a private runtime directory")
    blocked = readiness(args.snapshot)
    if blocked:
        parser.error(f"sampling deferred: {blocked}")
    args.output.mkdir(parents=True)
    images = args.output / "images"
    images.mkdir()
    conn = _db_readonly(args.database)
    try:
        events = conn.execute("SELECT event_id, original_path, started_at FROM events WHERE homespace_id=1 ORDER BY started_at DESC LIMIT 500").fetchall()
        try:
            roi_row = conn.execute("SELECT revision FROM baseline_revisions WHERE homespace_id=1").fetchone()
            roi_revision = int(roi_row[0]) if roi_row else None
        except sqlite3.Error:
            roi_revision = None
        base = args.base_dir.resolve()
        candidate_ids = set()
        try:
            for event_id, raw_json in conn.execute("SELECT event_id, result_json FROM event_observations WHERE homespace_id=1"):
                result = json.loads(raw_json)
                if any(interval.get("state") == "candidate" for interval in result.get("intervals", [])):
                    candidate_ids.add(event_id)
        except (sqlite3.Error, ValueError, TypeError):
            pass
        selected = _select_events([(event_id, path, started, event_id in candidate_ids) for event_id, path, started in events], base, args.limit)
        if len(selected) != args.limit:
            raise RuntimeError(f"only {len(selected)} original files fit source containment and scene caps")
        for item in selected:
            digest = hashlib.sha256()
            with item["source"].open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            item["source_sha256"] = digest.hexdigest()
        scene_counts = {scene: sum(item["recorded_time_bucket"] == scene for item in selected) for scene in ("day", "night")}
        samples, source_records = [], []
        for item in selected:
            if (blocked := readiness(args.snapshot)):
                raise RuntimeError(f"sampling aborted before next source: {blocked}")
            duration, source_width, source_height = _probe_duration(args.ffprobe, item["source"])
            source_records.append({"event_id": item["event_id"], "source_relative_path": item["source_relative_path"],
                "source_sha256": item["source_sha256"], "capture_day": item["capture_day"], "recorded_time_bucket": item["recorded_time_bucket"],
                "time_reference": "events.started_at_local_kst", "duration_sec": round(duration, 3),
                "source_width": source_width, "source_height": source_height, "observed_candidate_available": item["has_candidate"]})
            times = _observation_times(conn, item["event_id"], duration)
            method = "observation_candidate" if times else "duration_fallback_25_50_75"
            if not times:
                times = [duration * .25, duration * .5, duration * .75]
            for index, second in enumerate(times):
                sid = f"s{hashlib.sha256(str(item['event_id']).encode()).hexdigest()[:12]}-{index + 1}"
                image = images / f"{sid}.jpg"
                _extract(args.ffmpeg, item["source"], second, image)
                samples.append({"sample_id": sid, "event_id": item["event_id"], "image": f"images/{image.name}",
                    "frame_sec": round(second, 3), "time_source": method, "recorded_time_bucket": item["recorded_time_bucket"],
                    "source_sha256": item["source_sha256"], "source_relative_path": item["source_relative_path"], "source_width": source_width, "source_height": source_height,
                    "roi_revision": roi_revision, "split": "", "split_group": "", "review_state": "unreviewed",
                    "hamster_presence": "uncertain", "bbox": None, "interference": "unknown", "visibility": "unknown", "appearance": "unknown", "reviewer": ""})
        day_assignment, groups = _assign_splits(selected)
        sha_split = {item["source_sha256"]: day_assignment[item["capture_day"]] for item in selected}
        for sample in samples:
            sample["split"], sample["split_group"] = sha_split[sample["source_sha256"]]
        manifest = {"schema": "homestudio-identity-samples-v1", "review_schema": "homestudio-identity-review-v1",
            "training_ready": False, "source_count": len(selected), "recorded_time_bucket_counts": scene_counts,
            "sources": source_records,
            "split_counts": {split: sum(s["split"] == split for s in samples) for split in SPLITS},
            "capture_day_count": len({item["capture_day"] for item in selected}), "split_group_count": len(groups),
            "split_readiness": "insufficient_capture_groups" if len(groups) < 3 or any(not sum(s["split"] == split for s in samples) for split in SPLITS) else "human_review_required",
            "roi_revision": roi_revision, "samples": samples}
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (args.output / "review.html").write_text(_review_html(manifest), encoding="utf-8")
        print(json.dumps({"status": "prepared", "source_count": len(selected), "frame_count": len(samples),
            "recorded_time_bucket_counts": scene_counts, "split_counts": manifest["split_counts"], "split_readiness": manifest["split_readiness"], "training_ready": False}, separators=(",", ":")))
    except Exception:
        (args.output / "FAILED.txt").write_text("Sampling incomplete; review and training export are blocked.\n", encoding="utf-8")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
