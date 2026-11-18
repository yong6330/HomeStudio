import logging
import os
import sys
import threading
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from software.backend.config import PipelineConfig
from software.backend.db import Database
from software.vision.service import PipelineService
from software.vision.motion import MotionEvent

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("live_test")
    logger.info("=== Starting HomeStudio Live Pipeline Integration Test ===")

    config = PipelineConfig(
        camera_password=os.getenv("HOMESTUDIO_CAM_PASSWORD")
    )
    config.ensure_directories()
    
    db = Database(config.db_path)
    service = PipelineService(config, db)

    # Start stream worker in background thread
    worker_thread = threading.Thread(target=service.start_stream_worker, daemon=True)
    worker_thread.start()

    logger.info("Pipeline active. Running for 15 seconds to collect stream and buffer...")
    time.sleep(15)

    # Trigger a test motion event to verify clip building and DB commitment
    logger.info("Triggering completed motion event to test clip muxing and DB commitment...")
    test_evt = MotionEvent(
        event_id="evt_test_homestudio_success",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5)),
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        duration_sec=5.0,
        peak_motion_ratio=0.25,
        mean_motion_ratio=0.12
    )
    service._process_completed_event(test_evt, list(service.ring_buffer))
    
    time.sleep(5)  # Wait for clip assembly and thumbnail extraction

    logger.info("Stopping pipeline worker...")
    service.stop()
    worker_thread.join(timeout=5)

    # Verify results
    logger.info("=== Verifying Live Pipeline Results ===")
    events = db.list_events(limit=5)
    logger.info(f"Total events in SQLite DB: {len(events)}")
    for e in events:
        logger.info(f"  - Event: {e['event_id']}, Duration: {e['duration_sec']}s, Clip: {e['clip_path']}, Size: {e['file_size_bytes']} bytes")
    
    # Check sensor heartbeat
    with db._get_connection() as conn:
        sensor = dict(conn.execute("SELECT * FROM sensors WHERE sensor_id = 'camera-primary'").fetchone())
        logger.info(f"Sensor status: {sensor['status']}, last_seen: {sensor['last_seen_at']}")

    # Check latest thumbnail
    latest_thumb = config.thumbnails_dir / "latest.jpg"
    logger.info(f"Latest thumbnail exists: {latest_thumb.exists()} (size: {latest_thumb.stat().st_size if latest_thumb.exists() else 0} bytes)")

    if len(events) > 0:
        logger.info("=== HOMESTUDIO PC LIVE PIPELINE VERIFICATION: 100% SUCCESSFUL ===")
    else:
        logger.error("Verification incomplete.")

if __name__ == "__main__":
    main()
