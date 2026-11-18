import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator
import uuid

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_daypart(started_at: str) -> Optional[str]:
    """Classify the stored event-start time in KST; this is not an IR-filter reading."""
    try:
        value = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        # KST is UTC+09:00 year-round; fixed offset avoids a tzdata dependency on Windows.
        hour = value.astimezone(timezone(timedelta(hours=9))).hour
        return "night" if hour >= 18 or hour < 6 else "day"
    except (AttributeError, TypeError, ValueError):
        return None

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            with conn:
                yield conn
        finally:
            conn.close()

    def close(self) -> None:
        pass

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sensors (
                sensor_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                physical_device TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                firmware_version TEXT
            );

            CREATE TABLE IF NOT EXISTS care_targets (
                care_target_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'Asia/Seoul',
                care_day_start_local TEXT NOT NULL DEFAULT '12:00',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                care_target_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                activity_score REAL NOT NULL,
                quality_score REAL NOT NULL,
                clip_path TEXT,
                thumbnail_path TEXT,
                is_protected INTEGER NOT NULL DEFAULT 0,
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                distance_px REAL,
                active_frames INTEGER,
                track_json TEXT,
                FOREIGN KEY (sensor_id) REFERENCES sensors (sensor_id),
                FOREIGN KEY (care_target_id) REFERENCES care_targets (care_target_id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_started_at ON events(started_at);
            CREATE INDEX IF NOT EXISTS idx_events_is_protected ON events(is_protected);
            CREATE TABLE IF NOT EXISTS online_minutes (minute TEXT PRIMARY KEY);  -- UTC 'YYYY-MM-DDTHH:MM' with a healthy frame (data coverage)
            CREATE TABLE IF NOT EXISTS baseline_revisions (
                homespace_id INTEGER PRIMARY KEY,
                signature TEXT NOT NULL,
                since TEXT NOT NULL,
                revision INTEGER NOT NULL,
                rebuilding INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_data_revision (
                id INTEGER PRIMARY KEY CHECK (id = 1), revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_observations (
                event_id TEXT PRIMARY KEY,
                homespace_id INTEGER NOT NULL,
                analysis_revision TEXT NOT NULL,
                roi_revision INTEGER,
                result_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_observations_space ON event_observations(homespace_id, event_id);
            INSERT OR IGNORE INTO event_data_revision VALUES (1, 0);
            CREATE TRIGGER IF NOT EXISTS events_revision_insert AFTER INSERT ON events
            BEGIN UPDATE event_data_revision SET revision = revision + 1 WHERE id = 1; END;
            CREATE TRIGGER IF NOT EXISTS events_revision_update AFTER UPDATE ON events
            BEGIN UPDATE event_data_revision SET revision = revision + 1 WHERE id = 1; END;
            CREATE TRIGGER IF NOT EXISTS events_revision_delete AFTER DELETE ON events
            BEGIN UPDATE event_data_revision SET revision = revision + 1 WHERE id = 1; END;

            -- Default seed data
            INSERT OR IGNORE INTO sensors (sensor_id, source_type, physical_device, role, status, last_seen_at)
            VALUES ('camera-primary', 'camera', 'TVS-W1000', 'primary_view', 'online', datetime('now'));

            INSERT OR IGNORE INTO care_targets (care_target_id, name, target_type, timezone, care_day_start_local, created_at)
            VALUES ('target-hamster', '햄스터', 'hamster', 'Asia/Seoul', '12:00', datetime('now'));
            """)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
            for col, typ in (("distance_px", "REAL"), ("active_frames", "INTEGER"), ("track_json", "TEXT"), ("behavior_json", "TEXT"), ("original_path", "TEXT"),
                             ("capture_daypart", "TEXT"), ("capture_daypart_source", "TEXT"), ("ir_cut_state", "TEXT")):
                if col not in cols:
                    conn.execute(f"ALTER TABLE events ADD COLUMN {col} {typ}")
            # Backfill once from immutable event time. Do not infer optical IR-cut position.
            for row in conn.execute("SELECT event_id, started_at FROM events WHERE capture_daypart IS NULL").fetchall():
                daypart = _capture_daypart(row["started_at"])
                conn.execute("UPDATE events SET capture_daypart=?, capture_daypart_source='legacy_timestamp', ir_cut_state='unknown' WHERE event_id=?",
                             (daypart, row["event_id"]))
            sensor_cols = {r[1] for r in conn.execute("PRAGMA table_info(sensors)")}
            for col, typ in (("homespace_id", "INTEGER NOT NULL DEFAULT 1"), ("name", "TEXT"),
                             ("installation_json", "TEXT NOT NULL DEFAULT '{}'"),
                             ("installation_revision", "INTEGER NOT NULL DEFAULT 1"), ("updated_at", "TEXT"),
                             ("hardware_key", "TEXT"), ("hardware_mac", "TEXT"), ("csi_source", "TEXT"),
                             ("device_type", "TEXT"), ("usb_serial_number", "TEXT"), ("usb_port", "TEXT")):
                if col not in sensor_cols:
                    conn.execute(f"ALTER TABLE sensors ADD COLUMN {col} {typ}")
            conn.execute("UPDATE sensors SET name=physical_device WHERE name IS NULL")
            conn.execute("UPDATE sensors SET updated_at=last_seen_at WHERE updated_at IS NULL")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_sensors_space ON sensors(homespace_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sensors_space_hardware ON sensors(homespace_id, hardware_key)
                    WHERE source_type='wifi_csi' AND hardware_key IS NOT NULL;
                CREATE TABLE IF NOT EXISTS sensor_installation_history (
                    sensor_id TEXT NOT NULL, homespace_id INTEGER NOT NULL, revision INTEGER NOT NULL,
                    installation_json TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(sensor_id, revision));
            """)
        from .homespace import ensure
        ensure(self)

    def event_revision(self) -> int:
        with self._get_connection() as conn:
            return conn.execute("SELECT revision FROM event_data_revision WHERE id=1").fetchone()[0]

    def insert_event(
        self,
        event_type: str,
        started_at: str,
        ended_at: str,
        duration_sec: float,
        activity_score: float = 1.0,
        quality_score: float = 1.0,
        clip_path: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        file_size_bytes: int = 0,
        sensor_id: str = "camera-primary",
        care_target_id: str = "target-hamster",
        event_id: Optional[str] = None,
        distance_px: Optional[float] = None,
        active_frames: Optional[int] = None,
        track_json: Optional[str] = None,
        behavior_json: Optional[str] = None,
        homespace_id: int = 1,
        original_path: Optional[str] = None,
    ) -> str:
        if not event_id:
            event_id = f"evt_{uuid.uuid4().hex[:12]}"
        
        now = utc_now_iso()
        capture_daypart = _capture_daypart(started_at)
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO events (
                event_id, event_type, source_type, sensor_id, care_target_id,
                started_at, ended_at, duration_sec, activity_score, quality_score,
                clip_path, thumbnail_path, is_protected, file_size_bytes, created_at,
                distance_px, active_frames, track_json, behavior_json, homespace_id, original_path,
                capture_daypart, capture_daypart_source, ir_cut_state
            ) VALUES (?, ?, 'camera', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'capture_time', 'unknown')
            """, (
                event_id, event_type, sensor_id, care_target_id,
                started_at, ended_at, duration_sec, activity_score, quality_score,
                clip_path, thumbnail_path, file_size_bytes, now,
                distance_px, active_frames, track_json, behavior_json, homespace_id, original_path, capture_daypart
            ))
        return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        from .homespace import sql_space
        frag, args = sql_space()
        with self._get_connection() as conn:
            row = conn.execute(f"SELECT * FROM events WHERE event_id = ?{frag}", (event_id, *args)).fetchone()
            return dict(row) if row else None

    def delete_event(self, event_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            if cur.rowcount:
                conn.execute("DELETE FROM event_observations WHERE event_id = ?", (event_id,))
            return cur.rowcount > 0

    def list_events(
        self,
        limit: int = 50,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from .homespace import sql_space
        frag, extra = sql_space()
        query = "SELECT * FROM events WHERE 1=1" + frag
        params: List[Any] = list(extra)
        if start_time:
            query += " AND started_at >= ?"
            params.append(start_time)
        if end_time:
            query += " AND started_at <= ?"
            params.append(end_time)
        
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def list_sessions(self, gap_sec: float = 30.0, start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict[str, Any]]:
        """Activity sessions derived from events: consecutive events whose gap is <= gap_sec (covers 60s splits)."""
        from datetime import datetime
        ts = lambda v: datetime.fromisoformat(v).timestamp()
        from .homespace import sql_space
        frag, extra = sql_space()
        query, params = "SELECT started_at, ended_at, duration_sec, distance_px, active_frames FROM events WHERE 1=1" + frag, list(extra)
        if start_time:
            query += " AND started_at >= ?"
            params.append(start_time)
        if end_time:
            query += " AND started_at <= ?"
            params.append(end_time)
        with self._get_connection() as conn:
            rows = conn.execute(query + " ORDER BY started_at", params).fetchall()
        sessions: List[Dict[str, Any]] = []
        for r in sorted(rows, key=lambda r: ts(r["started_at"])):  # mixed Z/+00:00 strings do not sort lexically
            cur = sessions[-1] if sessions else None
            if cur is None or ts(r["started_at"]) - ts(cur["ended_at"]) > gap_sec:
                cur = {"started_at": r["started_at"], "ended_at": r["ended_at"], "active_sec": 0.0,
                       "distance_px": 0.0, "active_frames": 0, "event_count": 0}
                sessions.append(cur)
            if ts(r["ended_at"]) > ts(cur["ended_at"]):
                cur["ended_at"] = r["ended_at"]
            cur["active_sec"] = round(cur["active_sec"] + r["duration_sec"], 2)
            cur["distance_px"] = round(cur["distance_px"] + (r["distance_px"] or 0.0), 2)
            cur["active_frames"] += r["active_frames"] or 0
            cur["event_count"] += 1
        for x in sessions:
            x["span_sec"] = round(ts(x["ended_at"]) - ts(x["started_at"]), 2)
        return sessions

    def set_event_protection(self, event_id: str, is_protected: bool) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE events SET is_protected = ? WHERE event_id = ?",
                (1 if is_protected else 0, event_id)
            )
            return cur.rowcount > 0

    def get_unprotected_events_oldest_first(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE is_protected = 0 AND (clip_path IS NOT NULL OR original_path IS NOT NULL) ORDER BY started_at ASC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_event_media_deleted(self, event_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE events SET clip_path = NULL, thumbnail_path = NULL, original_path = NULL, file_size_bytes = 0 WHERE event_id = ?",
                (event_id,)
            )

    def get_total_media_bytes(self) -> int:
        with self._get_connection() as conn:
            row = conn.execute("SELECT COALESCE(SUM(file_size_bytes), 0) AS total FROM events").fetchone()
            return int(row["total"]) if row else 0

    def update_sensor_heartbeat(self, sensor_id: str = "camera-primary", status: str = "online") -> None:
        now = utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sensors SET status = ?, last_seen_at = ? WHERE sensor_id = ?",
                (status, now, sensor_id)
            )
            if status == "online":
                conn.execute("INSERT OR IGNORE INTO online_minutes VALUES (?)", (now[:16],))
