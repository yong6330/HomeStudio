import os
import urllib.error
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.32"
    url = f"http://{ip}/LAPI/V1.0/System/Reboot"
    
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))

    print(f"Sending PUT request to {url}...")
    req = urllib.request.Request(url, method="PUT")
    try:
        with opener.open(req, timeout=10) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            print(f"HTTP {resp.status} response:\n{data}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}:\n{e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    main()
