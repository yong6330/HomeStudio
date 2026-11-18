import os
import time
import urllib.error
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))
    url = f"http://{ip}/LAPI/V1.0/Channels/1/Media/Video/Streams/0/Snapshot"

    req = urllib.request.Request(url, headers={"Connection": "close"})
    try:
        with opener.open(req, timeout=5) as resp:
            data = resp.read()
            print(f"Success: {len(data)} bytes")
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    main()
