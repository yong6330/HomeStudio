import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any

from .config import PipelineConfig
from .db import Database

logger = logging.getLogger("homestudio.retention")

class RetentionManager:
    def __init__(self, config: PipelineConfig, db: Database):
        self.config = config
        self.db = db

    def check_and_clean(self) -> Dict[str, Any]:
        """
        Checks total media storage and disk free space.
        If limits are exceeded, purges oldest unprotected clips until within limits.
        """
        stats = {
            "deleted_count": 0,
            "freed_bytes": 0,
            "total_media_bytes": 0,
            "free_disk_bytes": 0,
            "status": "ok"
        }

        # 1. Check disk free space
        try:
            total, used, free = shutil.disk_usage(self.config.base_dir)
            stats["free_disk_bytes"] = free
        except Exception as e:
            logger.warning(f"Could not read disk usage for {self.config.base_dir}: {e}")
            free = self.config.min_free_disk_bytes + 1  # Fallback

        # 2. Check total media size in DB
        total_media = self.db.get_total_media_bytes()
        stats["total_media_bytes"] = total_media

        needs_cleanup = (
            total_media > self.config.max_storage_bytes or
            free < self.config.min_free_disk_bytes
        )

        if not needs_cleanup:
            return stats

        logger.info(
            f"Retention triggered: total_media={total_media / 1024**2:.1f}MB / max={self.config.max_storage_bytes / 1024**2:.1f}MB, "
            f"free_disk={free / 1024**2:.1f}MB / min={self.config.min_free_disk_bytes / 1024**2:.1f}MB"
        )

        # 3. Retrieve oldest unprotected events and delete media files
        unprotected = self.db.get_unprotected_events_oldest_first(limit=200)
        
        for evt in unprotected:
            if total_media <= (self.config.max_storage_bytes * 0.85) and free >= self.config.min_free_disk_bytes:
                break

            event_id = evt["event_id"]
            freed_for_evt = 0
            failed = False
            roots = [self.config.events_dir.resolve(), self.config.thumbnails_dir.resolve()]
            for key in ("clip_path", "original_path", "thumbnail_path"):
                if not evt.get(key):
                    continue
                path = Path(evt[key]).resolve()
                if path.name == "latest.jpg" or not any(root in path.parents for root in roots):
                    failed = True
                    continue
                try:
                    if path.exists():
                        size = path.stat().st_size
                        path.unlink()
                        freed_for_evt += size
                except OSError:
                    failed = True
                    logger.warning("Could not remove event media %s", event_id)
            if failed:
                # Keep references so failed Windows unlinks can be retried.
                continue

            # Update DB to reflect deleted media
            self.db.mark_event_media_deleted(event_id)
            stats["deleted_count"] += 1
            stats["freed_bytes"] += freed_for_evt
            total_media -= evt["file_size_bytes"]
            free += freed_for_evt

        stats["total_media_bytes"] = total_media
        stats["free_disk_bytes"] = free
        logger.info(f"Retention complete: deleted {stats['deleted_count']} clips, freed {stats['freed_bytes'] / 1024**2:.2f}MB")
        return stats
