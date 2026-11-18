import os
import subprocess
import sys

def main():
    password = os.getenv("HOMESTUDIO_CAM_PASSWORD", "").strip()
    cam_ip = os.getenv("HOMESTUDIO_CAM_IP", "192.168.0.31").strip()
    sub_url = f"rtsp://codex:{password}@{cam_ip}:554/media/video2"
    
    ffmpeg_bin = r"C:\HomeStudio\tools\ffmpeg\bin\ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
    
    cmd = [
        ffmpeg_bin,
        "-y",
        "-nostdin",
        "-loglevel", "info",
        "-rtsp_transport", "tcp",
        "-i", sub_url,
        "-t", "3",
        "-f", "null",
        "-"
    ]
    
    print(f"Running FFmpeg against {cam_ip}...", flush=True)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Return code:", res.returncode, flush=True)
    stderr_text = res.stderr.decode(errors="replace")
    print("=== FFmpeg Stderr Output ===", flush=True)
    for line in stderr_text.splitlines():
        if any(k in line for k in ["Stream #", "Output #", "frame=", "hevc", "Input #", "Duration", "Error", "401", "Unauthorized", "failed"]):
            print(" ", line, flush=True)

if __name__ == "__main__":
    main()
