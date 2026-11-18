from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Optional

def _default_base_dir() -> Path:
    env_dir = os.getenv("HOMESTUDIO_BASE_DIR")
    if env_dir:
        return Path(env_dir)
    if os.name == 'nt':
        if Path("D:/").exists():
            return Path(r"D:\HomeStudio")
        return Path(r"C:\HomeStudio")
    return Path("./homestudio_data")

def _default_cam_ip() -> str:
    env_ip = os.getenv("HOMESTUDIO_CAM_IP")
    if env_ip:
        return env_ip
    # Default to homestudio LAN IP if known, otherwise fallback
    return "192.168.0.32"  # wired Ethernet (main)

@dataclass
class PipelineConfig:
    # Camera Stream Settings
    camera_ip: str = field(default_factory=_default_cam_ip)
    camera_port: int = int(os.getenv("HOMESTUDIO_CAM_PORT", "554"))
    camera_username: str = os.getenv("HOMESTUDIO_CAM_USER", "grok")
    camera_password: Optional[str] = os.getenv("HOMESTUDIO_CAM_PASSWORD", None)
    
    # Stream source: "snapshot" (HTTP LAPI JPEG polling, default) or "rtsp"
    stream_source: str = os.getenv("HOMESTUDIO_STREAM_SOURCE", "snapshot")
    http_port: int = int(os.getenv("HOMESTUDIO_CAM_HTTP_PORT", "80"))
    snapshot_path: str = "/LAPI/V1.0/Channels/1/Media/Video/Streams/0/Snapshot"
    snapshot_fps: float = float(os.getenv("HOMESTUDIO_SNAPSHOT_FPS", "2"))
    snapshot_timeout_sec: float = 5.0

    sub_stream_path: str = "/media/video2"
    main_stream_path: str = "/media/video1"
    
    # Motion Detection Settings
    motion_downscale_width: int = 160
    motion_downscale_height: int = 90
    motion_fps: int = 10
    motion_diff_threshold: int = 25
    motion_ratio_start_threshold: float = 0.015  # 1.5% pixels changed to trigger
    motion_ratio_end_threshold: float = 0.005    # 0.5% pixels changed to keep active
    motion_min_duration_sec: float = 2.0         # Discard bursts shorter than 2s
    motion_max_duration_sec: float = 60.0        # Split long events into 60s clips
    # false-event guards (evt_933fc5c53146: light strip at the glass edge + OSD clock + centroid teleports)
    motion_warmup_sec: float = 45.0              # no detection while the background is (re)learned (start, mask change)
    motion_border: float = 0.03                  # always-masked frame border
    motion_osd_box: tuple = (0.0, 0.0, 0.30, 0.09)  # camera clock overlay (top-left), always masked
    motion_min_blob_px: int = 16                 # at 160x90 (~hamster-sized at this zoom)
    motion_max_aspect: float = 4.0               # reject thin strips
    motion_min_fill: float = 0.3                 # reject sparse/ragged blobs
    motion_max_speed_px: float = 80.0            # px/s in the motion frame; farther = teleport
    motion_static_sec: float = 8.0               # a change that stays put this long is background
    motion_bright_jump: float = 2.5              # mean brightness off its slow average = light change; also >=3 blobs at once
    motion_edge_band: float = 0.08               # drop events whose track is mostly this close to the edge
    
    # Clip & Buffer Settings
    original_recording: bool = field(default_factory=lambda: os.getenv("HOMESTUDIO_ORIGINAL_RECORDING") == "1")
    pre_roll_sec: int = 5                        # 5s pre-event buffer
    post_roll_sec: int = 5                       # 5s post-event buffer
    
    # Storage Paths (Supports both C:\ and D:\ drives on Windows)
    base_dir: Path = field(default_factory=_default_base_dir)
    
    # Retention Settings
    max_storage_bytes: int = int(os.getenv("HOMESTUDIO_MAX_STORAGE_BYTES", 15 * 1024 * 1024 * 1024))  # 15 GB default
    min_free_disk_bytes: int = int(os.getenv("HOMESTUDIO_MIN_FREE_BYTES", 3 * 1024 * 1024 * 1024))   # 3 GB
    retention_check_interval_sec: int = 300      # Check every 5 minutes

    def __post_init__(self):
        if self.camera_password:
            self.camera_password = self.camera_password.strip()

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def events_dir(self) -> Path:
        return self.base_dir / "events"

    @property
    def thumbnails_dir(self) -> Path:
        return self.base_dir / "thumbnails"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "homestudio.db"

    @property
    def ffmpeg_bin(self) -> str:
        if os.name == 'nt':
            candidate = (self.base_dir / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")
            if candidate.exists():
                return str(candidate)
            return "ffmpeg.exe"
        return "ffmpeg"

    @property
    def ffprobe_bin(self) -> str:
        if os.name == 'nt':
            candidate = (self.base_dir / "tools" / "ffmpeg" / "bin" / "ffprobe.exe")
            if candidate.exists():
                return str(candidate)
            return "ffprobe.exe"
        return "ffprobe"

    def get_snapshot_url(self) -> str:
        """Credential-free URL; auth is handled by HTTP digest in SnapshotSource."""
        return f"http://{self.camera_ip}:{self.http_port}{self.snapshot_path}"

    def get_rtsp_sub_url(self) -> str:
        if self.camera_password:
            return f"rtsp://{self.camera_username}:{self.camera_password}@{self.camera_ip}:{self.camera_port}{self.sub_stream_path}"
        return f"rtsp://{self.camera_ip}:{self.camera_port}{self.sub_stream_path}"

    def get_rtsp_main_url(self) -> str:
        if self.camera_password:
            return f"rtsp://{self.camera_username}:{self.camera_password}@{self.camera_ip}:{self.camera_port}{self.main_stream_path}"
        return f"rtsp://{self.camera_ip}:{self.camera_port}{self.main_stream_path}"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
