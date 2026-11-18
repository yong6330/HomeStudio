"""Accounts (P3-07/07a): email ID, scrypt password hashes, cookie sessions, email codes, family invites, onboarding.

Stdlib only. Mail is NOT configured yet: LogSender writes verification/reset codes to the server log (dev only).
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import homespace as hs

log = logging.getLogger("homestudio.auth")
COOKIE = "hs_session"
DEVICE_COOKIE = "hs_device"  # remembered device; only this lets a PIN unlock
DEVICE_TTL = timedelta(days=90)
PIN_FAILS = 5
PHOTO_MAX = 2 * 1024 * 1024
SESSION_TTL = timedelta(hours=12)
REMEMBER_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=10)
CODE_TRIES = 5
CODE_SENDS = 3  # codes per email+purpose per CODE_TTL; each new code resets tries, so sends must be capped
LOCK_FAILS, LOCK_SEC = 5, 15 * 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SPECIAL = "!@#$%^&*()-_=+[]{};:'\",.<>/?\\|`~"
PUBLIC_PREFIXES = ("/api/health", "/api/auth/")
INVITE_TTL = timedelta(hours=24)  # Stitch "가족 초대": 24시간 후 만료, 1회 사용
INVITE_CHECKS = 10  # failed invite checks per client per 10 min


LOCAL_CLIENTS = {"127.0.0.1", "::1", "testclient"}  # first admin may only be created on the PC itself


class LogSender:
    """Pluggable mail sender. Replace with SMTP when configured.
    Codes are never written to the server log. With HOMESTUDIO_DEV_MAIL=1 (default off) they go to a local file
    (data/dev_mail.log, owner-only permissions where the OS supports it) for development."""

    def __init__(self, path=None):
        self.path = path

    def send(self, to: str, purpose: str, code: str) -> None:
        log.warning("[MAIL-DEV] no mail sender configured: code for to=%s purpose=%s not delivered (hidden)", to, purpose)
        if os.getenv("HOMESTUDIO_DEV_MAIL") == "1" and self.path:
            new = not os.path.exists(self.path)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"{_now().isoformat()} to={to} purpose={purpose} code={code}\n")
            if new:
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass


def password_problems(pw: str) -> List[str]:
    p = []
    if len(pw) < 8: p.append("length")
    if not re.search(r"[A-Z]", pw): p.append("upper")
    if not re.search(r"[a-z]", pw): p.append("lower")
    if not re.search(r"\d", pw): p.append("digit")
    if not any(ch in SPECIAL for ch in pw): p.append("special")
    return p


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(dk) // 2)
        return hmac.compare_digest(got.hex(), dk)
    except Exception:
        return False


_DUMMY = hash_password("Dummy!pass1")  # equalise timing for unknown emails
_sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
_now = lambda: datetime.now(timezone.utc)


def init_tables(db) -> None:
    with db._get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL,
            role TEXT NOT NULL, verified_at TEXT, created_at TEXT NOT NULL, terms_agreed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_codes (
            email TEXT NOT NULL, purpose TEXT NOT NULL, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
            tries INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (email, purpose));
        CREATE TABLE IF NOT EXISTS invites (
            code_hash TEXT PRIMARY KEY, created_by INTEGER NOT NULL, expires_at TEXT NOT NULL, used_by INTEGER);
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, pin_fails INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        """)
        icols = [r[1] for r in conn.execute("PRAGMA table_info(invites)")]
        if "created_at" not in icols:
            conn.execute("ALTER TABLE invites ADD COLUMN created_at TEXT")
        if "revoked_at" not in icols:
            conn.execute("ALTER TABLE invites ADD COLUMN revoked_at TEXT")
        if "pin_hash" not in [r[1] for r in conn.execute("PRAGMA table_info(users)")]:
            conn.execute("ALTER TABLE users ADD COLUMN pin_hash TEXT")
        cols = [r[1] for r in conn.execute("PRAGMA table_info(care_targets)")]
        if "species" not in cols:
            conn.execute("ALTER TABLE care_targets ADD COLUMN species TEXT")
    hs.ensure(db)


class SignupIn(BaseModel):
    email: str
    password: str
    password_confirm: str
    agree_terms: bool = False
    agree_privacy: bool = False
    agree_camera: bool = False
    invite_code: Optional[str] = None


class LoginIn(BaseModel):
    email: str
    password: str
    remember: bool = False


class CodeIn(BaseModel):
    code: str


class EmailIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    email: str
    code: str
    password: str
    password_confirm: str


class PasswordIn(BaseModel):
    current: str
    password: str
    password_confirm: str


class PinIn(BaseModel):
    password: str
    pin: str


class PinUnlockIn(BaseModel):
    pin: str


class PetIn(BaseModel):
    name: str
    species: str
    sex: Optional[str] = None
    birthday: Optional[str] = None
    weight_g: Optional[float] = None


class ScheduleIn(BaseModel):
    care_day_start: str


def install(app: FastAPI, db, sender: Optional[LogSender] = None, cookie_secure: Optional[bool] = None) -> None:
    init_tables(db)
    sender = sender or LogSender(db.db_path.parent / "dev_mail.log")
    secure = cookie_secure if cookie_secure is not None else os.getenv("HOMESTUDIO_COOKIE_SECURE") == "1"
    photo = db.db_path.parent / "pet.jpg"
    fails: Dict[str, List[float]] = {}  # email -> failure timestamps (in-memory, resets on restart)
    sends: Dict[tuple, List[float]] = {}  # (email, purpose) -> send timestamps
    checks: Dict[str, List[float]] = {}  # client ip -> failed invite checks

    def q(sql, args=(), one=False):
        with db._get_connection() as conn:
            cur = conn.execute(sql, args)
            return cur.fetchone() if one else cur.fetchall()

    def current(request: Request):
        tok = request.cookies.get(COOKIE)
        if not tok:
            return None
        row = q("SELECT u.*, s.expires_at FROM auth_sessions s JOIN users u USING(user_id) WHERE s.token_hash=?", (_sha(tok),), True)
        if not row or datetime.fromisoformat(row["expires_at"]) < _now():
            return None
        return row

    def start_session(resp: Response, user_id: int, remember: bool = False):
        tok = secrets.token_urlsafe(32)
        ttl = REMEMBER_TTL if remember else SESSION_TTL
        q("INSERT INTO auth_sessions VALUES (?,?,?,?)", (_sha(tok), user_id, (_now() + ttl).isoformat(), _now().isoformat()))
        resp.set_cookie(COOKIE, tok, max_age=int(ttl.total_seconds()) if remember else None, httponly=True,
                        samesite="strict", secure=secure, path="/")

    def remember_device(resp: Response, user_id: int):
        tok = secrets.token_urlsafe(32)
        q("INSERT INTO devices VALUES (?,?,0,?)", (_sha(tok), user_id, _now().isoformat()))
        resp.set_cookie(DEVICE_COOKIE, tok, max_age=int(DEVICE_TTL.total_seconds()), httponly=True, samesite="strict", secure=secure, path="/")

    def device(request: Request):
        tok = request.cookies.get(DEVICE_COOKIE)
        if not tok:
            return None
        d = q("SELECT d.*, u.pin_hash, u.email FROM devices d JOIN users u USING(user_id) WHERE d.token_hash=?", (_sha(tok),), True)
        if not d or datetime.fromisoformat(d["created_at"]) + DEVICE_TTL < _now():
            return None
        return d

    def send_code(email: str, purpose: str):
        t = time.time()
        recent = [x for x in sends.get((email, purpose), []) if t - x < CODE_TTL.total_seconds()]
        if len(recent) >= CODE_SENDS:
            sends[(email, purpose)] = recent
            return None
        sends[(email, purpose)] = recent + [t]
        code = f"{secrets.randbelow(10 ** 6):06d}"
        q("INSERT OR REPLACE INTO auth_codes VALUES (?,?,?,?,0)", (email, purpose, _sha(code), (_now() + CODE_TTL).isoformat()))
        sender.send(email, purpose, code)
        return (_now() + CODE_TTL).isoformat()

    def check_code(email: str, purpose: str, code: str) -> bool:
        row = q("SELECT * FROM auth_codes WHERE email=? AND purpose=?", (email, purpose), True)
        if not row or datetime.fromisoformat(row["expires_at"]) < _now() or row["tries"] >= CODE_TRIES:
            return False
        if not hmac.compare_digest(row["code_hash"], _sha(code.strip())):
            q("UPDATE auth_codes SET tries=tries+1 WHERE email=? AND purpose=?", (email, purpose))
            return False
        q("DELETE FROM auth_codes WHERE email=? AND purpose=?", (email, purpose))
        return True

    def live_invite(code: str):
        inv = q("SELECT * FROM invites WHERE code_hash=? AND used_by IS NULL AND revoked_at IS NULL",
                (_sha((code or "").strip().upper().replace("-", "")),), True)
        return inv if inv and datetime.fromisoformat(inv["expires_at"]) > _now() else None

    def need(request: Request, admin=False, verified=True):
        u = current(request)
        if not u:
            raise HTTPException(401, "login required")
        if verified and not u["verified_at"]:
            raise HTTPException(403, "email not verified")
        if admin and not hs.can_manage(db, u):
            raise HTTPException(403, "admin only")
        return u

    app.state.need = need

    def check_pw(pw: str, confirm: str):
        probs = password_problems(pw)
        if probs or pw != confirm:
            raise HTTPException(422, {"password": probs, "match": pw == confirm})

    def photo_for(user_id=None):
        sid = hs.space_id(db, user_id) if user_id else 1
        return db.db_path.parent / ("pet.jpg" if sid in (None, 1) else f"pet_{sid}.jpg")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        p = request.url.path
        token = None
        try:
            if (p.startswith("/api/") or p.startswith("/media/")) and not p.startswith(PUBLIC_PREFIXES):
                u = current(request)
                if not u:
                    return JSONResponse({"detail": "login required"}, 401)
                if not u["verified_at"] and not p.startswith(("/api/onboarding",)):
                    return JSONResponse({"detail": "email not verified"}, 403)
                sid = hs.space_id(db, u["user_id"])
                token = hs.current_space.set(sid if sid is not None else -1)
            ctype = request.headers.get("content-type", "")
            if p == "/api/pet/photo" and ctype in ("image/jpeg", "image/png"):
                return await call_next(request)
            bodiless = request.headers.get("content-length") == "0" or \
                ("content-length" not in request.headers and "transfer-encoding" not in request.headers)
            if request.method == "POST" and p.startswith("/api/") and not ctype.startswith("application/json") and not bodiless:
                return JSONResponse({"detail": "json only"}, 415)  # with SameSite=Strict, blocks form-based CSRF
            return await call_next(request)
        finally:
            if token is not None:
                hs.current_space.reset(token)

    def settings(user_id=None):
        rows = dict(q("SELECT key, value FROM app_settings"))
        m = hs.membership(db, user_id) if user_id else None
        sid = m["homespace_id"] if m else None
        if sid:
            pet = q("SELECT name, species, care_day_start_local FROM care_targets WHERE homespace_id=?", (sid,), True)
            for k in ("pet_extra", "onboarding_done"):
                v = hs.get_setting(db, sid, k)
                if v is not None:
                    rows[k] = v
        else:
            pet = q("SELECT name, species, care_day_start_local FROM care_targets LIMIT 1", one=True)
        return rows, pet, m

    @app.get("/api/auth/state")
    def state(request: Request):
        u = current(request)
        rows, pet, m = settings(u["user_id"] if u else None)
        has_admin = q("SELECT 1 FROM users WHERE role='admin' LIMIT 1", one=True) is not None
        d = device(request)
        return {"pin_available": bool(d and d["pin_hash"]), "pin_set": bool(u and u["pin_hash"]),"has_admin": has_admin, "onboarding_done": rows.get("onboarding_done") == "1",
                "user": {"email": u["email"], "role": u["role"], "verified": bool(u["verified_at"]),
                         "space_role": m["role"] if m else None, "homespace_id": m["homespace_id"] if m else None,
                         "homespace_name": m["name"] if m else None} if u else None,
                "pet": {"name": pet["name"], "species": pet["species"], "care_day_start": pet["care_day_start_local"],
                        "has_photo": photo_for(u["user_id"]).is_file(), **json.loads(rows.get("pet_extra", "{}"))} if pet and u else None,
                "mail_sender": "log"}

    @app.post("/api/auth/signup")
    def signup(body: SignupIn, request: Request, response: Response):
        email = body.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(422, {"email": "invalid"})
        check_pw(body.password, body.password_confirm)
        if not (body.agree_terms and body.agree_privacy and body.agree_camera):
            raise HTTPException(422, {"agree": "required"})
        has_admin = q("SELECT 1 FROM users WHERE role='admin' LIMIT 1", one=True) is not None
        invite = None
        if has_admin:
            invite = live_invite(body.invite_code)
            if not invite:
                raise HTTPException(403, "invite required")
        elif (request.client.host if request.client else "") not in LOCAL_CLIENTS:
            raise HTTPException(403, "first admin must be created on the HomeStudio PC (http://127.0.0.1)")
        if q("SELECT 1 FROM users WHERE email=?", (email,), True):
            raise HTTPException(409, "email exists")
        now = _now().isoformat()
        with db._get_connection() as conn:
            uid = conn.execute("INSERT INTO users (email,pw_hash,role,created_at,terms_agreed_at) VALUES (?,?,?,?,?)",
                               (email, hash_password(body.password), "member" if has_admin else "admin", now, now)).lastrowid
            if invite:
                conn.execute("UPDATE invites SET used_by=? WHERE code_hash=?", (uid, invite["code_hash"]))
        space = int(invite["homespace_id"]) if invite and invite["homespace_id"] else 1
        hs.add_member(db, space, uid, "member" if has_admin else "owner")
        start_session(response, uid)
        return {"ok": True, "role": "member" if has_admin else "admin", "code_expires_at": send_code(email, "verify")}

    @app.post("/api/auth/verify")
    def verify(body: CodeIn, request: Request):
        u = need(request, verified=False)
        if not check_code(u["email"], "verify", body.code):
            raise HTTPException(400, "invalid or expired code")
        q("UPDATE users SET verified_at=? WHERE user_id=?", (_now().isoformat(), u["user_id"]))
        return {"ok": True}

    @app.post("/api/auth/resend")
    def resend(request: Request):
        u = need(request, verified=False)
        exp = send_code(u["email"], "verify")
        if not exp:
            raise HTTPException(429, "too many codes; wait and retry")
        return {"ok": True, "code_expires_at": exp}

    @app.post("/api/auth/login")
    def login(body: LoginIn, response: Response):
        email = body.email.strip().lower()
        t = time.time()
        recent = [x for x in fails.get(email, []) if t - x < LOCK_SEC]
        fails[email] = recent
        if len(recent) >= LOCK_FAILS:
            raise HTTPException(429, {"locked_sec": int(LOCK_SEC - (t - recent[0])), "failures": len(recent)})
        u = q("SELECT * FROM users WHERE email=?", (email,), True)
        if not verify_password(body.password, u["pw_hash"] if u else _DUMMY) or not u:
            recent.append(t)
            raise HTTPException(401, {"failures": len(recent), "max": LOCK_FAILS})
        fails.pop(email, None)
        start_session(response, u["user_id"], body.remember)
        if body.remember:
            remember_device(response, u["user_id"])
        return {"ok": True, "verified": bool(u["verified_at"])}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            q("DELETE FROM auth_sessions WHERE token_hash=?", (_sha(tok),))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.post("/api/auth/password")
    def change_password(body: PasswordIn, request: Request):
        u = need(request)
        if not verify_password(body.current, u["pw_hash"]):
            raise HTTPException(401, "current password wrong")
        check_pw(body.password, body.password_confirm)
        q("UPDATE users SET pw_hash=? WHERE user_id=?", (hash_password(body.password), u["user_id"]))
        q("DELETE FROM auth_sessions WHERE user_id=? AND token_hash<>?", (u["user_id"], _sha(request.cookies.get(COOKIE, ""))))
        q("DELETE FROM devices WHERE user_id=? AND token_hash<>?", (u["user_id"], _sha(request.cookies.get(DEVICE_COOKIE, ""))))
        return {"ok": True}

    @app.post("/api/auth/pin")
    def set_pin(body: PinIn, request: Request, response: Response):
        u = need(request)
        if not re.fullmatch(r"\d{4,6}", body.pin):
            raise HTTPException(422, "PIN must be 4-6 digits")
        if not verify_password(body.password, u["pw_hash"]):
            raise HTTPException(401, "password wrong")
        q("UPDATE users SET pin_hash=? WHERE user_id=?", (hash_password(body.pin), u["user_id"]))
        d = device(request)
        if d and d["user_id"] == u["user_id"]:
            q("UPDATE devices SET pin_fails=0 WHERE token_hash=?", (d["token_hash"],))
        else:
            remember_device(response, u["user_id"])
        return {"ok": True}

    @app.post("/api/auth/pin/clear")
    def clear_pin(request: Request):
        u = need(request)
        q("UPDATE users SET pin_hash=NULL WHERE user_id=?", (u["user_id"],))
        return {"ok": True}

    @app.post("/api/auth/lock")
    def lock(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            q("DELETE FROM auth_sessions WHERE token_hash=?", (_sha(tok),))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.post("/api/auth/pin/unlock")
    def pin_unlock(body: PinUnlockIn, request: Request, response: Response):
        d = device(request)
        if not d or not d["pin_hash"]:
            raise HTTPException(401, "no remembered device: use password")
        if not verify_password(body.pin, d["pin_hash"]):
            fails = d["pin_fails"] + 1
            if fails >= PIN_FAILS:
                q("DELETE FROM devices WHERE token_hash=?", (d["token_hash"],))
                response.delete_cookie(DEVICE_COOKIE, path="/")
                raise HTTPException(423, {"failures": fails, "max": PIN_FAILS})
            q("UPDATE devices SET pin_fails=? WHERE token_hash=?", (fails, d["token_hash"]))
            raise HTTPException(401, {"failures": fails, "max": PIN_FAILS})
        q("UPDATE devices SET pin_fails=0 WHERE token_hash=?", (d["token_hash"],))
        start_session(response, d["user_id"])
        return {"ok": True}

    @app.post("/api/pet/photo")
    async def pet_photo(request: Request):
        u = need(request, admin=True)
        if request.headers.get("content-type") not in ("image/jpeg", "image/png"):
            raise HTTPException(415, "jpg/png only")
        try:
            if int(request.headers.get("content-length") or 0) > PHOTO_MAX:
                raise HTTPException(413, "max 2MB")  # refuse before reading anything
        except ValueError:
            raise HTTPException(400, "bad content-length")
        buf = bytearray()
        async for chunk in request.stream():  # chunked uploads: stop as soon as the cap is crossed
            buf += chunk
            if len(buf) > PHOTO_MAX:
                raise HTTPException(413, "max 2MB")
        data = bytes(buf)
        if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")):
            raise HTTPException(415, "not a jpg/png")
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(415, "undecodable image")
        h, w = img.shape[:2]
        k = 512 / max(h, w)
        if k < 1:
            img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])  # re-encode: drops EXIF/GPS/any payload
        photo_for(u["user_id"]).write_bytes(buf.tobytes())
        return {"ok": True}

    @app.get("/media/pet.jpg")
    def pet_jpg(request: Request):
        from fastapi.responses import FileResponse
        u = need(request)
        path = photo_for(u["user_id"])
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.post("/api/auth/forgot")
    def forgot(body: EmailIn):
        email = body.email.strip().lower()
        if q("SELECT 1 FROM users WHERE email=?", (email,), True):
            send_code(email, "reset")
        return {"ok": True}  # same answer either way (no account enumeration)

    @app.post("/api/auth/reset")
    def reset(body: ResetIn):
        email = body.email.strip().lower()
        check_pw(body.password, body.password_confirm)
        if not check_code(email, "reset", body.code):
            raise HTTPException(400, "invalid or expired code")
        uid = q("SELECT user_id FROM users WHERE email=?", (email,), True)["user_id"]
        q("UPDATE users SET pw_hash=?, verified_at=COALESCE(verified_at, ?) WHERE user_id=?", (hash_password(body.password), _now().isoformat(), uid))
        q("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
        q("DELETE FROM devices WHERE user_id=?", (uid,))  # a reset revokes remembered devices, so a PIN can no longer unlock
        fails.pop(email, None)
        return {"ok": True}

    @app.post("/api/invites")
    def create_invite(request: Request):
        u = need(request, admin=True)
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        now = _now()
        exp = (now + INVITE_TTL).isoformat()
        sid = hs.space_id(db, u["user_id"]) or 1
        with db._get_connection() as conn:
            iid = conn.execute("INSERT INTO invites (code_hash, created_by, expires_at, used_by, created_at, homespace_id) VALUES (?,?,?,NULL,?,?)",
                               (_sha(code), u["user_id"], exp, now.isoformat(), sid)).lastrowid
        return {"id": iid, "code": code, "expires_at": exp, "created_at": now.isoformat()}

    @app.get("/api/invites")
    def list_invites(request: Request):
        """Pending (unused, unrevoked, unexpired) invites. Only hashes are stored, so codes are never listed."""
        u = need(request, admin=True)
        sid = hs.space_id(db, u["user_id"]) or 1
        rows = q("""SELECT rowid AS id, created_at, expires_at FROM invites
                    WHERE used_by IS NULL AND revoked_at IS NULL AND (homespace_id IS NULL OR homespace_id=?)
                    ORDER BY rowid""", (sid,))
        return [dict(r) for r in rows if datetime.fromisoformat(r["expires_at"]) > _now()]

    @app.post("/api/invites/{invite_id}/revoke")
    def revoke_invite(invite_id: int, request: Request):
        need(request, admin=True)
        with db._get_connection() as conn:
            n = conn.execute("UPDATE invites SET revoked_at=? WHERE rowid=? AND used_by IS NULL AND revoked_at IS NULL",
                             (_now().isoformat(), invite_id)).rowcount
        if not n:
            raise HTTPException(404, "no pending invite")
        return {"ok": True}

    @app.post("/api/auth/invite/check")
    def check_invite(body: Dict[str, Any], request: Request):
        """Public preview of the home an invite code joins (rate-limited per client: brute force stays impractical)."""
        ip = request.client.host if request.client else ""
        t = time.time()
        recent = [x for x in checks.get(ip, []) if t - x < 600]
        if len(recent) >= INVITE_CHECKS:
            checks[ip] = recent
            raise HTTPException(429, "too many checks")
        inv = live_invite(str(body.get("code") or ""))
        if not inv:
            checks[ip] = recent + [t]
            raise HTTPException(404, "invalid or expired invite")
        rows, pet, _m = settings(inv["created_by"])
        admin = q("SELECT email FROM users WHERE user_id=?", (inv["created_by"],), True)
        local = admin["email"].split("@")[0] if admin else ""
        extra = json.loads(rows.get("pet_extra", "{}"))
        cam = json.loads(rows.get("camera_binding", "null") or "null")
        return {"pet_name": pet["name"] if pet else None, "species": pet["species"] if pet else None, "weight_g": extra.get("weight_g"),
                "birthday": extra.get("birthday"), "has_photo": photo_for(inv["created_by"]).is_file(),
                "admin": (local[:2] + "…") if len(local) > 2 else local, "cameras": 1 if cam else 0,
                "camera_name": rows.get("camera_name"), "expires_at": inv["expires_at"]}

    @app.get("/api/members")
    def members(request: Request):
        u = need(request)
        sid = hs.space_id(db, u["user_id"])
        return hs.members(db, sid) if sid else []

    class RoleIn(BaseModel):
        role: str

    @app.post("/api/members/{user_id}/role")
    def member_role(user_id: int, body: RoleIn, request: Request):
        u = need(request)
        try:
            hs.set_role(db, u["user_id"], user_id, body.role)
        except ValueError:
            raise HTTPException(422, "role")
        except PermissionError:
            raise HTTPException(403, "owner only")
        return {"ok": True}

    @app.post("/api/homespace/transfer")
    def homespace_transfer(body: Dict[str, Any], request: Request):
        u = need(request)
        try:
            hs.transfer(db, u["user_id"], int(body.get("user_id")))
        except (PermissionError, TypeError, ValueError):
            raise HTTPException(403, "owner only")
        return {"ok": True}

    @app.delete("/api/members/{user_id}")
    def member_remove(user_id: int, request: Request):
        u = need(request)
        try:
            hs.remove_member(db, u["user_id"], user_id)
        except PermissionError:
            raise HTTPException(403, "cannot remove")
        return {"ok": True}

    @app.post("/api/onboarding/pet")
    def pet(body: PetIn, request: Request):
        u = need(request, admin=True)
        name = body.name.strip()
        if not 1 <= len(name) <= 10 or body.species not in ("골든 햄스터", "드워프 햄스터", "로보로브스키", "기타 소동물"):
            raise HTTPException(422, "invalid pet")
        sid = hs.space_id(db, u["user_id"]) or 1
        from .insights import _observation_epoch
        with db._get_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE care_targets SET name=?, species=? WHERE homespace_id=?", (name, body.species, sid))
            _observation_epoch(c, sid)
        extra = {"sex": body.sex if body.sex in ("male", "female") else None,
                 "birthday": body.birthday if body.birthday and re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.birthday) else None,
                 "weight_g": body.weight_g if body.weight_g and 0 < body.weight_g < 1000 else None}
        raw = json.dumps(extra)
        hs.put_setting(db, sid, "pet_extra", raw)
        if sid == 1:
            q("INSERT OR REPLACE INTO app_settings VALUES ('pet_extra', ?)", (raw,))
        return {"ok": True}

    @app.post("/api/onboarding/schedule")
    def schedule(body: ScheduleIn, request: Request):
        u = need(request, admin=True)
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", body.care_day_start):
            raise HTTPException(422, "HH:MM")
        sid = hs.space_id(db, u["user_id"]) or 1
        from .insights import _observation_epoch
        with db._get_connection() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE care_targets SET care_day_start_local=? WHERE homespace_id=?", (body.care_day_start, sid))
            _observation_epoch(c, sid)
        return {"ok": True}

    @app.post("/api/onboarding/complete")
    def complete(request: Request):
        u = need(request, admin=True)
        sid = hs.space_id(db, u["user_id"]) or 1
        hs.put_setting(db, sid, "onboarding_done", "1")
        if sid == 1:
            q("INSERT OR REPLACE INTO app_settings VALUES ('onboarding_done','1')")
        return {"ok": True}
