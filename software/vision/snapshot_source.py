"""HTTP Snapshot frame source (fallback for cameras whose RTSP sends no RTP payload).

Polls the Uniview LAPI snapshot endpoint with HTTP digest auth and converts each
JPEG to a downscaled grayscale buffer for MotionDetector via ffmpeg.
"""
import json
import logging
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional

from ..backend.config import PipelineConfig

logger = logging.getLogger("homestudio.snapshot")


class SnapshotSource:
    def __init__(self, config: PipelineConfig, opener=None, locator=None, clock=None):
        from datetime import datetime, timezone
        self.config = config
        self.locator, self.clock = locator, clock or (lambda: datetime.now(timezone.utc))
        self.fails, self.retry_at = 0, None
        from .camera_locator import BACKOFF_MIN
        self.backoff, self.resolve_at = BACKOFF_MIN, None
        self.mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        if opener is None:
            # Digest only: a Basic handler would send the password in clear text to whatever answers at a stale IP
            from .digest import opener as digest_opener
            opener = digest_opener(self.mgr)  # one credentialed try per request, global backoff on 401
        self.opener = opener
        self.set_ip(config.camera_ip)
        self.interval = 1.0 / max(config.snapshot_fps, 0.1)

    def set_ip(self, ip: str) -> None:
        self.ip = self.config.camera_ip = ip
        self.url = self.config.get_snapshot_url()
        self.privacy_url = f"http://{ip}:{self.config.http_port}/LAPI/V1.0/System/PrivacyProtection"
        if self.config.camera_password:
            self.mgr.add_password(None, f"http://{ip}:{self.config.http_port}/", self.config.camera_username, self.config.camera_password)

    def _result(self, ok: bool) -> None:
        """Count consecutive failures; after a few, re-resolve the bound camera by MAC. While on a non-wired
        interface, retry the preferred (wired) MAC every PREFERRED_RETRY_MIN minutes."""
        if not self.locator:
            return
        from datetime import timedelta
        from .camera_locator import BACKOFF_MAX, BACKOFF_MIN, FAILS_BEFORE_RESOLVE, PREFERRED_RETRY_MIN, load_binding
        self.fails = 0 if ok else self.fails + 1
        found = None
        if ok:
            self.backoff, self.resolve_at = BACKOFF_MIN, None
        if self.fails >= FAILS_BEFORE_RESOLVE and (self.resolve_at is None or self.clock() >= self.resolve_at):
            self.fails = 0
            found = self.locator.resolve()
            if not found:  # camera really gone: sweep less and less often (15 s -> 10 min)
                self.resolve_at = self.clock() + timedelta(seconds=self.backoff)
                self.backoff = min(self.backoff * 2, BACKOFF_MAX)
        elif ok:
            b = load_binding(self.locator.db) or {}
            if b.get("iface") not in (None, "wired") and any(m["iface"] == "wired" for m in b.get("macs", [])):
                now = self.clock()
                if self.retry_at is None:
                    self.retry_at = now + timedelta(minutes=PREFERRED_RETRY_MIN)
                elif now >= self.retry_at:
                    self.retry_at = now + timedelta(minutes=PREFERRED_RETRY_MIN)
                    found = self.locator.resolve(only=["wired"])
        if found and found[0] != self.ip:
            old = self.ip
            self.set_ip(found[0])
            self.locator.switched(found[0], found[1], found[2], old)
            self.retry_at = None

    def fetch_jpeg(self) -> Optional[bytes]:
        try:
            req = urllib.request.Request(self.url, headers={"Connection": "close"})
            with self.opener.open(req, timeout=self.config.snapshot_timeout_sec) as r:
                data = r.read()
            if data[:2] != b"\xff\xd8":
                logger.warning("Snapshot response is not a JPEG")
                self._result(False)
                return None
            self._result(True)
            return data
        except (urllib.error.URLError, OSError) as e:
            logger.warning(f"Snapshot fetch failed: {getattr(e, 'code', '')} {type(e).__name__}")
            self._result(False)
            return None

    def fetch_privacy(self) -> Optional[bool]:
        """LAPI privacy (lens retracted) flag; None if unknown."""
        try:
            with self.opener.open(urllib.request.Request(self.privacy_url), timeout=self.config.snapshot_timeout_sec) as r:
                v = bool(json.loads(r.read())["Response"]["Data"]["Enabled"])
            self._result(True)
            return v
        except Exception as e:
            logger.warning(f"Privacy status fetch failed: {type(e).__name__}")
            self._result(False)  # while paused for privacy this is the only poll, so it must also drive re-resolution
            return None

    def set_privacy(self, enabled: bool) -> bool:
        """LAPI PUT PrivacyProtection: re-sends the camera's current Data with only Enabled changed."""
        try:
            with self.opener.open(urllib.request.Request(self.privacy_url), timeout=self.config.snapshot_timeout_sec) as r:
                data = json.loads(r.read())["Response"]["Data"]
            data["Enabled"] = 1 if enabled else 0
            req = urllib.request.Request(self.privacy_url, data=json.dumps(data).encode(), method="PUT",
                                         headers={"Content-Type": "application/json"})
            with self.opener.open(req, timeout=self.config.snapshot_timeout_sec) as r:
                return json.loads(r.read())["Response"]["ResponseCode"] == 0
        except Exception as e:
            logger.warning(f"Privacy set failed: {type(e).__name__}")
            return False

    def jpeg_to_gray(self, jpeg: bytes) -> Optional[bytes]:
        w, h = self.config.motion_downscale_width, self.config.motion_downscale_height
        cmd = [self.config.ffmpeg_bin, "-nostdin", "-loglevel", "error", "-f", "image2pipe",
               "-i", "pipe:0", "-vf", f"scale={w}:{h}", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"]
        try:
            res = subprocess.run(cmd, input=jpeg, capture_output=True, timeout=10)
            if res.returncode == 0 and len(res.stdout) == w * h:
                return res.stdout
        except Exception as e:
            logger.error(f"JPEG decode failed: {e}")
        return None
