"""ONVIF GetProfiles + GetStreamUri helper (no secrets stored).
Usage: echo <password> | python onvif_stream_uri.py --user codex [--media http://IP/onvif/media]
Password is read from stdin (or CAM_PASS env). Stream URIs are printed with credentials redacted.
"""
import argparse, base64, datetime, hashlib, os, re, sys, urllib.request, json

def wsse(user, pw):
    nonce = os.urandom(16)
    created = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + pw.encode()).digest()).decode()
    return ('<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            '<UsernameToken><Username>%s</Username>'
            '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">%s</Password>'
            '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</Nonce>'
            '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">%s</Created>'
            '</UsernameToken></Security></s:Header>') % (user, digest, base64.b64encode(nonce).decode(), created)

def call(url, body, user, pw, mode):
    hdr = wsse(user, pw) if mode == 'wsse' else ''
    env = ('<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
           'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">'
           '%s<s:Body>%s</s:Body></s:Envelope>') % (hdr, body)
    req = urllib.request.Request(url, env.encode(), {'Content-Type': 'application/soap+xml; charset=utf-8'})
    handlers = []
    if mode == 'digest':
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm(); pm.add_password(None, url, user, pw)
        handlers = [urllib.request.HTTPDigestAuthHandler(pm)]
    try:
        r = urllib.request.build_opener(*handlers).open(req, timeout=10)
        return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')

def tag(x, name):
    return re.findall(r'<[^>]*:%s[^>]*>([^<]*)<' % name, x)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--user', default=os.environ.get('CAM_USER', 'grok'))
    ap.add_argument('--media', default='http://192.168.0.32/onvif/media'); a = ap.parse_args()
    pw = os.environ.get('CAM_PASS') or sys.stdin.readline().rstrip('\r\n')
    out = {}
    for mode in ('wsse', 'digest'):
        st, x = call(a.media, '<trt:GetProfiles/>', a.user, pw, mode)
        print('[%s] GetProfiles HTTP %s' % (mode, st))
        if st != 200: print(x[:300]); continue
        for blk in re.split(r'<trt:Profiles ', x)[1:]:
            tok = re.search(r'token="([^"]+)"', blk).group(1)
            p = {'name': (tag(blk, 'Name') or [''])[0], 'encoding': (tag(blk, 'Encoding') or [''])[0],
                 'width': (tag(blk, 'Width') or [''])[0], 'height': (tag(blk, 'Height') or [''])[0],
                 'fps': (tag(blk, 'FrameRateLimit') or [''])[0], 'bitrate': (tag(blk, 'BitrateLimit') or [''])[0]}
            st2, y = call(a.media, '<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup><trt:ProfileToken>%s</trt:ProfileToken></trt:GetStreamUri>' % tok, a.user, pw, mode)
            uri = (tag(y, 'Uri') or ['ERR %s' % st2])[0].replace('&amp;', '&')
            p['uri'] = re.sub(r'//[^/@]+@', '//***@', uri)
            out[tok] = p
        break
    # also H.265 via Media2 if available
    print(json.dumps(out, indent=1, ensure_ascii=False))

if __name__ == '__main__':
    main()
