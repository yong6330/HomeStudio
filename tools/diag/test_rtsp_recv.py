import hashlib
import os
import re
import socket
import sys
import time

def test_rtsp_video_only(stream_path):
    password = os.getenv("CAM_PASS", "")
    ip = "192.168.0.32"
    uri = f"rtsp://{ip}:554/{stream_path}"
    print(f"\n==========================================")
    print(f"Testing {uri} (VIDEO ONLY)")
    print(f"==========================================")

    s = socket.socket()
    s.settimeout(10)
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
    print("DESCRIBE response:", auth_resp.split("\r\n")[0])

    # 2. SETUP ONLY VIDEO
    v_track = f"rtsp://{ip}/{stream_path}/video"
    ha2_v = hashlib.md5(f"SETUP:{v_track}".encode()).hexdigest()
    auth_v = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{v_track}", response="{hashlib.md5(f"{ha1}:{nonce}:{ha2_v}".encode()).hexdigest()}"'
    s.sendall((
        f"SETUP {v_track} RTSP/1.0\r\n"
        f"CSeq: 3\r\n"
        f"Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n"
        f"Authorization: {auth_v}\r\n\r\n"
    ).encode())
    v_resp = s.recv(2048).decode(errors="replace")
    print("SETUP video response:\n", v_resp.strip())
    session_id = re.search(r'Session:\s*([^\s;]+)', v_resp).group(1)

    # 3. PLAY
    ha2_play = hashlib.md5(f"PLAY:{uri}".encode()).hexdigest()
    auth_play = f'Digest username="codex", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{hashlib.md5(f"{ha1}:{nonce}:{ha2_play}".encode()).hexdigest()}"'
    s.sendall((
        f"PLAY {uri} RTSP/1.0\r\n"
        f"CSeq: 4\r\n"
        f"Session: {session_id}\r\n"
        f"Authorization: {auth_play}\r\n\r\n"
    ).encode())
    
    # 4. Stream loop for 10 seconds
    print("Listening on socket for 10 seconds...")
    start_time = time.time()
    packet_counts = {}
    total_bytes = 0
    s.settimeout(3.0)

    # Read first response (PLAY 200 OK + trailing binary data)
    try:
        first_chunk = s.recv(4096)
        print(f"First chunk ({len(first_chunk)} bytes):\n{first_chunk[:300]}")
        total_bytes += len(first_chunk)
    except Exception as e:
        print("First chunk error:", e)

    while time.time() - start_time < 10:
        try:
            chunk = s.recv(4096)
            if not chunk:
                print("Socket EOF")
                break
            total_bytes += len(chunk)
            # Parse interleaved channels: $ <channel> <len_hi> <len_lo>
            idx = 0
            while idx < len(chunk):
                if chunk[idx] == 0x24 and idx + 4 <= len(chunk): # '$'
                    ch = chunk[idx+1]
                    plen = (chunk[idx+2] << 8) | chunk[idx+3]
                    packet_counts[ch] = packet_counts.get(ch, 0) + 1
                    idx += 4 + plen
                else:
                    idx += 1
        except socket.timeout:
            print("Socket read timed out")
            break
        except Exception as e:
            print("Recv exception:", e)
            break

    print(f"Result for {stream_path}: Total bytes = {total_bytes}, Channels seen = {packet_counts}")

    # TEARDOWN
    try:
        s.sendall(f"TEARDOWN {uri} RTSP/1.0\r\nCSeq: 5\r\nSession: {session_id}\r\n\r\n".encode())
    except Exception:
        pass
    s.close()

def main():
    test_rtsp_video_only("media/video2")
    test_rtsp_video_only("media/video1")

if __name__ == "__main__":
    main()
