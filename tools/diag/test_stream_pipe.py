import os
import subprocess
import sys
import time

def main():
    password = os.getenv("HOMESTUDIO_CAM_PASSWORD", "").strip()
    cam_ip = os.getenv("HOMESTUDIO_CAM_IP", "192.168.0.31").strip()
    sub_url = f"rtsp://codex:{password}@{cam_ip}:554/media/video2"
    
    ffmpeg_bin = r"C:\HomeStudio\tools\ffmpeg\bin\ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
    
    cmd = [
        ffmpeg_bin,
        "-y",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", sub_url,
        "-r", "10",
        "-s", "160x90",
        "-pix_fmt", "gray",
        "-f", "rawvideo",
        "-an",
        "pipe:1"
    ]
    
    print(f"Spawning FFmpeg process for {cam_ip} with stderr=DEVNULL...", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    frame_size = 160 * 90
    count = 0
    t0 = time.time()
    
    print("Reading frames from stdout pipe for 5 seconds...", flush=True)
    while (time.time() - t0) < 5:
        buf = proc.stdout.read(frame_size)
        if not buf or len(buf) != frame_size:
            print(f"Stream finished or short read: {len(buf) if buf else 0} bytes", flush=True)
            break
        count += 1
        
    elapsed = time.time() - t0
    fps = count / elapsed if elapsed > 0 else 0
    print(f"Read {count} frames in {elapsed:.2f}s ({fps:.1f} fps)!", flush=True)
    
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
        
    if count >= 30:
        print("TEST PASSED: Real-time grayscale stream decoding verified!", flush=True)
    else:
        print(f"TEST FAILED: Only read {count} frames.", flush=True)

if __name__ == "__main__":
    main()
