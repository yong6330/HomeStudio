import hashlib
import os
import re
import socket
import sys

def main():
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    uri = f"rtsp://{ip}:554/media/video2"

    s = socket.socket()
    s.settimeout(5)
    s.connect((ip, 554))
    
    # 1. Unauthenticated DESCRIBE
    s.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
    resp = s.recv(2048).decode(errors="replace")
    
    realm_m = re.search(r'realm="([^"]+)"', resp)
    nonce_m = re.search(r'nonce="([^"]+)"', resp)
    
    if not realm_m or not nonce_m:
        print("Failed to get realm/nonce:", resp[:200])
        return

    realm = realm_m.group(1)
    nonce = nonce_m.group(1)

    # 2. Digest Auth Calculation
    ha1 = hashlib.md5(f"codex:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
    resp_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

    auth_hdr = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{resp_hash}"'
    req = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 2\r\nAuthorization: {auth_hdr}\r\n\r\n"
    
    s.sendall(req.encode())
    auth_resp = s.recv(4096).decode(errors="replace")
    s.close()

    print("=== FULL RESPONSE ===")
    print(auth_resp)

if __name__ == "__main__":
    main()
