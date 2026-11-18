"""Find the bound camera by MAC address (wired preferred, Wi-Fi fallback) instead of trusting a fixed IP.

Binding (app_settings 'camera_binding'): {"macs": [{"mac", "iface"}], "model", "ip", "mac", "iface"}.
Resolution: ARP table -> if a bound MAC is missing, a quick UDP sweep of the /24 (fills the OS ARP cache) +
WS-Discovery probe -> verify the model via LAPI DeviceInfo (Digest) before switching. HOMESTUDIO_CAM_IP overrides all.
"""
import json
import logging
import re
import socket
import subprocess
import time
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger("homestudio.locator")
PREFERRED_RETRY_MIN = 10
FAILS_BEFORE_RESOLVE = 3
BACKOFF_MIN, BACKOFF_MAX = 15, 600  # seconds between unsuccessful re-resolutions (doubles, reset on success)
_ARP = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})\D+?((?:[0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2})")


def norm_mac(m: str) -> str:
    return "-".join(p.zfill(2) for p in re.split(r"[:-]", m.lower()))


def parse_arp(text: str) -> Dict[str, str]:
    """`arp -a` output (Windows or macOS/Linux) -> {mac: ip}."""
    out = {}
    for line in text.splitlines():
        m = _ARP.search(line)
        if m:
            out[norm_mac(m.group(2))] = m.group(1)
    return out


def arp_table() -> Dict[str, str]:
    try:
        return parse_arp(subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10).stdout)
    except Exception as e:
        log.warning("arp failed: %s", type(e).__name__)
        return {}


def ws_discovery(timeout: float = 2.0) -> List[str]:
    """ONVIF WS-Discovery probe; returns responder IPs."""
    msg = ('<?xml version="1.0"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
           'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
           '<e:Header><w:MessageID>uuid:homestudio-probe</w:MessageID><w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
           '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header><e:Body><d:Probe/></e:Body></e:Envelope>')
    ips = set()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.3)
        s.sendto(msg.encode(), ("239.255.255.250", 3702))
        end = time.time() + timeout
        while time.time() < end:
            try:
                ips.add(s.recvfrom(65535)[1][0])
            except socket.timeout:
                pass
    except OSError as e:
        log.warning("ws-discovery failed: %s", e)
    finally:
        s.close()
    return sorted(ips)


def sweep(prefix: str) -> None:
    """Touch every host of prefix.0/24 with one UDP datagram so the OS refreshes its ARP cache (no subprocess per host)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for i in range(1, 255):
            try:
                s.sendto(b"", (f"{prefix}.{i}", 9))
            except OSError:
                pass
    finally:
        s.close()
    ws_discovery(1.5)
    time.sleep(1.0)


def local_prefix() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip.rsplit(".", 1)[0]
    except OSError:
        return "192.168.0"


def local_prefixes() -> List[str]:
    """/24 prefixes of every active private IPv4 interface (wired + Wi-Fi), default-route one first.
    Link-local, loopback and Tailscale/CGNAT (100.64/10) addresses are skipped."""
    import ipaddress
    out = [local_prefix()]
    try:
        ips = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        ips = set()
    for ip in sorted(ips):
        a = ipaddress.ip_address(ip)
        if a.is_private and not (a.is_link_local or a.is_loopback or a in ipaddress.ip_network("100.64.0.0/10")):
            p = ip.rsplit(".", 1)[0]
            if p not in out:
                out.append(p)
    return out


def ident(v) -> Optional[dict]:
    """verify() may return a model string (tests) or {"model", "serial_hash"}."""
    return v if isinstance(v, dict) else ({"model": v, "serial_hash": None} if v else None)


def lapi_model(config) -> Callable[[str], Optional[dict]]:
    """Returns ip -> {"model", "serial_hash"} via LAPI DeviceInfo (Digest auth). Only a hash of the serial is kept."""
    import hashlib

    def model(ip: str) -> Optional[dict]:
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, f"http://{ip}:{config.http_port}/", config.camera_username, config.camera_password or "")
        from .digest import opener as digest_opener
        op = digest_opener(mgr)  # one credentialed try, shared 401 backoff
        try:
            with op.open(f"http://{ip}:{config.http_port}/LAPI/V1.0/System/DeviceInfo", timeout=4) as r:
                d = json.loads(r.read())["Response"]["Data"]
            serial = d.get("SerialNumber") or d.get("Serial") or d.get("SN")
            return {"model": d.get("DeviceModel") or d.get("Model"),
                    "firmware": d.get("FirmwareVersion") or d.get("SoftwareVersion"),
                    "serial_hash": hashlib.sha256(str(serial).encode()).hexdigest()[:16] if serial else None}
        except Exception:
            return None
    return model


def use_locator(env) -> bool:
    return not env.get("HOMESTUDIO_CAM_IP")  # manual override wins


def load_binding(db) -> Optional[dict]:
    with db._get_connection() as c:
        c.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        r = c.execute("SELECT value FROM app_settings WHERE key='camera_binding'").fetchone()
    return json.loads(r[0]) if r else None


def save_binding(db, macs: List[dict], model: str, ip: Optional[str], mac: Optional[str] = None, iface: Optional[str] = None,
                 serial_hash: Optional[str] = None) -> dict:
    b = {"macs": [{"mac": norm_mac(m["mac"]), "iface": m.get("iface", "unknown")} for m in macs], "model": model,
         "ip": ip, "mac": norm_mac(mac) if mac else None, "iface": iface, "serial_hash": serial_hash}
    with db._get_connection() as c:
        c.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        c.execute("INSERT OR REPLACE INTO app_settings VALUES ('camera_binding', ?)", (json.dumps(b),))
    return b


class CameraLocator:
    def __init__(self, db, verify: Callable[[str], Optional[str]], arp=arp_table, sweep=sweep, prefix: Optional[str] = None,
                 prefixes: Callable[[], List[str]] = local_prefixes):
        self.db, self.verify, self.arp, self.sweep, self.prefix, self.prefixes = db, verify, arp, sweep, prefix, prefixes
        self.last_ident: Optional[dict] = None

    def _matches(self, ip: str, mac: str, b: dict) -> bool:
        """Only IPs that ARP maps to a bound MAC get credentials; accept on model (+ serial hash once known),
        then re-check ARP so a device that took over the IP meanwhile is not accepted."""
        idn = ident(self.verify(ip))
        if not idn or idn["model"] != b["model"] or (b.get("serial_hash") and idn.get("serial_hash") != b["serial_hash"]):
            return False
        if self.arp().get(mac) != ip:
            return False
        self.last_ident = idn
        return True

    def resolve(self, only: Optional[List[str]] = None) -> Optional[Tuple[str, str, str]]:
        """(ip, mac, iface) of the first bound MAC (wired first) that answers with the bound model."""
        b = load_binding(self.db)
        if not b:
            return None
        macs = sorted(b["macs"], key=lambda m: m["iface"] != "wired")
        if only:
            macs = [m for m in macs if m["iface"] in only]
        for attempt in range(2):
            table = self.arp()
            for m in macs:
                ip = table.get(m["mac"])
                if ip and self._matches(ip, m["mac"], b):
                    return ip, m["mac"], m["iface"]
            if attempt == 0:
                for p in ([self.prefix] if self.prefix else self.prefixes()):
                    self.sweep(p)
        return None

    def discover(self, ips: List[str], prefix: str) -> List[dict]:
        """Candidates that answer LAPI DeviceInfo, with their MAC from ARP. Credentials go only to ONVIF
        WS-Discovery responders and to IPs whose ARP MAC is already bound, never to every host on the LAN."""
        self.sweep(prefix)
        arp = self.arp()
        table = {ip: mac for mac, ip in arp.items()}
        b = load_binding(self.db) or {}
        bound = {arp[m["mac"]] for m in b.get("macs", []) if m["mac"] in arp}
        out = []
        for ip in sorted(set(ips) | bound):
            if not ip.startswith(prefix + "."):
                continue
            idn = ident(self.verify(ip))
            if idn and idn["model"]:
                out.append({"ip": ip, "mac": table.get(ip), "model": idn["model"]})
        return out

    def switched(self, ip: str, mac: str, iface: str, old: Optional[str]) -> None:
        b = load_binding(self.db)
        save_binding(self.db, b["macs"], b["model"], ip, mac, iface, b.get("serial_hash"))
        log.warning("camera address changed: %s -> %s (%s)", old, ip, iface)
        from ..backend import insights
        insights.add_notification(self.db, f"camera_address:{ip}:{int(time.time() // 60)}", "camera_address", "info",
                                  "카메라 주소가 바뀌었어요", f"{'유선' if iface == 'wired' else 'Wi-Fi' if iface == 'wifi' else '네트워크'} 연결({ip})로 다시 연결했어요. 이전 주소: {old or '-'}.")


def make_source(config, db):
    """SnapshotSource bound to the registered camera (last-known IP + MAC re-resolution), unless HOMESTUDIO_CAM_IP is set."""
    import os
    from .snapshot_source import SnapshotSource
    if not use_locator(os.environ):
        return SnapshotSource(config)
    b = load_binding(db)
    if b and b.get("ip"):
        config.camera_ip = b["ip"]
    return SnapshotSource(config, locator=CameraLocator(db, lapi_model(config)) if b else None)
