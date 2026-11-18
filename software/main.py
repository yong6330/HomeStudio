"""HomeStudio service entrypoint.

Run:  python software/main.py   (or: python -m software.main from the repo root)
Camera password comes from HOMESTUDIO_CAM_PASSWORD (set by tools/start_service.py from stdin); never logged.
Logs go to HOMESTUDIO_LOG_DIR (default <base_dir>/logs) and stdout unless --no-stdout.
"""
import argparse
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from software.backend.config import PipelineConfig  # noqa: E402
from software.backend.db import Database  # noqa: E402
from software.vision.service import PipelineService  # noqa: E402


def setup_logging(log_dir: Path, to_stdout: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(log_dir / "service.log", encoding="utf-8")]
    if to_stdout:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="HomeStudio video event pipeline")
    ap.add_argument("--no-stdout", action="store_true", help="log to file only (detached mode)")
    args = ap.parse_args(argv)

    config = PipelineConfig()
    log_dir = Path(os.getenv("HOMESTUDIO_LOG_DIR", str(config.base_dir / "logs")))
    setup_logging(log_dir, not args.no_stdout)
    (log_dir / "service.pid").write_text(str(os.getpid()))
    logger = logging.getLogger("homestudio.main")
    logger.info(f"Service start pid={os.getpid()} source={config.stream_source} fps={config.snapshot_fps}")

    service = PipelineService(config, Database(config.db_path))

    def sig_handler(signum, frame):
        logger.info(f"Signal {signum} received. Stopping pipeline...")
        service.stop()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        service.start_stream_worker()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt. Exiting...")
    finally:
        service.stop()


if __name__ == "__main__":
    main()
