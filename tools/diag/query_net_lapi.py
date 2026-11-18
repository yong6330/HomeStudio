import os
import urllib.error
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))

    endpoints = [
        "/LAPI/V1.0/System/Network",
        "/LAPI/V1.0/System/Network/Interfaces",
        "/LAPI/V1.0/System/Network/Wired",
        "/LAPI/V1.0/System/Network/Wireless",
        "/LAPI/V1.0/System/Network/Interfaces/1",
        "/LAPI/V1.0/System/Network/Interfaces/0",
        "/LAPI/V1.0/System/Network/WLAN",
        "/LAPI/V1.0/Channels/1/Media/Video/Streams",
        "/LAPI/V1.0/Channels/1/Media/Video/Encode",
    ]

    for ep in endpoints:
        url = f"http://{ip}{ep}"
        try:
            req = urllib.request.Request(url)
            with opener.open(req, timeout=3) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                print(f"[{ep}] HTTP {resp.status}:\n{data[:400]}\n")
        except urllib.error.HTTPError as e:
            print(f"[{ep}] HTTP Error {e.code}")
        except Exception as e:
            print(f"[{ep}] Error: {e}")

if __name__ == "__main__":
    main()
