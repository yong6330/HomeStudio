import os
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))

    try:
        req = urllib.request.Request(f"http://{ip}/device_cap.xml")
        with opener.open(req, timeout=5) as resp:
            data = resp.read()
            with open("C:/HomeStudio/device_cap.xml", "wb") as f:
                f.write(data)
            print("Saved C:/HomeStudio/device_cap.xml, length:", len(data))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
