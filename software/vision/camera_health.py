"""Camera health state: online / privacy / dark / offline (P2-10)."""
import statistics


class CameraHealth:
    def __init__(self, dark_mean: float = 15.0, dark_std: float = 5.0, dark_frames: int = 10, fail_limit: int = 5):
        self.dark_mean, self.dark_std, self.dark_frames, self.fail_limit = dark_mean, dark_std, dark_frames, fail_limit
        self.privacy = False
        self.dark_count = 0
        self.fail_count = 0
        self.state = "online"

    @property
    def paused(self) -> bool:
        return self.privacy

    def _update(self) -> bool:
        if self.privacy:
            new = "privacy"
        elif self.fail_count >= self.fail_limit:
            new = "offline"
        elif self.dark_count >= self.dark_frames:
            new = "dark"
        else:
            new = "online"
        changed, self.state = new != self.state, new
        return changed

    def set_privacy(self, enabled: bool) -> bool:
        self.privacy = enabled
        return self._update()

    def fetch_failed(self) -> bool:
        self.fail_count += 1
        return self._update()

    def frame(self, gray: bytes) -> bool:
        """Returns True if state changed. Dark = near-black or near-uniform frame."""
        self.fail_count = 0
        dark = statistics.fmean(gray) < self.dark_mean or statistics.pstdev(gray) < self.dark_std
        self.dark_count = self.dark_count + 1 if dark else 0
        return self._update()
