"""One-shot HTTP Digest for the camera: never let urllib re-send credentials in a loop (account lockout).

urllib's HTTPDigestAuthHandler retries a rejected Digest up to 5 times per request. Here a request that already
carried Authorization and still gets 401 fails immediately, and every rejection closes a process-wide gate that
blocks further credentialed requests for a growing backoff (60 s -> 1 h, reset on the next success).
"""
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("homestudio.digest")
GATE_MIN, GATE_MAX = 60, 3600


class AuthGate:
    def __init__(self, clock=time.monotonic):
        self.clock, self.until, self.backoff = clock, 0.0, GATE_MIN

    def allowed(self) -> bool:
        return self.clock() >= self.until

    def rejected(self) -> None:
        self.until = self.clock() + self.backoff
        log.warning("camera rejected credentials; no auth attempts for %ss", self.backoff)
        self.backoff = min(self.backoff * 2, GATE_MAX)

    def ok(self) -> None:
        self.until, self.backoff = 0.0, GATE_MIN


GATE = AuthGate()


class OneShotDigestHandler(urllib.request.HTTPDigestAuthHandler):
    def __init__(self, mgr=None, gate: AuthGate = None):
        super().__init__(mgr)
        self.gate = gate or GATE

    def http_error_401(self, req, fp, code, msg, headers):
        if req.has_header(self.auth_header):  # our one credentialed try was rejected
            try:
                self.gate.rejected()
                raise urllib.error.HTTPError(req.full_url, code, "digest auth rejected", headers, fp)
            finally:
                # urllib resets this only after its superclass handler returns;
                # this terminal rejection intentionally raises before that point.
                self.reset_retry_count()
        if not self.gate.allowed():
            raise urllib.error.HTTPError(req.full_url, code, "digest auth paused after rejection", headers, fp)
        return super().http_error_401(req, fp, code, msg, headers)

    def http_response(self, req, response):
        if req.has_header(self.auth_header) and response.status < 400:
            self.gate.ok()
        return response


def opener(mgr, gate: AuthGate = None):
    return urllib.request.build_opener(OneShotDigestHandler(mgr, gate))
