"""One SQLite database, one row-set per homespace.

A homespace is a household: its pet, zones, events, and care-day settings.
People join that space as owner, subadmin, or member. Individual names and
polygons are rows, not source constants. Separate database files per space
would split the one camera pipeline on this host; the space id is the boundary.
"""
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

current_space: ContextVar[Optional[int]] = ContextVar("hs_space", default=None)

OWNER, SUBADMIN, MEMBER = "owner", "subadmin", "member"
MANAGE = (OWNER, SUBADMIN)


def sql_space(column: str = "homespace_id"):
    sid = current_space.get()
    if sid is None:
        return "", []
    return f" AND {column} = ?", [sid]


def ensure(db, backfill: bool = True) -> None:
    with db._get_connection() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS homespaces (
            homespace_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS homespace_members (
            homespace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (homespace_id, user_id));
        CREATE TABLE IF NOT EXISTS space_settings (
            homespace_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (homespace_id, key));
        CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        _add(c, "events", "homespace_id", "INTEGER NOT NULL DEFAULT 1")
        _add(c, "care_targets", "homespace_id", "INTEGER NOT NULL DEFAULT 1")
        _add(c, "invites", "homespace_id", "INTEGER NOT NULL DEFAULT 1")
        if c.execute("SELECT 1 FROM homespaces WHERE homespace_id=1").fetchone() is None:
            pet = c.execute("SELECT name FROM care_targets ORDER BY created_at LIMIT 1").fetchone()
            label = "우리 집"
            if pet and pet[0] and pet[0] not in ("햄스터", "모찌", "보리"):
                label = f"{pet[0]} 홈"
            c.execute("INSERT INTO homespaces (homespace_id, name, created_at) VALUES (1, ?, ?)",
                      (label, datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE care_targets SET homespace_id=1 WHERE homespace_id IS NULL OR homespace_id=0")
        for k in ("zones", "pet_extra", "onboarding_done"):
            if c.execute("SELECT 1 FROM space_settings WHERE homespace_id=1 AND key=?", (k,)).fetchone():
                continue
            row = c.execute("SELECT value FROM app_settings WHERE key=?", (k,)).fetchone()
            if row:
                c.execute("INSERT INTO space_settings (homespace_id, key, value) VALUES (1, ?, ?)", (k, row[0]))
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        n = c.execute("SELECT COUNT(*) FROM homespace_members").fetchone()[0]
        if backfill and n == 0 and "users" in tables:
            users = c.execute("SELECT user_id, role FROM users ORDER BY user_id").fetchall()
            owner_set = False
            for u in users:
                role = MEMBER
                if u[1] == "admin" and not owner_set:
                    role, owner_set = OWNER, True
                elif u[1] == "admin":
                    role = SUBADMIN
                c.execute("INSERT OR IGNORE INTO homespace_members (homespace_id, user_id, role) VALUES (1, ?, ?)",
                          (u[0], role))


def _add(c, table: str, col: str, decl: str) -> None:
    if table not in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        return
    have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
    if col not in have:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def space_id(db, user_id: int) -> Optional[int]:
    m = membership(db, user_id)
    return m["homespace_id"] if m else None


def membership(db, user_id: int) -> Optional[Dict[str, Any]]:
    ensure(db)
    with db._get_connection() as c:
        row = c.execute("""
            SELECT m.homespace_id, m.user_id, m.role, h.name
            FROM homespace_members m JOIN homespaces h USING (homespace_id)
            WHERE m.user_id=?""", (user_id,)).fetchone()
    return dict(row) if row else None


def can_manage(db, user) -> bool:
    m = membership(db, user["user_id"])
    return bool(m and m["role"] in MANAGE)


def can_delete_events(db, user) -> bool:
    return membership(db, user["user_id"]) is not None


def get_setting(db, space_id_: int, key: str) -> Optional[str]:
    ensure(db, backfill=False)
    with db._get_connection() as c:
        row = c.execute("SELECT value FROM space_settings WHERE homespace_id=? AND key=?", (space_id_, key)).fetchone()
    return row[0] if row else None


def put_setting(db, space_id_: int, key: str, value: str) -> None:
    ensure(db, backfill=False)
    with db._get_connection() as c:
        c.execute("INSERT OR REPLACE INTO space_settings (homespace_id, key, value) VALUES (?, ?, ?)",
                  (space_id_, key, value))


def add_member(db, space_id_: int, user_id: int, role: str) -> None:
    ensure(db, backfill=False)
    if role not in (OWNER, SUBADMIN, MEMBER):
        raise ValueError("role")
    with db._get_connection() as c:
        c.execute("INSERT OR IGNORE INTO homespace_members (homespace_id, user_id, role) VALUES (?, ?, ?)",
                  (space_id_, user_id, role))


def members(db, space_id_: int) -> List[Dict[str, Any]]:
    ensure(db, backfill=False)
    with db._get_connection() as c:
        rows = c.execute("""
            SELECT u.user_id, u.email, m.role, u.verified_at IS NOT NULL AS verified
            FROM homespace_members m JOIN users u USING (user_id)
            WHERE m.homespace_id=?
            ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'subadmin' THEN 1 ELSE 2 END, u.user_id
        """, (space_id_,)).fetchall()
    return [{**dict(r), "verified": bool(r["verified"])} for r in rows]


def _pair(db, actor_id: int, target_id: int):
    a, t = membership(db, actor_id), membership(db, target_id)
    if not a or not t or a["homespace_id"] != t["homespace_id"]:
        raise PermissionError("not in this homespace")
    return a, t


def set_role(db, actor_id: int, target_id: int, role: str) -> None:
    if role not in (SUBADMIN, MEMBER):
        raise ValueError("role")
    a, t = _pair(db, actor_id, target_id)
    if a["role"] != OWNER or t["role"] == OWNER or actor_id == target_id:
        raise PermissionError("owner only")
    with db._get_connection() as c:
        c.execute("UPDATE homespace_members SET role=? WHERE homespace_id=? AND user_id=?",
                  (role, a["homespace_id"], target_id))


def transfer(db, actor_id: int, target_id: int) -> None:
    a, t = _pair(db, actor_id, target_id)
    if a["role"] != OWNER or t["role"] == OWNER or actor_id == target_id:
        raise PermissionError("owner only")
    with db._get_connection() as c:
        verified = c.execute("SELECT verified_at FROM users WHERE user_id=?", (target_id,)).fetchone()
        if not verified or not verified[0]:
            raise PermissionError("unverified")
        c.execute("UPDATE homespace_members SET role=? WHERE homespace_id=? AND user_id=?",
                  (OWNER, a["homespace_id"], target_id))
        c.execute("UPDATE homespace_members SET role=? WHERE homespace_id=? AND user_id=?",
                  (SUBADMIN, a["homespace_id"], actor_id))


def remove_member(db, actor_id: int, target_id: int) -> None:
    a, t = _pair(db, actor_id, target_id)
    if t["role"] == OWNER or actor_id == target_id:
        raise PermissionError("cannot remove the owner")
    if a["role"] == SUBADMIN and t["role"] != MEMBER:
        raise PermissionError("subadmin can remove members only")
    if a["role"] not in MANAGE:
        raise PermissionError("manage only")
    with db._get_connection() as c:
        c.execute("DELETE FROM homespace_members WHERE homespace_id=? AND user_id=?", (a["homespace_id"], target_id))
        c.execute("DELETE FROM auth_sessions WHERE user_id=?", (target_id,))
