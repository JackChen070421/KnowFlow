"""Local-only accounts, sessions and per-account settings for the dashboard.

The dashboard is a single-process demo on 127.0.0.1, so sessions live in memory
and disappear when the window closes. Passwords are stored as salted scrypt
hashes in ``data/auth/users.json`` (Git-ignored); the file is generated on first
start and is never served to the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from knowflow.contracts import repo_root

COOKIE_NAME = "kf_session"
DEFAULT_PASSWORD = "123456"
DEFAULT_TTL_SECONDS = 8 * 3600
MIN_PASSWORD_LENGTH = 8

# scrypt parameters: ~16 MB of memory per hash, fast enough for a local login.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32

TONE_CHOICES = ("warm", "direct", "rigorous")
LENGTH_CHOICES = ("brief", "standard", "detailed")
INSUFFICIENT_CHOICES = ("prompt", "probe")
HOME_CHOICES = ("overview", "course", "students", "plan")
SEMESTER_CHOICES = ("第一学期", "第二学期", "全年")

DEFAULT_PROFILE = {
    "term": "2026-2027秋",
    "classes": "",
    "subject": "数学",
}
TERM_PATTERN = re.compile(r"^\d{4}-\d{4}[春秋]$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")
DEFAULT_PREFERENCES = {
    "tone": "warm",
    "report_length": "standard",
    "insufficient": "prompt",
    "home_view": "overview",
}
DEFAULT_THRESHOLDS = {
    # 与 knowflow.diagnosis.mastery.DiagnosisConfig 的默认口径对齐（0.75 / 0.40 / 2），
    # 这样合并后正式数据的诊断数字与已有报告、PPT 保持一致。
    "coverage_sufficient": 10,
    "coverage_missing": 3,
    # 诊断门槛单独一项：过去它由 coverage_missing 直接换算，改一个覆盖率显示阈值
    # 就会把所有知识点推成"待观察"。两者分开后各管一件事。
    "min_evidence": 2,
    "mastery_mastered": 75,
    "mastery_weak": 40,
}


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
            "profile": dict(DEFAULT_PROFILE),
            "preferences": dict(DEFAULT_PREFERENCES),
            "thresholds": dict(DEFAULT_THRESHOLDS),
        },
        {
            "username": student_id,
            "role": "student",
            "student_id": student_id,
            "display_name": f"学生 {student_id}",
            "profile": dict(DEFAULT_PROFILE),
            "preferences": dict(DEFAULT_PREFERENCES),
            "thresholds": dict(DEFAULT_THRESHOLDS),
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


def _clean_text(value, limit: int, label: str) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValueError(f"{label}不能超过 {limit} 个字。")
    return text


def _migrate_profile(profile: dict | None) -> dict:
    """Accept the older ``year`` + ``semester`` pair and expose ``term``."""

    source = dict(profile or {})
    merged = {**DEFAULT_PROFILE, **source}
    if not source.get("term"):
        year = str(source.get("year") or "2026-2027")
        semester = str(source.get("semester") or "第一学期")
        merged["term"] = f"{year}{'秋' if '第一' in semester else '春'}"
    merged.pop("year", None)
    merged.pop("semester", None)
    return merged


def _validate_thresholds(values: dict) -> dict:
    merged = {**DEFAULT_THRESHOLDS, **(values or {})}
    try:
        coverage_ok = int(merged["coverage_sufficient"])
        coverage_missing = int(merged["coverage_missing"])
        min_evidence = int(merged["min_evidence"])
        mastery_ok = int(merged["mastery_mastered"])
        mastery_weak = int(merged["mastery_weak"])
    except (TypeError, ValueError) as exc:
        raise ValueError("阈值必须是整数。") from exc
    if not 1 <= coverage_missing < coverage_ok <= 500:
        raise ValueError("覆盖度阈值需满足：缺失线 ≥1，且小于充足线（最大 500）。")
    if not 1 <= min_evidence <= 20:
        raise ValueError("诊断证据门槛需介于 1 到 20 条之间。")
    if not 1 <= mastery_weak < mastery_ok <= 100:
        raise ValueError("掌握度阈值需满足：需巩固线 ≥1%，且小于已掌握线（最大 100%）。")
    return {
        "coverage_sufficient": coverage_ok,
        "coverage_missing": coverage_missing,
        "min_evidence": min_evidence,
        "mastery_mastered": mastery_ok,
        "mastery_weak": mastery_weak,
    }


def _validate_preferences(values: dict) -> dict:
    merged = {**DEFAULT_PREFERENCES, **(values or {})}
    if merged["tone"] not in TONE_CHOICES:
        raise ValueError("语气选项不合法。")
    if merged["report_length"] not in LENGTH_CHOICES:
        raise ValueError("报告长度选项不合法。")
    if merged["insufficient"] not in INSUFFICIENT_CHOICES:
        raise ValueError("数据不足时的默认行为不合法。")
    if merged["home_view"] not in HOME_CHOICES:
        raise ValueError("默认首页不合法。")
    return {key: merged[key] for key in DEFAULT_PREFERENCES}


def read_policy_thresholds(path: Path) -> dict | None:
    """Read the teacher thresholds from disk without creating an account file."""

    path = Path(path)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for user in document.get("users", []):
        if (user.get("role") or "student") == "teacher":
            return {**DEFAULT_THRESHOLDS, **(user.get("thresholds") or {})}
    return None


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
        self._load()

    def _load(self) -> None:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self._document = document
        self._users = {str(u["username"]): u for u in document.get("users", [])}
        self._sessions: dict[str, tuple[Account, float]] = {}

    def _save(self) -> None:
        self._document["users"] = list(self._users.values())
        target = self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        temp.write_text(
            json.dumps(self._document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, target)

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

    # ---- per-account settings -------------------------------------------------

    def _user(self, username: str) -> dict:
        user = self._users.get(username)
        if user is None:
            raise ValueError("账号不存在。")
        return user

    def policy_thresholds(self) -> dict:
        """Analysis thresholds that drive diagnosis: the teacher account wins."""

        for user in self._users.values():
            if (user.get("role") or "student") == "teacher":
                return {**DEFAULT_THRESHOLDS, **(user.get("thresholds") or {})}
        return dict(DEFAULT_THRESHOLDS)

    def settings_payload(self, username: str) -> dict:
        user = self._user(username)
        account = Account(
            username=str(user["username"]),
            role=user.get("role") or "student",
            student_id=user.get("student_id"),
            display_name=str(user.get("display_name") or user["username"]),
        )
        return {
            "account": account.as_dict(),
            "profile": _migrate_profile(user.get("profile")),
            "preferences": {**DEFAULT_PREFERENCES, **(user.get("preferences") or {})},
            "thresholds": {**DEFAULT_THRESHOLDS, **(user.get("thresholds") or {})},
        }

    def update_profile(self, username: str, values: dict) -> dict:
        user = self._user(username)
        if not isinstance(values, dict):
            raise ValueError("个人资料格式不正确。")
        profile = _migrate_profile(user.get("profile"))
        new_username = username
        if "username" in values:
            new_username = self.rename_user(username, str(values.get("username") or ""))
            user = self._users[new_username]
        if "display_name" in values:
            name = _clean_text(values.get("display_name"), 24, "姓名")
            if not name:
                raise ValueError("姓名不能为空。")
            user["display_name"] = name
        if "term" in values:
            term = _clean_text(values.get("term"), 11, "当前学期")
            if not TERM_PATTERN.match(term):
                raise ValueError("学期格式应为 2026-2027秋 或 2026-2027春。")
            profile["term"] = term
        if "classes" in values:
            profile["classes"] = _clean_text(values.get("classes"), 40, "任教班级")
        if "subject" in values:
            profile["subject"] = _clean_text(values.get("subject"), 20, "科目")
        user["profile"] = profile
        self._save()
        return self.settings_payload(new_username)

    def update_preferences(
        self,
        username: str,
        preferences: dict | None = None,
        thresholds: dict | None = None,
    ) -> dict:
        user = self._user(username)
        if preferences is not None:
            current = {**DEFAULT_PREFERENCES, **(user.get("preferences") or {})}
            user["preferences"] = _validate_preferences({**current, **preferences})
        if thresholds is not None:
            current = {**DEFAULT_THRESHOLDS, **(user.get("thresholds") or {})}
            user["thresholds"] = _validate_thresholds({**current, **thresholds})
        self._save()
        return self.settings_payload(username)

    def rename_user(self, username: str, new_username: str) -> str:
        user = self._user(username)
        cleaned = str(new_username or "").strip()
        if cleaned == username:
            return username
        if not USERNAME_PATTERN.match(cleaned):
            raise ValueError("用户名需为 3–24 位字母、数字或 _ . -。")
        if cleaned in self._users:
            raise ValueError("该用户名已被占用。")
        del self._users[username]
        user["username"] = cleaned
        self._users[cleaned] = user
        for token, (account, expires) in list(self._sessions.items()):
            if account.username == username:
                self._sessions[token] = (
                    Account(cleaned, account.role, account.student_id, account.display_name),
                    expires,
                )
        self._save()
        return cleaned

    def change_password(
        self,
        username: str,
        current: str,
        new: str,
        typed_username: str | None = None,
    ) -> None:
        user = self._user(username)
        if typed_username is not None and str(typed_username).strip() != username:
            raise ValueError("用户名与当前登录账号不一致。")
        if not verify_password(
            current or "", user.get("salt", ""), user.get("password_hash", "")
        ):
            raise ValueError("当前密码不正确。")
        if len(new or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"新密码至少 {MIN_PASSWORD_LENGTH} 位。")
        if new == current:
            raise ValueError("新密码不能与当前密码相同。")
        user.update(hash_password(new))
        self._save()
