from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
import queue
from pathlib import Path
import subprocess
import threading
import time
from typing import Optional, Deque, List
import uuid

from ..backend.config import PipelineConfig
from ..backend.db import Database
from ..backend.retention import RetentionManager
from .motion import MotionDetector, MotionEvent
from ..backend import behavior
from .clip_recorder import ClipRecorder
from .snapshot_source import SnapshotSource
from .camera_health import CameraHealth
from .original_buffer import OriginalBuffer

logger = logging.getLogger("homestudio.pipeline")
ACTIVITY_SETTING_KEY = "vision_activity_v1"
ACTIVITY_HEARTBEAT_SEC = 30.0


def rtsp_allowed() -> bool:
    """Legacy RTSP detection puts credentials in argv; secure original recording uses stdin instead."""
    return os.getenv("HOMESTUDIO_ALLOW_RTSP") == "1"


class PipelineService:
    def __init__(self, config: PipelineConfig, db: Optional[Database] = None):
        self.config = config
        self.config.ensure_directories()
        self.db = db or Database(config.db_path)
        self.retention = RetentionManager(self.config, self.db)
        self.recorder = ClipRecorder(self.config)
        self.original = OriginalBuffer(config) if config.original_recording and config.stream_source == "snapshot" else None
        self._media_lock = threading.RLock()
        self._media_generation = 0
        self._media_paused = False
        self._snapshot_pins = {}
        self._event_queue = queue.Queue(maxsize=2)
        self._event_worker = None
        self._worker_stop = threading.Event()
        
        self.temp_buffer_dir = self.config.base_dir / "temp_buffer"
        self.temp_buffer_dir.mkdir(parents=True, exist_ok=True)
        
        self.detector = MotionDetector(
            width=config.motion_downscale_width,
            height=config.motion_downscale_height,
            fps=(config.snapshot_fps if config.stream_source == "snapshot" else config.motion_fps),
            diff_threshold=config.motion_diff_threshold,
            start_ratio=config.motion_ratio_start_threshold,
            end_ratio=config.motion_ratio_end_threshold,
            min_duration_sec=config.motion_min_duration_sec,
            max_duration_sec=config.motion_max_duration_sec,
            post_roll_sec=config.post_roll_sec,
            on_event_start=self._on_motion_start,
            on_event_end=self._on_motion_end,
            on_event_discard=self._on_motion_discard,
            min_blob_px=config.motion_min_blob_px, warmup_sec=config.motion_warmup_sec, border=config.motion_border,
            osd_box=config.motion_osd_box, max_aspect=config.motion_max_aspect, min_fill=config.motion_min_fill,
            max_speed_px=config.motion_max_speed_px, static_sec=config.motion_static_sec,
            bright_jump=config.motion_bright_jump, edge_band=config.motion_edge_band,
        )
        
        self.running = False
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        
        if self.config.stream_source == "snapshot":
            pre = max(int(self.config.pre_roll_sec * self.config.snapshot_fps), 1)
            self.ring_buffer: Deque[Path] = deque(maxlen=pre)
        else:
            self.ring_buffer = deque(maxlen=6)
        self.active_event_segments: List[Path] = []
        self.is_recording_event = False
        self.current_event_id: Optional[str] = None
        self.last_retention_check = time.time()
        self._activity_episode_start = 0.0
        self._activity_start_notified = False
        self._last_detector_frame_at = 0.0
        self._activity_state_published: Optional[str] = None
        self._activity_last_write_at = 0.0
        self._activity_seen_at: Optional[str] = None
        self._publish_activity_state("unknown", force=True)

    def _publish_activity_state(self, state: str, seen_at: Optional[float] = None, force: bool = False) -> None:
        """Publish bounded, space-scoped detector state for the API process."""
        if state not in ("active", "idle", "unknown"):
            state = "unknown"
        now = time.time()
        if seen_at is not None and state in ("active", "idle"):
            self._activity_seen_at = datetime.fromtimestamp(seen_at, timezone.utc).isoformat()
        if not force and state == self._activity_state_published and now - self._activity_last_write_at < ACTIVITY_HEARTBEAT_SEC:
            return
        value = json.dumps({"state": state, "activity_seen_at": self._activity_seen_at}, separators=(",", ":"))
        try:
            with self.db._get_connection() as conn:
                conn.execute("""INSERT INTO space_settings(homespace_id,key,value) VALUES(1,?,?)
                    ON CONFLICT(homespace_id,key) DO UPDATE SET value=excluded.value""",
                    (ACTIVITY_SETTING_KEY, value))
        except Exception as e:
            logger.warning("Activity state publish failed: %s", type(e).__name__)
        self._activity_state_published = state
        self._activity_last_write_at = now

    def _activity_from_frame(self, now: float, motion_ratio: float, warming: bool, camera_state: str = "online") -> None:
        """Expose observed movement only; detector event post-roll is not current activity."""
        if warming or self.detector.roi_pixels <= 0 or camera_state != "online":
            self._publish_activity_state("unknown")
            return
        recent = 0 <= now - self.detector.last_active_ts <= max(2.5, 3.0 / max(self.detector.fps, 1))
        active = bool(self.detector.is_active and motion_ratio > 0 and recent)
        self._publish_activity_state("active" if active else "idle", seen_at=now)

    def _prepare_detector_frame(self, now: float) -> None:
        if self._last_detector_frame_at and now - self._last_detector_frame_at > 10:
            # A camera gap is missing observation, not evidence that an activity ended.
            if self.is_recording_event:
                self._on_motion_discard(now)
            self._activity_episode_start = 0.0
            self._activity_start_notified = False
            self.detector.is_active = False
            self.detector.episode_start_ts = 0.0
            self.detector.quiet_frames = 0
        self._last_detector_frame_at = now

    def _activity_notifications_after_frame(self, now: float) -> None:
        episode = self.detector.episode_start_ts
        if self.detector.is_active and episode:
            if episode != self._activity_episode_start:
                self._activity_episode_start = episode
                self._activity_start_notified = False
            if now - episode >= 30 * 60 and not self._activity_start_notified:
                self._notify_activity("start", episode, now)
                self._activity_start_notified = True
            return
        episode = self._activity_episode_start
        if not episode:
            return
        end = self.detector.last_active_ts or now
        if end - episode >= 30 * 60:
            if not self._activity_start_notified:
                self._notify_activity("start", episode, episode + 30 * 60)
            self._notify_activity("end", episode, end)
        self._activity_episode_start = 0.0
        self._activity_start_notified = False

    def _notify_activity(self, phase: str, episode: float, at: float) -> None:
        from ..backend import insights
        started = datetime.fromtimestamp(episode, timezone.utc).isoformat(timespec="seconds")
        observed = datetime.fromtimestamp(at, timezone.utc)
        with self.db._get_connection() as c:
            row = c.execute("SELECT name FROM care_targets WHERE homespace_id=1 ORDER BY created_at LIMIT 1").fetchone()
        pet = row[0] if row and row[0] else "반려동물"
        if phase == "start":
            title, body = f"{pet}가 30분째 활동하고 있어요", f"{observed.astimezone(insights.KST):%H:%M}까지 연속 활동이 관찰됐어요. 실제 모습도 함께 살펴봐 주세요."
        else:
            title, body = f"{pet}의 연속 활동이 끝났어요", f"{observed.astimezone(insights.KST):%H:%M}에 30분 이상 이어진 움직임 기록이 마무리됐어요."
        insights.add_notification(self.db, f"activity:{phase}:{started}", "activity", "info", title, body, now=observed)

    def _on_motion_start(self, timestamp: float) -> None:
        if self.is_recording_event and self.current_event_id:
            logger.warning(f"Motion start while event {self.current_event_id} still open; discarding stale state")
            if self.original:
                self.original.release(self.current_event_id)
        self.current_event_id = f"evt_{uuid.uuid4().hex[:12]}"
        self.is_recording_event = True
        self.active_event_segments = list(self.ring_buffer)
        if self.original:
            self.original.pin(self.current_event_id, timestamp)
        logger.info(f"Motion Event START [{self.current_event_id}] - Pre-roll segments: {len(self.active_event_segments)}")

    def _on_motion_discard(self, timestamp: float) -> None:
        logger.info(f"Motion Event DISCARD [{self.current_event_id}] - shorter than min duration")
        if self.original and self.current_event_id:
            self.original.release(self.current_event_id)
        self.is_recording_event = False
        self.current_event_id = None
        self.active_event_segments = []

    def _on_motion_end(self, event: MotionEvent) -> None:
        event_id = self.current_event_id or f"evt_{uuid.uuid4().hex[:12]}"
        event.event_id = event_id
        self.is_recording_event = False
        self.current_event_id = None
        
        segments_to_build = list(self.active_event_segments)
        self.active_event_segments = []
        
        logger.info(f"Motion Event END [{event_id}] - Muxing {len(segments_to_build)} segments, Duration: {event.duration_sec}s")
        
        with self._media_lock:
            if self._media_paused or self._worker_stop.is_set():
                if self.original:
                    self.original.release(event_id)
                return
            if self._event_worker is None:
                self._event_worker = threading.Thread(target=self._event_loop, daemon=True)
                self._event_worker.start()
            try:
                self._event_queue.put_nowait((event, segments_to_build, self._media_generation))
                self._snapshot_pins[event_id] = segments_to_build
            except queue.Full:
                if self.original:
                    self.original.release(event_id)
                # Detection metadata remains available when conversion falls behind.
                self._process_completed_event(event, [], self._media_generation, use_original=False)

    def _event_loop(self):
        while not self._worker_stop.is_set():
            try:
                event, segments, generation = self._event_queue.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                self._process_completed_event(event, segments, generation)
            finally:
                with self._media_lock:
                    self._snapshot_pins.pop(event.event_id, None)
                    if self.original:
                        self.original.release(event.event_id)
                self._event_queue.task_done()

    def _pause_media(self):
        with self._media_lock:
            self._media_generation += 1
            self._media_paused = True
            self.recorder.cancel()
            if self.original:
                self.original.pause()
            if self.is_recording_event:
                self._on_motion_discard(time.time())
            self._activity_episode_start = 0.0
            self._activity_start_notified = False
            self.detector.is_active = False
            self.detector.episode_start_ts = 0.0
            self._last_detector_frame_at = 0.0
            self.ring_buffer.clear()
            self.active_event_segments.clear()
            for frame in self.temp_buffer_dir.glob('seg_*.jpg'):
                try:
                    frame.unlink()
                except OSError:
                    pass
            self._snapshot_pins.clear()
            while True:
                try:
                    self._event_queue.get_nowait()
                    self._event_queue.task_done()
                except queue.Empty:
                    break

    def _process_completed_event(self, event: MotionEvent, segments: List[Path], generation=None, use_original=True) -> None:
        generation = self._media_generation if generation is None else generation
        date_str = datetime.fromisoformat(event.started_at.replace('Z', '+00:00')).strftime("%Y%m%d")
        registered = False
        try:
            with self._media_lock:
                if generation != self._media_generation or self._media_paused:
                    return
                self.recorder.resume()
            
            # Original failure falls back only to snapshots from this same event.
            clip_path: Optional[Path] = None
            thumb_path: Optional[Path] = None
            size_bytes = 0
            original_path = None
            if self.original and use_original:
                # Event metadata ends at last detected motion; preserve clip post-roll independently.
                end = datetime.fromisoformat(event.ended_at.replace('Z', '+00:00')).timestamp() + self.config.post_roll_sec
                deadline = time.monotonic() + 8
                original_segments = []
                while time.monotonic() < deadline:
                    with self._media_lock:
                        if generation != self._media_generation or self._media_paused:
                            return
                    original_segments = self.original.select(event.event_id, end + 1)
                    if original_segments or event.event_id not in self.original.pins:
                        break
                    if self._worker_stop.wait(.2):
                        return
                if original_segments:
                    clip_path, thumb_path, size_bytes, original_path = self.recorder.build_original_clip(
                        original_segments, event.event_id, date_str)
            if not clip_path and segments and str(segments[0]).lower().endswith(".jpg"):
                clip_path, thumb_path, size_bytes = self.recorder.build_snapshot_clip(
                    segments, event.event_id, date_str
                )
            with self._media_lock:
                if generation != self._media_generation or self._media_paused:
                    return
                self.db.insert_event(
                    original_path=str(original_path) if original_path else None,
                    event_type="motion",
                    started_at=event.started_at,
                    ended_at=event.ended_at,
                    duration_sec=event.duration_sec,
                    activity_score=event.mean_motion_ratio,
                    quality_score=1.0,
                    clip_path=str(clip_path) if clip_path and clip_path.exists() else None,
                    thumbnail_path=str(thumb_path) if thumb_path and thumb_path.exists() else None,
                    file_size_bytes=size_bytes,
                    event_id=event.event_id,
                    distance_px=event.distance_px,
                    active_frames=event.active_frames,
                    track_json=json.dumps(event.track, separators=(",", ":")),
                    behavior_json=json.dumps(behavior.features(event.track), separators=(",", ":"))
                )
                registered = True
            logger.info(f"Event {event.event_id} recorded in DB: size={size_bytes} bytes, clip={clip_path}, distance={event.distance_px}px, active_frames={event.active_frames}")
        except Exception as e:
            logger.error("Failed to process completed event %s: %s", event.event_id, type(e).__name__)
        finally:
            if not registered:
                for folder, pattern in ((self.config.events_dir / date_str, f"{event.event_id}_*"),
                                        (self.config.thumbnails_dir / date_str, f"thumb_{event.event_id}.*")):
                    for path in folder.glob(pattern):
                        path.unlink(missing_ok=True)

    def _cleanup_old_temp_segments(self) -> None:
        with self._media_lock:
            keep_set = set(self.ring_buffer) | set(self.active_event_segments)
            keep_set.update(p for paths in self._snapshot_pins.values() for p in paths)
        for p in self.temp_buffer_dir.glob("seg_*.*"):
            if p not in keep_set:
                try:
                    if (time.time() - p.stat().st_mtime) > 300:  # > max event (60s) + pre-roll + async mux time
                        p.unlink()
                except Exception:
                    pass

    def start_stream_worker(self) -> None:
        if self.config.stream_source == "snapshot":
            return self.start_snapshot_worker()
        if not rtsp_allowed():
            logger.error("RTSP source disabled: ffmpeg would get the camera password on its command line "
                         "(visible in the process list). Use snapshot, or set HOMESTUDIO_ALLOW_RTSP=1 on a single-user PC.")
            return
        self.running = True
        frame_size = self.config.motion_downscale_width * self.config.motion_downscale_height
        seg_pattern = str(self.temp_buffer_dir / "seg_%05d.ts").replace("\\", "/")

        while self.running:
            rtsp_url = self.config.get_rtsp_sub_url()
            logger.info("Connecting to camera RTSP sub stream...")

            cmd = [
                self.config.ffmpeg_bin,
                "-y",
                "-nostdin",
                "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                # Output 1: TS Segments for Ring Buffer
                "-map", "0:v",
                "-c:v", "copy",
                "-f", "segment",
                "-segment_time", "2",
                "-segment_format", "mpegts",
                "-reset_timestamps", "1",
                seg_pattern,
                # Output 2: Raw grayscale frames for MotionDetector
                "-map", "0:v",
                "-vf", f"fps={self.config.motion_fps},scale={self.config.motion_downscale_width}:{self.config.motion_downscale_height}",
                "-pix_fmt", "gray",
                "-f", "rawvideo",
                "-an",
                "pipe:1"
            ]

            try:
                self._ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                
                logger.info("Stream worker active. Processing frames...")
                self.db.update_sensor_heartbeat()
                last_heartbeat = time.time()
                frames_processed = 0

                while self.running and self._ffmpeg_proc.poll() is None:
                    raw_frame = self._ffmpeg_proc.stdout.read(frame_size)
                    if not raw_frame or len(raw_frame) != frame_size:
                        break

                    now = time.time()
                    frames_processed += 1
                    self._prepare_detector_frame(now)
                    
                    # 1. Process motion detection
                    warming = self.detector.bg_frame is None or self.detector.warm_left > 0
                    ratio, _ = self.detector.process_frame(raw_frame, now)
                    self._activity_from_frame(now, ratio, warming)
                    self._activity_notifications_after_frame(now)

                    # 2. Track segments in ring buffer
                    segments = sorted(self.temp_buffer_dir.glob("seg_*.ts"), key=os.path.getmtime)
                    if segments:
                        latest = segments[-1]
                        if not self.ring_buffer or latest != self.ring_buffer[-1]:
                            self.ring_buffer.append(latest)
                            if self.is_recording_event and latest not in self.active_event_segments:
                                self.active_event_segments.append(latest)

                    # 3. Periodic heartbeat & retention
                    if (now - last_heartbeat) > 10:
                        self.db.update_sensor_heartbeat()
                        logger.info(f"Pipeline active: {frames_processed} frames analyzed. Current motion: {'ACTIVE' if self.detector.is_active else 'IDLE'}")
                        last_heartbeat = now

                    if (now - self.last_retention_check) > self.config.retention_check_interval_sec:
                        self.retention.check_and_clean()
                        self._cleanup_old_temp_segments()
                        self.last_retention_check = now

            except Exception as e:
                logger.error(f"Stream worker error: {e}")
            finally:
                if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
                    try:
                        self._ffmpeg_proc.terminate()
                        self._ffmpeg_proc.wait(timeout=3)
                    except Exception:
                        self._ffmpeg_proc.kill()

            if self.running:
                logger.warning("Stream disconnected. Waiting 5s before reconnecting...")
                time.sleep(5)

    def _health_changed(self, health: CameraHealth) -> None:
        logger.warning(f"Camera health -> {health.state}")
        self.db.update_sensor_heartbeat(status=health.state)
        if health.state != "online":
            self._publish_activity_state("unknown")

    def _apply_cage_mask(self) -> None:
        """Re-read the user's 'cage' zone (motion mask); no cage zone = whole frame."""
        from ..backend import zones
        try:
            cage = next((z["points"] for z in zones.load(self.db) if z["kind"] == "cage"), None)
        except Exception as e:
            logger.warning(f"zone load failed: {type(e).__name__}")
            return
        if cage != getattr(self, "_cage", "unset"):
            self._cage = cage
            self.detector.set_roi(cage)  # also restarts the background model + warm-up
            logger.info(f"cage mask: {'whole frame' if cage is None else f'{len(cage)} points'}")

    def start_snapshot_worker(self) -> None:
        try:
            self._snapshot_loop()
        finally:
            self.stop()

    def _snapshot_loop(self) -> None:
        """HTTP Snapshot polling loop (fallback when RTSP delivers no RTP payload)."""
        self.running = True
        from .camera_locator import make_source
        src = make_source(self.config, self.db)  # bound camera by MAC (HOMESTUDIO_CAM_IP overrides)
        health = CameraHealth()
        logger.info(f"Snapshot worker active: {src.url} @ {self.config.snapshot_fps} fps")
        self.db.update_sensor_heartbeat()
        last_heartbeat = time.time()
        last_privacy_check = 0.0
        privacy = None
        frames_processed = 0
        seq = 0
        latest = self.config.thumbnails_dir / "latest.jpg"
        while self.running:
            t0 = time.time()
            if t0 - last_privacy_check >= 30:
                last_privacy_check = t0
                self._apply_cage_mask()
                privacy = src.fetch_privacy()
                if privacy is True or (self.original and privacy is None):
                    self._pause_media()
                    # Unknown privacy must discard detection state as well as persisted media.
                    self.detector.is_active = False
                    self.detector.bg_frame = None
                    self._publish_activity_state("unknown")
                elif privacy is False:
                    with self._media_lock:
                        self._media_paused = False
                if privacy is not None and health.set_privacy(privacy):
                    self._health_changed(health)
            if health.paused or self._media_paused:
                if t0 == last_privacy_check:
                    self.db.update_sensor_heartbeat(status=health.state)  # keep last_seen fresh while paused
                time.sleep(1.0)
                continue
            if self.original:
                try:
                    self.original.tick(src, privacy)
                except (OSError, ValueError):
                    self.original.pause()
                    logger.warning("Original buffer unavailable; snapshot detection continues")
            jpeg = src.fetch_jpeg()
            if jpeg is None:
                if health.fetch_failed():
                    self._health_changed(health)
                time.sleep(min(5.0, src.interval * health.fail_count))
                continue
            seq += 1
            frame_path = self.temp_buffer_dir / f"seg_{seq:06d}.jpg"
            frame_path.write_bytes(jpeg)
            try:
                latest.write_bytes(jpeg)
            except Exception:
                pass
            self.ring_buffer.append(frame_path)
            if self.is_recording_event:
                self.active_event_segments.append(frame_path)
            gray = src.jpeg_to_gray(jpeg)
            if gray:
                frames_processed += 1
                if health.frame(gray):
                    self._health_changed(health)
                self._prepare_detector_frame(t0)
                warming = self.detector.bg_frame is None or self.detector.warm_left > 0
                ratio, _ = self.detector.process_frame(gray, t0)
                self._activity_from_frame(t0, ratio, warming, health.state)
                self._activity_notifications_after_frame(t0)
            now = time.time()
            if (now - last_heartbeat) > 10:
                self.db.update_sensor_heartbeat(status=health.state)
                logger.info(f"Pipeline active (snapshot): {frames_processed} frames analyzed. Camera: {health.state}. Current motion: {'ACTIVE' if self.detector.is_active else 'IDLE'}")
                last_heartbeat = now
            if (now - self.last_retention_check) > self.config.retention_check_interval_sec:
                self.retention.check_and_clean()
                self._cleanup_old_temp_segments()
                self.last_retention_check = now
            time.sleep(max(0.0, src.interval - (time.time() - t0)))

    def stop(self) -> None:
        self.running = False
        self._worker_stop.set()
        if self.original:
            self.original.stop()
        self._pause_media()
        if self._event_worker and self._event_worker is not threading.current_thread():
            self._event_worker.join(timeout=5)
        if self.original:
            self.original.pause()
        if self._ffmpeg_proc and self._ffmpeg_proc.poll() is None:
            try:
                self._ffmpeg_proc.terminate()
            except Exception:
                pass
