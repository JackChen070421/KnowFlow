"""Local-only accounts and in-memory sessions for the dashboard.

The dashboard is a single-process demo on 127.0.0.1, so sessions live in memory
and disappear when the window closes. Passwords are stored as salted scrypt
hashes in ``data/auth/users.json`` (Git-ignored); the file is generated on first
start and is never served to the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from knowflow.contracts import repo_root

COOKIE_NAME = "kf_session"
DEFAULT_PASSWORD = "123456"
DEFAULT_TTL_SECONDS = 8 * 3600

# scrypt parameters: ~16 MB of memory per hash, fast enough for a local login.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(
    password: str,
    salt_hex: str | None = None,
    *,
    n: int = _SCRYPT_N,
    r: int = _SCRYPT_R,
    p: int = _SCRYPT_P,
) -> dict[str, str]:
    """Return ``{"salt": ..., "password_hash": ...}`` as hex strings."""

    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_DKLEN,
        maxmem=64 * 1024 * 1024,
    )
    return {"salt": salt.hex(), "password_hash": digest.hex()}


def verify_password(password: str, salt_hex: str, expected_hex: str) -> bool:
    if not salt_hex or not expected_hex:
        return False
    candidate = hash_password(password, salt_hex)["password_hash"]
    return hmac.compare_digest(candidate, expected_hex)


@dataclass(frozen=True)
class Account:
    username: str
    role: str  # "teacher" | "student"
    student_id: str | None
    display_name: str

    def as_dict(self) -> dict:
        return {
            "authenticated": True,
            "username": self.username,
            "role": self.role,
            "student_id": self.student_id,
            "display_name": self.display_name,
        }


def default_users_path() -> Path:
    return repo_root() / "data" / "auth" / "users.json"


def write_default_users(path: Path, student_id: str, password: str = DEFAULT_PASSWORD) -> dict:
    """Create the demo account file: one teacher plus one student."""

    accounts = [
        {
            "username": "teacher",
            "role": "teacher",
            "student_id": None,
            "display_name": "教师",
        },
        {
            "username": student_id,
            "role": "student",
            "student_id": student_id,
            "display_name": f"学生 {student_id}",
        },
    ]
    for account in accounts:
        account.update(hash_password(password))
    document = {
        "version": 1,
        "note": "本机演示账号：密码为 scrypt 哈希，本文件已被 Git 忽略，请勿提交或分享。",
        "users": accounts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return document


class AuthStore:
    """Accounts loaded from disk plus volatile sessions."""

    def __init__(
        self,
        path: Path,
        student_id: str,
        password: str = DEFAULT_PASSWORD,
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.ttl = ttl
        self.created = False
        if not self.path.is_file():
            write_default_users(self.path, student_id, password)
            self.created = True
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self._users = {str(u["username"]): u for u in document.get("users", [])}
        self._sessions: dict[str, tuple[Account, float]] = {}

    @property
    def usernames(self) -> list[str]:
        return sorted(self._users)

    def authenticate(self, username: str, password: str) -> Account | None:
        user = self._users.get((username or "").strip())
        if user is None:
            # Compare against a dummy hash so a missing user costs the same time.
            hash_password(password or "", "00" * 16)
            return None
        if not verify_password(
            password or "", user.get("salt", ""), user.get("password_hash", "")
        ):
            return None
        role = user.get("role") or "student"
        return Account(
            username=str(user["username"]),
            role=role,
            student_id=user.get("student_id"),
            display_name=str(user.get("display_name") or user["username"]),
        )

    def new_session(self, account: Account) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (account, time.time() + self.ttl)
        return token

    def resolve(self, token: str | None) -> Account | None:
        if not token:
            return None
        entry = self._sessions.get(token)
        if entry is None:
            return None
        account, expires = entry
        if expires < time.time():
            self._sessions.pop(token, None)
            return None
        return account

    def drop(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)
