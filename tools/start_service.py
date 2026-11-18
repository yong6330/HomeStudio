"""Launch software/main.py detached. Reads camera password from stdin (one line); never prints it."""
import os, subprocess, sys
pw = sys.stdin.readline().rstrip("\r\n")
env = dict(os.environ, HOMESTUDIO_CAM_PASSWORD=pw, PYTHONUNBUFFERED="1")
flags = 0x00000008 | 0x00000200 | 0x01000000  # DETACHED | NEW_GROUP | BREAKAWAY_FROM_JOB
p = subprocess.Popen([sys.executable, r"C:\HomeStudio\software\main.py", "--no-stdout"], env=env, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(r"C:\HomeStudio\logs\service.stderr.log", "ab"),
                     close_fds=True)
print("started pid", p.pid)
