"""390px screenshots of every HomeStudio screen through the real account flow. Stdlib only (Chrome/Edge DevTools protocol).

  python shots.py --base http://127.0.0.1:8080 --out logs/ui_shots --log logs/api.log --browser "<path to msedge/chrome>"

Creates a throwaway admin (signup -> email code read from the API server log -> onboarding) and screenshots each
screen. Use a temp DB or delete the test account afterwards. Dev tool only, never used at runtime.
"""
import argparse, base64, json, os, re, socket, struct, subprocess, tempfile, time, urllib.request
from pathlib import Path

PW = "Hamster!2026"


class CDP:
    def __init__(self, ws_url):
        host, port, path = re.match(r"ws://([^:/]+):(\d+)(/.*)", ws_url).groups()
        self.s = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.rest, self.n = buf.split(b"\r\n\r\n", 1)[1], 0

    def _recv(self, k):
        while len(self.rest) < k:
            self.rest += self.s.recv(1 << 20)
        out, self.rest = self.rest[:k], self.rest[k:]
        return out

    def _frame(self):
        data = b""
        while True:
            b1, b2 = self._recv(2)
            ln = b2 & 0x7F
            if ln == 126: ln = struct.unpack(">H", self._recv(2))[0]
            elif ln == 127: ln = struct.unpack(">Q", self._recv(8))[0]
            data += self._recv(ln)
            if b1 & 0x80: return data

    def call(self, method, **params):
        self.n += 1
        msg = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        hdr = bytes([0x81]) + (bytes([0x80 | len(msg)]) if len(msg) < 126 else bytes([0x80 | 126]) + struct.pack(">H", len(msg)) if len(msg) < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", len(msg)))
        self.s.sendall(hdr + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(msg)))
        while True:
            r = json.loads(self._frame())
            if r.get("id") == self.n:
                if "error" in r: raise RuntimeError(r["error"])
                return r.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True, help="API server log (dev mail sender writes codes there)")
    ap.add_argument("--browser", required=True); ap.add_argument("--email", default="shots-admin@example.com")
    ap.add_argument("--p307a", action="store_true"); ap.add_argument("--dev2", action="store_true"); ap.add_argument("--dev3", action="store_true"); ap.add_argument("--dev4", action="store_true"); ap.add_argument("--zones", action="store_true"); ap.add_argument("--photo", help="jpg for the pet photo upload shot")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prof = tempfile.mkdtemp()
    br = subprocess.Popen([a.browser, "--headless=new", "--remote-debugging-port=9333", f"--user-data-dir={prof}",
                           "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"])
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/list")); break
            except Exception:
                time.sleep(0.3)
        c = CDP([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"])
        c.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
        c.call("Emulation.setTimezoneOverride", timezoneId="Asia/Seoul")

        def wait(sel, t=15):
            for _ in range(int(t / 0.25)):
                if c.js(f"!!document.querySelector({json.dumps(sel)})"): return
                time.sleep(0.25)
            raise TimeoutError(f"{sel} not found at {c.js('location.href')}: {c.js('document.body.innerHTML.slice(0,300)')}")

        def go(h, sel="main"):
            c.call("Page.navigate", url=f"{a.base}/#{h}"); time.sleep(0.6); wait(sel)

        def fill(sel, v):
            c.js(f"(e=>{{e.value={json.dumps(v)};e.dispatchEvent(new Event('input',{{bubbles:true}}))}})(document.querySelector({json.dumps(sel)}))")

        def click(sel): c.js(f"document.querySelector({json.dumps(sel)}).click()")

        def shot(name):
            time.sleep(1.0)
            c.js("Promise.all([...document.images].map(i=>{i.loading='eager';return i.complete?0:new Promise(r=>{i.onload=i.onerror=r;setTimeout(r,5000)})}))")
            h = c.js("document.documentElement.scrollHeight")
            c.call("Emulation.setDeviceMetricsOverride", width=390, height=max(844, h), deviceScaleFactor=2, mobile=True)
            time.sleep(0.8)
            png = c.call("Page.captureScreenshot", format="png")["data"]
            (out / f"{name}.png").write_bytes(base64.b64decode(png))
            c.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
            print("saved", name, h)

        def code(purpose="verify"):
            m = re.findall(rf"to={re.escape(a.email)} purpose={purpose} code=(\d{{6}})", Path(a.log).read_text(errors="ignore"))
            return m[-1]

        c.call("Network.enable"); c.call("Network.clearBrowserCookies")
        for n in ("welcome", "login", "signup", "forgot", "pin"):
            go(n); shot(f"auth_{n}")
        go("signup", "#user-email")
        fill("#user-email", a.email); fill("#user-password", PW); fill("#user-password-confirm", PW)
        click("#agree-all"); c.js("document.querySelector('#agree-all').dispatchEvent(new Event('change'))")
        shot("auth_signup_filled")
        click("#btn-next"); wait("#code-boxes div")
        k = code(); fill("#authCodeInput", k[:3]); shot("auth_verify")
        fill("#authCodeInput", k); click("#submitCta"); wait("#pet-name-input")
        fill("#pet-name-input", "보리"); shot("auth_pet")
        click("#next-step-btn"); wait("#time-display-hour"); shot("auth_schedule")
        click("#btn-next"); wait("#confirmConnectionBtn"); shot("auth_discover")  # discovery scan (one Digest try per ONVIF responder)
        go("camera", "#cam-img"); shot("auth_camera")
        click("#btn-complete"); wait("#btn-home"); shot("auth_done")
        go("home", "#bars div"); shot("ui_home")
        go("timeline", "[data-k=count]"); time.sleep(1); shot("ui_timeline")
        href = c.js("(document.querySelector('a[href^=\"#session/\"]')||{}).getAttribute?.('href')")
        if href:
            go(href[1:], "#vid"); shot("ui_session")
        go("status", "[data-k=me]"); time.sleep(1); shot("ui_status")
        if a.dev3:  # baseline + notification center (temp DB seeded by seed_baseline.py)
            go("home", "#bars div"); time.sleep(1.5); shot("dev3_home")
            go("notifications", "#btn-read"); time.sleep(1); shot("dev3_notifications")
            go("status", "[data-k=me]"); time.sleep(2); shot("dev3_status")
            go("schedule", "#quiet-toggle"); time.sleep(1); shot("dev3_schedule")
        if a.zones:  # zones editor + per-zone stats on home/timeline/session (mock dir with seeded zones)
            go("home", "#bars div"); time.sleep(1.5); shot("zone_home")
            go("timeline", "[data-k=count]"); time.sleep(1); click('[data-filter="wheel"]'); time.sleep(0.5); shot("zone_timeline_wheel")
            href = c.js("(document.querySelector('.timeline-card:not(.hidden) a[href^=\"#session/\"]')||{}).getAttribute?.('href')")
            if href:
                go(href[1:], "#vid"); shot("zone_session")
            go("zones", "#zone-stage"); time.sleep(1)
            click('[data-kind="cage"]')  # draft cage rectangle (not saved)
            c.js("(s=>{const r=s.getBoundingClientRect();for(const [x,y] of [[0.03,0.3],[0.95,0.92]]) s.onclick({clientX:r.left+r.width*x,clientY:r.top+r.height*y})})(document.querySelector('#zone-stage'))")
            shot("zone_editor")
            go("status", "[data-k=me]"); time.sleep(1.5); shot("zone_status")
        if a.dev4:  # end-of-day verdict + long inactivity notifications (mock dir)
            go("home", "#bars div"); time.sleep(1.5); shot("dev4_home")
            go("notifications", "#btn-read"); time.sleep(1); shot("dev4_notifications")
        if a.dev2:  # privacy switch (real LAPI state, read-only: never clicked) + pet info opened from settings
            time.sleep(2); shot("dev2_status")
            go("pet", "#pet-name-input"); shot("dev2_pet_settings")
            go("status", "[data-k=me]")
        if a.p307a:  # P3-07a: password change, PIN set/unlock/lockout, pet photo, favorite
            shot("p307a_status")
            go("password", "#password-form"); fill("#reset-code", PW); fill("#reset-password", "Sunflower#77"); fill("#reset-confirm", "Sunflower#77")
            shot("p307a_password")
            go("pinset", "#pin-dots")
            c.js("document.querySelector('#pin-password').value=" + json.dumps(PW))
            for d in "2468": click(f'.keypad-btn[data-val="{d}"]')
            shot("p307a_pinset")
            click("#bio-quick-btn"); time.sleep(0.5)
            for d in "2468": click(f'.keypad-btn[data-val="{d}"]')
            click("#bio-quick-btn"); time.sleep(2)
            c.js("fetch('/api/pet/photo',{method:'POST',headers:{'Content-Type':'image/jpeg'},body:Uint8Array.from(atob(" + json.dumps(base64.b64encode(Path(a.photo).read_bytes()).decode()) + "),c=>c.charCodeAt(0))}).then(r=>r.status)")
            go("pet", "#pet-name-input"); shot("p307a_pet_photo")
            if href:
                go(href[1:], "#vid"); click("#favBtn"); time.sleep(1); shot("p307a_session_favorite"); click("#favBtn"); time.sleep(0.5)
            go("status", "[data-k=me]"); click("#btn-lock"); wait("#pin-dots div")
            for d in "13": click(f'.keypad-btn[data-val="{d}"]')
            shot("p307a_pin_unlock")
            for d in "57": click(f'.keypad-btn[data-val="{d}"]')
            click("#bio-quick-btn"); wait("#pin-error:not(.hidden)"); shot("p307a_pin_wrong")
            c.js("document.querySelectorAll('.keypad-btn')")
            for d in "2468": click(f'.keypad-btn[data-val="{d}"]')
            click("#bio-quick-btn"); time.sleep(1.5); wait("main"); shot("p307a_unlocked_home")
        c.call("Network.clearBrowserCookies")
        go("invite", "#invite-field"); shot("auth_invite")
        go("start", "#submit-cta"); shot("auth_start")
        go("join", "#invite-code-input"); shot("auth_join")
        go("login", "#email"); fill("#email", a.email); fill("#password", "Wrong!pass1")
        click("#login-form button[type=submit]"); wait("#login-error:not(.hidden)"); shot("auth_login_error")
    finally:
        br.terminate()


if __name__ == "__main__":
    main()
