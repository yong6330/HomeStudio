from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import subprocess
import time
import threading
import shutil
from typing import Optional, Tuple
import uuid

from ..backend.config import PipelineConfig

logger = logging.getLogger("homestudio.recorder")

class ClipRecorder:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._lock = threading.Lock()
        self._proc = None
        self._cancelled = False

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._proc and self._proc.poll() is None:
                self._proc.kill()

    def resume(self):
        with self._lock:
            self._cancelled = False

    def _run(self, cmd, timeout=120, input=None):
        with self._lock:
            if self._cancelled:
                raise RuntimeError("Media processing cancelled")
            proc = self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.communicate(input=input, timeout=timeout)
            return subprocess.CompletedProcess(cmd, proc.returncode, stderr=b'')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            with self._lock:
                self._proc = None

    def build_original_clip(self, segments, event_id, date_str):
        target = self.config.events_dir / date_str
        target.mkdir(parents=True, exist_ok=True)
        original = target / f"{event_id}_original.ts"
        preview = target / f"{event_id}_sub.mp4"
        thumb = self.config.thumbnails_dir / date_str / f"thumb_{event_id}.jpg"
        ok = False
        try:
            manifest = "ffconcat version 1.0\n" + "".join(
                "file 'file:%s'\n" % str(Path(p).resolve()).replace("\\", "/").replace("'", "'\\''")
                for p in segments)
            remux = [self.config.ffmpeg_bin, '-y', '-nostdin', '-v', 'error', '-xerror',
                     '-f', 'concat', '-safe', '0', '-protocol_whitelist', 'file,pipe', '-i', 'pipe:0',
                     '-map', '0:v:0', '-c:v', 'copy', '-an', '-f', 'mpegts', str(original)]
            if self._run(remux, input=manifest.encode()).returncode:
                return None, None, 0, None
            # Decode with explode so broken HEVC/TS never becomes a successful original.
            validate = [self.config.ffmpeg_bin, '-nostdin', '-v', 'error', '-xerror',
                        '-err_detect', 'explode', '-threads', '1', '-i', str(original),
                        '-map', '0:v:0', '-an', '-f', 'null', '-']
            if not original.stat().st_size or self._run(validate).returncode:
                return None, None, 0, None
            cmd = [self.config.ffmpeg_bin, '-y', '-nostdin', '-v', 'error', '-xerror',
                   '-threads', '1', '-filter_threads', '1', '-i', str(original), '-map', '0:v:0', '-an',
                   '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p',
                   '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-crf', '23',
                   '-movflags', '+faststart', str(preview)]
            if self._run(cmd).returncode or not preview.is_file():
                return None, None, 0, None
            if not self.extract_thumbnail(preview, thumb):
                return None, None, 0, None
            ok = True
            return preview, thumb, sum(p.stat().st_size for p in (original, preview, thumb)), original
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            logger.warning("Original clip unavailable; snapshot fallback for %s", event_id)
            return None, None, 0, None
        finally:
            if not ok:
                for path in (original, preview, thumb):
                    path.unlink(missing_ok=True)


    def extract_thumbnail(self, input_video_path: Path, output_thumb_path: Path) -> bool:
        """
        Extracts a representative JPEG thumbnail from the middle/start of the video clip.
        """
        output_thumb_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.config.ffmpeg_bin,
            "-y",
            "-nostdin",
            "-ss", "0.5",
            "-i", str(input_video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(output_thumb_path)
        ]
        try:
            res = self._run(cmd, timeout=10)
            if res.returncode == 0 and output_thumb_path.exists():
                latest_path = self.config.thumbnails_dir / "latest.jpg"
                try:
                    import shutil
                    shutil.copy2(output_thumb_path, latest_path)
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error(f"Failed to extract thumbnail from {input_video_path}: {e}")
        return False

    def build_snapshot_clip(
        self,
        frames: list,
        event_id: str,
        date_str: Optional[str] = None,
    ) -> Tuple[Optional[Path], Optional[Path], int]:
        """Builds an MP4 from buffered snapshot JPEG frames (snapshot source mode)."""
        frames = [Path(f) for f in frames if Path(f).exists()]
        if not frames:
            return None, None, 0
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        target_dir = self.config.events_dir / date_str
        target_dir.mkdir(parents=True, exist_ok=True)
        output_mp4 = target_dir / f"{event_id}_sub.mp4"
        list_file = target_dir / f"{event_id}_frames.txt"
        dur = 1.0 / max(self.config.snapshot_fps, 0.1)
        lines = []
        for f in frames:
            lines.append("file '%s'" % str(f.resolve()).replace("\\", "/"))
            lines.append(f"duration {dur:.3f}")
        lines.append("file '%s'" % str(frames[-1].resolve()).replace("\\", "/"))
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd = [self.config.ffmpeg_bin, "-y", "-nostdin", "-loglevel", "error",
               "-f", "concat", "-safe", "0", "-i", str(list_file),
               "-vf", "fps=%s,format=yuv420p" % max(int(round(self.config.snapshot_fps)), 1),
               "-c:v", "libx264", "-preset", "veryfast", "-movflags", "+faststart", str(output_mp4)]
        built = False
        try:
            res = self._run(cmd, timeout=60)
            if res.returncode != 0 or not output_mp4.exists():
                logger.error(f"Snapshot clip build failed for {event_id}: {res.stderr[-300:]!r}")
                return None, None, 0
            built = True
        finally:
            if not built:
                output_mp4.unlink(missing_ok=True)
            try:
                list_file.unlink()
            except Exception:
                pass
        thumb_path = self.config.thumbnails_dir / date_str / f"thumb_{event_id}.jpg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(frames[len(frames) // 2], thumb_path)
        try:
            shutil.copy2(thumb_path, self.config.thumbnails_dir / "latest.jpg")
        except Exception:
            pass
        return output_mp4, thumb_path, output_mp4.stat().st_size + thumb_path.stat().st_size

    def record_direct_clip(
        self,
        event_id: str,
        duration_sec: float,
        date_str: Optional[str] = None
    ) -> Tuple[Optional[Path], Optional[Path], int]:
        """
        Directly captures a high-speed lossless H.265 MP4 clip from the camera RTSP sub stream.
        """
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        target_dir = self.config.events_dir / date_str
        target_dir.mkdir(parents=True, exist_ok=True)
        
        output_mp4 = target_dir / f"{event_id}_sub.mp4"
        rtsp_url = self.config.get_rtsp_sub_url()

        cmd = [
            self.config.ffmpeg_bin,
            "-y",
            "-nostdin",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-t", str(max(round(duration_sec, 1), 2.0)),
            "-c:v", "copy",
            "-tag:v", "hvc1",
            "-movflags", "+faststart",
            "-an",
            str(output_mp4)
        ]

        try:
            res = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=int(duration_sec + 15))
            if res.returncode != 0 or not output_mp4.exists():
                logger.error(f"FFmpeg direct record failed for {event_id}")
                return None, None, 0

            file_size = output_mp4.stat().st_size
            thumb_dir = self.config.thumbnails_dir / date_str
            thumb_path = thumb_dir / f"thumb_{event_id}.jpg"
            self.extract_thumbnail(output_mp4, thumb_path)

            return output_mp4, thumb_path, file_size
        except Exception as e:
            logger.error(f"Error recording direct clip for {event_id}: {e}")
            return None, None, 0
