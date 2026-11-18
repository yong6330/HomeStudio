import os
import urllib.request

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{ip}/", "codex", password)
    opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))

    snapshot_urls = [
        f"http://{ip}/LAPI/V1.0/Channels/1/Media/Video/Streams/0/Snapshot",
        f"http://{ip}/LAPI/V1.0/Channels/1/Media/Video/Streams/1/Snapshot",
        f"http://{ip}/LAPI/V1.0/Channels/1/Media/Video/Streams/2/Snapshot",
        f"http://{ip}/LAPI/V1.0/Channels/0/Media/Video/Streams/0/Snapshot",
        f"http://{ip}/LAPI/V1.0/Channels/0/Media/Video/Streams/1/Snapshot",
        f"http://{ip}/images/snapshot.jpg",
        f"http://{ip}/snapshot.jpg",
        f"http://{ip}/media/video1/snapshot.jpg",
        f"http://{ip}/media/video2/snapshot.jpg",
    ]

    for url in snapshot_urls:
        try:
            req = urllib.request.Request(url)
            with opener.open(req, timeout=5) as resp:
                data = resp.read()
                ct = resp.headers.get("Content-Type")
                print(f"SUCCESS: {url} -> HTTP {resp.status}, Content-Type: {ct}, Length: {len(data)}")
                if len(data) > 100 and (b"\xff\xd8" in data[:10] or "image" in str(ct)):
                    with open("C:/HomeStudio/test_snapshot.jpg", "wb") as f:
                        f.write(data)
                    print(f"--> Saved C:/HomeStudio/test_snapshot.jpg ({len(data)} bytes)!")
                    break
        except Exception as e:
            print(f"FAILED: {url} -> {e}")

if __name__ == "__main__":
    main()
