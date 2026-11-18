"""Homespace-scoped USB sensor discovery, read-only CSI checks, and registry."""
import hashlib
import json
import platform
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from . import homespace as hs

FIELDS = {"name", "role", "connection", "location", "height", "direction", "notes", "peer_sensor_id"}
LIMITS = {"name": 80, "location": 200, "height": 100, "direction": 100, "notes": 500}
ROLES = {"transmitter", "receiver"}
CONNECTIONS = {"usb_serial", "network"}
DISCOVERY_TTL_SEC = 120.0
CONNECT_LIMIT_SEC = 5.0
CSI_ONLINE_TTL_SEC = 30.0
CSI_SOURCE = "espressif/esp-csi@8633d67152db2808f141cc1595970aa9cf406045"
_PORT_SCAN_LOCK = threading.Lock()


class SensorAlreadyRegistered(Exception):
    pass


def _serial_port_rows(timeout_sec=3.0):
    """Run platform USB-serial enumeration with a bounded request wait."""
    if not _PORT_SCAN_LOCK.acquire(blocking=False):
        raise TimeoutError("USB serial scan is already running")
    done, result = threading.Event(), {}

    def scan():
        try:
            from serial.tools import list_ports
            result["ports"] = list(list_ports.comports(include_links=False))
        except ImportError as exc:
            result["error"] = RuntimeError("USB sensor discovery requires pyserial==3.5 from requirements.txt")
            result["error"].__cause__ = exc
        except Exception as exc:
            result["error"] = exc
        finally:
            _PORT_SCAN_LOCK.release()
            done.set()

    threading.Thread(target=scan, name="sensor-usb-scan", daemon=True).start()
    if not done.wait(timeout_sec):
        raise TimeoutError("USB serial scan timed out")
    if "error" in result:
        raise RuntimeError("USB serial enumeration failed") from result["error"]
    return result["ports"]


def _descriptor(port):
    vid, pid = getattr(port, "vid", None), getattr(port, "pid", None)
    if vid is None or pid is None:
        return None  # exclude Bluetooth, virtual/debug ports without USB IDs
    serial_number = getattr(port, "serial_number", None) or None
    location = getattr(port, "location", None) or None
    device = str(getattr(port, "device", ""))
    manufacturer = getattr(port, "manufacturer", None) or None
    product = getattr(port, "product", None) or None
    if vid == 0x303A and pid == 0x1001:
        device_type = "esp_usb_serial_jtag"
    elif vid == 0x10C4 and pid in {0xEA60, 0xEA70, 0xEA71, 0xEA72, 0xEA73, 0xEA80, 0xEA81, 0xEA82}:
        device_type = "cp210x_usb_uart"
    elif vid == 0x1A86 and pid in {0x7523, 0x5523, 0x7522, 0x55D4, 0x55D3}:
        device_type = "wch_ch34x_usb_uart"
    else:
        device_type = "usb_serial_unknown"
    mac = None
    # Espressif documents 303A:1001 iSerialNumber as its factory MAC; bridge serials are never treated as MACs.
    if vid == 0x303A and pid == 0x1001 and serial_number:
        if re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", serial_number):
            mac = serial_number.upper()
    identity = f"{vid:04x}:{pid:04x}:serial:{serial_number}" if serial_number else f"{vid:04x}:{pid:04x}:port:{location or device}"
    device_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {"port": device, "vendor_id": f"{vid:04x}", "product_id": f"{pid:04x}",
            "manufacturer": manufacturer, "product": product, "serial_number": serial_number,
            "device_type": device_type, "hardware_mac": mac,
            "hardware_id": mac or serial_number,
            "identity_source": "usb_descriptors", "identity_strength": "serial" if serial_number else "port",
            "_device_key": device_key}


def _new_scan_id():
    return "scan_" + uuid.uuid4().hex


def discover_usb(app, space_id, db=None):
    ports = _serial_port_rows()
    candidates = []
    for port in ports:
        item = _descriptor(port)
        if item is None:
            continue
        item["candidate_id"] = "usb_" + uuid.uuid4().hex
        item["registered_sensor_id"] = None
        if db is not None:
            with db._get_connection() as c:
                row = c.execute("SELECT sensor_id FROM sensors WHERE homespace_id=? AND hardware_key=? AND source_type='wifi_csi'",
                                (space_id, item["_device_key"])).fetchone()
            item["registered_sensor_id"] = row[0] if row else None
        candidates.append(item)
    scan_id, now, monotonic = _new_scan_id(), datetime.now(timezone.utc).isoformat(), time.monotonic()
    with app.state.sensor_scan_lock:
        app.state.sensor_discovery_scans = {
            key: value for key, value in app.state.sensor_discovery_scans.items()
            if monotonic - value["created_monotonic"] <= DISCOVERY_TTL_SEC
        }
        app.state.sensor_discovery_scans[scan_id] = {
            "space_id": space_id, "created_monotonic": monotonic, "scanned_at": now,
            "candidates": {c["candidate_id"]: c for c in candidates},
        }
    public = [{k: v for k, v in c.items() if not k.startswith("_")} for c in candidates]
    return {"scan_id": scan_id, "scanned_at": now, "host_platform": platform.system().lower(), "candidates": public}


def _scan_candidate(app, space_id, scan_id, candidate_id):
    if not isinstance(scan_id, str) or not isinstance(candidate_id, str):
        raise ValueError("scan_id and candidate_id required")
    with app.state.sensor_scan_lock:
        scan = app.state.sensor_discovery_scans.get(scan_id)
        if not scan or scan["space_id"] != space_id or time.monotonic() - scan["created_monotonic"] > DISCOVERY_TTL_SEC:
            raise LookupError("USB scan expired or unavailable; scan again")
        candidate = scan["candidates"].get(candidate_id)
        if not candidate:
            raise LookupError("USB candidate not found in scan")
        return scan, candidate


def _find_current_port(candidate):
    for port in _serial_port_rows():
        current = _descriptor(port)
        if current and current["port"] == candidate["port"] and current["_device_key"] == candidate["_device_key"]:
            return current
    return None


def connect_usb_candidate(app, space_id, payload, db=None):
    if not isinstance(payload, dict) or not {"scan_id", "candidate_id"} <= set(payload) or set(payload) - {"scan_id", "candidate_id", "sensor_id"}:
        raise ValueError("body requires scan_id and candidate_id; optional sensor_id must be registered already")
    scan, candidate = _scan_candidate(app, space_id, payload["scan_id"], payload["candidate_id"])
    registered_id = payload.get("sensor_id")
    registered_role = registered_last_seen = None
    if registered_id:
        if not db:
            raise LookupError("registered sensor unavailable")
        with db._get_connection() as c:
            registered = c.execute("SELECT sensor_id,hardware_key,role,last_seen_at FROM sensors WHERE sensor_id=? AND homespace_id=? AND source_type='wifi_csi'",
                                   (registered_id, space_id)).fetchone()
        if not registered or registered["hardware_key"] != candidate["_device_key"]:
            raise LookupError("registered sensor does not match this USB candidate")
        candidate["registered_sensor_id"] = registered_id
        registered_role, registered_last_seen = registered["role"], registered["last_seen_at"]
    elif candidate.get("registered_sensor_id"):
        raise LookupError("USB device is already registered; rescan and connect its registered candidate")
    current = _find_current_port(candidate)
    if current is None:
        raise LookupError("USB device moved or disconnected; scan again")
    from tools.diag.csi_capture import CSIParser, CSI_HEADER, COMMIT, MAX_LINE_BYTES
    parser = CSIParser(max_line_bytes=MAX_LINE_BYTES, accept_headerless_data=True)
    samples, last_sample_at, unsupported = 0, None, False
    serial_port, opened = None, False
    try:
        import serial
        # Configure modem-control lines low before opening to avoid DTR/RTS reset/bootloader pulses.
        serial_port = serial.Serial(port=None, baudrate=921600, timeout=0.2, write_timeout=0.2)
        serial_port.dtr = False
        serial_port.rts = False
        serial_port.port = candidate["port"]
        serial_port.open()
        opened = True
        started = time.monotonic()
        while time.monotonic() - started < CONNECT_LIMIT_SEC:
            raw = serial_port.readline(MAX_LINE_BYTES + 1)
            if not raw:
                continue
            try:
                sample = parser.feed(raw)
            except ValueError:
                unsupported = True
                break
            if sample:
                samples += 1
                last_sample_at = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        # Device permissions, unplug, and stream errors are user-action outcomes, never fake liveness.
        reason = type(exc).__name__
        got_samples = samples > 0
        result = {"status": "csi_stream_detected" if got_samples else "port_unavailable" if not opened else "usb_open_no_csi",
                  "firmware_format_supported": got_samples, "samples": samples,
                  "identity_verified": True, "serial_opened": opened, "device_present": opened,
                  "malformed_rows": parser.malformed_rows, "header_seen": parser.header_seen,
                  "tested_at": datetime.now(timezone.utc).isoformat(), "sampled_at": last_sample_at,
                  "source_commit": COMMIT,
                  "action": "CSI_DATA sample schema matched the approved Espressif format." if got_samples else
                  "USB serial port could not be read. Reconnect the board and retry." if not opened else
                  "No valid CSI_DATA sample was received. Install the approved CSI receiver firmware, then rescan and retry.",
                  "detail": reason}
        with app.state.sensor_scan_lock:
            candidate["connection_test"] = result if opened else None
        if registered_id and db is not None:
            failed_status = "offline" if not opened or (registered_role == "receiver" and registered_last_seen) else "pending"
            with db._get_connection() as c:
                c.execute("""UPDATE sensors SET status=?,last_seen_at=CASE WHEN ? THEN ? ELSE last_seen_at END,
                           csi_source=CASE WHEN ? THEN ? ELSE csi_source END,updated_at=?
                           WHERE sensor_id=? AND homespace_id=? AND source_type='wifi_csi'""",
                          ("online" if got_samples else failed_status, int(got_samples), last_sample_at,
                           int(got_samples), f"CSV schema compatible with {CSI_SOURCE}", datetime.now(timezone.utc).isoformat(),
                           registered_id, space_id))
        return result
    finally:
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
    status = "csi_stream_detected" if samples else "unsupported_stream" if unsupported else "usb_open_no_csi"
    result = {"status": status, "firmware_format_supported": bool(samples), "samples": samples,
              "identity_verified": True, "serial_opened": True, "device_present": True,
              "malformed_rows": parser.malformed_rows, "header_seen": parser.header_seen,
              "tested_at": datetime.now(timezone.utc).isoformat(), "sampled_at": last_sample_at,
              "source_commit": COMMIT,
              "action": "CSI_DATA sample schema matched the approved Espressif format." if samples else
              "No valid CSI_DATA sample was received. Install the approved CSI receiver firmware, then rescan and retry."}
    with app.state.sensor_scan_lock:
        candidate["connection_test"] = result if serial_port is not None else None
    if registered_id and db is not None:
        with db._get_connection() as c:
            c.execute("""UPDATE sensors SET status=?,last_seen_at=CASE WHEN ? THEN ? ELSE last_seen_at END,
                       csi_source=CASE WHEN ? THEN ? ELSE csi_source END,updated_at=?
                       WHERE sensor_id=? AND homespace_id=? AND source_type='wifi_csi'""",
                      ("online" if samples else "offline", int(samples > 0), last_sample_at,
                       int(samples > 0), f"CSV schema compatible with {CSI_SOURCE}", datetime.now(timezone.utc).isoformat(),
                       registered_id, space_id))
    return result


def register_discovered_sensor(db, app, space_id, payload):
    fields = {"scan_id", "candidate_id", "name", "role", "location", "height", "direction", "notes", "peer_sensor_id"}
    if not isinstance(payload, dict) or set(payload) - fields:
        raise ValueError("unknown registration fields")
    scan, candidate = _scan_candidate(app, space_id, payload.get("scan_id"), payload.get("candidate_id"))
    proof = candidate.get("connection_test")
    if not proof or not proof.get("serial_opened"):
        raise ValueError("run a successful USB connection test before registration")
    data = _payload({**{k: v for k, v in payload.items() if k not in {"scan_id", "candidate_id"}}, "connection": "usb_serial"})
    installation = {k: data.get(k) for k in ("connection", "location", "height", "direction", "notes", "peer_sensor_id")}
    sid, sensor_id = space_id, "sensor_" + uuid.uuid4().hex
    physical_device = candidate.get("product") or candidate["device_type"]
    hardware_key = candidate["_device_key"]
    has_csi = bool(proof.get("samples") and proof.get("status") == "csi_stream_detected")
    last_seen = proof.get("sampled_at") or ""
    source = f"CSV schema compatible with {CSI_SOURCE}" if has_csi else None
    now = datetime.now(timezone.utc).isoformat()
    raw = json.dumps(installation, ensure_ascii=False, separators=(",", ":"))
    try:
        with db._get_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            _check_peer(c, sid, installation["peer_sensor_id"])
            existing = c.execute("SELECT sensor_id FROM sensors WHERE homespace_id=? AND hardware_key=? AND source_type='wifi_csi'",
                                 (sid, hardware_key)).fetchone()
            if existing:
                raise SensorAlreadyRegistered("USB hardware is already registered in this homespace")
            c.execute("""INSERT INTO sensors(sensor_id,source_type,physical_device,role,status,last_seen_at,firmware_version,
                       homespace_id,name,installation_json,installation_revision,updated_at,hardware_key,hardware_mac,csi_source,
                       device_type,usb_serial_number,usb_port)
                       VALUES(?, 'wifi_csi', ?, ?, ?, ?, NULL, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                      (sensor_id, physical_device, data["role"], "online" if has_csi else "pending", last_seen, sid, data["name"], raw, now,
                       hardware_key, candidate.get("hardware_mac"), source, candidate["device_type"], candidate.get("serial_number"), candidate["port"]))
            snapshot = _history_snapshot(installation, data["role"], None)
            c.execute("INSERT INTO sensor_installation_history VALUES(?,?,?,?,?)", (sensor_id, sid, 1, snapshot, now))
            row = c.execute("SELECT * FROM sensors WHERE sensor_id=?", (sensor_id,)).fetchone()
    except SensorAlreadyRegistered:
        raise
    result = _installation(row)
    result["connection_evidence"] = {"source": source, "sampled_at": last_seen or None, "sample_count": proof.get("samples", 0),
                                      "serial_opened": True}
    with app.state.sensor_scan_lock:
        candidate["registered_sensor_id"] = sensor_id
    return result


def _space():
    return hs.current_space.get() or 1


def current_space_id():
    return _space()


def _installation(row):
    d = dict(row)
    d["installation"] = json.loads(d.pop("installation_json") or "{}")
    fresh = False
    if d["status"] == "online" and d.get("last_seen_at"):
        try:
            seen = datetime.fromisoformat(d["last_seen_at"].replace("Z", "+00:00"))
            fresh = (datetime.now(timezone.utc) - seen.astimezone(timezone.utc)).total_seconds() <= CSI_ONLINE_TTL_SEC
        except (TypeError, ValueError):
            pass
    d["connected"] = bool(fresh)
    if d["status"] == "online" and not fresh:
        d["status"] = "offline"
    d.pop("hardware_key", None)
    return d


def _payload(payload, partial=False):
    if not isinstance(payload, dict):
        raise ValueError("body must be an object")
    unknown = set(payload) - FIELDS
    if unknown:
        raise ValueError("unknown fields: " + ", ".join(sorted(unknown)))
    out = dict(payload)
    for k, n in LIMITS.items():
        if k in out:
            if not isinstance(out[k], str) or len(out[k]) > n or (k == "name" and not 1 <= len(out[k].strip()) <= n):
                raise ValueError(f"invalid {k}")
            out[k] = out[k].strip() if k != "notes" else out[k]
    if "role" in out and (not isinstance(out["role"], str) or out["role"] not in ROLES):
        raise ValueError("invalid role")
    if "connection" in out and (not isinstance(out["connection"], str) or out["connection"] not in CONNECTIONS):
        raise ValueError("invalid connection")
    if "peer_sensor_id" in out and out["peer_sensor_id"] is not None and not isinstance(out["peer_sensor_id"], str):
        raise ValueError("invalid peer_sensor_id")
    if not partial:
        if not isinstance(out.get("name"), str) or not out.get("name", "").strip():
            raise ValueError("name required")
        if out.get("role") not in ROLES or out.get("connection") not in CONNECTIONS:
            raise ValueError("role and connection required")
    return out


def list_sensors(db):
    hs.ensure(db, backfill=False)
    with db._get_connection() as c:
        rows = c.execute("SELECT * FROM sensors WHERE homespace_id=? ORDER BY sensor_id", (_space(),)).fetchall()
    return [_installation(r) for r in rows]


def _check_peer(c, sid, peer, self_id=None):
    if not peer:
        return
    if peer == self_id:
        raise ValueError("sensor cannot peer with itself")
    row = c.execute("SELECT sensor_id FROM sensors WHERE sensor_id=? AND homespace_id=? AND source_type='wifi_csi'", (peer, sid)).fetchone()
    if not row:
        raise ValueError("peer sensor not found in this homespace")


def _history_snapshot(installation, role, firmware_version):
    return json.dumps({"installation": installation, "role": role, "firmware_version": firmware_version},
                      ensure_ascii=False, separators=(",", ":"))


def create_sensor(db, payload):
    raise ValueError("USB discovery and a successful CSI connection test are required")


def update_sensor(db, sensor_id, payload):
    data = _payload(payload, partial=True)
    if not data:
        raise ValueError("no fields to update")
    sid, now = _space(), datetime.now(timezone.utc).isoformat()
    with db._get_connection() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM sensors WHERE sensor_id=? AND homespace_id=?", (sensor_id, sid)).fetchone()
        if not row:
            return None
        old = dict(row)
        if old["source_type"] != "wifi_csi":
            return None
        if data.get("connection", "usb_serial") != "usb_serial":
            raise ValueError("registered USB sensors cannot change connection type")
        installation = json.loads(old.get("installation_json") or "{}")
        for k in ("connection", "location", "height", "direction", "notes", "peer_sensor_id"):
            if k in data:
                installation[k] = data[k]
        if "peer_sensor_id" not in installation:
            installation["peer_sensor_id"] = None
        _check_peer(c, sid, installation.get("peer_sensor_id"), sensor_id)
        revision = old.get("installation_revision") or 1
        raw = json.dumps(installation, ensure_ascii=False, separators=(",", ":"))
        role = data.get("role", old["role"])
        firmware = old["firmware_version"]
        changed = raw != (old.get("installation_json") or "{}")
        revision_changed = changed or role != old["role"] or firmware != old["firmware_version"]
        if revision_changed:
            revision += 1
            snapshot = _history_snapshot(installation, role, firmware)
            c.execute("INSERT INTO sensor_installation_history VALUES(?,?,?,?,?)", (sensor_id, sid, revision, snapshot, now))
        c.execute("""UPDATE sensors SET name=?,role=?,firmware_version=?,installation_json=?,installation_revision=?,updated_at=?
                   WHERE sensor_id=? AND homespace_id=?""",
                  (data.get("name", old["name"]), role, firmware, raw, revision, now, sensor_id, sid))
        out = c.execute("SELECT * FROM sensors WHERE sensor_id=?", (sensor_id,)).fetchone()
    return _installation(out)
