import hashlib
import os
import re
import socket
import sys

def test_stream(stream_name):
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.31"
    uri = f"rtsp://{ip}:554/{stream_name}"
    print(f"\n--- Testing {uri} ---")

    s = socket.socket()
    s.settimeout(5)
    s.connect((ip, 554))
    
    # 1. DESCRIBE
    s.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
    resp = s.recv(2048).decode(errors="replace")
    
    realm_m = re.search(r'realm="([^"]+)"', resp)
    nonce_m = re.search(r'nonce="([^"]+)"', resp)
    if not realm_m:
        print("No realm:", resp)
        s.close()
        return

    realm = realm_m.group(1)
    nonce = nonce_m.group(1)

    ha1 = hashlib.md5(f"codex:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
    resp_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()

    auth_hdr = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{resp_hash}"'
    s.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 2\r\nAuthorization: {auth_hdr}\r\n\r\n".encode())
    auth_resp = s.recv(4096).decode(errors="replace")
    print("DESCRIBE response:", auth_resp.split("\r\n")[0])

    # 2. SETUP video track
    v_track = f"rtsp://{ip}/{stream_name}/video"
    ha2_v = hashlib.md5(f"SETUP:{v_track}".encode()).hexdigest()
    auth_v = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{v_track}", response="{hashlib.md5(f"{ha1}:{nonce}:{ha2_v}".encode()).hexdigest()}"'
    s.sendall((
        f"SETUP {v_track} RTSP/1.0\r\n"
        f"CSeq: 3\r\n"
        f"Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n"
        f"Authorization: {auth_v}\r\n\r\n"
    ).encode())
    v_resp = s.recv(2048).decode(errors="replace")
    print("Video SETUP:", v_resp.split("\r\n")[0])
    session_m = re.search(r'Session:\s*([^\s;]+)', v_resp)
    if not session_m:
        print("No session in SETUP response")
        s.close()
        return
    session_id = session_m.group(1)

    # 3. PLAY
    ha2_play = hashlib.md5(f"PLAY:{uri}".encode()).hexdigest()
    auth_play = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{hashlib.md5(f"{ha1}:{nonce}:{ha2_play}".encode()).hexdigest()}"'
    s.sendall((
        f"PLAY {uri} RTSP/1.0\r\n"
        f"CSeq: 4\r\n"
        f"Session: {session_id}\r\n"
        f"Authorization: {auth_play}\r\n\r\n"
    ).encode())
    play_resp = s.recv(2048).decode(errors="replace")
    print("PLAY:", play_resp.split("\r\n")[0])

    # 4. Read packets
    s.settimeout(5)
    total_bytes = 0
    try:
        for i in range(10):
            data = s.recv(4096)
            if not data:
                print("Socket closed by remote")
                break
            total_bytes += len(data)
            print(f"Recv packet {i+1}: {len(data)} bytes, starts with: {data[:4]}")
    except socket.timeout:
        print("Recv timed out after PLAY")

    print(f"Total bytes received for {stream_name}:", total_bytes)

    # 5. TEARDOWN
    s.sendall(f"TEARDOWN {uri} RTSP/1.0\r\nCSeq: 5\r\nSession: {session_id}\r\n\r\n".encode())
    s.close()

def main():
    test_stream("media/video1")
    test_stream("media/video2")

if __name__ == "__main__":
    main()
