"""Bounded reader for the pinned Espressif ESP32-S3 CSI_DATA CSV stream.

This is a capture/quality tool only. It does not infer activity or write raw data
unless the operator explicitly supplies --output.
"""
import argparse
import csv
import io
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "https://github.com/espressif/esp-csi/tree/8633d67152db2808f141cc1595970aa9cf406045"
COMMIT = "8633d67152db2808f141cc1595970aa9cf406045"
CSI_HEADER = (
    "type", "id", "mac", "rssi", "rate", "sig_mode", "mcs", "bandwidth", "smoothing",
    "not_sounding", "aggregation", "stbc", "fec_coding", "sgi", "noise_floor", "ampdu_cnt",
    "channel", "secondary_channel", "local_timestamp", "ant", "sig_len", "rx_state", "len",
    "first_word", "data",
)
MAX_LINE_BYTES = 64 * 1024
MAX_CSI_BYTES = 4096
MAX_DURATION_SEC = 600.0
MAX_IDLE_TIMEOUT_SEC = 60.0
MAX_SAMPLES = 100_000
MAX_RAW_BYTES = 64 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[2]


class LiveReader:
    def __init__(self, serial_port):
        self.serial_port = serial_port
        self.is_live = True

    def readline(self, size):
        return self.serial_port.readline(size)


class CSIParser:
    def __init__(self, max_line_bytes=MAX_LINE_BYTES, accept_headerless_data=False):
        if not isinstance(max_line_bytes, int) or max_line_bytes < 1 or max_line_bytes > MAX_LINE_BYTES:
            raise ValueError("invalid max line length")
        self.max_line_bytes = max_line_bytes
        self.accept_headerless_data = bool(accept_headerless_data)
        self.header_seen = False
        self.malformed_rows = 0
        self.skipped_lines = 0

    def feed(self, line):
        if isinstance(line, bytes):
            try:
                line = line.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                self.malformed_rows += 1
                return None
        if not isinstance(line, str):
            self.malformed_rows += 1
            return None
        if len(line.encode("utf-8")) > self.max_line_bytes:
            self.malformed_rows += 1
            raise ValueError("CSI line exceeds maximum length")
        line = line.strip("\r\n")
        if not line:
            self.skipped_lines += 1
            return None
        try:
            row = next(csv.reader([line], strict=True))
        except (csv.Error, StopIteration):
            self.malformed_rows += 1
            return None
        if tuple(row) == CSI_HEADER:
            self.header_seen = True
            return None
        if row and row[0] == "type":
            raise ValueError("unexpected CSI header; expected pinned ESP32-S3 CSV schema")
        if not row or row[0] != "CSI_DATA":
            self.skipped_lines += 1
            return None
        if not self.header_seen and not self.accept_headerless_data:
            self.malformed_rows += 1
            return None
        if len(row) != len(CSI_HEADER):
            self.malformed_rows += 1
            return None
        try:
            values = dict(zip(CSI_HEADER, row))
            numeric = [k for k in CSI_HEADER[1:-1] if k != "mac"]
            for key in numeric:
                values[key] = int(values[key], 10)
            first = values["first_word"]
            nbytes = values["len"]
            if first not in (0, 1) or nbytes < 1 or nbytes > MAX_CSI_BYTES:
                raise ValueError("invalid CSI length/first_word")
            raw = values["data"].strip()
            if len(raw) < 2 or raw[0] != "[" or raw[-1] != "]":
                raise ValueError("invalid CSI data array")
            body = raw[1:-1].strip()
            data = [] if not body else [int(part.strip(), 10) for part in body.split(",")]
            if len(data) != nbytes or any(v < -128 or v > 127 for v in data):
                raise ValueError("CSI data length/value mismatch")
            analysis_data = data[4:] if first else data
            amplitudes = [round(math.hypot(analysis_data[i], analysis_data[i + 1]), 4)
                          for i in range(0, len(analysis_data) - 1, 2)]
            meta = {key: values[key] for key in CSI_HEADER[1:-1]}
            return {"sequence": values["id"], "board_timestamp_raw": row[18],
                    "first_word_invalid": bool(first), "metadata": meta,
                    "data": data, "amplitude": amplitudes}
        except (ValueError, OverflowError):
            self.malformed_rows += 1
            return None


class SequenceTracker:
    """Counts visible gaps and resets; it never treats board time as synchronized."""
    def __init__(self):
        self.previous = None
        self.epoch = 0
        self.gaps = 0
        self.missing = 0
        self.resets = 0
        self.wraps = 0

    def observe(self, seq):
        gap, reset, wrap = 0, False, False
        if self.previous is not None:
            if self.previous > 2_147_483_000 and seq < -2_147_483_000:
                wrap = True
                self.wraps += 1
            elif self.previous < -2_147_483_000 and 0 <= seq <= 1_000:
                reset = True
                self.epoch += 1
                self.resets += 1
            elif seq < self.previous:
                reset = True
                self.epoch += 1
                self.resets += 1
            elif seq > self.previous + 1:
                gap = seq - self.previous - 1
                self.gaps += 1
                self.missing += gap
        self.previous = seq
        return {"epoch": self.epoch, "gap": gap, "reset": reset, "wrap": wrap}


class CaptureSession:
    def __init__(self, duration_sec=60.0, idle_timeout_sec=10.0, max_samples=MAX_SAMPLES,
                 max_output_bytes=MAX_RAW_BYTES, max_line_bytes=MAX_LINE_BYTES):
        if not isinstance(duration_sec, (int, float)) or not 0 < duration_sec <= MAX_DURATION_SEC:
            raise ValueError(f"duration must be >0 and <= {MAX_DURATION_SEC}s")
        if not isinstance(idle_timeout_sec, (int, float)) or not 0 < idle_timeout_sec <= MAX_IDLE_TIMEOUT_SEC:
            raise ValueError(f"idle timeout must be >0 and <= {MAX_IDLE_TIMEOUT_SEC}s")
        if not isinstance(max_samples, int) or not 1 <= max_samples <= MAX_SAMPLES:
            raise ValueError(f"sample limit must be 1..{MAX_SAMPLES}")
        if not isinstance(max_output_bytes, int) or not 1 <= max_output_bytes <= MAX_RAW_BYTES:
            raise ValueError(f"output limit must be 1..{MAX_RAW_BYTES} bytes")
        self.duration_sec = float(duration_sec)
        self.idle_timeout_sec = float(idle_timeout_sec)
        self.max_samples = max_samples
        self.max_output_bytes = max_output_bytes
        self.parser = CSIParser(max_line_bytes)
        self.sequence = SequenceTracker()

    def _validate_output(self, output):
        if output is None:
            return None
        path = Path(output).expanduser().resolve()
        if path == REPO_ROOT or REPO_ROOT in path.parents:
            raise ValueError("raw CSI output must be outside the Git worktree")
        if not path.parent.is_dir():
            raise ValueError("output directory must already exist")
        if path.exists():
            raise FileExistsError(path)
        return path

    def run(self, reader, output=None, clock=None):
        clock = clock or time.monotonic
        output_path = self._validate_output(output)  # fail before reading any input
        start = clock()
        last_data = start
        stop_reason = "eof"
        samples = invalid_first = output_bytes = 0
        writer = output_path.open("xb") if output_path else None
        try:
            while True:
                now = clock()
                if now - start >= self.duration_sec:
                    stop_reason = "duration_limit"
                    break
                if now - last_data >= self.idle_timeout_sec:
                    stop_reason = "idle_timeout"
                    break
                raw = reader.readline(self.parser.max_line_bytes + 1)
                if raw in (b"", ""):
                    # File/pipe EOF is immediate; serial timeout is an empty read before idle deadline.
                    if getattr(reader, "is_live", False):
                        continue
                    stop_reason = "eof"
                    break
                last_data = clock()
                try:
                    sample = self.parser.feed(raw)
                except ValueError as exc:
                    if "maximum length" in str(exc):
                        stop_reason = "line_limit"
                        break
                    raise
                if sample is None:
                    continue
                sample["sequence_state"] = self.sequence.observe(sample["sequence"])
                sample["capture_host_utc"] = datetime.now(timezone.utc).isoformat()
                sample["capture_monotonic_ns"] = time.monotonic_ns()
                samples += 1
                invalid_first += int(sample["first_word_invalid"])
                if writer:
                    envelope = {"source": "espressif/esp-csi", "source_commit": COMMIT, "sample": sample}
                    blob = (json.dumps(envelope, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
                    if output_bytes + len(blob) > self.max_output_bytes:
                        raise ValueError("raw CSI output size limit reached")
                    writer.write(blob)
                    writer.flush()
                    output_bytes += len(blob)
                if samples >= self.max_samples:
                    stop_reason = "sample_limit"
                    break
        finally:
            if writer:
                writer.close()
        ended = clock()
        return {"source": "espressif/esp-csi", "source_commit": COMMIT,
                "samples": samples, "malformed_rows": self.parser.malformed_rows,
                "skipped_lines": self.parser.skipped_lines, "first_word_invalid_samples": invalid_first,
                "sequence_gaps": self.sequence.gaps, "missing_sequence_count": self.sequence.missing,
                "sequence_resets": self.sequence.resets, "sequence_wraps": self.sequence.wraps,
                "duration_sec": round(max(0.0, ended - start), 3), "stop_reason": stop_reason,
                "raw_saved": bool(output_path), "raw_bytes": output_bytes}


def _args(argv=None):
    p = argparse.ArgumentParser(description="Bounded Espressif CSI_DATA reader; summary-only unless --output is explicit.")
    p.add_argument("--port", help="USB serial device (COMx on Windows, /dev/cu.* on macOS)")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--duration", type=float, default=60.0, help="capture duration, 0..600 seconds (default 60)")
    p.add_argument("--idle-timeout", type=float, default=10.0)
    p.add_argument("--output", help="explicit JSONL path outside this worktree; must not already exist")
    a = p.parse_args(argv)
    # Validate all user inputs before opening a serial port or reading stdin.
    CaptureSession(a.duration, a.idle_timeout)
    if not isinstance(a.baud, int) or a.baud < 1200 or a.baud > 4_000_000:
        p.error("--baud must be 1200..4000000")
    if a.port is not None and (not a.port.strip() or len(a.port) > 256):
        p.error("invalid --port")
    if a.output:
        CaptureSession(a.duration, a.idle_timeout)._validate_output(a.output)
    return a


def main(argv=None):
    try:
        args = _args(argv)
        serial_port = None
        if args.port:
            try:
                import serial
            except ImportError:
                print("pyserial is optional and is not installed; use stdin or install pyserial in an isolated tool environment.", file=sys.stderr)
                return 2
            serial_port = serial.Serial(args.port, baudrate=args.baud, timeout=0.25)
            reader = LiveReader(serial_port)
        else:
            if sys.stdin.isatty():
                print("stdin must be a finite CSV file/pipe; use --port for live capture.", file=sys.stderr)
                return 2
            reader = sys.stdin.buffer
        session = CaptureSession(args.duration, args.idle_timeout)
        result = session.run(reader, output=args.output)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"CSI capture stopped: {exc}", file=sys.stderr)
        return 2
    finally:
        if "serial_port" in locals() and serial_port is not None:
            serial_port.close()


if __name__ == "__main__":
    raise SystemExit(main())
