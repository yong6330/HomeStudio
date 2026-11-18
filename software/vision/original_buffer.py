"""Bounded compressed main-stream buffer; no camera credentials leave stdin memory."""
import csv
import logging
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.parse import quote
import uuid

from . import digest

log = logging.getLogger('homestudio.original')


class OriginalBuffer:
    MAX_BYTES = 64 * 1024 * 1024
    RETRY_SEC = 600

    def __init__(self, config):
        self.config = config
        self.root = config.base_dir / 'original_buffer'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.proc = None
        self.closed = False
        self.session = None
        self.anchor = None
        self.ip = None
        self.retry_at = 0.0
        self.last_closed = 0.0
        self.segments = {}  # path -> (wall start, wall end, session)
        self.pins = {}  # event_id -> pre-roll wall start
        self.routed_identity = None
        self.bound_warning = None
        # A prior process's partial buffers have no trustworthy wall-time anchor.
        for path in self.root.iterdir():
            if path.is_dir():
                shutil.rmtree(path)

    def writer_input(self, ip, session):
        c = self.config
        user, password = quote(c.camera_username, safe=''), quote(c.camera_password or '', safe='')
        url = f'rtsp://{user}:{password}@{ip}:{c.camera_port}{c.main_stream_path}'
        manifest = f"ffconcat version 1.0\nfile '{url}'\noption rtsp_transport tcp\noption timeout 6000000\n"
        # shortcut: omit TVS-W1000's malformed prefix SEI; revisit for cameras requiring SEI metadata.
        cmd = [c.ffmpeg_bin, '-hide_banner', '-nostdin', '-loglevel', 'error',
               '-f', 'concat', '-safe', '0', '-protocol_whitelist', 'pipe,rtsp,tcp,udp', '-i', 'pipe:0',
               '-map', '0:v:0', '-c:v', 'copy', '-bsf:v', 'filter_units=remove_types=39',
               '-an', '-f', 'segment', '-segment_time', '2',
               '-segment_format', 'mpegts', '-reset_timestamps', '1',
               '-segment_list', str(session / 'index.csv'), '-segment_list_type', 'csv',
               '-segment_list_size', '64', str(session / '%06d.ts')]
        return cmd, manifest.encode()

    def _bound(self, source):
        import os
        from .camera_locator import ident, load_binding
        if os.getenv('HOMESTUDIO_CAM_IP'):
            return source.ip == os.environ['HOMESTUDIO_CAM_IP']
        if source.locator is None:
            return self._binding_denied('camera locator unavailable')
        binding = load_binding(source.locator.db) or {}
        table = source.locator.arp()
        if any(table.get(m['mac']) == source.ip for m in binding.get('macs', [])):
            self.routed_identity = None
            self.bound_warning = None
            return True
        if source.ip in table.values():
            self.routed_identity = None
            return self._binding_denied('source IP resolves to an unregistered MAC')
        if binding.get('ip') != source.ip or not binding.get('model') or not binding.get('serial_hash'):
            self.routed_identity = None
            return self._binding_denied('routed source lacks a registered serial identity')

        identity = (source.ip, binding['model'], binding['serial_hash'])
        now = time.monotonic()
        if self.routed_identity and self.routed_identity[:3] == identity and self.routed_identity[3] > now:
            return True
        try:
            verified = ident(source.locator.verify(source.ip))
        except Exception:
            verified = None
        if not verified or verified.get('model') != binding['model'] or verified.get('serial_hash') != binding['serial_hash']:
            self.routed_identity = None
            return self._binding_denied('routed source identity did not match registration')
        self.routed_identity = (*identity, now + 60)
        self.bound_warning = None
        return True

    def _binding_denied(self, reason):
        if self.bound_warning != reason:
            log.warning('Original recording gated by camera identity (%s)', reason)
            self.bound_warning = reason
        return False

    def tick(self, source, privacy):
        with self.lock:
            if self.closed:
                return
            if privacy is not False:
                self.pause()
                return
            now = time.time()
            if self.proc and self.ip != source.ip:
                self.pause()
            if self.proc:
                exit_code = self.proc.poll()
                if exit_code is not None or now - self.last_closed > 20:
                    # stderr may contain a credential URL. Never retain or log it.
                    self.pause()
                    self.retry_at = now + self.RETRY_SEC
                    if exit_code is not None:
                        log.warning('Original writer stopped (process exited, code=%s); retrying after backoff', exit_code)
                    else:
                        log.warning('Original writer stopped (no closed segments); retrying after backoff')
                    return
                self.read_closed(self.session, self.anchor)
                self.cleanup(now)
                total = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
                if total > self.MAX_BYTES or shutil.disk_usage(self.root).free < self.config.min_free_disk_bytes:
                    self.pause()
                    self.retry_at = now + self.RETRY_SEC
                return
            if now < self.retry_at or not digest.GATE.allowed() or not self._bound(source):
                return
            if shutil.disk_usage(self.root).free < self.config.min_free_disk_bytes + self.MAX_BYTES:
                return
            self.session = self.root / uuid.uuid4().hex
            self.session.mkdir()
            self.anchor, self.ip, self.last_closed = None, source.ip, now
            cmd, stdin = self.writer_input(source.ip, self.session)
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.proc.stdin.write(stdin)
                self.proc.stdin.close()
            except (OSError, ValueError):
                self.pause()
                self.retry_at = now + self.RETRY_SEC
                log.warning('Original writer unavailable; snapshot fallback remains active')

    def read_closed(self, session, anchor):
        index = session / 'index.csv'
        if not index.exists():
            return
        with self.lock:
            with index.open(newline='') as stream:
                for row in csv.reader(stream):
                    if len(row) != 3:
                        continue
                    try:
                        path = session / Path(row[0]).name
                        start, end = float(row[1]), float(row[2])
                    except ValueError:
                        continue
                    if not path.is_file() or end <= start:
                        continue
                    if anchor is None:
                        # Closed-file mtime tracks packet arrival, excluding connect and poll delay.
                        anchor = self.anchor = path.stat().st_mtime - end
                    if path not in self.segments:
                        self.last_closed = time.time()
                        self.segments[path] = (anchor + start, anchor + end, session)

    def pin(self, event_id, start):
        with self.lock:
            if len(self.pins) >= 4:
                return False
            self.pins[event_id] = start - self.config.pre_roll_sec
            return True

    def select(self, event_id, end):
        with self.lock:
            start = self.pins.get(event_id)
            if start is None or end - start > self.config.motion_max_duration_sec + self.config.pre_roll_sec + 10:
                return []
            rows = sorted(((p, *v) for p, v in self.segments.items() if v[1] > start and v[0] < end), key=lambda r: r[1])
            if not rows or rows[0][1] > start or rows[-1][2] < end:
                return []
            if any(a[3] != b[3] or abs(a[2] - b[1]) > .1 for a, b in zip(rows, rows[1:])):
                return []
            return [r[0] for r in rows]

    def release(self, event_id):
        with self.lock:
            self.pins.pop(event_id, None)
            for folder in self.root.iterdir():
                if folder.is_dir() and folder != self.session and not any(v[2] == folder for v in self.segments.values()):
                    try:
                        shutil.rmtree(folder)
                    except OSError:
                        log.warning('Original buffer cleanup deferred until reader exits')

    def cleanup(self, now):
        with self.lock:
            cutoff = min([now - self.config.pre_roll_sec - 4, *self.pins.values()])
            for path, (_, end, _) in list(self.segments.items()):
                if end < cutoff:
                    path.unlink(missing_ok=True)
                    del self.segments[path]

    def stop(self):
        with self.lock:
            self.closed = True
            self.pause()

    def pause(self):
        with self.lock:
            if self.proc:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait()
                self.proc = None
            self.pins.clear()
            self.segments.clear()
            self.anchor = self.session = None
            self.routed_identity = None
            for path in self.root.iterdir():
                if path.is_dir():
                    try:
                        shutil.rmtree(path)
                    except OSError:
                        # Windows may still have a conversion reader; release retries cleanup.
                        log.warning('Original buffer cleanup deferred until reader exits')
