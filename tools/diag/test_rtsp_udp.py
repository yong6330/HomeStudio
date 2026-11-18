import socket
import re
import hashlib
import os
import time

def test_udp(stream_path="media/video2"):
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.32"
    uri = f"rtsp://{ip}:554/{stream_path}"
    print(f"\n--- Testing UDP RTSP: {uri} ---")
    s = socket.socket()
    s.settimeout(5)
    s.connect((ip, 554))
    
    # 1. DESCRIBE
    s.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
    resp = s.recv(2048).decode(errors="replace")
    realm = re.search(r'realm="([^"]+)"', resp).group(1)
    nonce = re.search(r'nonce="([^"]+)"', resp).group(1)
    ha1 = hashlib.md5(f"codex:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
    resp_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    auth_hdr = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{resp_hash}"'
    s.sendall(f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 2\r\nAuthorization: {auth_hdr}\r\n\r\n".encode())
    auth_resp = s.recv(4096).decode(errors="replace")

    # 2. Bind UDP ports
    rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtp_sock.bind(("0.0.0.0", 50000))
    rtp_sock.settimeout(5)

    v_track = f"rtsp://{ip}/{stream_path}/video"
    ha2_v = hashlib.md5(f"SETUP:{v_track}".encode()).hexdigest()
    auth_v = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{v_track}", response="{hashlib.md5(f"{ha1}:{nonce}:{ha2_v}".encode()).hexdigest()}"'
    s.sendall((
        f"SETUP {v_track} RTSP/1.0\r\n"
        f"CSeq: 3\r\n"
        f"Transport: RTP/AVP;unicast;client_port=50000-50001\r\n"
        f"Authorization: {auth_v}\r\n\r\n"
    ).encode())
    v_resp = s.recv(2048).decode(errors="replace")
    print("UDP SETUP response:\n", v_resp.strip())
    session_m = re.search(r'Session:\s*([^\s;]+)', v_resp)
    if not session_m:
        print("No session in response!")
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
    print("PLAY response:\n", play_resp.strip())

    print("Waiting for UDP RTP packets on port 50000 for 5s...")
    try:
        pkts = 0
        total_len = 0
        t0 = time.time()
        while time.time() - t0 < 5:
            data, addr = rtp_sock.recvfrom(4096)
            pkts += 1
            total_len += len(data)
            if pkts == 1:
                print(f"FIRST UDP PACKET from {addr}, length: {len(data)}")
        print(f"Received {pkts} UDP packets, total bytes: {total_len}")
    except socket.timeout:
        print("UDP recvfrom TIMED OUT")

    # 4. TEARDOWN
    s.sendall(f"TEARDOWN {uri} RTSP/1.0\r\nCSeq: 5\r\nSession: {session_id}\r\n\r\n".encode())
    s.close()
    rtp_sock.close()

if __name__ == "__main__":
    test_udp("media/video2")
