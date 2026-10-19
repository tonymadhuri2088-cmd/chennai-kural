"""SQLite storage for the complaint portal. Standard library only.

Every call opens its own short connection, so the web server's threads and the
background overdue check never share a connection.
"""

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS officers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    field TEXT NOT NULL,
    level TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    zone_number INTEGER
);
CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    citizen_name TEXT NOT NULL,
    citizen_contact TEXT NOT NULL,
    complaint_text TEXT NOT NULL,
    complaint_type TEXT NOT NULL,
    subtype TEXT,
    urgent INTEGER NOT NULL,
    classifier TEXT NOT NULL,
    field TEXT NOT NULL,
    escalation_key TEXT,
    owner_label TEXT NOT NULL,
    fix_days INTEGER,
    fix_hours INTEGER,
    stage_path TEXT NOT NULL,
    stage TEXT NOT NULL,
    stage_since TEXT NOT NULL,
    stage_deadline TEXT,
    status TEXT NOT NULL,
    assigned_officer_id INTEGER,
    resolution_note TEXT,
    zone_number INTEGER,
    zone_name TEXT,
    ward_number INTEGER,
    ward_name TEXT,
    problem_address TEXT,
    landmark TEXT,
    worker_mobile TEXT,
    worker_accepted_at TEXT,
    completed_at TEXT,
    completed_by TEXT
);
CREATE TABLE IF NOT EXISTS workers (
    mobile TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    zone_number INTEGER NOT NULL,
    zone_name TEXT NOT NULL,
    ward_number INTEGER NOT NULL,
    ward_name TEXT,
    department TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    created_at TEXT NOT NULL,
    from_officer_id INTEGER,
    to_officer_id INTEGER,
    payload TEXT NOT NULL,
    UNIQUE (complaint_id, stage)
);
CREATE TABLE IF NOT EXISTS citizens (
    mobile TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    zone_number INTEGER NOT NULL,
    zone_name TEXT NOT NULL,
    ward_number INTEGER NOT NULL,
    ward_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_complaint ON events (complaint_id, id);
CREATE INDEX IF NOT EXISTS complaints_by_officer ON complaints (assigned_officer_id);
CREATE INDEX IF NOT EXISTS complaints_by_deadline ON complaints (status, stage_deadline);
"""

COMPLAINT_COLUMNS = [
    "id", "created_at", "updated_at", "citizen_name", "citizen_contact", "complaint_text",
    "complaint_type", "subtype", "urgent", "classifier", "field", "escalation_key",
    "owner_label", "fix_days", "fix_hours", "stage_path", "stage", "stage_since",
    "stage_deadline", "status", "assigned_officer_id", "resolution_note",
    "zone_number", "zone_name", "ward_number", "ward_name", "problem_address", "landmark",
    "worker_mobile", "worker_accepted_at", "completed_at", "completed_by",
    "complaint_kind", "category", "photo_files",
    "router_message", "router_timeline",
]

# Columns added after the first version. Older database files get them on start-up.
ADDED_COLUMNS = {
    "complaints": {
        "zone_number": "INTEGER",
        "zone_name": "TEXT",
        "ward_number": "INTEGER",
        "ward_name": "TEXT",
        "problem_address": "TEXT",
        "landmark": "TEXT",
        "worker_mobile": "TEXT",
        "worker_accepted_at": "TEXT",
        "completed_at": "TEXT",
        "completed_by": "TEXT",
        "complaint_kind": "TEXT",
        "category": "TEXT",
        "photo_files": "TEXT",
        # What the router produced when the complaint was registered: its message to the citizen,
        # and its timeline (charter repair time and escalation days) as JSON.
        "router_message": "TEXT",
        "router_timeline": "TEXT",
    },
    "officers": {
        "zone_number": "INTEGER",
        "employee_id": "TEXT",
        "position": "TEXT",
        "mobile": "TEXT",
        "email": "TEXT",
        # Accounts made before sign-up existed were set up by an administrator, so they start approved.
        "status": "TEXT NOT NULL DEFAULT 'approved'",
        "created_at": "TEXT",
    },
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Add any column that an older database file does not have yet."""
    for table, columns in ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


class Store:
    """Reads and writes complaints, officers, and the event log."""

    def __init__(self, path: str) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            _migrate(conn)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Citizen accounts

    def get_citizen(self, mobile: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM citizens WHERE mobile = ?", (mobile,)).fetchone()
        return dict(row) if row else None

    def create_citizen(self, mobile: str, name: str, address: str, zone_number: int, zone_name: str,
                       ward_number: int, ward_name: Optional[str], at: str) -> bool:
        """Store a new citizen sign-up. Return False if this mobile number is already registered."""
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO citizens (mobile, name, address, zone_number, zone_name, ward_number, ward_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (mobile, name, address, zone_number, zone_name, ward_number, ward_name, at, at),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def save_citizen(self, mobile: str, name: str, address: str, zone_number: int, zone_name: str,
                     ward_number: int, ward_name: Optional[str], at: str) -> None:
        """Create the citizen's account, or update its details if it exists. The created time is kept."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO citizens (mobile, name, address, zone_number, zone_name, ward_number, ward_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mobile) DO UPDATE SET
                    name = excluded.name, address = excluded.address,
                    zone_number = excluded.zone_number, zone_name = excluded.zone_name,
                    ward_number = excluded.ward_number, ward_name = excluded.ward_name,
                    updated_at = excluded.updated_at
                """,
                (mobile, name, address, zone_number, zone_name, ward_number, ward_name, at, at),
            )

    # Complaints

    def new_complaint_id(self, now: datetime) -> str:
        """Return an unused complaint ID such as CMP-20261015-4821."""
        day = now.strftime("%Y%m%d")
        while True:
            candidate = f"CMP-{day}-{secrets.randbelow(10000):04d}"
            if self.get_complaint(candidate) is None:
                return candidate

    def insert_complaint(self, row: Dict[str, Any]) -> None:
        columns = ", ".join(COMPLAINT_COLUMNS)
        marks = ", ".join("?" for _ in COMPLAINT_COLUMNS)
        values = [row.get(column) for column in COMPLAINT_COLUMNS]
        with self._conn() as conn:
            conn.execute(f"INSERT INTO complaints ({columns}) VALUES ({marks})", values)

    def get_complaint(self, complaint_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return dict(row) if row else None

    def list_complaints(self, where: str = "1 = 1", params: Sequence[Any] = (), limit: int = 200) -> List[Dict[str, Any]]:
        """List complaints. The where clause is written by this code, never taken from a user."""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM complaints WHERE {where} ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_complaint(self, complaint_id: str, **fields: Any) -> None:
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE complaints SET {assignments} WHERE id = ?",
                (*fields.values(), complaint_id),
            )

    def claim_complaint(self, complaint_id: str, mobile: str, at: str) -> bool:
        """Give an open complaint to a worker. False if it is closed or another worker already has it."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE complaints SET worker_mobile = ?, worker_accepted_at = ?, updated_at = ? "
                "WHERE id = ? AND worker_mobile IS NULL AND status = 'open'",
                (mobile, at, at, complaint_id),
            )
            return cursor.rowcount == 1

    def release_complaint(self, complaint_id: str, at: str) -> None:
        """Take the complaint back from its worker. It stays open."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE complaints SET worker_mobile = NULL, worker_accepted_at = NULL, updated_at = ? WHERE id = ?",
                (at, complaint_id),
            )

    # Workers

    def get_worker(self, mobile: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM workers WHERE mobile = ?", (mobile,)).fetchone()
        return dict(row) if row else None

    def create_worker(self, mobile: str, name: str, address: str, zone_number: int, zone_name: str,
                      ward_number: int, ward_name: Optional[str], department: str, at: str) -> bool:
        """Store a new worker sign-up. Return False if this mobile number is already registered as a worker."""
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO workers (mobile, name, address, zone_number, zone_name, ward_number, ward_name,
                                         department, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (mobile, name, address, zone_number, zone_name, ward_number, ward_name, department, at, at),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    # Notices for officers (a complaint that passed its time limit)

    def add_notice(self, complaint_id: str, stage: str, at: str, from_officer_id: Optional[int],
                   to_officer_id: Optional[int], payload: str) -> bool:
        """Record a notice once per complaint and stage. Return False if it was already recorded."""
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO notices (complaint_id, stage, created_at, from_officer_id, to_officer_id, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (complaint_id, stage, at, from_officer_id, to_officer_id, payload),
            )
            return cursor.rowcount == 1

    def list_notices(self, officer_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """Notices for one officer (sent from or to them), or every notice when officer_id is None."""
        with self._conn() as conn:
            if officer_id is None:
                rows = conn.execute("SELECT * FROM notices ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notices WHERE from_officer_id = ? OR to_officer_id = ? ORDER BY id DESC LIMIT ?",
                    (officer_id, officer_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    # Events

    def add_event(self, complaint_id: str, at: str, actor: str, kind: str, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (complaint_id, at, actor, kind, message) VALUES (?, ?, ?, ?, ?)",
                (complaint_id, at, actor, kind, message),
            )

    def get_events(self, complaint_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE complaint_id = ? ORDER BY id", (complaint_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    # Officers

    def insert_officer(self, username: str, name: str, field: str, level: str, password_hash: str,
                       zone_number: Optional[int] = None, *, employee_id: Optional[str] = None,
                       position: Optional[str] = None, mobile: Optional[str] = None, email: Optional[str] = None,
                       status: str = "approved", at: Optional[str] = None) -> int:
        """Add an officer. Sign-ups are added with status "pending" until the District Head Office approves them."""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO officers (username, name, field, level, password_hash, zone_number,
                                      employee_id, position, mobile, email, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (username, name, field, level, password_hash, zone_number,
                 employee_id, position, mobile, email, status, at),
            )
            return int(cursor.lastrowid)

    def set_officer_status(self, username: str, status: str) -> bool:
        """Approve or change an officer account. Return False if no officer has this username."""
        with self._conn() as conn:
            cursor = conn.execute("UPDATE officers SET status = ? WHERE username = ?", (status, username))
            return cursor.rowcount == 1

    def get_officer(self, officer_id: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM officers WHERE id = ?", (officer_id,)).fetchone()
        return dict(row) if row else None

    def get_officer_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM officers WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

    def list_officers(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM officers ORDER BY field, level, username").fetchall()
        return [dict(row) for row in rows]

    def find_officer(self, field: str, level: str, zone_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Return the officer for a field, level, and zone.

        An officer set up for this zone is preferred. Otherwise an officer with no zone (covering the whole
        city) is used. The district head covers every field.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM officers
                WHERE level = ? AND (field = ? OR field = 'all')
                  AND (zone_number IS NULL OR zone_number = ?)
                ORDER BY CASE WHEN zone_number = ? THEN 0 ELSE 1 END,
                         CASE WHEN field = ? THEN 0 ELSE 1 END,
                         id
                LIMIT 1
                """,
                (level, field, zone_number, zone_number, field),
            ).fetchone()
        return dict(row) if row else None
