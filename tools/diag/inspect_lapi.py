import json
import os
import urllib.error
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.32"
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))

    urls = [
        "/LAPI/V1.0/System/DeviceInfo",
        "/LAPI/V1.0/System/Network/Interfaces",
        "/LAPI/V1.0/Channels/1/Media/Video/Streams",
        "/LAPI/V1.0/Channels/1/Media/Video/Streams/0",
        "/LAPI/V1.0/Channels/1/Media/Video/Streams/1",
        "/LAPI/V1.0/Channels/1/Media/Video/Encode",
        "/LAPI/V1.0/Channels/1/Media/Video/Encode/0",
        "/LAPI/V1.0/Channels/1/Media/Video/Encode/1",
        "/LAPI/V1.0/Channels/1/Media/Video/Live",
        "/LAPI/V1.0/System/Security/RTSP",
        "/LAPI/V1.0/System/Network/Port",
        "/LAPI/V1.0/System/Network/RTSP",
    ]

    for path in urls:
        url = f"http://{ip}{path}"
        try:
            req = urllib.request.Request(url)
            with opener.open(req, timeout=3) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                print(f"=== {path} (HTTP {resp.status}) ===")
                print(data[:500])
        except urllib.error.HTTPError as e:
            print(f"=== {path} (HTTP {e.code}) ===")
        except Exception as e:
            print(f"=== {path} (Error: {e}) ===")

if __name__ == "__main__":
    main()
