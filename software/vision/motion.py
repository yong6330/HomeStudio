from dataclasses import dataclass, field
import math
from datetime import datetime, timezone
import time
from typing import Optional, Tuple, List, Callable

import cv2
import numpy as np

@dataclass
class MotionEvent:
    event_id: str
    started_at: str
    ended_at: str
    duration_sec: float
    peak_motion_ratio: float
    mean_motion_ratio: float
    trigger_type: str = "motion"
    distance_px: float = 0.0
    active_frames: int = 0
    track: List[Tuple[float, float, float]] = field(default_factory=list)  # (t_offset_sec, x, y)

class MotionDetector:
    def __init__(
        self,
        width: int = 160,
        height: int = 90,
        fps: int = 10,
        diff_threshold: int = 25,
        start_ratio: float = 0.015,
        end_ratio: float = 0.005,
        min_duration_sec: float = 2.0,
        max_duration_sec: float = 60.0,
        post_roll_sec: float = 5.0,
        bg_history_sec: float = 60.0,
        min_blob_px: int = 4,
        # false-event guards (all off by default; the service turns them on, see PipelineConfig)
        warmup_sec: float = 0.0,             # ignore motion this long after (re)starting the background model
        border: float = 0.0,                 # always-masked frame border (fraction of width/height)
        osd_box: Optional[Tuple[float, float, float, float]] = None,  # always-masked camera clock overlay (x0, y0, x1, y1)
        max_aspect: Optional[float] = None,  # reject blobs longer than this ratio (thin light strips/edges)
        min_fill: float = 0.0,               # reject blobs filling less than this share of their bbox
        max_speed_px: Optional[float] = None,  # px/s: farther blobs are teleports, not the same animal
        static_sec: Optional[float] = None,  # a blob that stays put this long is absorbed into the background
        bright_jump: Optional[float] = None,  # brightness jump (0-255) that marks an exposure/light change
        edge_band: float = 0.0,              # drop events whose track lies mostly within this band of the frame edge
        edge_share: float = 0.6,
        on_event_start: Optional[Callable[[float], None]] = None,
        on_event_end: Optional[Callable[[MotionEvent], None]] = None,
        on_event_discard: Optional[Callable[[float], None]] = None
    ):
        self.width = width
        self.height = height
        self.total_pixels = width * height
        self.fps = fps
        self.diff_threshold = diff_threshold
        self.start_ratio = start_ratio
        self.end_ratio = end_ratio
        self.min_duration_sec = min_duration_sec
        self.max_duration_sec = max_duration_sec
        self.post_roll_sec = post_roll_sec
        self.bg_history = max(int(bg_history_sec * fps), 1)  # MOG2 adapts to static changes over ~this window
        
        self.on_event_start = on_event_start
        self.on_event_end = on_event_end
        self.on_event_discard = on_event_discard
        
        self.bg_frame = None  # cv2 MOG2 subtractor; None = (re)initialise on next frame
        self.last_centroid: Optional[Tuple[float, float]] = None
        self.min_blob_px = min_blob_px
        self.warmup_frames = int(warmup_sec * fps)
        self.max_aspect, self.min_fill, self.max_speed_px = max_aspect, min_fill, max_speed_px
        self.static_frames = int(static_sec * fps) if static_sec else 0
        self.bright_jump, self.edge_band, self.edge_share = bright_jump, edge_band, edge_share
        self.warm_left = 0
        self.prev_mean: Optional[float] = None
        self.prev_ts: Optional[float] = None
        self.still = 0
        self.lost = 0
        self.fixed = np.full((height, width), 255, np.uint8)  # border + OSD, always excluded
        bx, by = int(round(border * width)), int(round(border * height))
        if bx or by:
            self.fixed[:by, :] = 0; self.fixed[height - by:, :] = 0; self.fixed[:, :bx] = 0; self.fixed[:, width - bx:] = 0
        if osd_box:
            x0, y0, x1, y1 = osd_box
            self.fixed[int(y0 * height):int(np.ceil(y1 * height)), int(x0 * width):int(np.ceil(x1 * width))] = 0
        self.roi_bounds = self._mask_bounds(self.fixed)
        self._kernel = np.ones((3, 3), np.uint8)
        self.track: List[Tuple[float, float, float]] = []
        self.roi = None  # uint8 mask (255 = analysed); None = whole frame
        self.roi_pixels = self.total_pixels
        self.is_active = False
        self.event_start_ts: float = 0.0
        self.episode_start_ts: float = 0.0
        self.event_start_iso: str = ""
        self.last_active_ts: float = 0.0
        
        self.ratios_in_event: List[float] = []
        self.quiet_frames: int = 0
        self.post_roll_frames = int(post_roll_sec * fps)

    def _illumination(self, img: np.ndarray) -> np.ndarray:
        """OpenCV illumination normalization (divide by a wide Gaussian).

        A lamp, exposure change, or broad reflection lifts the local average and
        disappears. A small high-contrast animal remains. This is cv2.divide, not
        a custom detector.
        """
        sigma = max(self.width * 0.45, 1.0)
        mask = self.roi if self.roi is not None else self.fixed
        if mask.min() == 0:
            # Normalize only observed pixels: excluded motion must not change the cage's lighting field.
            weights = (mask != 0).astype(np.float32)
            field = cv2.GaussianBlur(img * weights, (0, 0), sigmaX=sigma)
            field /= np.maximum(cv2.GaussianBlur(weights, (0, 0), sigmaX=sigma), 1e-6)
            normalized = cv2.divide(img, np.maximum(field, 1), scale=128, dtype=cv2.CV_8U)
            normalized[mask == 0] = 0
            return normalized
        field = cv2.GaussianBlur(img, (0, 0), sigmaX=sigma)
        return cv2.divide(img, np.maximum(field, 1), scale=128)

    @staticmethod
    def _mask_bounds(mask: np.ndarray) -> Tuple[int, int, int, int]:
        ys, xs = np.nonzero(mask)
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def set_roi(self, points: Optional[List[List[float]]]) -> None:
        """Cage mask: motion outside this normalized polygon is ignored (people walking past). None = whole frame."""
        roi = np.zeros((self.height, self.width), np.uint8)
        if points is not None:
            if points:
                cv2.fillPoly(roi, [np.array([[round(x * (self.width - 1)), round(y * (self.height - 1))] for x, y in points], np.int32)], 255)
        else:
            roi[:] = 255
        roi = cv2.bitwise_and(roi, self.fixed)
        n = cv2.countNonZero(roi)
        if points is None and n == self.total_pixels:
            self.roi, self.roi_pixels = None, self.total_pixels
        else:
            self.roi, self.roi_pixels = roi, n
        self.roi_bounds = self._mask_bounds(self.roi if self.roi is not None else self.fixed) if n else (0, 0, 0, 0)
        self._reset_tracking(time.time())

    def _reset_tracking(self, timestamp: float) -> None:
        """Clear scene/event state when the analysed pixels change or become empty."""
        if self.is_active and self.on_event_discard:
            self.on_event_discard(timestamp)
        self.is_active = False
        self.event_start_ts = 0.0
        self.episode_start_ts = 0.0
        self.event_start_iso = ""
        self.last_active_ts = 0.0
        self.last_centroid = None
        self.track = []
        self.ratios_in_event = []
        self.quiet_frames = 0
        self.prev_ts = None
        self.prev_mean = None
        self.still = 0
        self.lost = 0
        self._fresh = True
        self.bg_frame = None  # new area: relearn (and warm up) before detecting

    def _add_track(self, timestamp: float) -> None:
        if self.last_centroid and getattr(self, "_fresh", True):  # no stale repeats while the blob is lost
            x, y = self.last_centroid
            self.track.append((round(timestamp - self.event_start_ts, 2), round(x, 1), round(y, 1)))

    def process_frame(self, gray_frame: bytes, timestamp: Optional[float] = None) -> Tuple[float, Optional[MotionEvent]]:
        """
        Processes a raw grayscale frame buffer (length = width * height).
        Returns (motion_ratio, completed_event_or_None).
        """
        if timestamp is None:
            timestamp = time.time()

        if len(gray_frame) != self.total_pixels:
            raise ValueError(f"Expected {self.total_pixels} bytes for {self.width}x{self.height}, got {len(gray_frame)}")

        raw = np.frombuffer(gray_frame, dtype=np.uint8).reshape(self.height, self.width)
        mask = self.roi if self.roi is not None else self.fixed
        if self.roi_pixels == 0:
            self._reset_tracking(timestamp)
            return 0.0, None
        if mask.min() == 0:
            pixels = np.sort(raw[mask != 0])
            trim = pixels.size // 10
            # Trim foreground extremes while retaining broad partial lighting changes that a median misses.
            mean = float(pixels[trim:pixels.size - trim].mean()) if pixels.size else 0.0
        else:
            mean = float(raw.mean())
        img = self._illumination(raw)
        # lighting change (sun/cloud, lamp, exposure): brightness drifts away from its slow average -> not animal motion
        lit = self.bright_jump is not None and self.prev_mean is not None and abs(mean - self.prev_mean) >= self.bright_jump
        self.prev_mean = mean if self.prev_mean is None or lit else 0.95 * self.prev_mean + 0.05 * mean
        if self.bg_frame is None:
            # MOG2 background model (ezTrack-style: foreground mask -> centroid), own implementation
            self.bg_frame = cv2.createBackgroundSubtractorMOG2(history=self.bg_history, varThreshold=self.diff_threshold, detectShadows=False)
            self.bg_frame.apply(img, learningRate=1.0)
            self.last_centroid = None
            self.warm_left, self.still, self.lost = self.warmup_frames, 0, 0
            return 0.0, None
        if self.warm_left > 0:  # warm-up: learn the scene (auto rate), no detection
            self.warm_left -= 1
            self.bg_frame.apply(img)
            return 0.0, None

        mask = self.bg_frame.apply(img, learningRate=1.0 / self.bg_history)  # fixed rate; MOG2 auto rate is ~1/(2n) at warm-up and absorbs motion
        if self.roi is not None:
            mask = cv2.bitwise_and(mask, self.roi)
        elif self.fixed.min() == 0:
            mask = cv2.bitwise_and(mask, self.fixed)
        diff_count = cv2.countNonZero(mask)
        # blobs after opening (speckle removed)
        n, _, stats, cents = cv2.connectedComponentsWithStats(cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel))
        ok = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < self.min_blob_px:
                continue
            if self.max_aspect and max(w, h) > self.max_aspect * min(w, h):
                continue  # thin strip (window light at the glass edge, door frame)
            if self.min_fill and area < self.min_fill * w * h:
                continue
            ok.append(i)
        robust = bool(self.max_aspect or self.min_fill or self.max_speed_px)
        qualifying = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= self.min_blob_px]
        if qualifying:
            roi_x0, roi_y0, roi_x1, roi_y1 = self.roi_bounds
            roi_width, roi_height = roi_x1 - roi_x0 + 1, roi_y1 - roi_y0 + 1
            min_x = min(stats[i, cv2.CC_STAT_LEFT] for i in qualifying)
            min_y = min(stats[i, cv2.CC_STAT_TOP] for i in qualifying)
            max_x = max(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] - 1 for i in qualifying)
            max_y = max(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] - 1 for i in qualifying)
            # Local body parts can form several blobs; light/reflections need broad spread in both cage axes.
            global_blobs = len(qualifying) >= 3 and (max_x - min_x + 1) >= 0.6 * roi_width and (max_y - min_y + 1) >= 0.6 * roi_height
        else:
            global_blobs = False
        if robust and (lit or global_blobs):
            # Broad lighting changes are absorbed; compact multi-part motion remains eligible.
            self.bg_frame.apply(img, learningRate=0.3)
            ok, self.still = [], 0
        pick = max(ok, key=lambda i: stats[i, cv2.CC_STAT_AREA], default=None)
        prev = self.last_centroid if self.is_active else None
        if self.max_speed_px and prev is not None and ok:
            dt = max(timestamp - (self.prev_ts or timestamp), 1.0 / self.fps)
            near = min(ok, key=lambda i: math.dist(cents[i], prev))
            pick = near if math.dist(cents[near], prev) <= self.max_speed_px * dt else None  # teleport: not the animal
        self.prev_ts = timestamp
        new_c = tuple(cents[pick]) if pick is not None else None
        if new_c is None and prev is not None and self.max_speed_px:  # keep the last position briefly (robust mode)
            self.lost += 1
            if self.lost >= 3:  # lost the animal: next blob anywhere may start the track again
                self.last_centroid = None
        else:
            self.lost = 0
            self.last_centroid = new_c
        if self.static_frames and new_c is not None and prev is not None and math.dist(new_c, prev) < 1.5:
            self.still += 1
            if self.still >= self.static_frames:  # a change that does not move (moved object, light patch): absorb it
                self.bg_frame.apply(img, learningRate=0.5)
                self.still, new_c, self.last_centroid = 0, None, None
        else:
            self.still = 0
        motion_ratio = (float(stats[pick, cv2.CC_STAT_AREA]) if pick is not None and new_c is not None else 0.0) / self.roi_pixels if robust \
            else diff_count / self.roi_pixels  # thresholds are relative to the analysed (cage) area
        # robust mode: a hamster is a few dozen px of 14k, so start/keep on "a valid, continuous blob is present"
        trig = (1.0 if new_c is not None else 0.0) if robust else motion_ratio
        self._fresh = new_c is not None or not robust
        completed_event: Optional[MotionEvent] = None

        if not self.is_active:
            # Check for motion start
            if trig >= self.start_ratio:
                self.is_active = True
                self.event_start_ts = timestamp
                self.episode_start_ts = timestamp
                self.event_start_iso = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                self.last_active_ts = timestamp
                self.ratios_in_event = [motion_ratio]
                self.quiet_frames = 0
                self.track = []
                self._add_track(timestamp)
                if self.on_event_start:
                    self.on_event_start(timestamp)
        else:
            # Active motion event
            self.ratios_in_event.append(motion_ratio)
            self._add_track(timestamp)
            
            if trig >= self.end_ratio:
                self.last_active_ts = timestamp
                self.quiet_frames = 0
            else:
                self.quiet_frames += 1

            duration = timestamp - self.event_start_ts
            is_quiet_expired = self.quiet_frames >= self.post_roll_frames
            is_max_reached = duration >= self.max_duration_sec

            if is_quiet_expired or is_max_reached:
                effective_duration = self.last_active_ts - self.event_start_ts
                
                edge = self.edge_band and self.track and sum(
                    1 for _, x, y in self.track if min(x, self.width - 1 - x) < self.edge_band * self.width or min(y, self.height - 1 - y) < self.edge_band * self.height
                ) >= self.edge_share * len(self.track)
                if (effective_duration >= self.min_duration_sec or is_max_reached) and not edge:
                    peak = max(self.ratios_in_event) if self.ratios_in_event else 0.0
                    mean = sum(self.ratios_in_event) / len(self.ratios_in_event) if self.ratios_in_event else 0.0
                    end_iso = datetime.fromtimestamp(self.last_active_ts, timezone.utc).isoformat()
                    
                    completed_event = MotionEvent(
                        event_id="",
                        started_at=self.event_start_iso,
                        ended_at=end_iso,
                        duration_sec=round(effective_duration, 2),
                        peak_motion_ratio=round(peak, 4),
                        mean_motion_ratio=round(mean, 4),
                        distance_px=round(sum(math.dist(a[1:], b[1:]) for a, b in zip(self.track, self.track[1:])), 2),
                        active_frames=len(self.track),
                        track=self.track,
                    )
                    if self.on_event_end:
                        self.on_event_end(completed_event)
                elif self.on_event_discard:
                    # Started but too short: let listeners close the open event state
                    self.on_event_discard(timestamp)
                
                if is_max_reached and trig >= self.start_ratio:
                    self.event_start_ts = timestamp
                    self.event_start_iso = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                    self.last_active_ts = timestamp
                    self.ratios_in_event = [motion_ratio]
                    self.quiet_frames = 0
                    self.track = []
                    self._add_track(timestamp)
                    # Continuation segment after max-duration split is a new event
                    if self.on_event_start:
                        self.on_event_start(timestamp)
                else:
                    self.is_active = False
                    self.episode_start_ts = 0.0
                    self.ratios_in_event = []
                    self.quiet_frames = 0

        return motion_ratio, completed_event
