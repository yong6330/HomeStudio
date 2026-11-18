"""LAPI probe with HTTP digest. Password from stdin. Usage: python lapi_probe.py [--put PATH JSON] path1 path2 ..."""
import sys, urllib.request, json
pw = sys.stdin.readline().rstrip("\r\n"); host = "http://192.168.0.32"
mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm(); mgr.add_password(None, host, "codex", pw)
op = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))
args = sys.argv[1:]
def go(path, data=None, method="GET"):
    req = urllib.request.Request(host + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        r = op.open(req, timeout=8); b = r.read(); st = r.status
    except urllib.error.HTTPError as e:
        b = e.read(); st = e.code
    except Exception as e:
        b = repr(e).encode(); st = "ERR"
    t = b.decode("utf-8", "replace").replace(pw, "***")
    print("==", method, path, st); print(t[:1500])
if args and args[0] == "--put":
    go(args[1], args[2].encode(), "PUT")
else:
    for p in args: go(p)
