"""Password hashing, login sessions, and one-time codes. Standard library only."""

import hashlib
import hmac
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

ITERATIONS = 200_000
SESSION_HOURS = 8
CODE_MINUTES = 10
MAX_CODE_TRIES = 5
CITIZEN_SESSION_DAYS = 365  # citizens stay logged in until they log out; this caps it at a year
# India has no daylight saving, so a fixed offset is exact and needs no time-zone database.
INDIA = timezone(timedelta(hours=5, minutes=30), "IST")


def next_midnight_india(now: datetime) -> datetime:
    """The next 00:00 in India (IST) after this moment, as an aware UTC datetime."""
    local = now.astimezone(INDIA)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Check a password against a stored hash. Malformed hashes never match."""
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


class Sessions:
    """Login sessions kept in memory. A server restart logs everyone out.

    The portal keeps two sets: one for officers (the stored value is the officer's ID) and one
    for citizens (the stored value is the citizen's mobile number).
    """

    def __init__(self) -> None:
        self._items: Dict[str, Tuple[Any, datetime]] = {}
        self._lock = threading.Lock()

    def create(self, subject: Any, now: datetime, expires: Optional[datetime] = None) -> str:
        """Start a session and return its token. It ends at expires (default: SESSION_HOURS from now)."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._items[token] = (subject, expires or now + timedelta(hours=SESSION_HOURS))
        return token

    def who(self, token: Optional[str], now: datetime) -> Optional[Any]:
        """Return what a token was issued for, or None if it is unknown or expired."""
        if not token:
            return None
        with self._lock:
            item = self._items.get(token)
            if item is None:
                return None
            subject, expires = item
            if now >= expires:
                del self._items[token]
                return None
            return subject

    def officer_id(self, token: Optional[str], now: datetime) -> Optional[Any]:
        """Same as who(), named for officer sessions."""
        return self.who(token, now)

    def drop(self, token: Optional[str]) -> None:
        """End a session."""
        if token:
            with self._lock:
                self._items.pop(token, None)


class OneTimeCodes:
    """Six-digit codes that expire, and stop working after too many wrong tries. Kept in memory.

    Each code is stored as a digest bound to its key, so a code issued for one key cannot be
    used for another. A code is used up on the first success.
    """

    def __init__(self) -> None:
        self._items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _digest(key: str, code: str) -> str:
        return hashlib.sha256(f"{key}:{code}".encode("utf-8")).hexdigest()

    def issue(self, key: str, now: datetime, payload: Any = None) -> str:
        """Create a new code for a key, replacing any code already issued for it."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        with self._lock:
            self._items[key] = {
                "digest": self._digest(key, code),
                "expires": now + timedelta(minutes=CODE_MINUTES),
                "tries": 0,
                "payload": payload,
            }
        return code

    def pending(self, key: str, now: datetime) -> bool:
        """True if a code is waiting to be entered for this key."""
        with self._lock:
            item = self._items.get(key)
            return item is not None and now < item["expires"]

    def check(self, key: str, code: Any, now: datetime) -> Tuple[str, Any]:
        """Check a code. Return (outcome, payload).

        Outcome is "ok", "wrong", "expired", "locked", or "none". The payload is returned only on "ok".
        """
        given = code.strip() if isinstance(code, str) else ""
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return "none", None
            if now >= item["expires"]:
                del self._items[key]
                return "expired", None
            if item["tries"] >= MAX_CODE_TRIES:
                del self._items[key]
                return "locked", None
            if hmac.compare_digest(item["digest"], self._digest(key, given)):
                del self._items[key]
                return "ok", item["payload"]
            item["tries"] += 1
            return "wrong", None

    def drop(self, key: str) -> None:
        """Forget any code issued for a key."""
        with self._lock:
            self._items.pop(key, None)
