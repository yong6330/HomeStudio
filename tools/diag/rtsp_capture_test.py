"""10s RTSP capture test. Password via stdin or CAM_PASS env; never printed.
Usage: echo <pw> | python rtsp_capture_test.py --path /media/video2 --transport tcp
"""
import argparse, os, re, subprocess, sys, urllib.parse
FF = r'C:\HomeStudio\tools\ffmpeg\bin'
ap = argparse.ArgumentParser()
ap.add_argument('--host', default='192.168.0.32'); ap.add_argument('--user', default='codex')
ap.add_argument('--path', default='/media/video2'); ap.add_argument('--transport', default='tcp')
ap.add_argument('--secs', default='10'); ap.add_argument('--out', default=None)
a = ap.parse_args()
pw = os.environ.get('CAM_PASS') or sys.stdin.readline().rstrip('\r\n')
url = 'rtsp://%s:%s@%s%s' % (urllib.parse.quote(a.user, safe=''), urllib.parse.quote(pw, safe=''), a.host, a.path)
out = a.out or r'C:\HomeStudio\data\cap_%s_%s.mp4' % (a.path.strip('/').replace('/', '_'), a.transport)
os.makedirs(os.path.dirname(out), exist_ok=True)
cmd = [FF + r'\ffmpeg.exe', '-hide_banner', '-loglevel', 'info', '-y', '-rtsp_transport', a.transport,
       '-timeout', '10000000', '-i', url, '-map', '0:v', '-t', a.secs, '-c', 'copy', out]
try:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=int(a.secs) + 40)
    log = p.stderr; rc = p.returncode
except subprocess.TimeoutExpired as e:
    log = (e.stderr or b'').decode('utf-8', 'replace') if isinstance(e.stderr, bytes) else (e.stderr or ''); rc = 'TIMEOUT'
log = log.replace(pw, '***').replace(urllib.parse.quote(pw, safe=''), '***')
log = re.sub(r'//[^/@\s]+@', '//***@', log)
print('rc=', rc); print('\n'.join(log.splitlines()[-25:]))
if os.path.exists(out):
    print('size=', os.path.getsize(out))
    pr = subprocess.run([FF + r'\ffprobe.exe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height,avg_frame_rate', '-of', 'compact', out], capture_output=True, text=True)
    print(pr.stdout, pr.stderr)
